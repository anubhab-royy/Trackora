"""
backup_service.py — public-facing service for orchestrating manual backups.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from services.backup.backup_manager import BackupManager
    from services.backup.backup_result import BackupResult, BackupInfo


class BackupService:
    """Exposes high-level backup functions decoupled from internal managers."""

    def __init__(self, backup_manager: BackupManager) -> None:
        self._manager = backup_manager

    def perform_manual_backup(self) -> BackupResult:
        """Trigger an immediate manual database backup."""
        return self._manager.create_backup("manual")

    def get_backup_history(self) -> list[BackupInfo]:
        """Return a list of available backups sorted by creation date."""
        # Convert core BackupInfo to service-level BackupInfo for strict compatibility
        from services.backup.backup_result import BackupInfo as ServiceBackupInfo
        core_backups = self._manager._core.list_backups(sort_by="created_at")
        
        return [
            ServiceBackupInfo(
                backup_id=b.backup_id,
                backup_path=b.backup_path,
                size_bytes=b.size_bytes,
                created_at=b.created_at,
                schema_version=b.schema_version,
                trackora_version=b.trackora_version,
                backup_type=b.backup_type,
                file_count=b.file_count,
            )
            for b in core_backups
        ]
