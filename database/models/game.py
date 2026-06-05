# Game dataclass

"""
Game model for GameTracker.

Maps directly to the `games` table defined in database_schema.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Game:
    """
    Represents a tracked game.

    Matches the `games` table schema exactly:
        id              INTEGER PRIMARY KEY
        name            TEXT
        process_name    TEXT
        executable_path TEXT
        icon_path       TEXT
        is_enabled      INTEGER  (1 = enabled, 0 = disabled)
        first_played    DATETIME
        last_played     DATETIME
        created_at      DATETIME
        updated_at      DATETIME
    """

    name: str
    process_name: str
    executable_path: str
    icon_path: str = ""
    is_enabled: bool = True
    first_played: datetime | None = None
    last_played: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None  # None until persisted

    def __post_init__(self) -> None:
        """Validate required fields after construction."""
        if not self.name or not self.name.strip():
            raise ValueError("Game name must not be empty.")
        if not self.process_name or not self.process_name.strip():
            raise ValueError("Game process_name must not be empty.")
        if not self.executable_path or not self.executable_path.strip():
            raise ValueError("Game executable_path must not be empty.")