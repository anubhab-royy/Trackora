"""
backup_manager.py — orchestrates backup operations and retention cleanups.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from services.backup.backup_result import BackupResult
from services.backup.backup_validator import BackupValidator
from trackora.core.backup_manager import BackupManager as CoreBackupManager
from trackora.core.schema_version_manager import SchemaVersionManager

logger = logging.getLogger(__name__)


class BackupManager:
    """Orchestrates manual and scheduled backups and handles retention policy.

    Delegates low-level file copy operations to the core BackupManager.
    """

    def __init__(self, schema_version_manager: SchemaVersionManager, backup_dir: Path | None = None) -> None:
        self._core = CoreBackupManager(schema_version_manager, backup_dir)
        self._lock = threading.Lock()
        self.backup_dir = self._core._backup_dir

    def create_backup(self, backup_type: str = "manual") -> BackupResult:
        """Create a validated backup of the SQLite database.

        Concurrently protected to avoid running multiple backups in parallel.
        Enforces retention policy for scheduled backups.

        Args:
            backup_type: Reason for the backup ("manual", "scheduled", "pre_migration", "pre_restore").

        Returns:
            BackupResult detailing the operation's outcome.
        """
        if not self._lock.acquire(blocking=False):
            logger.warning("BackupManager: Backup already in progress. Skipping.")
            return BackupResult(
                success=False,
                backup_id="",
                backup_path=None,
                size_bytes=0,
                file_count=0,
                created_at=datetime.now(timezone.utc),
                error="Backup already in progress.",
            )

        try:
            logger.info("BackupManager: backup process started (type=%s)", backup_type)
            core_res = self._core.create_backup(backup_type)

            if not core_res.success:
                logger.error("BackupManager: core backup creation failed: %s", core_res.error)
                return BackupResult(
                    success=False,
                    backup_id=core_res.backup_id,
                    backup_path=None,
                    size_bytes=0,
                    file_count=0,
                    created_at=core_res.created_at,
                    error=core_res.error,
                )

            # Validate the newly created backup
            logger.info("BackupManager: validating backup archive %s", core_res.backup_id)
            is_valid, error_msg = BackupValidator.validate(core_res.backup_path)

            if not is_valid:
                logger.error("BackupManager: validation failed for backup %s: %s", core_res.backup_id, error_msg)
                # Safely delete invalid backup file
                try:
                    core_res.backup_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return BackupResult(
                    success=False,
                    backup_id=core_res.backup_id,
                    backup_path=None,
                    size_bytes=0,
                    file_count=0,
                    created_at=core_res.created_at,
                    error=f"Backup validation failed: {error_msg}",
                )

            logger.info("BackupManager: validation successful for backup %s", core_res.backup_id)

            # Enforce retention if scheduled
            if backup_type == "scheduled":
                self.enforce_retention()

            logger.info("BackupManager: backup process completed successfully: %s", core_res.backup_id)
            return BackupResult(
                success=True,
                backup_id=core_res.backup_id,
                backup_path=core_res.backup_path,
                size_bytes=core_res.size_bytes,
                file_count=core_res.file_count,
                created_at=core_res.created_at,
            )

        except Exception as exc:
            logger.exception("BackupManager: unhandled exception during backup")
            return BackupResult(
                success=False,
                backup_id="",
                backup_path=None,
                size_bytes=0,
                file_count=0,
                created_at=datetime.now(timezone.utc),
                error=str(exc),
            )
        finally:
            self._lock.release()

    def enforce_retention(self) -> None:
        """Scheduled backups retention: keep latest 10, delete oldest."""
        logger.info("BackupManager: enforcing scheduled backups retention policy.")
        try:
            backups = self._core.list_backups(sort_by="created_at")
            scheduled_backups = [b for b in backups if b.backup_type == "scheduled"]

            if len(scheduled_backups) <= 10:
                logger.info("BackupManager: scheduled backups count (%d) is within limit.", len(scheduled_backups))
                return

            to_delete = scheduled_backups[10:]
            deleted_count = 0
            for b in to_delete:
                if self._core.delete_backup(b.backup_id):
                    deleted_count += 1
                    logger.info("BackupManager: deleted old scheduled backup %s", b.backup_id)

            logger.info("BackupManager: retention cleanup completed. Deleted %d backup(s).", deleted_count)
        except Exception as exc:
            logger.error("BackupManager: failed to enforce retention policy: %s", exc)
