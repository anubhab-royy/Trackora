"""
GitHubIssueService — GitHub REST API integration for support submissions.

Submits bug reports, feature requests, and feedback as GitHub Issues.
Reads authentication and repository configuration from SettingsRepository.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from database.repositories.settings_repository import SettingsRepository
from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport

logger = logging.getLogger(__name__)

_API_TIMEOUT_SECONDS = 15

_GITHUB_SETTINGS_TOKEN = "github_token"
_GITHUB_SETTINGS_OWNER = "github_repo_owner"
_GITHUB_SETTINGS_REPO = "github_repo_name"


class IssueType(Enum):
    BUG = "bug"
    FEATURE = "feature-request"
    FEEDBACK = "feedback"


@dataclass
class IssueResult:
    success: bool
    issue_url: str | None = None
    error_message: str | None = None


@dataclass
class GitHubConfig:
    token: str
    repo_owner: str
    repo_name: str

    @property
    def api_url(self) -> str:
        return (
            f"https://api.github.com/repos/"
            f"{self.repo_owner}/{self.repo_name}/issues"
        )

    @property
    def is_valid(self) -> bool:
        return bool(self.token and self.repo_owner and self.repo_name)


class GitHubIssueService:
    """Creates GitHub Issues from Trackora support submissions.

    Args:
        settings_repo: SettingsRepository for reading GitHub config.
    """

    def __init__(self, settings_repo: SettingsRepository) -> None:
        self._settings_repo = settings_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_bug(self, report: BugReport) -> IssueResult:
        """Submit a bug report as a GitHub issue."""
        title = report.title
        body = self._build_bug_body(report)
        return self.create_issue(IssueType.BUG, title, body)

    def submit_feature(self, request: FeatureRequest) -> IssueResult:
        """Submit a feature request as a GitHub issue."""
        title = request.title
        body = self._build_feature_body(request)
        return self.create_issue(IssueType.FEATURE, title, body)

    def submit_feedback(self, feedback: FeedbackReport) -> IssueResult:
        """Submit feedback as a GitHub issue."""
        title = feedback.subject
        body = self._build_feedback_body(feedback)
        return self.create_issue(IssueType.FEEDBACK, title, body)

    def create_issue(
        self, issue_type: IssueType, title: str, body: str
    ) -> IssueResult:
        """Create a GitHub issue via the REST API.

        Returns:
            IssueResult with success status, url, and optional error.
        """
        config = self._load_config()
        if config is None:
            return IssueResult(
                success=False,
                error_message=(
                    "GitHub not configured. Set github_token, "
                    "github_repo_owner, and github_repo_name in settings."
                ),
            )

        payload = {
            "title": title,
            "body": body,
            "labels": [issue_type.value],
        }

        try:
            return self._post_issue(config, payload)
        except URLError as exc:
            logger.error("Network error posting GitHub issue: %s", exc)
            return IssueResult(
                success=False,
                error_message=(
                    "Network error: could not reach GitHub. "
                    "Check your internet connection."
                ),
            )
        except Exception as exc:
            logger.exception("Unexpected error posting GitHub issue: %s", exc)
            return IssueResult(
                success=False,
                error_message="An unexpected error occurred while submitting.",
            )

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> GitHubConfig | None:
        token = self._settings_repo.get_value(_GITHUB_SETTINGS_TOKEN)
        owner = self._settings_repo.get_value(_GITHUB_SETTINGS_OWNER)
        repo = self._settings_repo.get_value(_GITHUB_SETTINGS_REPO)
        cfg = GitHubConfig(token=token, repo_owner=owner, repo_name=repo)
        if not cfg.is_valid:
            logger.warning("GitHub config incomplete: token=%(t)r owner=%(o)r repo=%(r)r",
                           {"t": bool(token), "o": owner, "r": repo})
            return None
        return cfg

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _post_issue(
        self, config: GitHubConfig, payload: dict[str, Any]
    ) -> IssueResult:
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            config.api_url,
            data=data,
            headers={
                "Authorization": f"Bearer {config.token}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Trackora/1.1",
            },
        )

        try:
            with urlopen(req, timeout=_API_TIMEOUT_SECONDS) as resp:
                response_body = json.loads(resp.read().decode("utf-8"))
                issue_url: str | None = response_body.get("html_url")
                logger.info(
                    "GitHub issue created: %s (type=%s)",
                    issue_url,
                    payload.get("labels", [""])[0],
                )
                return IssueResult(success=True, issue_url=issue_url)
        except URLError as exc:
            return self._handle_http_error(exc)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON response from GitHub: %s", exc)
            return IssueResult(
                success=False,
                error_message="Received an invalid response from GitHub.",
            )

    def _handle_http_error(self, exc: URLError) -> IssueResult:
        """Interpret HTTP error codes into user-facing messages."""
        status = getattr(exc, "code", None)
        if status is None:
            logger.error("GitHub connection error: %s", exc)
            return IssueResult(
                success=False,
                error_message="Could not connect to GitHub. Check your network.",
            )

        if status == 401:
            logger.error("GitHub authentication failed (401)")
            return IssueResult(
                success=False,
                error_message="GitHub authentication failed. "
                "Check that your personal access token is valid.",
            )
        if status == 403:
            logger.error("GitHub rate limit or forbidden (403)")
            return IssueResult(
                success=False,
                error_message="GitHub rate limit reached or access denied. "
                "Try again later.",
            )
        if status == 404:
            logger.error("GitHub repo not found (404)")
            return IssueResult(
                success=False,
                error_message="GitHub repository not found. "
                "Check your repo owner and name settings.",
            )

        logger.error("GitHub API error HTTP %s: %s", status, exc)
        return IssueResult(
            success=False,
            error_message=f"GitHub API returned HTTP {status}. "
            "Check your configuration and try again.",
        )

    # ------------------------------------------------------------------
    # Body Templates
    # ------------------------------------------------------------------

    @staticmethod
    def _build_bug_body(report: BugReport) -> str:
        return (
            f"### Description\n{report.description}\n\n"
            f"### Expected Result\n{report.expected_behavior}\n\n"
            f"### Actual Result\n{report.actual_behavior}\n\n"
            f"### Steps to Reproduce\n{report.steps_to_reproduce}\n\n"
            f"---\n"
            f"*Submitted via Trackora*\n"
            f"*Severity: {report.severity}*"
        )

    @staticmethod
    def _build_feature_body(request: FeatureRequest) -> str:
        return (
            f"### Description\n{request.description}\n\n"
            f"### Why Needed\n{request.use_case}\n\n"
            f"---\n"
            f"*Submitted via Trackora*\n"
            f"*Priority: {request.priority}*"
        )

    @staticmethod
    def _build_feedback_body(feedback: FeedbackReport) -> str:
        return (
            f"{feedback.message}\n\n"
            f"---\n"
            f"*Submitted via Trackora*\n"
            f"*Category: {feedback.category}*\n"
            f"*Contact OK: {feedback.contact_ok}*"
        )
