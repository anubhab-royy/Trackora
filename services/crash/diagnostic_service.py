"""
DiagnosticService — collects environment, tracking, and log data for crash reports.

Zero UI imports.  Zero PyQt6 imports.  Safe to import anywhere.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from trackora import __version__
from trackora.core.paths import LOGS_DIR

logger = logging.getLogger(__name__)


@dataclass
class CrashReport:
    """Immutable snapshot of the application state at crash time.

    Fields:
        report_id:         Unique identifier (UUID4).
        timestamp:         ISO-8601 UTC timestamp.
        app_version:       Trackora version string (e.g. "1.1.0").
        os_version:        Full OS version (e.g. "Windows-10-10.0.22631").
        os_platform:       Short platform name (e.g. "Windows").
        active_sessions:   List of active game sessions at crash time.
        tracked_games:     Count of tracked games.
        stack_trace:       Captured Python traceback, if available.
        recent_log_entries: Last N log lines from the current log file.
        crash_type:        "unexpected_shutdown" or "unhandled_exception".
        was_tracking:      True if the tracker was running.
    """
    report_id: str
    timestamp: str
    app_version: str
    os_version: str
    os_platform: str
    active_sessions: list[dict[str, Any]]
    tracked_games: int
    stack_trace: str | None
    recent_log_entries: list[str]
    crash_type: str
    was_tracking: bool


class DiagnosticService:
    """Collects diagnostic information for crash reports.

    Args:
        log_dir:   Path to the log directory (defaults to %APPDATA%/Trackora/logs/).
        log_lines: Number of recent log lines to capture (default 50).
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        log_lines: int = 50,
    ) -> None:
        self._log_dir = log_dir or self._default_log_dir()
        self._log_lines = log_lines

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_report(
        self,
        crash_type: str = "unexpected_shutdown",
        stack_trace: str | None = None,
        active_sessions: list[dict[str, Any]] | None = None,
        tracked_games: int = 0,
        was_tracking: bool = False,
    ) -> CrashReport:
        """Build a CrashReport from the current environment.

        Args:
            crash_type:     "unexpected_shutdown" or "unhandled_exception".
            stack_trace:    Captured traceback string, or None.
            active_sessions: Snapshot of active sessions, or None.
            tracked_games:  Number of tracked games (0 if unknown).
            was_tracking:   True if the process monitor was active.

        Returns:
            A fully populated CrashReport.
        """
        return CrashReport(
            report_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            app_version=self._get_app_version(),
            os_version=self._get_os_version(),
            os_platform=self._get_os_platform(),
            active_sessions=active_sessions or [],
            tracked_games=tracked_games,
            stack_trace=stack_trace,
            recent_log_entries=self._get_recent_log_entries(),
            crash_type=crash_type,
            was_tracking=was_tracking,
        )

    def save_report(self, report: CrashReport, storage_dir: Path) -> Path:
        """Atomically write a crash report to disk.

        Args:
            report:      The crash report to persist.
            storage_dir: Target directory (created if missing).

        Returns:
            Path to the saved JSON file.
        """
        storage_dir.mkdir(parents=True, exist_ok=True)
        report_path = storage_dir / f"{report.report_id}.json"
        tmp_path = report_path.with_suffix(".tmp")

        import json

        data = self.serialize(report)
        tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        os.replace(str(tmp_path), str(report_path))

        logger.info("Crash report saved: %s", report_path)
        return report_path

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def serialize(report: CrashReport) -> dict[str, Any]:
        return {
            "report_id": report.report_id,
            "timestamp": report.timestamp,
            "app_version": report.app_version,
            "os_version": report.os_version,
            "os_platform": report.os_platform,
            "active_sessions": report.active_sessions,
            "tracked_games": report.tracked_games,
            "stack_trace": report.stack_trace,
            "recent_log_entries": report.recent_log_entries,
            "crash_type": report.crash_type,
            "was_tracking": report.was_tracking,
        }

    @staticmethod
    def deserialize(data: dict[str, Any]) -> CrashReport:
        return CrashReport(**data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_app_version() -> str:
        return __version__

    @staticmethod
    def _get_os_version() -> str:
        return platform.platform()

    @staticmethod
    def _get_os_platform() -> str:
        return platform.system()

    def _get_recent_log_entries(self) -> list[str]:
        lines: list[str] = []
        log_file = self._log_dir / "trackora.log"
        if not log_file.is_file():
            return lines

        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")
            all_lines = text.splitlines()
            lines = all_lines[-self._log_lines:]
        except OSError as exc:
            logger.warning("Cannot read log file %s: %s", log_file, exc)

        return lines

    @staticmethod
    def _default_log_dir() -> Path:
        return LOGS_DIR
