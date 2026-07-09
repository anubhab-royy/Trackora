"""
SupportCenterController.

Bridges the SupportService (business layer) and the SupportCenterWidget (view).
Handles navigation, read-only data loading, and form submission.
"""

from __future__ import annotations

import logging

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.support_service import (
    SupportService,
    SupportSubmitResult,
)
from ui.support_center.support_center_widget import SupportCenterWidget

logger = logging.getLogger(__name__)


_RESULT_TYPE_SUCCESS = "success"
_RESULT_TYPE_INFO = "info"
_RESULT_TYPE_WARNING = "warning"
_RESULT_TYPE_ERROR = "error"


class SupportCenterController:
    """
    Controller for the Support Center screen.

    Args:
        view:            SupportCenterWidget instance.
        support_service: SupportService instance.
    """

    def __init__(
        self,
        view: SupportCenterWidget,
        support_service: SupportService,
    ) -> None:
        self._view = view
        self._service = support_service
        self._submitting_pages: set[str] = set()
        self._connect_signals()
        logger.info("SupportCenterController initialised.")

    def _connect_signals(self) -> None:
        self._view.navigation_requested.connect(self._on_page_changed)
        self._view.submit_requested.connect(self._on_submit)

    def _on_page_changed(self, page_key: str) -> None:
        logger.debug("Support page changed: %s", page_key)
        self._view.clear_submit_result(page_key)

    def _on_submit(self, page_key: str) -> None:
        if page_key in self._submitting_pages:
            logger.debug("Submission already in progress for %s, ignoring", page_key)
            return

        logger.info("Submit requested for page: %s", page_key)
        self._submitting_pages.add(page_key)
        self._view.set_submitting(page_key, True)

        try:
            if page_key == "report_bug":
                self._submit_bug()
            elif page_key == "suggest_feature":
                self._submit_feature()
            elif page_key == "feedback":
                self._submit_feedback()
            else:
                logger.warning("Unknown submit page: %s", page_key)
        except Exception:
            logger.exception("Unexpected submission error on %s", page_key)
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_ERROR,
                "An unexpected error occurred while submitting the report.",
            )
        finally:
            self._submitting_pages.discard(page_key)
            self._view.set_submitting(page_key, False)

    def _submit_bug(self) -> None:
        data = self._view.get_bug_form_data()
        if not data["title"] or not data["description"]:
            self._view.set_submit_result(
                "report_bug", _RESULT_TYPE_WARNING,
                "Title and description are required.",
            )
            return
        report = BugReport(
            title=data["title"],
            description=data["description"],
            steps_to_reproduce=data["steps"],
            expected_behavior=data["expected"],
            actual_behavior=data["actual"],
            severity=data["severity"],
        )
        result = self._service.submit_bug_report(report)
        if result.local_stored:
            self._view.clear_bug_form()
        self._show_submit_result("report_bug", result)

    def _submit_feature(self) -> None:
        data = self._view.get_feature_form_data()
        if not data["title"] or not data["description"]:
            self._view.set_submit_result(
                "suggest_feature", _RESULT_TYPE_WARNING,
                "Title and description are required.",
            )
            return
        request = FeatureRequest(
            title=data["title"],
            description=data["description"],
            use_case=data["use_case"],
            priority=data["priority"],
        )
        result = self._service.submit_feature_request(request)
        if result.local_stored:
            self._view.clear_feature_form()
        self._show_submit_result("suggest_feature", result)

    def _submit_feedback(self) -> None:
        data = self._view.get_feedback_form_data()
        if not data["subject"] or not data["message"]:
            self._view.set_submit_result(
                "feedback", _RESULT_TYPE_WARNING,
                "Subject and message are required.",
            )
            return
        feedback = FeedbackReport(
            subject=data["subject"],
            message=data["message"],
            category=data["category"],
            contact_ok=data["contact_ok"],
        )
        result = self._service.submit_feedback(feedback)
        if result.local_stored:
            self._view.clear_feedback_form()
        self._show_submit_result("feedback", result)

    # ------------------------------------------------------------------
    # Result Mapping
    #
    # Every possible SupportSubmitResult outcome maps to exactly one
    # user-facing confirmation.  No ambiguous states, no silent failures.
    #
    # The UI consumes only the result object — no MongoDB exceptions,
    # no QueueValidator internals, no retry logic inspection.
    # ------------------------------------------------------------------

    def _show_submit_result(
        self, page_key: str, result: SupportSubmitResult
    ) -> None:
        # 1. Local storage failure — should never happen in practice,
        #    but catches truly unexpected infrastructure errors.
        if not result.local_stored:
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_ERROR,
                "An unexpected error occurred while submitting the report.",
            )
            return

        # 2. Backend accepted the report.
        if result.github_success:
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_SUCCESS,
                "Your report has been submitted successfully.",
            )
            return

        # 3. Backend failed but report was queued for offline retry.
        if result.queued:
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_INFO,
                "No internet connection.\n\n"
                "Your report has been saved locally and will be submitted "
                "automatically when Trackora reconnects.",
            )
            return

        # 4. Permanent (non-retryable) backend failure — use the error
        #    string from the result to pick a user-friendly message.
        error = result.github_error or ""

        err_lower = error.lower()

        if "auth" in err_lower:
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_WARNING,
                "Trackora couldn't authenticate with the support service.",
            )
        elif "config" in err_lower or "not configured" in err_lower:
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_WARNING,
                "Trackora couldn't submit the report because the support "
                "service configuration is invalid.",
            )
        elif "permission" in err_lower or "forbidden" in err_lower or "denied" in err_lower:
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_WARNING,
                "The report couldn't be submitted because access was denied.",
            )
        elif "invalid" in err_lower or "unsupported" in err_lower:
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_WARNING,
                "The report contains invalid information and couldn't be "
                "submitted. Please review your input and try again.",
            )
        else:
            # Unknown / unexpected error — safe generic fallback.
            self._view.set_submit_result(
                page_key, _RESULT_TYPE_ERROR,
                "An unexpected error occurred while submitting the report.",
            )

    def navigate_to(self, page: str) -> None:
        """Programmatically navigate to a support page.

        Args:
            page: One of 'report_bug', 'suggest_feature', 'feedback'.
        """
        self._view.navigate_to(page)
