"""SupportService — architecture interface for support operations.

Current implementation uses in-memory storage.
Future iterations will integrate with GitHub API for issue tracking.
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


class SupportService:
    """Service interface for support center operations.

    Current: in-memory storage with stub methods.
    Future: GitHub API issue creation and retrieval.

    Architecture rules:
    - No UI imports.
    - No SQL.
    - Returns typed domain models and DTOs.
    """

    def __init__(self) -> None:
        self._bug_reports: list[BugReport] = []
        self._feature_requests: list[FeatureRequest] = []
        self._feedback_reports: list[FeedbackReport] = []

    def submit_bug_report(self, report: BugReport) -> bool:
        """Store a bug report.

        Returns True when the report is accepted.
        """
        report.id = str(uuid4())
        self._bug_reports.append(report)
        logger.info("Bug report stored: %s", report.title)
        return True

    def submit_feature_request(self, request: FeatureRequest) -> bool:
        """Store a feature request.

        Returns True when the request is accepted.
        """
        request.id = str(uuid4())
        self._feature_requests.append(request)
        logger.info("Feature request stored: %s", request.title)
        return True

    def submit_feedback(self, feedback: FeedbackReport) -> bool:
        """Store a feedback submission.

        Returns True when the feedback is accepted.
        """
        feedback.id = str(uuid4())
        self._feedback_reports.append(feedback)
        logger.info("Feedback stored: %s", feedback.subject)
        return True

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
                is_published=False,
            ),
            UpcomingUpdate(
                title="Enhanced Statistics Export",
                description="Export detailed statistics including charts and trends.",
                version="1.3.0",
                is_published=False,
            ),
        ]
