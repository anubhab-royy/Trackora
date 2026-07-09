"""
health_monitor.py — background health monitoring loop and orchestrator.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from services.health.health_result import HealthResult
from services.health.health_status import HealthStatus

if TYPE_CHECKING:
    from services.health.health_registry import HealthRegistry

logger = logging.getLogger(__name__)


class HealthMonitor(QObject):
    """Periodically executes health checks on a background timer.

    Emits notification signals on service degradation and executes
    recovery strategies if available.
    """

    notification_requested = pyqtSignal(str, str)  # (title, message)
    status_changed = pyqtSignal(str, object, object)  # (service_name, old_result, new_result)

    def __init__(self, registry: HealthRegistry, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.run_checks)
        self.last_results: dict[str, HealthResult] = {}

    def start(self, interval_ms: int = 30000) -> None:
        """Start the health monitoring QTimer."""
        self._timer.start(interval_ms)
        logger.info("Background Health Monitor started (interval=%dms)", interval_ms)
        # Execute immediately on start
        self.run_checks()

    def stop(self) -> None:
        """Stop the health monitoring QTimer."""
        self._timer.stop()
        logger.info("Background Health Monitor stopped")

    def run_checks(self) -> None:
        """Execute all registered checks, log transitions, and trigger recovery/alerts."""
        logger.debug("Executing background health checks...")
        for check in self._registry.get_all():
            name = check.name()
            try:
                result = check.check()
            except Exception as exc:
                logger.exception("Health check '%s' raised an exception", name)
                result = HealthResult(
                    HealthStatus.FAILED,
                    f"Health check raised exception: {exc}",
                    {"error": str(exc)},
                )

            old_result = self.last_results.get(name)
            self.last_results[name] = result

            # 1. Status change handling (logging and signal emission)
            if old_result is None or old_result.status != result.status:
                self._log_status_change(name, old_result, result)
                self.status_changed.emit(name, old_result, result)

                # 2. Trigger notification on degradation
                if result.status in (HealthStatus.WARNING, HealthStatus.FAILED):
                    self._request_notification(name, result)

            # 3. Safe Automatic Recovery execution
            if result.status == HealthStatus.FAILED:
                recover_fn = getattr(check, "recover", None)
                if recover_fn is not None:
                    try:
                        success = recover_fn()
                        if success:
                            logger.info("Health check '%s': recovery attempt succeeded.", name)
                        else:
                            logger.warning("Health check '%s': recovery attempt failed.", name)
                    except Exception as exc:
                        logger.exception("Health check '%s': recovery function crashed", name)

    def _log_status_change(self, name: str, old: HealthResult | None, new: HealthResult) -> None:
        old_status = old.status.value if old else "UNKNOWN"
        msg = f"{name} health: {old_status} -> {new.status.value}. Message: {new.message}"
        if new.status == HealthStatus.HEALTHY:
            logger.info(msg)
        elif new.status == HealthStatus.WARNING:
            logger.warning(msg)
        elif new.status == HealthStatus.FAILED:
            logger.error(msg)

    def _request_notification(self, name: str, result: HealthResult) -> None:
        title = f"Trackora Alert — {name}"
        message = result.message
        logger.info("Requesting tray notification for '%s' degradation", name)
        self.notification_requested.emit(title, message)
