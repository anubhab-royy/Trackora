"""
health_check.py — definitions for service health checks.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Any

from services.health.health_result import HealthResult
from services.health.health_status import HealthStatus
from trackora.core.paths import CRASH_DIR

logger = logging.getLogger(__name__)


class BaseHealthCheck(ABC):
    """Abstract base class representing a single diagnostic health check."""

    @abstractmethod
    def name(self) -> str:
        """Return the unique human-readable name of the service check."""
        pass

    @abstractmethod
    def check(self) -> HealthResult:
        """Execute the health check and return a HealthResult."""
        pass


class TrackingEngineHealthCheck(BaseHealthCheck):
    """Monitors process detection thread status and state sync."""

    def __init__(self, process_monitor: Any, tracking_state: Any) -> None:
        self._monitor = process_monitor
        self._state = tracking_state

    def name(self) -> str:
        return "Tracking Engine"

    def check(self) -> HealthResult:
        if self._monitor is None or self._state is None:
            return HealthResult(HealthStatus.FAILED, "Tracking engine components not initialized.")

        is_running = getattr(self._state, "is_running", False)
        thread = getattr(self._monitor, "_thread", None)
        thread_alive = thread.is_alive() if thread else False
        session_mgr_exists = getattr(self._monitor, "_session_manager", None) is not None

        details = {
            "state_is_running": is_running,
            "thread_exists": thread is not None,
            "thread_alive": thread_alive,
            "session_manager_exists": session_mgr_exists,
        }

        if is_running:
            if thread is None or not thread_alive:
                return HealthResult(
                    HealthStatus.FAILED,
                    "Tracking engine state is active but monitor thread is dead.",
                    details,
                )
            return HealthResult(HealthStatus.HEALTHY, "Tracking engine active and polling.", details)

        return HealthResult(HealthStatus.HEALTHY, "Tracking engine is idle.", details)

    def recover(self) -> bool:
        """Attempt safe recovery by restarting the process monitor thread."""
        try:
            logger.info("TrackingEngineHealthCheck: attempting automatic recovery.")
            if self._monitor is not None:
                # Force state reset so start() triggers thread recreation
                if self._state is not None:
                    self._state.is_running = False
                self._monitor.start()
                return True
        except Exception as exc:
            logger.exception("TrackingEngineHealthCheck: recovery failed: %s", exc)
        return False


class SQLiteHealthCheck(BaseHealthCheck):
    """Monitors database connection state, query execution, and journal mode."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def name(self) -> str:
        return "SQLite Database"

    def check(self) -> HealthResult:
        if self._conn is None:
            return HealthResult(HealthStatus.FAILED, "SQLite database connection not initialized.")

        details: dict[str, Any] = {}
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.fetchone()

            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
            details["journal_mode"] = mode

            if mode.lower() != "wal":
                return HealthResult(
                    HealthStatus.WARNING,
                    f"SQLite database is not in WAL mode (current: {mode}).",
                    details,
                )
            return HealthResult(HealthStatus.HEALTHY, "Database query operational, WAL mode active.", details)
        except Exception as exc:
            return HealthResult(
                HealthStatus.FAILED,
                f"Database check failed with exception: {exc}",
                {"error": str(exc)},
            )


class MongoDBHealthCheck(BaseHealthCheck):
    """Checks MongoDB configuration and cached connectivity states non-blockingly."""

    def __init__(self, mongo_connection: Any) -> None:
        self._mongo = mongo_connection

    def name(self) -> str:
        return "MongoDB Support Service"

    def check(self) -> HealthResult:
        uri = os.environ.get("MONGODB_URI", "")
        if not uri:
            return HealthResult(
                HealthStatus.WARNING,
                "MongoDB connection URI is not configured in environment.",
                {"configured": False},
            )

        if self._mongo is None:
            return HealthResult(
                HealthStatus.WARNING,
                "MongoDB connection manager not initialized.",
                {"configured": True, "initialized": False},
            )

        if getattr(self._mongo, "is_pending", False) is True:
            return HealthResult(
                HealthStatus.HEALTHY,
                "MongoDB connection validation pending...",
                {"configured": True, "initialized": True, "pending": True},
            )

        is_available = getattr(self._mongo, "is_available", False)
        auth_failed = getattr(self._mongo, "_auth_failed", False)
        last_error = getattr(self._mongo, "last_error", None)

        details = {
            "configured": True,
            "initialized": True,
            "is_available": is_available,
            "auth_failed": auth_failed,
            "last_error": last_error,
        }

        if auth_failed:
            return HealthResult(
                HealthStatus.WARNING,
                f"MongoDB authentication failed: {last_error}",
                details,
            )

        if not is_available:
            return HealthResult(
                HealthStatus.WARNING,
                f"MongoDB connection offline: {last_error or 'health check not run/failed'}",
                details,
            )

        return HealthResult(HealthStatus.HEALTHY, "MongoDB connection online.", details)


