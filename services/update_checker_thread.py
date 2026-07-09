"""
UpdateCheckerThread — T-202 (Automatic Update System, Phase 1)

Performs the GitHub release check entirely off the UI thread so that
network latency never blocks the event loop or delays rendering.

Architecture:
    - Lives in services/ (System Services layer).
    - No UI imports. No SQL. No repository access.
    - Receives a fully-constructed UpdateCenterService via __init__.
    - Emits check_completed(UpdateCheckResult) or check_failed(str).
    - Safe to re-use: each start() call triggers one network round-trip
      (unless UpdateCenterService rate-limits it).

Usage (from ui/main_window.py):
    self._update_thread = UpdateCheckerThread(self._update_service)
    self._update_thread.check_completed.connect(self._on_update_check_result)
    self._update_thread.check_failed.connect(self._on_update_check_failed)
    self._update_thread.start()
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from services.update_center_service import UpdateCenterService, UpdateCheckResult

logger = logging.getLogger(__name__)


class UpdateCheckerThread(QThread):
    """
    Background thread that runs UpdateCenterService.check_for_updates().

    Signals:
        check_completed (UpdateCheckResult): emitted when the check succeeds.
        check_failed    (str):               emitted when an unhandled exception
                                             is raised inside run().

    Args:
        update_service: A fully initialised UpdateCenterService instance.
    """

    check_completed: pyqtSignal = pyqtSignal(object)   # UpdateCheckResult
    check_failed:    pyqtSignal = pyqtSignal(str)

    def __init__(self, update_service: UpdateCenterService) -> None:
        super().__init__()
        self._update_service = update_service

    # ------------------------------------------------------------------
    # QThread contract
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute the update check on the worker thread."""
        try:
            result = self._update_service.check_for_updates()
            self.check_completed.emit(result)
        except Exception as exc:                          # pragma: no cover
            logger.error("UpdateCheckerThread: unhandled error: %s", exc)
            self.check_failed.emit(str(exc))
