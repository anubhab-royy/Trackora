"""
SupportService — orchestrates support operations.

Stores submissions locally, submits via an AbstractReportService backend,
and queues failed submissions for retry via ReportQueueService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import uuid4

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.reporting_interface import AbstractReportService
from services.update_announcements_service import (
    AnnouncementsResult,
    FeatureAnnouncement,
    UpdateAnnouncementsService,
)

logger = logging.getLogger(__name__)


@dataclass
class UpcomingUpdate:
    title: str
    description: str
    version: str
    is_published: bool = False


@dataclass
class SupportSubmitResult:
    """Result of a support submission.

    Attributes:
        local_stored:   True when the report was persisted in memory.
        github_success: True when the report was also submitted to GitHub.
        github_url:     URL of the created GitHub issue (if applicable).
        github_error:   Error message if GitHub submission failed.
        queued:         True when the report was queued for offline retry.
        queued_path:    Path to the queued JSON file (if applicable).
    """
    local_stored: bool
    github_success: bool = False
    github_url: str | None = None
    github_error: str | None = None
    queued: bool = False
    queued_path: str | None = None

    @property
    def success(self) -> bool:
        """Overall success — local storage always counts."""
        return self.local_stored


# Errors that should NOT be queued for retry (configuration issues).
_NON_RETRYABLE_KEYWORDS = [
    "not configured",
    "authentication failed",
    "not found",
    "check your",
]


def _is_retryable(error_message: str | None) -> bool:
    """Return True if the GitHub error is transient and worth retrying."""
    if error_message is None:
        return False
    lower = error_message.lower()
    return not any(kw in lower for kw in _NON_RETRYABLE_KEYWORDS)


class SupportService:
    """Service interface for support center operations.

    Stores submissions in memory, optionally forwards them
    to a report backend (e.g. GitHub Issue service), and queues
    failed submissions for offline retry.

    Architecture rules:
    - No UI imports.
    - No SQL.
    - Returns typed domain models and DTOs.
    """

    def __init__(
        self,
        github_service: AbstractReportService | None = None,
        queue_service: object | None = None,
        announcements_service: UpdateAnnouncementsService | None = None,
    ) -> None:
        self._github_service = github_service
        self._queue_service = queue_service
        self._announcements_service = announcements_service
        self._bug_reports: list[BugReport] = []
        self._feature_requests: list[FeatureRequest] = []
        self._feedback_reports: list[FeedbackReport] = []

    def submit_bug_report(self, report: BugReport) -> SupportSubmitResult:
        """Store and optionally submit a bug report.

        Returns SupportSubmitResult with local, GitHub, and queue status.
        """
        report.id = str(uuid4())
        self._bug_reports.append(report)
        logger.info("Bug report stored locally: %s", report.title)

        return self._submit_with_github_and_queue(
            "submit_bug", report,
            self._serialize_bug_report(report),
        )

    def submit_feature_request(
        self, request: FeatureRequest
    ) -> SupportSubmitResult:
        """Store and optionally submit a feature request."""
        request.id = str(uuid4())
        self._feature_requests.append(request)
        logger.info("Feature request stored locally: %s", request.title)

        return self._submit_with_github_and_queue(
            "submit_feature", request,
            self._serialize_feature_request(request),
        )

    def submit_feedback(self, feedback: FeedbackReport) -> SupportSubmitResult:
        """Store and optionally submit feedback."""
        feedback.id = str(uuid4())
        self._feedback_reports.append(feedback)
        logger.info("Feedback stored locally: %s", feedback.subject)

        return self._submit_with_github_and_queue(
            "submit_feedback", feedback,
            self._serialize_feedback(feedback),
        )

    def process_queue(self) -> object | None:
        """Process the offline report queue.

        Returns QueueProcessResult from the queue service,
        or None if no queue service is configured.
        """
        if self._queue_service is None:
            logger.info("No queue service configured, skipping queue processing.")
            return None
        return self._queue_service.process_queue(self._queue_submit_fn())

    # ------------------------------------------------------------------
    # Internal: GitHub + queue orchestration
    # ------------------------------------------------------------------

    def _submit_with_github_and_queue(
        self, github_method: str,
        model: object,
        serialized: dict[str, object],
    ) -> SupportSubmitResult:
        github_success, github_url, github_error = self._try_github_submit(
            github_method, model
        )

        queued = False
        queued_path = None

        if not github_success and _is_retryable(github_error):
            result = self._try_queue_report(self._report_type(github_method), serialized)
            if result is not None:
                queued = True
                queued_path = str(result)

        return SupportSubmitResult(
            local_stored=True,
            github_success=github_success,
            github_url=github_url,
            github_error=github_error,
            queued=queued,
            queued_path=queued_path,
        )

    def _try_github_submit(
        self, method: str, model: object
    ) -> tuple[bool, str | None, str | None]:
        """Attempt to forward a submission to GitHub.

        Returns (success, url, error_message).
        """
        if self._github_service is None:
            return False, None, None
        try:
            method_fn = getattr(self._github_service, method, None)
            if method_fn is None:
                logger.warning("GitHub service missing method: %s", method)
                return False, None, None
            result = method_fn(model)
            if result.success:
                logger.info("GitHub issue created: %s", result.issue_url)
                return True, result.issue_url, None
            logger.warning("GitHub submission failed: %s", result.error_message)
            return False, None, result.error_message
        except Exception as exc:
            logger.exception("GitHub submission error: %s", exc)
            return False, None, str(exc)

    def _try_queue_report(
        self, report_type: str, data: dict[str, object]
    ) -> object | None:
        """Attempt to queue a report for offline retry."""
        if self._queue_service is None:
            return None
        try:
            return self._queue_service.save_report(report_type, data)
        except Exception as exc:
            logger.exception("Failed to queue report: %s", exc)
            return None

    def _queue_submit_fn(self):
        """Return a callable for QueueProcessService to submit queued reports."""
        github = self._github_service

        def submit(report_type: str, data: dict) -> bool:
            if github is None:
                return False
            method_name = _GITHUB_METHOD_MAP.get(report_type)
            if method_name is None:
                return False
            model = _reconstruct_model(report_type, data)
            if model is None:
                return False
            try:
                method_fn = getattr(github, method_name, None)
                if method_fn is None:
                    return False
                result = method_fn(model)
                return bool(result.success)
            except Exception:
                logger.exception("Error submitting queued %s report", report_type)
                return False

        return submit

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_bug_report(report: BugReport) -> dict[str, object]:
        return {
            "title": report.title,
            "description": report.description,
            "steps_to_reproduce": report.steps_to_reproduce,
            "expected_behavior": report.expected_behavior,
            "actual_behavior": report.actual_behavior,
            "severity": report.severity,
        }

    @staticmethod
    def _serialize_feature_request(
        request: FeatureRequest,
    ) -> dict[str, object]:
        return {
            "title": request.title,
            "description": request.description,
            "use_case": request.use_case,
            "priority": request.priority,
        }

    @staticmethod
    def _serialize_feedback(
        feedback: FeedbackReport,
    ) -> dict[str, object]:
        return {
            "subject": feedback.subject,
            "message": feedback.message,
            "category": feedback.category,
            "contact_ok": feedback.contact_ok,
        }

    @staticmethod
    def _report_type(github_method: str) -> str:
        mapping = {
            "submit_bug": "bug",
            "submit_feature": "feature",
            "submit_feedback": "feedback",
        }
        return mapping.get(github_method, "unknown")

    # ------------------------------------------------------------------
    # Upcoming announcements
    # ------------------------------------------------------------------

    def get_upcoming_updates(self) -> list[UpcomingUpdate]:
        """Return the feature list from announcements.

        Extracted from AnnouncementsResult for backward compatibility.
        """
        result = self.get_announcements()
        return [
            UpcomingUpdate(
                title=f.title,
                description=f.description,
                version=f.version,
                is_published=f.is_published,
            )
            for f in result.features
        ]

    def refresh_announcements(self) -> AnnouncementsResult:
        """Force a remote refresh of announcements.

        Raises the underlying exception on failure (caller should handle it).
        """
        if self._announcements_service is not None:
            result = self._announcements_service.refresh()
            return result
        return self.get_announcements()

    def get_announcements(self) -> AnnouncementsResult:
        """Return full announcements including current/upcoming versions.

        Delegates to UpdateAnnouncementsService if configured;
        otherwise returns a hardcoded fallback so the UI is never empty.
        """
        if self._announcements_service is not None:
            try:
                return self._announcements_service.get_announcements()
            except Exception as exc:
                logger.warning(
                    "Announcements service error: %s", exc
                )

        return AnnouncementsResult(
            current_version="1.0.0",
            upcoming_version="1.1.0",
            features=[
                FeatureAnnouncement(
                    title="Support Center Launch",
                    description="Centralized hub for bug reports, "
                                "feature requests, and feedback.",
                    version="1.1.0",
                    is_published=False,
                ),
                FeatureAnnouncement(
                    title="GitHub Integration",
                    description="Submit bug reports and feature requests "
                                "directly to GitHub Issues.",
                    version="1.2.0",
                    is_published=True,
                ),
                FeatureAnnouncement(
                    title="Offline Report Queue",
                    description="Reports are saved locally when offline "
                                "and auto-submitted on next launch.",
                    version="1.2.0",
                    is_published=True,
                ),
                FeatureAnnouncement(
                    title="Enhanced Statistics Export",
                    description="Export detailed statistics including "
                                "charts and trends.",
                    version="1.3.0",
                    is_published=False,
                ),
            ],
            source="fallback",
        )


# Module-level helper for reconstructing models during queue processing.


_REPORT_TYPE_CLS_MAP: dict[str, type] = {
    "bug": BugReport,
    "feature": FeatureRequest,
    "feedback": FeedbackReport,
}

_GITHUB_METHOD_MAP: dict[str, str] = {
    "bug": "submit_bug",
    "feature": "submit_feature",
    "feedback": "submit_feedback",
}


def _reconstruct_model(
    report_type: str, data: dict
) -> BugReport | FeatureRequest | FeedbackReport | None:
    """Reconstruct a domain model from queued JSON data."""
    cls = _REPORT_TYPE_CLS_MAP.get(report_type)
    if cls is None:
        return None
    try:
        return cls(**data)
    except (TypeError, ValueError) as exc:
        logger.error(
            "Failed to reconstruct %s model: %s", report_type, exc
        )
        return None
