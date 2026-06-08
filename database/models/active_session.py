# ActiveSession dataclass (crash recovery)

"""
ActiveSession model for GameTracker.

Maps directly to the `active_sessions` table defined in database_schema.md.

Purpose:
    Crash recovery and shutdown recovery.
    Written when a session starts; deleted when a session ends normally.
    On restart, any rows still present represent sessions that need recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class ActiveSession:
    """
    Represents a currently running (in-progress) session.

    Matches the `active_sessions` table schema exactly:
        id          INTEGER PRIMARY KEY
        game_id     INTEGER
        process_id  INTEGER
        start_time  DATETIME
        created_at  DATETIME
    """

    game_id: int
    process_id: int
    start_time: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    id: int | None = None  # None until persisted

    def __post_init__(self) -> None:
        """Validate fields after construction."""
        if self.game_id <= 0:
            raise ValueError("game_id must be a positive integer.")
        if self.process_id <= 0:
            raise ValueError("process_id must be a positive integer.")