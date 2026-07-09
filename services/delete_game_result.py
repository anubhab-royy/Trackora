"""
DeleteGameResult — Phase 14
Result object returned by DeleteGameService operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DeleteGameResult:
    """Structured result returned from DeleteGameService operations."""
    success: bool
    game_id: int
    game_name: str
    error_message: Optional[str] = None
    duration_ms: float = 0.0

    @property
    def message(self) -> str:
        """Backwards-compatibility accessor mapping to the UI's expectation."""
        if self.success:
            return f"Game '{self.game_name}' deleted successfully."
        return self.error_message or "Unknown error"