class UpdateServiceHealthCheck(BaseHealthCheck):
    """Monitors the update manager thread state and check execution history."""

    def __init__(self, update_service: Any, main_window: Any) -> None:
        self._service = update_service
        self._window = main_window
        self._consecutive_runs = 0

    def name(self) -> str:
        return "Update Service"

    def check(self) -> HealthResult:
        if self._service is None:
            return HealthResult(HealthStatus.FAILED, "Update service not initialized.")

        thread = getattr(self._window, "_update_thread", None)
        thread_running = thread.isRunning() if (thread and hasattr(thread, "isRunning")) else False

        if thread_running:
            self._consecutive_runs += 1
        else:
            self._consecutive_runs = 0

        last_checked = None
        if self._service._settings_repo:
            last_checked = self._service._settings_repo.get_value("update_last_checked")

        details = {
            "thread_exists": thread is not None,
            "thread_running": thread_running,
            "last_checked": last_checked,
            "consecutive_checks_running": self._consecutive_runs,
        }

        if last_checked:
            try:
                last_dt = datetime.fromisoformat(last_checked)
                if last_dt.tzinfo is not None:
                    last_dt = last_dt.replace(tzinfo=None)
                now = datetime.now(UTC).replace(tzinfo=None)
                details["last_check_age_seconds"] = (now - last_dt).total_seconds()
            except Exception:
                pass

        if self._consecutive_runs > 4:
            return HealthResult(
                HealthStatus.WARNING,
                "Background update check has been running for an unusually long time (possibly stuck).",
                details,
            )

        return HealthResult(HealthStatus.HEALTHY, "Update service is operational.", details)


class CrashServiceHealthCheck(BaseHealthCheck):
    """Verifies crash manager operations and filesystem permissions."""

    def __init__(self, crash_service: Any, recovery_manager: Any) -> None:
        self._crash = crash_service
        self._recovery = recovery_manager

    def name(self) -> str:
        return "Crash Service"

    def check(self) -> HealthResult:
        if self._crash is None:
            return HealthResult(HealthStatus.FAILED, "Crash service not initialized.")

        state_mgr = getattr(self._crash, "state_manager", None)
        if state_mgr is None:
            return HealthResult(HealthStatus.FAILED, "Crash state manager not available.")

        details = {
            "recovery_manager_available": self._recovery is not None,
            "state_file_exists": state_mgr.state_path.is_file() if state_mgr else False,
            "crash_dir_writable": os.access(CRASH_DIR, os.W_OK),
        }

        try:
            if not os.access(CRASH_DIR, os.W_OK):
                return HealthResult(HealthStatus.FAILED, "Crash reports directory is not writable.", details)
            state_mgr.detect_crash()
        except Exception as exc:
            return HealthResult(
                HealthStatus.FAILED,
                f"Crash state manager read/write check failed: {exc}",
                details,
            )

        return HealthResult(HealthStatus.HEALTHY, "Crash service operational.", details)


class BackgroundWorkersHealthCheck(BaseHealthCheck):
    """Monitors standard scheduler timers and queue processors."""

    def __init__(self, main_window: Any) -> None:
        self._window = main_window

    def name(self) -> str:
        return "Background Workers"

    def check(self) -> HealthResult:
        if self._window is None:
            return HealthResult(HealthStatus.FAILED, "Main window reference not available.")

        timer = getattr(self._window, "_queue_retry_timer", None)
        timer_active = timer.isActive() if timer else False

        details = {
            "queue_retry_timer_exists": timer is not None,
            "queue_retry_timer_active": timer_active,
        }

        if timer is not None and not timer_active:
            return HealthResult(
                HealthStatus.WARNING,
                "Queue retry timer is not active.",
                details,
            )

        return HealthResult(HealthStatus.HEALTHY, "All background workers are active.", details)

    def recover(self) -> bool:
        """Attempt safe recovery by restarting the queue retry timer."""
        try:
            logger.info("BackgroundWorkersHealthCheck: attempting automatic recovery.")
            timer = getattr(self._window, "_queue_retry_timer", None)
            if timer is not None and not timer.isActive():
                timer.start(60000)
                return True
        except Exception as exc:
            logger.exception("BackgroundWorkersHealthCheck: recovery failed: %s", exc)
        return False
