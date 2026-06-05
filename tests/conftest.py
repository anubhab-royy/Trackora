"""
tests/conftest.py

Shared pytest fixtures for Phase 2 tests.
No real DB.  No real psutil.  No real filesystem.
"""

from __future__ import annotations

import pytest

from tracker.tracking_state import TrackedGame, TrackingState


# ---------------------------------------------------------------------------
# In-memory repository fakes
# ---------------------------------------------------------------------------

class FakeActiveSessionsRepo:
    """Minimal in-memory stand-in for ActiveSessionsRepository."""

    def __init__(self) -> None:
        self._rows: dict[int, dict] = {}
        self._next_id = 1

    def create(self, game_id: int, process_id: int, start_time) -> int:
        row_id = self._next_id
        self._next_id += 1
        self._rows[row_id] = {
            "id": row_id,
            "game_id": game_id,
            "process_id": process_id,
            "start_time": start_time,
        }
        return row_id

    def delete(self, active_session_id: int) -> None:
        self._rows.pop(active_session_id, None)

    def get_all(self) -> list[dict]:
        return list(self._rows.values())

    # Test helpers
    def count(self) -> int:
        return len(self._rows)

    def get(self, active_session_id: int) -> dict | None:
        return self._rows.get(active_session_id)


class FakeSessionsRepo:
    """Minimal in-memory stand-in for SessionsRepository."""

    def __init__(self) -> None:
        self._rows: dict[int, dict] = {}
        self._next_id = 1

    def create(self, game_id: int, start_time, end_time, duration_seconds: int) -> int:
        row_id = self._next_id
        self._next_id += 1
        self._rows[row_id] = {
            "id": row_id,
            "game_id": game_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration_seconds,
        }
        return row_id

    # Test helpers
    def count(self) -> int:
        return len(self._rows)

    def all(self) -> list[dict]:
        return list(self._rows.values())


class FakeGamesRepo:
    """Minimal in-memory stand-in for GamesRepository."""

    def __init__(self) -> None:
        self._last_played: dict[int, object] = {}

    def update_last_played(self, game_id: int, played_at) -> None:
        self._last_played[game_id] = played_at

    # Test helper
    def get_last_played(self, game_id: int):
        return self._last_played.get(game_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_active_sessions_repo() -> FakeActiveSessionsRepo:
    return FakeActiveSessionsRepo()


@pytest.fixture
def fake_sessions_repo() -> FakeSessionsRepo:
    return FakeSessionsRepo()


@pytest.fixture
def fake_games_repo() -> FakeGamesRepo:
    return FakeGamesRepo()


@pytest.fixture
def empty_state() -> TrackingState:
    return TrackingState()


@pytest.fixture
def state_with_games() -> TrackingState:
    """TrackingState pre-loaded with two enabled tracked games."""
    state = TrackingState()
    state.add_tracked_game(TrackedGame(game_id=1, name="Witcher 3", process_name="witcher3.exe"))
    state.add_tracked_game(TrackedGame(game_id=2, name="Hades", process_name="hades.exe"))
    return state