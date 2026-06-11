"""
SupportService — orchestrates support operations.

Stores submissions locally and submits to GitHub via GitHubIssueService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import uuid4

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport

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
        local_stored:  True when the report was persisted in memory.
        github_success: True when the report was also submitted to GitHub.
        github_url:    URL of the created GitHub issue (if applicable).
        github_error:  Error message if GitHub submission failed.
    """
    local_stored: bool
    github_success: bool = False
    github_url: str | None = None
    github_error: str | None = None

    @property
    def success(self) -> bool:
        """Overall success — local storage always counts."""
        return self.local_stored


class SupportService:
    """Service interface for support center operations.

    Stores submissions in memory and optionally forwards them
    to GitHub Issues via a GitHubIssueService.

    Architecture rules:
    - No UI imports.
    - No SQL.
    - Returns typed domain models and DTOs.
    """

    def __init__(
        self,
        github_service: object | None = None,
    ) -> None:
        self._github_service = github_service
        self._bug_reports: list[BugReport] = []
        self._feature_requests: list[FeatureRequest] = []
        self._feedback_reports: list[FeedbackReport] = []

    def submit_bug_report(self, report: BugReport) -> SupportSubmitResult:
        """Store and optionally submit a bug report.

        Returns SupportSubmitResult with local and GitHub status.
        """
        report.id = str(uuid4())
        self._bug_reports.append(report)
        logger.info("Bug report stored locally: %s", report.title)

        github_result = self._try_github_submit("submit_bug", report)
        return SupportSubmitResult(
            local_stored=True,
            github_success=github_result[0],
            github_url=github_result[1],
            github_error=github_result[2],
        )

    def submit_feature_request(
        self, request: FeatureRequest
    ) -> SupportSubmitResult:
        """Store and optionally submit a feature request."""
        request.id = str(uuid4())
        self._feature_requests.append(request)
        logger.info("Feature request stored locally: %s", request.title)

        github_result = self._try_github_submit("submit_feature", request)
        return SupportSubmitResult(
            local_stored=True,
            github_success=github_result[0],
            github_url=github_result[1],
            github_error=github_result[2],
        )

    def submit_feedback(self, feedback: FeedbackReport) -> SupportSubmitResult:
        """Store and optionally submit feedback."""
        feedback.id = str(uuid4())
        self._feedback_reports.append(feedback)
        logger.info("Feedback stored locally: %s", feedback.subject)

        github_result = self._try_github_submit("submit_feedback", feedback)
        return SupportSubmitResult(
            local_stored=True,
            github_success=github_result[0],
            github_url=github_result[1],
            github_error=github_result[2],
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

    def get_upcoming_updates(self) -> list[UpcomingUpdate]:
        """Return a list of planned or published updates."""
        return [
            UpcomingUpdate(
                title="Support Center Launch",
                description="Centralized hub for bug reports, feature requests, and feedback.",
                version="1.1.0",
                is_published=False,
            ),
            UpcomingUpdate(
                title="GitHub Integration",
                description="Submit bug reports and feature requests directly to GitHub Issues.",
                version="1.2.0",
                is_published=True,
            ),
            UpcomingUpdate(
                title="Enhanced Statistics Export",
                description="Export detailed statistics including charts and trends.",
                version="1.3.0",
                is_published=False,
            ),
        ]
