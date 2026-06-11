# Session dataclass + factory

"""
Session model for Trackora.

Maps directly to the `sessions` table defined in database_schema.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Session:
    """
    Represents a completed gaming session.

    Matches the `sessions` table schema exactly:
        id               INTEGER PRIMARY KEY
        game_id          INTEGER  (FK → games.id)
        start_time       DATETIME
        end_time         DATETIME
        duration_seconds INTEGER
        created_at       DATETIME
    """

    game_id: int
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    id: int | None = None  # None until persisted

    def __post_init__(self) -> None:
        """Validate session integrity after construction."""
        if self.game_id <= 0:
            raise ValueError("game_id must be a positive integer.")
        if self.end_time < self.start_time:
            raise ValueError("end_time must not be before start_time.")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative.")

    @classmethod
    def from_start_and_end(
        cls,
        game_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> "Session":
        """
        Convenience factory that auto-calculates duration_seconds.

        Args:
            game_id:    The ID of the game being played.
            start_time: When the session started.
            end_time:   When the session ended.

        Returns:
            A fully constructed Session with duration_seconds filled in.
        """
        duration = max(0, int((end_time - start_time).total_seconds()))
        return cls(
            game_id=game_id,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
        )