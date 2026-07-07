"""
restore_manager.py — manages database restorations, coordination, and emergency rollbacks.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from services.backup.backup_manager import BackupManager
from services.backup.backup_validator import BackupValidator
from services.backup.restore_result import RestoreResult
from services.backup.restore_validator import RestoreValidator

logger = logging.getLogger(__name__)


class RestoreManager:
    """Manages the full safe database restore pipeline.

    Coordinates service shutdowns, emergency backups, database replacement,
    integrity checks, re-initialization of repositories, and automatic rollbacks on failure.
    """

    def __init__(
        self,
        backup_manager: BackupManager,
        db_path: Path,
        repositories: list[Any],
        schema_version_manager: Any,
        process_monitor: Any = None,
        health_monitor: Any = None,
        backup_scheduler: Any = None,
        main_window: Any = None,
    ) -> None:
        self._backup_manager = backup_manager
        self._db_path = db_path
        self._repos = repositories
        self._schema_version_manager = schema_version_manager
        self._monitor = process_monitor
        self._health = health_monitor
        self._scheduler = backup_scheduler
        self._window = main_window

    def restore(self, backup_id: str) -> RestoreResult:
        """Restore database state from backup ZIP file.

        Args:
            backup_id: The backup ID.

        Returns:
            RestoreResult detailing success or failure.
        """
        logger.info("RestoreManager: restore pipeline started for backup_id=%s", backup_id)
        backup_path = self._backup_manager.backup_dir / f"{backup_id}.zip"

        # 1. Structural and integrity validation on staging
        is_valid, err = BackupValidator.validate(backup_path)
        if not is_valid:
            logger.error("RestoreManager: validation failed for backup %s: %s", backup_id, err)
            return RestoreResult(success=False, backup_id=backup_id, error=f"Validation failed: {err}")

        # 2. Schema compatibility verification
        current_schema = self._schema_version_manager.read()
        is_compat, compat_err = RestoreValidator.verify_compatibility(backup_path, current_schema)
        if not is_compat:
            logger.error("RestoreManager: compatibility check failed: %s", compat_err)
            return RestoreResult(success=False, backup_id=backup_id, error=f"Compatibility check failed: {compat_err}")

        # 3. Create emergency safety backup of current database state
        logger.info("RestoreManager: creating emergency backup...")
        emergency_res = self._backup_manager.create_backup("pre_restore")
        if not emergency_res.success:
            logger.error("RestoreManager: safety backup creation failed: %s", emergency_res.error)
            return RestoreResult(success=False, backup_id=backup_id, error=f"Safety backup failed: {emergency_res.error}")

        emergency_backup_id = emergency_res.backup_id
        logger.info("RestoreManager: safety backup created: %s", emergency_backup_id)

        # 4. Stop all background monitoring services and timers
        logger.info("RestoreManager: stopping background tasks...")
        monitor_was_running = False
        if self._monitor and self._monitor.is_running:
            self._monitor.stop()
            monitor_was_running = True

        if self._health:
            self._health.stop()

        if self._scheduler:
            self._scheduler.stop()

        queue_timer = getattr(self._window, "_queue_retry_timer", None)
        if queue_timer:
            queue_timer.stop()

        # 5. Safely close existing SQLite connection
        prod_conn = None
        for repo in self._repos:
            prod_conn = getattr(repo, "_conn", None)
            if prod_conn:
                break

        if prod_conn:
            try:
                prod_conn.close()
                logger.info("RestoreManager: production database connection closed.")
            except Exception as exc:
                logger.warning("RestoreManager: failed to close database connection: %s", exc)

        # 6. Execute low-level restore replacement
        logger.info("RestoreManager: overwriting production database files...")
        core_res = self._backup_manager._core.restore_backup(backup_id)
        if not core_res.success:
            logger.error("RestoreManager: core database restore failed: %s. Rolling back.", core_res.error)
            self._rollback(emergency_backup_id, monitor_was_running)
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                safety_backup_id=emergency_backup_id,
                error=f"Core database restore failed: {core_res.error}. Emergency rollback executed.",
            )

        # 7. Re-open connection and run post-restore integrity checks
        new_conn = None
        try:
            new_conn = sqlite3.connect(str(self._db_path))
            for repo in self._repos:
                repo._conn = new_conn

            cursor = new_conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()[0]
            if res.lower() != "ok":
                raise RuntimeError(f"PRAGMA integrity_check failed: {res}")

            # Basic query check
            for repo in self._repos:
                if hasattr(repo, "get_all_games"):
                    repo.get_all_games()

            logger.info("RestoreManager: post-restore integrity check passed successfully.")
        except Exception as exc:
            logger.critical("RestoreManager: post-restore validation failed: %s. Rolling back.", exc)
            if new_conn:
                try:
                    new_conn.close()
                except Exception:
                    pass
            self._rollback(emergency_backup_id, monitor_was_running)
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                safety_backup_id=emergency_backup_id,
                error=f"Post-restore validation failed: {exc}. Emergency rollback executed.",
            )

        # 8. Resume background processes
        self._resume_services(monitor_was_running)
        logger.info("RestoreManager: restore completed successfully: %s", backup_id)
        return RestoreResult(
            success=True,
            backup_id=backup_id,
            safety_backup_id=emergency_backup_id,
        )

    def _rollback(self, emergency_backup_id: str, monitor_was_running: bool) -> None:
        """Roll back to the emergency safety backup file."""
        logger.warning("RestoreManager: triggering emergency rollback to safety backup: %s", emergency_backup_id)
        try:
            rollback_res = self._backup_manager._core.restore_backup(emergency_backup_id)
            if not rollback_res.success:
                raise RuntimeError(f"Safety backup restore failed: {rollback_res.error}")

            rolled_back_conn = sqlite3.connect(str(self._db_path))
            for repo in self._repos:
                repo._conn = rolled_back_conn

            logger.info("RestoreManager: emergency rollback completed successfully. Database restored to safe state.")
        except Exception as exc:
            logger.critical("RestoreManager: CRITICAL: rollback failed, system in inconsistent state: %s", exc)
        finally:
            self._resume_services(monitor_was_running)

    def _resume_services(self, monitor_was_running: bool) -> None:
        """Restart background tasks and request views to refresh."""
        logger.info("RestoreManager: resuming background services...")
        if self._health:
            self._health.start(30000)

        if self._scheduler:
            self._scheduler.start(60000)

        queue_timer = getattr(self._window, "_queue_retry_timer", None)
        if queue_timer:
            queue_timer.start(60000)

        if self._monitor and monitor_was_running:
            self._monitor.start()

        if self._window and hasattr(self._window, "_refresh_current_view"):
            try:
                self._window._refresh_current_view()
            except Exception:
                pass
