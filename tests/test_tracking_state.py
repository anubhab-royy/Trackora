"""
tests/test_tracking_state.py

Unit tests for tracker/tracking_state.py

Covers:
  - add_tracked_game / remove_tracked_game
  - process_name_index integrity
  - find_game_by_process (case-insensitive)
  - rebuild_index
  - is_game_active / get_active_session
  - ActiveSession.duration_seconds
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tracker.tracking_state import ActiveSession, TrackedGame, TrackingState


# ---------------------------------------------------------------------------
# TrackedGame
# ---------------------------------------------------------------------------

class TestTrackedGame:
    def test_defaults(self):
        g = TrackedGame(game_id=1, name="Hades", process_name="hades.exe")
        assert g.is_enabled is True

    def test_disabled_game(self):
        g = TrackedGame(game_id=2, name="Old Game", process_name="old.exe", is_enabled=False)
        assert g.is_enabled is False


# ---------------------------------------------------------------------------
# TrackingState — index management
# ---------------------------------------------------------------------------

class TestTrackingStateIndex:
    def test_empty_state(self):
        state = TrackingState()
        assert state.tracked_games == {}
        assert state.process_name_index == {}

    def test_add_game_updates_index(self):
        state = TrackingState()
        state.add_tracked_game(TrackedGame(game_id=1, name="Witcher 3", process_name="witcher3.exe"))
        assert "witcher3.exe" in state.process_name_index

    def test_disabled_game_not_in_index(self):
        state = TrackingState()
        state.add_tracked_game(
            TrackedGame(game_id=1, name="Disabled", process_name="disabled.exe", is_enabled=False)
        )
        # Still in tracked_games …
        assert 1 in state.tracked_games
        # … but not in the lookup index
        assert "disabled.exe" not in state.process_name_index

    def test_remove_game_clears_index(self):
        state = TrackingState()
        state.add_tracked_game(TrackedGame(game_id=1, name="X", process_name="x.exe"))
        state.remove_tracked_game(1)
        assert 1 not in state.tracked_games
        assert "x.exe" not in state.process_name_index

    def test_remove_nonexistent_game_is_safe(self):
        state = TrackingState()
        state.remove_tracked_game(999)   # must not raise

    def test_rebuild_index_after_manual_dict_mutation(self):
        """
        If someone mutates tracked_games directly (e.g. loading from DB),
        rebuild_index should sync the process_name_index.
        """
        state = TrackingState()
        state.tracked_games[1] = TrackedGame(game_id=1, name="A", process_name="a.exe")
        state.tracked_games[2] = TrackedGame(game_id=2, name="B", process_name="b.exe", is_enabled=False)
        state.rebuild_index()
        assert "a.exe" in state.process_name_index
        assert "b.exe" not in state.process_name_index

    def test_add_multiple_games(self):
        state = TrackingState()
        for i in range(5):
            state.add_tracked_game(TrackedGame(game_id=i, name=f"Game{i}", process_name=f"game{i}.exe"))
        assert len(state.tracked_games) == 5
        assert len(state.process_name_index) == 5


# ---------------------------------------------------------------------------
# TrackingState — lookups
# ---------------------------------------------------------------------------

class TestTrackingStateLookup:
    def test_find_game_by_process_exact_match(self):
        state = TrackingState()
        g = TrackedGame(game_id=1, name="Hades", process_name="hades.exe")
        state.add_tracked_game(g)
        assert state.find_game_by_process("hades.exe") is g

    def test_find_game_by_process_case_insensitive(self):
        state = TrackingState()
        g = TrackedGame(game_id=1, name="Hades", process_name="Hades.EXE")
        state.add_tracked_game(g)
        assert state.find_game_by_process("hades.exe") is g
        assert state.find_game_by_process("HADES.EXE") is g

    def test_find_game_returns_none_for_unknown(self):
        state = TrackingState()
        assert state.find_game_by_process("unknown.exe") is None

    def test_is_game_active_false_when_no_sessions(self):
        state = TrackingState()
        state.add_tracked_game(TrackedGame(game_id=1, name="X", process_name="x.exe"))
        assert state.is_game_active(1) is False

    def test_is_game_active_true_after_session_inserted(self):
        state = TrackingState()
        state.add_tracked_game(TrackedGame(game_id=1, name="X", process_name="x.exe"))
        session = ActiveSession(
            active_session_id=10,
            game_id=1,
            game_name="X",
            process_id=1234,
            start_time=datetime.now(),
        )
        state.active_sessions[1] = session
        assert state.is_game_active(1) is True

    def test_get_active_session_returns_session(self):
        state = TrackingState()
        session = ActiveSession(
            active_session_id=5, game_id=1, game_name="Y",
            process_id=999, start_time=datetime.now(),
        )
        state.active_sessions[1] = session
        assert state.get_active_session(1) is session

    def test_get_active_session_returns_none_for_inactive(self):
        state = TrackingState()
        assert state.get_active_session(42) is None


# ---------------------------------------------------------------------------
# ActiveSession
# ---------------------------------------------------------------------------

class TestActiveSession:
    def test_duration_seconds_nonzero(self):
        past = datetime.now() - timedelta(seconds=120)
        session = ActiveSession(
            active_session_id=1, game_id=1, game_name="Z",
            process_id=100, start_time=past,
        )
        # Should be approximately 120 (±2 for test timing)
        assert 118 <= session.duration_seconds() <= 125

    def test_duration_seconds_just_started(self):
        session = ActiveSession(
            active_session_id=1, game_id=1, game_name="Z",
            process_id=100, start_time=datetime.now(),
        )
        assert session.duration_seconds() >= 0