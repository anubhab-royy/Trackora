"""
backup_scheduler.py — background automatic scheduler for periodic database backups.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC, timedelta
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer

if TYPE_CHECKING:
    from services.backup.backup_manager import BackupManager


logger = logging.getLogger(__name__)


class BackupScheduler(QObject):
    """Monitors configured backup policies and triggers scheduled runs periodically.

    Runs fully in the background on the event loop via QTimer.
    """

    def __init__(self, backup_manager: BackupManager, settings_repo: object, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = backup_manager
        self._settings = settings_repo
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_and_trigger)

    def start(self, check_interval_ms: int = 60000) -> None:
        """Start the background check timer.

        Args:
            check_interval_ms: How frequently to evaluate the backup schedule (default: 60s).
        """
        self._timer.start(check_interval_ms)
        logger.info("BackupScheduler: automatic scheduler started (check_interval=%dms)", check_interval_ms)
        # Execute initial check immediately
        self.check_and_trigger()

    def stop(self) -> None:
        """Stop the background check timer."""
        self._timer.stop()
        logger.info("BackupScheduler: automatic scheduler stopped")

    def check_and_trigger(self) -> None:
        """Check the backup policy and trigger a scheduled run if due."""
        policy = getattr(self._settings, "get_value", lambda k: "disabled")("backup_schedule_policy") or "disabled"
        if policy == "disabled":
            return

        latest_scheduled = self.get_latest_scheduled_backup()
        due = False
        now = datetime.now(UTC).replace(tzinfo=None)

        if latest_scheduled is None:
            # If no scheduled backup exists, run one immediately
            logger.info("BackupScheduler: no previous scheduled backup found, triggering now.")
            due = True
        else:
            last_time = latest_scheduled.created_at
            if last_time.tzinfo is not None:
                last_time = last_time.replace(tzinfo=None)

            if policy == "daily":
                due = (now - last_time) >= timedelta(days=1)
            elif policy == "weekly":
                due = (now - last_time) >= timedelta(weeks=1)

        if due:
            logger.info("BackupScheduler: scheduled backup is due. Starting backup creation.")
            self._manager.create_backup("scheduled")

    def get_latest_scheduled_backup(self) -> object | None:
        """Look up the most recent scheduled backup from the history list."""
        backups = self._manager._core.list_backups(sort_by="created_at")
        for b in backups:
            if b.backup_type == "scheduled":
                return b
        return None
