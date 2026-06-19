"""
SupportCenterController.

Bridges the SupportService (business layer) and the SupportCenterWidget (view).
Handles navigation, read-only data loading, and form submission.
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import QMessageBox

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.support_service import SupportService
from ui.support_center.support_center_widget import SupportCenterWidget

logger = logging.getLogger(__name__)


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
        self._connect_signals()
        self._load_upcoming_updates()
        logger.info("SupportCenterController initialised.")

    def _connect_signals(self) -> None:
        self._view.navigation_requested.connect(self._on_page_changed)
        self._view.submit_requested.connect(self._on_submit)
        self._view.refresh_requested.connect(self._on_refresh)

    def _on_page_changed(self, page_key: str) -> None:
        logger.debug("Support page changed: %s", page_key)
        self._view.clear_submit_result(page_key)
        if page_key == "upcoming_updates":
            self._load_upcoming_updates()

    def _on_submit(self, page_key: str) -> None:
        logger.info("Submit requested for page: %s", page_key)
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
        except Exception as exc:
            logger.exception("Submission error on %s: %s", page_key, exc)
            self._view.set_submit_result(
                page_key, False, f"Error: {exc}"
            )
        finally:
            self._view.set_submitting(page_key, False)

    def _submit_bug(self) -> None:
        data = self._view.get_bug_form_data()
        if not data["title"] or not data["description"]:
            self._view.set_submit_result(
                "report_bug", False, "Title and description are required."
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
        self._show_submit_result("report_bug", result)

    def _submit_feature(self) -> None:
        data = self._view.get_feature_form_data()
        if not data["title"] or not data["description"]:
            self._view.set_submit_result(
                "suggest_feature", False,
                "Title and description are required."
            )
            return
        request = FeatureRequest(
            title=data["title"],
            description=data["description"],
            use_case=data["use_case"],
            priority=data["priority"],
        )
        result = self._service.submit_feature_request(request)
        self._show_submit_result("suggest_feature", result)

    def _submit_feedback(self) -> None:
        data = self._view.get_feedback_form_data()
        if not data["subject"] or not data["message"]:
            self._view.set_submit_result(
                "feedback", False,
                "Subject and message are required."
            )
            return
        feedback = FeedbackReport(
            subject=data["subject"],
            message=data["message"],
            category=data["category"],
            contact_ok=data["contact_ok"],
        )
        result = self._service.submit_feedback(feedback)
        self._show_submit_result("feedback", result)

    def _show_submit_result(
        self, page_key: str, result: object
    ) -> None:
        local_stored = getattr(result, "local_stored", False)
        backend_success = getattr(result, "github_success", False)
        backend_url = getattr(result, "github_url", None)
        backend_error = getattr(result, "github_error", None)
        queued = getattr(result, "queued", False)

        if not local_stored:
            self._view.set_submit_result(
                page_key, False, "Failed to save locally."
            )
            return

        if backend_success and backend_url:
            self._view.set_submit_result(
                page_key, True,
                f"Report submitted successfully.\nTrack it at: {backend_url}",
            )
        elif backend_success:
            self._view.set_submit_result(
                page_key, True,
                "Report submitted successfully.",
            )
        elif queued:
            self._view.set_submit_result(
                page_key, True,
                "Report saved locally and will be sent automatically.",
            )
        elif backend_error:
            self._view.set_submit_result(
                page_key, True,
                f"Report saved locally.\n{backend_error}",
            )
        else:
            self._view.set_submit_result(
                page_key, True,
                "Report saved locally and will be sent automatically.",
            )

    def _load_upcoming_updates(self) -> None:
        try:
            announcements = self._service.get_announcements()
            self._view.set_announcements(announcements)
        except Exception as exc:
            logger.error("Failed to load upcoming updates: %s", exc)

    def _on_refresh(self) -> None:
        """Force-refresh announcements from remote."""
        self._view.set_refresh_enabled(False)
        try:
            announcements = self._service.refresh_announcements()
            self._view.set_announcements(announcements)
        except Exception as exc:
            logger.warning("Refresh failed: %s", exc)
        finally:
            self._view.set_refresh_enabled(True)

    def navigate_to(self, page: str) -> None:
        """Programmatically navigate to a support page.

        Args:
            page: One of 'report_bug', 'suggest_feature', 'feedback',
                  'upcoming_updates'.
        """
        self._view.navigate_to(page)
