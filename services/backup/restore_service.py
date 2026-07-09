"""
restore_service.py — public-facing service for orchestrating database restores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from services.backup.restore_manager import RestoreManager
    from services.backup.restore_result import RestoreResult


class RestoreService:
    """Service layer exposing database restore functionality to the application UI."""

    def __init__(self, restore_manager: RestoreManager) -> None:
        self._manager = restore_manager

    def restore_backup(self, backup_id: str) -> RestoreResult:
        """Trigger a safe database restore from the specified backup ID.

        Enforces service pauses, emergency backups, database replacement,
        integrity verification, and automatic rollback on failure.

        Args:
            backup_id: The identifier of the backup to restore.

        Returns:
            RestoreResult detailing the outcome of the restore operation.
        """
        return self._manager.restore(backup_id)

    def restore_from_file(self, filepath: Path) -> RestoreResult:
        """Trigger a safe database restore from the specified backup file (ZIP or JSON).

        Args:
            filepath: Path to the backup file to restore.

        Returns:
            RestoreResult detailing the outcome of the restore operation.
        """
        return self._manager.restore_from_file(filepath)
