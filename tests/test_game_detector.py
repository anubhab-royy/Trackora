"""
tests/test_game_detector.py

Unit tests for tracker/game_detector.py

All tests use hand-crafted process snapshots — psutil is never called.
Covers AC-002 (detect start) and AC-003 (detect stop) at the logic level.
"""

from __future__ import annotations

import pytest

from tracker.game_detector import detect_changes
from tracker.tracking_state import ActiveSession, TrackedGame, TrackingState
from datetime import datetime


def _make_state(*games: tuple[int, str, str]) -> TrackingState:
    """
    Helper: build a TrackingState from (game_id, name, process_name) tuples.
    """
    state = TrackingState()
    for gid, name, proc in games:
        state.add_tracked_game(TrackedGame(game_id=gid, name=name, process_name=proc))
    return state


def _add_active(state: TrackingState, game_id: int, pid: int = 1000) -> None:
    """Helper: inject an active session into state."""
    game = state.tracked_games[game_id]
    state.active_sessions[game_id] = ActiveSession(
        active_session_id=game_id * 10,
        game_id=game_id,
        game_name=game.name,
        process_id=pid,
        start_time=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Start detection
# ---------------------------------------------------------------------------

class TestDetectStart:
    def test_detects_single_game_starting(self):
        state = _make_state((1, "Hades", "hades.exe"))
        running = {"hades.exe": 1234}
        result = detect_changes(state, running)
        assert (1, 1234) in result.started
        assert result.stopped == []

    def test_detects_multiple_games_starting(self):
        state = _make_state(
            (1, "Hades", "hades.exe"),
            (2, "Witcher 3", "witcher3.exe"),
        )
        running = {"hades.exe": 100, "witcher3.exe": 200, "notepad.exe": 300}
        result = detect_changes(state, running)
        started_ids = [gid for gid, _ in result.started]
        assert 1 in started_ids
        assert 2 in started_ids

    def test_does_not_start_already_active_game(self):
        state = _make_state((1, "Hades", "hades.exe"))
        _add_active(state, game_id=1, pid=1234)
        running = {"hades.exe": 1234}   # still running, same pid
        result = detect_changes(state, running)
        assert result.started == []

    def test_ignores_untracked_processes(self):
        state = _make_state((1, "Hades", "hades.exe"))
        running = {"chrome.exe": 555, "notepad.exe": 666}
        result = detect_changes(state, running)
        assert result.started == []
        assert result.stopped == []

    def test_empty_running_processes(self):
        state = _make_state((1, "Hades", "hades.exe"))
        result = detect_changes(state, {})
        assert result.started == []
        assert result.stopped == []

    def test_no_tracked_games(self):
        state = TrackingState()
        running = {"hades.exe": 100}
        result = detect_changes(state, running)
        assert result.started == []
        assert result.stopped == []

    def test_process_name_case_insensitive(self):
        state = _make_state((1, "Hades", "Hades.EXE"))
        running = {"hades.exe": 42}   # lower-case in the snapshot
        result = detect_changes(state, running)
        assert (1, 42) in result.started

    def test_disabled_game_not_started(self):
        state = TrackingState()
        state.add_tracked_game(
            TrackedGame(game_id=1, name="Disabled", process_name="disabled.exe", is_enabled=False)
        )
        running = {"disabled.exe": 100}
        result = detect_changes(state, running)
        assert result.started == []


# ---------------------------------------------------------------------------
# Stop detection
# ---------------------------------------------------------------------------

class TestDetectStop:
    def test_detects_single_game_stopping(self):
        state = _make_state((1, "Hades", "hades.exe"))
        _add_active(state, game_id=1)
        running = {}   # game is gone
        result = detect_changes(state, running)
        assert 1 in result.stopped

    def test_does_not_stop_still_running_game(self):
        state = _make_state((1, "Hades", "hades.exe"))
        _add_active(state, game_id=1, pid=1234)
        running = {"hades.exe": 1234}
        result = detect_changes(state, running)
        assert result.stopped == []

    def test_detects_one_stop_one_still_running(self):
        state = _make_state(
            (1, "Hades", "hades.exe"),
            (2, "Witcher 3", "witcher3.exe"),
        )
        _add_active(state, 1)
        _add_active(state, 2)
        running = {"witcher3.exe": 200}   # hades stopped, witcher still running
        result = detect_changes(state, running)
        assert 1 in result.stopped
        assert 2 not in result.stopped

    def test_no_active_sessions_means_no_stops(self):
        state = _make_state((1, "Hades", "hades.exe"))
        result = detect_changes(state, {})
        assert result.stopped == []


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------

class TestDetectCombined:
    def test_start_and_stop_in_same_tick(self):
        """
        Witcher stops, Hades starts — both changes detected in one pass.
        """
        state = _make_state(
            (1, "Hades", "hades.exe"),
            (2, "Witcher 3", "witcher3.exe"),
        )
        _add_active(state, game_id=2, pid=200)
        running = {"hades.exe": 100}   # hades appeared, witcher gone
        result = detect_changes(state, running)
        assert (1, 100) in result.started
        assert 2 in result.stopped