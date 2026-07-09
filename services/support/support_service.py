"""
SupportService — orchestrates support operations.

Stores submissions locally, submits via an AbstractReportService backend,
and queues failed submissions for retry via ReportQueueService.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.crash.diagnostic_service import CrashReport
from services.support.reporting_interface import AbstractReportService
from services.update_announcements_service import (
    AnnouncementsResult,
    FeatureAnnouncement,
    UpdateAnnouncementsService,
)

logger = logging.getLogger(__name__)

SUBSYSTEM = "Support"


def _cid() -> str:
    """Generate a short correlation ID for workflow tracing."""
    return uuid.uuid4().hex[:8]


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
        github_success: True when the report was also submitted to backend.
        github_url:     URL of the created item (if applicable).
        github_error:   Error message if backend submission failed.
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


# Errors that should NOT be queued for retry (configuration / permanent issues).
_NON_RETRYABLE_KEYWORDS = [
    "not configured",
    "configuration missing",
    "not available",
    "not found",
    "authentication failed",
    "permission denied",
    "permission error",
    "not authorized",
    "unauthorized",
    "forbidden",
    "invalid",
    "bad request",
    "unsupported",
    "check your",
]


def _is_retryable(error_message: str | None) -> bool:
    """Return True if the backend error is transient and worth retrying."""
    if error_message is None:
        return False
    lower = error_message.lower()
    return not any(kw in lower for kw in _NON_RETRYABLE_KEYWORDS)


class SupportService:
    """Service interface for support center operations.

    Stores submissions in memory, optionally forwards them
    to a report backend, and queues failed submissions
    for offline retry.

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
        correlation_id = _cid()
        report.id = str(uuid4())
        self._bug_reports.append(report)
        logger.info("[%s][%s] Submission started (bug: %s)", SUBSYSTEM, correlation_id, report.title)

        return self._submit_with_github_and_queue(
            "submit_bug", report,
            self._serialize_bug_report(report),
            correlation_id,
        )

    def submit_feature_request(
        self, request: FeatureRequest
    ) -> SupportSubmitResult:
        """Store and optionally submit a feature request."""
        correlation_id = _cid()
        request.id = str(uuid4())
        self._feature_requests.append(request)
        logger.info("[%s][%s] Submission started (feature: %s)", SUBSYSTEM, correlation_id, request.title)

        return self._submit_with_github_and_queue(
            "submit_feature", request,
            self._serialize_feature_request(request),
            correlation_id,
        )

    def submit_feedback(self, feedback: FeedbackReport) -> SupportSubmitResult:
        """Store and optionally submit feedback."""
        correlation_id = _cid()
        feedback.id = str(uuid4())
        self._feedback_reports.append(feedback)
        logger.info("[%s][%s] Submission started (feedback: %s)", SUBSYSTEM, correlation_id, feedback.subject)

        return self._submit_with_github_and_queue(
            "submit_feedback", feedback,
            self._serialize_feedback(feedback),
            correlation_id,
        )

    def submit_crash_report(self, report: CrashReport) -> SupportSubmitResult:
        """Store and submit a crash report."""
        correlation_id = _cid()
        logger.info("[%s][%s] Crash submission started (id: %s)", SUBSYSTEM, correlation_id, report.report_id)
        return self._submit_with_github_and_queue(
            "submit_crash", report,
            self._serialize_crash_report(report),
            correlation_id,
        )

    def is_connection_available(self) -> bool:
        """Return True if the remote report backend is validated and available."""
        if self._github_service is None:
            return True
        conn = getattr(self._github_service, "connection", None)
        if conn is None:
            conn = getattr(self._github_service, "_connection", None)
        if conn is None:
            return True
        return getattr(conn, "is_available", True)

    def process_queue(self) -> object | None:
        """Process the offline report queue.

        Returns QueueProcessResult from the queue service,
        or None if no queue service is configured.
        """
        if self._queue_service is None:
            logger.info("[%s] Queue processing skipped (no queue service)", SUBSYSTEM)
            return None

        # Check validation availability before executing pings
        if not self.is_connection_available():
            logger.info("[%s] Queue retry skipped (offline)", SUBSYSTEM)
            return None

        return self._queue_service.process_queue(self._queue_submit_fn())

    # ------------------------------------------------------------------
    # Internal: backend + queue orchestration
    # ------------------------------------------------------------------

    def _submit_with_github_and_queue(
        self, github_method: str,
        model: object,
        serialized: dict[str, object],
        correlation_id: str | None = None,
    ) -> SupportSubmitResult:
        github_success, github_url, github_error = self._try_github_submit(
            github_method, model, correlation_id
        )

        queued = False
        queued_path = None

        if not github_success and _is_retryable(github_error):
            result = self._try_queue_report(
                self._report_type(github_method), serialized, correlation_id
            )
            if result is not None:
                queued = True
                queued_path = str(result)
                logger.info("[%s][%s] Report queued locally", SUBSYSTEM, correlation_id)

        return SupportSubmitResult(
            local_stored=True,
            github_success=github_success,
            github_url=github_url,
            github_error=github_error,
            queued=queued,
            queued_path=queued_path,
        )

    def _try_github_submit(
        self, method: str, model: object,
        correlation_id: str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """Attempt to forward a submission to the backend.

        Returns (success, url, error_message).
        """
        cid = f"[{correlation_id}]" if correlation_id else ""
        if self._github_service is None:
            return False, None, None
        try:
            method_fn = getattr(self._github_service, method, None)
            if method_fn is None:
                logger.warning("[%s]%s Backend method missing: %s", SUBSYSTEM, cid, method)
                return False, None, None
            result = method_fn(model)
            if result.success:
                logger.info("[%s]%s Report submitted to backend", SUBSYSTEM, cid)
                return True, result.issue_url, None
            logger.warning("[%s]%s Backend submission failed: %s", SUBSYSTEM, cid, result.error_message)
            return False, None, result.error_message
        except Exception as exc:
            logger.exception("[%s]%s Backend submission error (%s)", SUBSYSTEM, cid, exc)
            return False, None, str(exc)

    def _try_queue_report(
        self, report_type: str, data: dict[str, object],
        correlation_id: str | None = None,
    ) -> object | None:
        """Attempt to queue a report for offline retry."""
        if self._queue_service is None:
            return None
        try:
            logger.info("[%s][%s] Queueing report (type=%s)", SUBSYSTEM, correlation_id, report_type)
            return self._queue_service.save_report(report_type, data)
        except Exception as exc:
            logger.exception("[%s][%s] Failed to queue report (%s)", SUBSYSTEM, correlation_id, exc)
            return None

    def _queue_submit_fn(self) -> Callable[[str, dict], bool | str]:
        """Return a callable for QueueProcessService to submit queued reports."""
        github = self._github_service

        def submit(report_type: str, data: dict) -> bool | str:
            if github is None:
                logger.info("[%s] Queue discard (no backend)", SUBSYSTEM)
                return "discard"
            method_name = _GITHUB_METHOD_MAP.get(report_type)
            if method_name is None:
                logger.info("[%s] Queue discard (unknown type: %s)", SUBSYSTEM, report_type)
                return "discard"
            model = _reconstruct_model(report_type, data)
            if model is None:
                logger.info("[%s] Queue discard (reconstruct failed: %s)", SUBSYSTEM, report_type)
                return "discard"
            try:
                method_fn = getattr(github, method_name, None)
                if method_fn is None:
                    logger.info("[%s] Queue discard (method missing: %s)", SUBSYSTEM, method_name)
                    return "discard"
                result = method_fn(model)
                if result.success:
                    logger.info("[%s] Queue retry succeeded (type=%s)", SUBSYSTEM, report_type)
                    return True

                # Classify the failure using validation status (from T-230)
                conn = getattr(github, "connection", None)
                if conn is None:
                    conn = getattr(github, "_connection", None)

                from services.support.mongo_connection import MongoValidationStatus
                status = getattr(conn, "validation_status", None) if conn else None

                # Non-retryable permanent configurations or auth errors
                if status in (
                    MongoValidationStatus.CONFIGURATION_MISSING,
                    MongoValidationStatus.AUTHENTICATION_FAILED,
                    MongoValidationStatus.PERMISSION_ERROR,
                ):
                    logger.info("[%s] Queue discard (permanent: %s)", SUBSYSTEM, status.value if status else "unknown")
                    return "discard"

                # Also inspect error message strings for payload validation restrictions
                err_msg = (result.error_message or "").lower()
                non_retryable_keywords = [
                    "unauthorized", "unsupported", "invalid payload",
                    "permission denied", "forbidden", "validation error",
                ]
                if any(kw in err_msg for kw in non_retryable_keywords):
                    logger.info("[%s] Queue discard (validation error)", SUBSYSTEM)
                    return "discard"

                # Otherwise transient error (Timeout, DNS, Connection failure) -> retryable
                logger.info("[%s] Queue retry deferred (transient)", SUBSYSTEM)
                return False
            except Exception as exc:
                logger.warning("[%s] Queue retry error (%s: %s)", SUBSYSTEM, report_type, exc)
                return "discard"

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
    def _serialize_crash_report(report: CrashReport) -> dict[str, object]:
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
    def _report_type(github_method: str) -> str:
        mapping = {
            "submit_bug": "bug",
            "submit_feature": "feature",
            "submit_feedback": "feedback",
            "submit_crash": "crash",
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
                    "[%s] Announcements service error: %s", SUBSYSTEM, exc
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
                    title="Direct Report Submission",
                    description="Submit bug reports and feature requests "
                                "directly from the Support Center.",
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
    "crash": CrashReport,
}

_GITHUB_METHOD_MAP: dict[str, str] = {
    "bug": "submit_bug",
    "feature": "submit_feature",
    "feedback": "submit_feedback",
    "crash": "submit_crash",
}


def _reconstruct_model(
    report_type: str, data: dict
) -> BugReport | FeatureRequest | FeedbackReport | CrashReport | None:
    """Reconstruct a domain model from queued JSON data."""
    cls = _REPORT_TYPE_CLS_MAP.get(report_type)
    if cls is None:
        return None
    try:
        return cls(**data)
    except (TypeError, ValueError) as exc:
        logger.error(
            "[%s] Model reconstruction failed (%s): %s", "Support", report_type, exc
        )
        return None
