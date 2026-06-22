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
        self, title: str, body: str
    ) -> SubmitResult:
        """Submit a crash report.

        The default implementation delegates to *submit_report*.
        """
        return self.submit_report(ReportType.CRASH, title, body)
