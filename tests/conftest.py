"""
tests/conftest.py

Shared pytest fixtures for Phase 2 tests.
No real DB.  No real psutil.  No real filesystem.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from database.models import ActiveSession as DbActiveSession, Session
from tracker.tracking_state import TrackedGame, TrackingState


# ---------------------------------------------------------------------------
# In-memory repository fakes (match real repo interfaces exactly)
# ---------------------------------------------------------------------------

class FakeActiveSessionsRepo:
    """In-memory stand-in for ActiveSessionsRepository.

    Matches the real interface: start_session(), end_session(), get_all().
    """

    def __init__(self) -> None:
        self._rows: dict[int, dict] = {}
        self._next_id = 1

    def start_session(self, active_session: DbActiveSession) -> DbActiveSession:
        row_id = self._next_id
        self._next_id += 1
        self._rows[row_id] = {
            "id": row_id,
            "game_id": active_session.game_id,
            "process_id": active_session.process_id,
            "start_time": active_session.start_time,
        }
        active_session.id = row_id
        return active_session

    def end_session(self, active_session_id: int) -> None:
        self._rows.pop(active_session_id, None)

    def get_all(self) -> list[DbActiveSession]:
        result = []
        for rid, row in self._rows.items():
            result.append(DbActiveSession(
                id=rid,
                game_id=row["game_id"],
                process_id=row["process_id"],
                start_time=row["start_time"],
            ))
        return result

    # Test helpers
    def count(self) -> int:
        return len(self._rows)

    def get(self, active_session_id: int) -> dict | None:
        return self._rows.get(active_session_id)


class FakeSessionsRepo:
    """In-memory stand-in for SessionsRepository.

    Matches the real interface: add().
    """

    def __init__(self) -> None:
        self._rows: dict[int, dict] = {}
        self._next_id = 1

    def add(self, session: Session) -> Session:
        row_id = self._next_id
        self._next_id += 1
        self._rows[row_id] = {
            "id": row_id,
            "game_id": session.game_id,
            "start_time": session.start_time,
            "end_time": session.end_time,
            "duration_seconds": session.duration_seconds,
        }
        session.id = row_id
        return session

    # Test helpers
    def count(self) -> int:
        return len(self._rows)

    def all(self) -> list[dict]:
        return list(self._rows.values())


class FakeGamesRepo:
    """In-memory stand-in for GamesRepository."""

    def __init__(self) -> None:
        self._last_played: dict[int, object] = {}

    def update_last_played(self, game_id: int, timestamp: datetime) -> None:
        self._last_played[game_id] = timestamp

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
