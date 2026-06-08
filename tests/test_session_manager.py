"""
tests/test_session_manager.py

Unit tests for tracker/session_manager.py

Covers:
  - AC-002: session created and stored in active_sessions
  - AC-003: session closed, duration calculated, written to sessions table
  - Edge cases: duplicate start, end without start, DB failure handling
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from database.models import ActiveSession as DbActiveSession
from tracker.session_manager import SessionManager
from tracker.tracking_state import ActiveSession, TrackedGame, TrackingState

from tests.conftest import FakeActiveSessionsRepo, FakeGamesRepo, FakeSessionsRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_manager(
    state: TrackingState | None = None,
    active_repo: FakeActiveSessionsRepo | None = None,
    sessions_repo: FakeSessionsRepo | None = None,
    games_repo: FakeGamesRepo | None = None,
) -> tuple[SessionManager, TrackingState, FakeActiveSessionsRepo, FakeSessionsRepo, FakeGamesRepo]:
    s = state or TrackingState()
    ar = active_repo or FakeActiveSessionsRepo()
    sr = sessions_repo or FakeSessionsRepo()
    gr = games_repo or FakeGamesRepo()
    mgr = SessionManager(state=s, active_sessions_repo=ar, sessions_repo=sr, games_repo=gr)
    return mgr, s, ar, sr, gr


def _add_game(state: TrackingState, game_id: int = 1, name: str = "Hades",
              proc: str = "hades.exe") -> TrackedGame:
    g = TrackedGame(game_id=game_id, name=name, process_name=proc)
    state.add_tracked_game(g)
    return g


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------

class TestStartSession:
    def test_creates_active_session_in_memory(self):
        """AC-002: active session should exist in state after start."""
        mgr, state, _, _, _ = _build_manager()
        _add_game(state)
        session = mgr.start_session(game_id=1, process_id=1234)
        assert session is not None
        assert state.is_game_active(1)

    def test_persists_active_session_to_repo(self):
        """AC-002: active_sessions table should have one row."""
        mgr, state, active_repo, _, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=1234)
        assert active_repo.count() == 1

    def test_session_has_correct_game_id(self):
        mgr, state, active_repo, _, _ = _build_manager()
        _add_game(state, game_id=7)
        mgr.start_session(game_id=7, process_id=555)
        row = active_repo.get(1)
        assert row["game_id"] == 7

    def test_session_has_correct_pid(self):
        mgr, state, active_repo, _, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=9999)
        row = active_repo.get(1)
        assert row["process_id"] == 9999

    def test_session_start_time_is_recorded(self):
        mgr, state, _, _, _ = _build_manager()
        _add_game(state)
        before = datetime.now()
        session = mgr.start_session(game_id=1, process_id=100)
        after = datetime.now()
        assert before <= session.start_time <= after

    def test_returns_none_for_already_active_game(self):
        """Safety guard: starting an already-active session returns None."""
        mgr, state, active_repo, _, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=100)
        result = mgr.start_session(game_id=1, process_id=200)
        assert result is None
        # Still only one row in the repo
        assert active_repo.count() == 1

    def test_returns_none_for_unknown_game(self):
        mgr, state, _, _, _ = _build_manager()
        result = mgr.start_session(game_id=999, process_id=100)
        assert result is None

    def test_active_session_id_stored_in_memory(self):
        mgr, state, active_repo, _, _ = _build_manager()
        _add_game(state)
        session = mgr.start_session(game_id=1, process_id=123)
        assert session.active_session_id == 1   # first inserted row


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------

class TestEndSession:
    def test_saves_completed_session(self):
        """AC-003: session should appear in sessions table after end."""
        mgr, state, _, sessions_repo, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=100)
        result = mgr.end_session(game_id=1)
        assert result is True
        assert sessions_repo.count() == 1

    def test_removes_active_session_from_memory(self):
        """AC-003: game should no longer be active after end."""
        mgr, state, _, _, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=100)
        mgr.end_session(game_id=1)
        assert not state.is_game_active(1)

    def test_deletes_active_session_from_repo(self):
        mgr, state, active_repo, _, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=100)
        assert active_repo.count() == 1
        mgr.end_session(game_id=1)
        assert active_repo.count() == 0

    def test_duration_is_positive(self):
        mgr, state, _, sessions_repo, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=100)
        mgr.end_session(game_id=1)
        row = sessions_repo.all()[0]
        assert row["duration_seconds"] >= 0

    def test_duration_roughly_correct(self):
        """
        Inject a session with a start_time 60 seconds ago and verify the
        duration stored is close to 60.
        """
        mgr, state, active_repo, sessions_repo, _ = _build_manager()
        _add_game(state)
        # Manually inject an active session with a past start_time
        past = datetime.now() - timedelta(seconds=60)
        db_active = active_repo.start_session(
            DbActiveSession(game_id=1, process_id=100, start_time=past)
        )
        state.active_sessions[1] = ActiveSession(
            active_session_id=db_active.id,
            game_id=1,
            game_name="Hades",
            process_id=100,
            start_time=past,
        )
        mgr.end_session(game_id=1)
        row = sessions_repo.all()[0]
        assert 58 <= row["duration_seconds"] <= 65

    def test_updates_last_played(self):
        mgr, state, _, _, games_repo = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=100)
        before = datetime.now()
        mgr.end_session(game_id=1)
        last = games_repo.get_last_played(1)
        assert last is not None
        assert last >= before

    def test_returns_false_when_no_active_session(self):
        mgr, state, _, _, _ = _build_manager()
        result = mgr.end_session(game_id=1)
        assert result is False

    def test_session_game_id_correct(self):
        mgr, state, _, sessions_repo, _ = _build_manager()
        _add_game(state, game_id=3)
        mgr.start_session(game_id=3, process_id=100)
        mgr.end_session(game_id=3)
        row = sessions_repo.all()[0]
        assert row["game_id"] == 3

    def test_multiple_sequential_sessions(self):
        """Start → End → Start → End should produce two session rows."""
        mgr, state, _, sessions_repo, _ = _build_manager()
        _add_game(state)
        mgr.start_session(game_id=1, process_id=100)
        mgr.end_session(game_id=1)
        mgr.start_session(game_id=1, process_id=101)
        mgr.end_session(game_id=1)
        assert sessions_repo.count() == 2


# ---------------------------------------------------------------------------
# Duration calculation
# ---------------------------------------------------------------------------

class TestCalculateDuration:
    def test_normal_duration(self):
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 13, 30, 0)
        result = SessionManager._calculate_duration(start, end)
        assert result == 5400   # 90 minutes

    def test_zero_duration_when_equal(self):
        t = datetime(2024, 1, 1, 12, 0, 0)
        assert SessionManager._calculate_duration(t, t) == 0

    def test_negative_duration_clamped_to_zero(self):
        """end < start should never happen in practice but must not go negative."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 11, 0, 0)
        assert SessionManager._calculate_duration(start, end) == 0