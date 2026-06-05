# no deps, import anywhere

"""
tracker/tracking_state.py

In-memory representation of the tracker's live state.
No database access.  No business logic beyond simple helpers.
Pure dataclasses — safe to import anywhere.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TrackedGame:
    """
    Lightweight snapshot of a game row that the tracker cares about.
    Populated from the database layer; the tracker never queries DB directly.
    """

    game_id: int
    name: str
    process_name: str          # e.g. "witcher3.exe"
    is_enabled: bool = True


@dataclass
class ActiveSession:
    """
    Represents one live gaming session held in memory.

    Mirrors the active_sessions DB table but is kept in RAM so the
    tracker can operate without hitting the database on every poll cycle.
    """

    active_session_id: int     # PK from active_sessions table
    game_id: int
    game_name: str
    process_id: int
    start_time: datetime

    def duration_seconds(self) -> int:
        """Return elapsed seconds since session start (live, not persisted)."""
        delta = datetime.now() - self.start_time
        return int(delta.total_seconds())


@dataclass
class TrackingState:
    """
    Mutable container for the complete live state of the tracker.

    ProcessMonitor reads this; SessionManager writes to it.
    Never persisted directly — the DB is the source of truth at restart.
    """

    # game_id -> TrackedGame  (populated from GamesRepository)
    tracked_games: dict[int, TrackedGame] = field(default_factory=dict)

    # game_id -> ActiveSession  (one session per game at a time)
    active_sessions: dict[int, ActiveSession] = field(default_factory=dict)

    # process_name.lower() -> game_id  (fast O(1) lookup on every poll)
    process_name_index: dict[str, int] = field(default_factory=dict)

    # Flag used by ProcessMonitor's loop
    is_running: bool = False

    def rebuild_index(self) -> None:
        """Rebuild process_name_index from tracked_games.  Call after any mutation."""
        self.process_name_index = {
            g.process_name.lower(): gid
            for gid, g in self.tracked_games.items()
            if g.is_enabled
        }
        logger.debug("Process name index rebuilt: %d entries", len(self.process_name_index))

    def add_tracked_game(self, game: TrackedGame) -> None:
        self.tracked_games[game.game_id] = game
        if game.is_enabled:
            self.process_name_index[game.process_name.lower()] = game.game_id

    def remove_tracked_game(self, game_id: int) -> None:
        game = self.tracked_games.pop(game_id, None)
        if game:
            self.process_name_index.pop(game.process_name.lower(), None)

    def find_game_by_process(self, process_name: str) -> TrackedGame | None:
        """Return the TrackedGame whose process_name matches, or None."""
        gid = self.process_name_index.get(process_name.lower())
        return self.tracked_games.get(gid) if gid is not None else None

    def is_game_active(self, game_id: int) -> bool:
        return game_id in self.active_sessions

    def get_active_session(self, game_id: int) -> ActiveSession | None:
        return self.active_sessions.get(game_id)