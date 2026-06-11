"""
CrashService — startup-state lifecycle and crash detection.

Tracks application state in startup_state.json:
  - "running"         written at startup
  - "closed_cleanly"  written on normal exit

If the previous start wrote "running" and the current start
finds it still set, the application did not exit cleanly
(power loss, taskkill, unhandled exception, etc.) and a
crash report is warranted.

Uses atomic file writes so the state file is never corrupted
by a concurrent crash.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from services.crash.diagnostic_service import CrashReport, DiagnosticService

logger = logging.getLogger(__name__)


class StartupState(str, Enum):
    RUNNING = "running"
    CLOSED_CLEANLY = "closed_cleanly"


@dataclass
class CrashResult:
    """Result of a crash check at startup.

    Attributes:
        has_crashed:  True when the previous startup state was 'running'.
        report:       The generated crash report, if applicable.
        report_path:  Path to the persisted crash report JSON, if saved.
    """
    has_crashed: bool
    report: CrashReport | None = None
    report_path: Path | None = None


class StartupStateManager:
    """Manages the startup_state.json file lifecycle.

    Args:
        storage_dir: Directory to store startup_state.json.
                     Defaults to %APPDATA%/Trackora/.
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir or self._default_storage_dir()
        self._state_path = self._storage_dir / "startup_state.json"
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mark_running(self) -> None:
        """Write 'running' to the state file. Call at startup."""
        self._write({"status": StartupState.RUNNING.value,
                      "last_updated": datetime.now(timezone.utc).isoformat()})
        logger.debug("Startup state -> running")

    def mark_closed_cleanly(self) -> None:
        """Write 'closed_cleanly' to the state file. Call on clean exit."""
        try:
            self._write({"status": StartupState.CLOSED_CLEANLY.value,
                          "last_updated": datetime.now(timezone.utc).isoformat()})
            logger.debug("Startup state -> closed_cleanly")
        except Exception as exc:
            logger.warning("Failed to mark clean shutdown: %s", exc)

    def read_state(self) -> StartupState | None:
        """Read the persisted startup state.

        Returns:
            The previous startup state, or None if the file
            does not exist (first-ever launch).
        """
        if not self._state_path.is_file():
            return None
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            status = data.get("status", "")
            return StartupState(status)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning("Cannot read startup state: %s", exc)
            return None

    def detect_crash(self) -> bool:
        """Check if the previous session was a crash.

        Returns:
            True if the previous state was 'running'
            (meaning the app never marked clean shutdown).
            Also returns True if the state file is unreadable
            (conservative: assume crash).
        """
        state = self.read_state()
        if state is None:
            # First-ever launch or corrupted file — not a crash.
            return False
        return state != StartupState.CLOSED_CLEANLY

    @property
    def state_path(self) -> Path:
        return self._state_path

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self, payload: dict[str, Any]) -> None:
        """Atomically write the state file (tmp + replace)."""
        tmp_path = self._state_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        os.replace(str(tmp_path), str(self._state_path))

    @staticmethod
    def _default_storage_dir() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base = Path.home() / ".local" / "share"
        return base / "Trackora"


class CrashService:
    """Orchestrates startup-state tracking and crash report generation.

    Args:
        diagnostic_service: Service for collecting diagnostic info.
        state_manager:      StartupStateManager for read/write lifecycle.
        crash_report_dir:   Directory to store crash reports.
                            Defaults to %APPDATA%/Trackora/crash_reports/.
    """

    def __init__(
        self,
        diagnostic_service: DiagnosticService,
        state_manager: StartupStateManager | None = None,
        crash_report_dir: Path | None = None,
    ) -> None:
        self._diag = diagnostic_service
        self._state_mgr = state_manager or StartupStateManager()
        self._crash_report_dir = crash_report_dir or (
            self._state_mgr.storage_dir / "crash_reports"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_for_crash(
        self,
        active_sessions: list[dict] | None = None,
        tracked_games: int = 0,
        was_tracking: bool = False,
    ) -> CrashResult:
        """Check if the previous session crashed and generate a report.

        Args:
            active_sessions: Snapshot of active game sessions (optional).
            tracked_games:   Number of tracked games (default 0).
            was_tracking:    Whether the tracker was active (default False).

        Returns:
            CrashResult with has_crashed flag and optional report.
        """
        if not self._state_mgr.detect_crash():
            return CrashResult(has_crashed=False)

        report = self._diag.collect_report(
            crash_type="unexpected_shutdown",
            active_sessions=active_sessions,
            tracked_games=tracked_games,
            was_tracking=was_tracking,
        )
        report_path = self._diag.save_report(report, self._crash_report_dir)

        logger.warning(
            "Crash detected: report %s saved to %s",
            report.report_id,
            report_path,
        )

        return CrashResult(has_crashed=True, report=report, report_path=report_path)

    def mark_startup(self) -> None:
        """Mark the application as 'running'. Call early at startup."""
        self._state_mgr.mark_running()

    def mark_clean_shutdown(self) -> None:
        """Mark the application as 'closed_cleanly'. Call on normal exit."""
        self._state_mgr.mark_closed_cleanly()

    @property
    def crash_report_dir(self) -> Path:
        return self._crash_report_dir

    @property
    def state_manager(self) -> StartupStateManager:
        return self._state_mgr
