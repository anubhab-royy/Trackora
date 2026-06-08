"""
SessionView dataclass — enriched session for display.

Sits in database.models because it is a data-transfer object consumed
by both the repository (where it is produced) and the UI (where it is
displayed).  Keeping it in models avoids architecture violations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SessionView:
    """A session row enriched with the game name via JOIN."""

    id: int
    game_id: int
    game_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    created_at: datetime
