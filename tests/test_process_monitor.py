"""
tests/test_process_monitor.py

Unit tests for tracker/process_monitor.py

The real polling thread and psutil are replaced with:
  - A synchronous call to _tick() (no real thread)
  - A fake snapshot_fn returning a controlled dict

Covers:
  - start / stop lifecycle
  - _tick → start_session on new process
  - _tick → end_session on vanished process
  - reload_tracked_games updates index
  - Double-start is a no-op
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tracker.process_monitor import ProcessMonitor
from tracker.session_manager import SessionManager
from tracker.tracking_state import ActiveSession, TrackedGame, TrackingState

from tests.conftest import FakeActiveSessionsRepo, FakeGamesRepo, FakeSessionsRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_monitor(
    games: list[TrackedGame] | None = None,
    snapshot: dict[str, int] | None = None,
) -> tuple[ProcessMonitor, TrackingState, FakeActiveSessionsRepo, FakeSessionsRepo]:
    state = TrackingState()
    if games:
        for g in games:
            state.add_tracked_game(g)

    active_repo = FakeActiveSessionsRepo()
    sessions_repo = FakeSessionsRepo()
    games_repo = FakeGamesRepo()

    session_mgr = SessionManager(
        state=state,
        active_sessions_repo=active_repo,
        sessions_repo=sessions_repo,
        games_repo=games_repo,
    )

    running_snapshot = dict(snapshot or {})

    monitor = ProcessMonitor(
        state=state,
        session_manager=session_mgr,
        poll_interval=0.05,
        snapshot_fn=lambda: running_snapshot,
    )
    return monitor, state, active_repo, sessions_repo


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestProcessMonitorLifecycle:
    def test_not_running_before_start(self):
        monitor, *_ = _build_monitor()
        assert not monitor.is_running

    def test_running_after_start(self):
        monitor, *_ = _build_monitor()
        monitor.start()
        try:
            assert monitor.is_running
        finally:
            monitor.stop()

    def test_not_running_after_stop(self):
        monitor, *_ = _build_monitor()
        monitor.start()
        monitor.stop()
        assert not monitor.is_running

    def test_double_start_is_safe(self):
        monitor, *_ = _build_monitor()
        monitor.start()
        monitor.start()   # should not raise or spawn second thread
        try:
            assert monitor.is_running
        finally:
            monitor.stop()

    def test_stop_without_start_is_safe(self):
        monitor, *_ = _build_monitor()
        monitor.stop()   # must not raise


# ---------------------------------------------------------------------------
# _tick: process start detected
# ---------------------------------------------------------------------------

class TestTickStart:
    def test_tick_creates_session_for_new_process(self):
        games = [TrackedGame(game_id=1, name="Hades", process_name="hades.exe")]
        monitor, state, active_repo, _ = _build_monitor(
            games=games, snapshot={"hades.exe": 100}
        )
        monitor._tick()
        assert state.is_game_active(1)
        assert active_repo.count() == 1

    def test_tick_no_session_for_untracked_process(self):
        games = [TrackedGame(game_id=1, name="Hades", process_name="hades.exe")]
        monitor, state, active_repo, _ = _build_monitor(
            games=games, snapshot={"chrome.exe": 200}
        )
        monitor._tick()
        assert not state.is_game_active(1)
        assert active_repo.count() == 0

    def test_tick_does_not_double_start_same_game(self):
        games = [TrackedGame(game_id=1, name="Hades", process_name="hades.exe")]
        monitor, state, active_repo, _ = _build_monitor(
            games=games, snapshot={"hades.exe": 100}
        )
        monitor._tick()
        monitor._tick()   # second tick — game still running
        assert active_repo.count() == 1


# ---------------------------------------------------------------------------
# _tick: process stop detected
# ---------------------------------------------------------------------------

class TestTickStop:
    def test_tick_ends_session_when_process_gone(self):
        games = [TrackedGame(game_id=1, name="Hades", process_name="hades.exe")]
        monitor, state, active_repo, sessions_repo = _build_monitor(
            games=games, snapshot={"hades.exe": 100}
        )
        # Tick 1: game starts
        monitor._tick()
        assert state.is_game_active(1)

        # Mutate snapshot to simulate game exit
        monitor._snapshot_fn = lambda: {}
        # Tick 2: game gone
        monitor._tick()

        assert not state.is_game_active(1)
        assert sessions_repo.count() == 1

    def test_tick_keeps_session_when_process_still_running(self):
        games = [TrackedGame(game_id=1, name="Hades", process_name="hades.exe")]
        monitor, state, _, sessions_repo = _build_monitor(
            games=games, snapshot={"hades.exe": 100}
        )
        monitor._tick()
        monitor._tick()   # still running
        assert state.is_game_active(1)
        assert sessions_repo.count() == 0


# ---------------------------------------------------------------------------
# reload_tracked_games
# ---------------------------------------------------------------------------

class TestReloadTrackedGames:
    def test_reload_replaces_all_games(self):
        games = [TrackedGame(game_id=1, name="Hades", process_name="hades.exe")]
        monitor, state, _, _ = _build_monitor(games=games)
        assert len(state.tracked_games) == 1

        new_games = [
            TrackedGame(game_id=2, name="Witcher 3", process_name="witcher3.exe"),
            TrackedGame(game_id=3, name="Celeste", process_name="celeste.exe"),
        ]
        monitor.reload_tracked_games(new_games)
        assert len(state.tracked_games) == 2
        assert 1 not in state.tracked_games
        assert 2 in state.tracked_games
        assert 3 in state.tracked_games

    def test_reload_updates_index(self):
        monitor, state, _, _ = _build_monitor()
        monitor.reload_tracked_games([
            TrackedGame(game_id=5, name="X", process_name="x.exe")
        ])
        assert state.find_game_by_process("x.exe") is not None

    def test_reload_with_empty_list_clears_state(self):
        games = [TrackedGame(game_id=1, name="Hades", process_name="hades.exe")]
        monitor, state, _, _ = _build_monitor(games=games)
        monitor.reload_tracked_games([])
        assert len(state.tracked_games) == 0
        assert len(state.process_name_index) == 0