"""
restore_result.py — data transfer objects for restore outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RestoreResult:
    """Outcome of a backup restore operation."""

    success: bool
    backup_id: str
    safety_backup_id: str | None = None
    error: str | None = None
