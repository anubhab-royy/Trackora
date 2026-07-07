"""
ReportingInterface — abstraction layer for report submission backends.

Defines:
  - ReportType enum         (bug / feature-request / feedback / crash)
  - SubmitResult dataclass  (success, report_id, issue_url, error_message)
  - AbstractReportService   (ABC that backends must implement)

Architecture rule:
  UI and business-logic code MUST depend on AbstractReportService,
  never on a concrete backend (e.g. GitHubIssueService) directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.crash.diagnostic_service import CrashReport


class ReportType(Enum):
    BUG = "bug"
    FEATURE = "feature-request"
    FEEDBACK = "feedback"
    CRASH = "crash"


@dataclass
class SubmitResult:
    """Result of a report submission.

    Attributes:
        success:       True when the remote service accepted the report.
        report_id:     Opaque identifier assigned by the backend.
        issue_url:     URL to the created item (backward-compat alias).
        error_message: Human-readable error when success is False.
    """
    success: bool
    report_id: str | None = None
    issue_url: str | None = None
    error_message: str | None = None


class AbstractReportService(ABC):
    """Abstract base for all report-submission backends.

    Subclasses must implement the typed convenience methods
    and the generic *submit_report* method.
    """

    @abstractmethod
    def submit_bug(self, report: BugReport) -> SubmitResult:
        """Submit a bug report."""

    @abstractmethod
    def submit_feature(self, request: FeatureRequest) -> SubmitResult:
        """Submit a feature request."""

    @abstractmethod
    def submit_feedback(self, feedback: FeedbackReport) -> SubmitResult:
        """Submit general feedback."""

    @abstractmethod
    def submit_report(
        self, report_type: ReportType, title: str, body: str
    ) -> SubmitResult:
        """Submit a pre-built report with an explicit type, title, and body."""

    # ------------------------------------------------------------------
    # Crash support (optional — backends may override)
    # ------------------------------------------------------------------

    def submit_crash(
        self, title_or_report: str | CrashReport, body: str | None = None
    ) -> SubmitResult:
        """Submit a crash report.

        The default implementation delegates to *submit_report*.
        """
        if isinstance(title_or_report, str):
            return self.submit_report(ReportType.CRASH, title_or_report, body or "")
        
        report = title_or_report
        title = f"Trackora Crash — {report.crash_type} ({report.timestamp})"
        body_str = self._build_crash_body(report)
        return self.submit_report(ReportType.CRASH, title, body_str)

    def _build_crash_body(self, report: CrashReport) -> str:
        """Build the markdown issue body for a crash report."""
        lines = [
            f"### Application Version\n{report.app_version}",
            f"### OS\n{report.os_platform} ({report.os_version})",
            f"### Timestamp\n{report.timestamp}",
            f"### Crash Type\n{report.crash_type}",
            f"### Was Tracking\n{report.was_tracking}",
            f"### Tracked Games\n{report.tracked_games}",
            "### Active Sessions",
        ]
        if report.active_sessions:
            for s in report.active_sessions:
                lines.append(f"- Game ID {s.get('game_id', '?')}: {s.get('game_name', '?')}")
        else:
            lines.append("*None*")

        if report.stack_trace:
            lines.append("\n### Stack Trace\n```\n" + report.stack_trace + "\n```")

        if report.recent_log_entries:
            lines.append("\n### Recent Log Entries\n```\n")
            lines.extend(report.recent_log_entries[-30:])
            lines.append("```")

        lines.append("\n---\n*Generated automatically by Trackora*")
        return "\n".join(lines)
