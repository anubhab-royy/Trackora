"""Tests for GitHubIssueService."""

import json
from unittest.mock import MagicMock, patch

import pytest

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.github_issue_service import (
    GitHubConfig,
    GitHubIssueService,
    IssueResult,
    IssueType,
)


@pytest.fixture
def mock_settings_repo():
    repo = MagicMock()
    repo.get_value.side_effect = lambda key, default="": {
        "github_token": "valid_token",
        "github_repo_owner": "testowner",
        "github_repo_name": "testrepo",
    }.get(key, default)
    return repo


@pytest.fixture
def service(mock_settings_repo):
    return GitHubIssueService(mock_settings_repo)


class TestGitHubConfig:
    def test_valid_config(self):
        cfg = GitHubConfig(token="t", repo_owner="o", repo_name="r")
        assert cfg.is_valid is True

    def test_empty_token_invalid(self):
        cfg = GitHubConfig(token="", repo_owner="o", repo_name="r")
        assert cfg.is_valid is False

    def test_empty_owner_invalid(self):
        cfg = GitHubConfig(token="t", repo_owner="", repo_name="r")
        assert cfg.is_valid is False

    def test_empty_repo_invalid(self):
        cfg = GitHubConfig(token="t", repo_owner="o", repo_name="")
        assert cfg.is_valid is False

    def test_api_url_format(self):
        cfg = GitHubConfig(token="t", repo_owner="owner", repo_name="repo")
        assert cfg.api_url == "https://api.github.com/repos/owner/repo/issues"


class TestGitHubIssueService:
    def test_initialise(self, service):
        assert service is not None

    def test_submit_bug_returns_issue_result(self, service):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        with patch.object(service, "create_issue", return_value=IssueResult(success=True, issue_url="https://github.com/issue/1")):
            result = service.submit_bug(report)
            assert isinstance(result, IssueResult)
            assert result.success is True

    def test_submit_feature_returns_issue_result(self, service):
        request = FeatureRequest(
            title="Feature", description="desc", use_case="uc"
        )
        with patch.object(service, "create_issue", return_value=IssueResult(success=True, issue_url="https://github.com/issue/2")):
            result = service.submit_feature(request)
            assert isinstance(result, IssueResult)
            assert result.success is True

    def test_submit_feedback_returns_issue_result(self, service):
        fb = FeedbackReport(subject="Feedback", message="msg")
        with patch.object(service, "create_issue", return_value=IssueResult(success=True, issue_url="https://github.com/issue/3")):
            result = service.submit_feedback(fb)
            assert isinstance(result, IssueResult)
            assert result.success is True


class TestCreateIssue:
    def test_missing_config_returns_error(self, mock_settings_repo):
        repo = MagicMock()
        repo.get_value.return_value = ""
        svc = GitHubIssueService(repo)
        result = svc.create_issue(IssueType.BUG, "Title", "Body")
        assert result.success is False
        assert "not configured" in (result.error_message or "").lower()

    def test_successful_creation(self, service):
        response_body = json.dumps({
            "html_url": "https://github.com/testowner/testrepo/issues/42"
        }).encode("utf-8")

        with patch(
            "services.support.github_issue_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = response_body
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = service.create_issue(
                IssueType.BUG, "Test Bug", "Bug body"
            )

        assert result.success is True
        assert result.issue_url == "https://github.com/testowner/testrepo/issues/42"
        assert result.error_message is None

    def test_uses_correct_api_url(self, service):
        with patch(
            "services.support.github_issue_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "html_url": ""
            }).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            service.create_issue(IssueType.BUG, "Title", "Body")

            call_args = mock_urlopen.call_args[0][0]
            assert call_args.full_url == (
                "https://api.github.com/repos/testowner/testrepo/issues"
            )
            assert call_args.headers["Authorization"] == "Bearer valid_token"

    def test_sends_correct_labels(self, service):
        with patch(
            "services.support.github_issue_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "html_url": ""
            }).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            service.create_issue(IssueType.FEATURE, "Title", "Body")

            payload = json.loads(
                mock_urlopen.call_args[0][0].data.decode("utf-8")
            )
            assert payload["labels"] == ["feature-request"]

    def test_feedback_label(self, service):
        with patch(
            "services.support.github_issue_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "html_url": ""
            }).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            service.create_issue(IssueType.FEEDBACK, "Title", "Body")

            payload = json.loads(
                mock_urlopen.call_args[0][0].data.decode("utf-8")
            )
            assert payload["labels"] == ["feedback"]


class TestHTTPErrors:
    def test_401_authentication_error(self, service):
        self._assert_http_error(service, 401, "authentication")

    def test_403_rate_limit_error(self, service):
        self._assert_http_error(service, 403, "rate limit")

    def test_404_repo_not_found(self, service):
        self._assert_http_error(service, 404, "not found")

    def test_500_server_error(self, service):
        self._assert_http_error(service, 500, "HTTP 500")

    def _assert_http_error(self, service, status_code: int, keyword: str):
        with patch(
            "services.support.github_issue_service.urlopen"
        ) as mock_urlopen:
            from urllib.error import HTTPError
            mock_urlopen.side_effect = HTTPError(
                url="https://api.github.com/repos/owner/repo/issues",
                code=status_code,
                msg="Error",
                hdrs={},
                fp=None,
            )
            result = service.create_issue(IssueType.BUG, "Title", "Body")
            assert result.success is False
            assert keyword.lower() in (result.error_message or "").lower()

    def test_network_error_without_code(self, service):
        from urllib.error import URLError
        with patch(
            "services.support.github_issue_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("Connection refused")
            result = service.create_issue(IssueType.BUG, "Title", "Body")
            assert result.success is False
            assert "connect" in (result.error_message or "").lower()

    def test_timeout(self, service):
        from urllib.error import URLError
        with patch(
            "services.support.github_issue_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("timed out")
            result = service.create_issue(IssueType.BUG, "Title", "Body")
            assert result.success is False
            assert result.error_message is not None


class TestBodyTemplates:
    def test_bug_body_includes_all_sections(self):
        report = BugReport(
            title="Bug",
            description="It crashes",
            steps_to_reproduce="1. Open\n2. Click",
            expected_behavior="Should work",
            actual_behavior="Crashes",
            severity="high",
        )
        body = GitHubIssueService._build_bug_body(report)
        assert "### Description" in body
        assert "It crashes" in body
        assert "### Expected Result" in body
        assert "Should work" in body
        assert "### Actual Result" in body
        assert "Crashes" in body
        assert "### Steps to Reproduce" in body
        assert "1. Open" in body
        assert "*Submitted via Trackora*" in body
        assert "*Severity: high*" in body

    def test_feature_body_includes_all_sections(self):
        request = FeatureRequest(
            title="Feature",
            description="Add dark mode",
            use_case="Better at night",
            priority="high",
        )
        body = GitHubIssueService._build_feature_body(request)
        assert "### Description" in body
        assert "Add dark mode" in body
        assert "### Why Needed" in body
        assert "Better at night" in body
        assert "*Priority: high*" in body

    def test_feedback_body_includes_all_sections(self):
        fb = FeedbackReport(
            subject="Great app",
            message="I love it",
            category="praise",
            contact_ok=True,
        )
        body = GitHubIssueService._build_feedback_body(fb)
        assert "I love it" in body
        assert "*Category: praise*" in body
        assert "*Contact OK: True*" in body


class TestSubmitMethods:
    def test_submit_bug_builds_body_from_report(self, service):
        report = BugReport(
            title="Bug Title",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
            severity="critical",
        )
        with patch.object(
            service, "create_issue", return_value=IssueResult(success=True)
        ) as mock_create:
            service.submit_bug(report)
            mock_create.assert_called_once()
            args, _ = mock_create.call_args
            assert args[0] == IssueType.BUG
            assert args[1] == "Bug Title"
            assert "desc" in args[2]
            assert "critical" in args[2]

    def test_submit_feature_builds_body_from_request(self, service):
        request = FeatureRequest(
            title="Feat Title",
            description="feat desc",
            use_case="uc",
            priority="low",
        )
        with patch.object(
            service, "create_issue", return_value=IssueResult(success=True)
        ) as mock_create:
            service.submit_feature(request)
            mock_create.assert_called_once()
            args, _ = mock_create.call_args
            assert args[0] == IssueType.FEATURE
            assert args[1] == "Feat Title"
            assert "feat desc" in args[2]

    def test_submit_feedback_builds_body_from_feedback(self, service):
        fb = FeedbackReport(
            subject="FB Subject", message="FB msg", category="complaint"
        )
        with patch.object(
            service, "create_issue", return_value=IssueResult(success=True)
        ) as mock_create:
            service.submit_feedback(fb)
            mock_create.assert_called_once()
            args, _ = mock_create.call_args
            assert args[0] == IssueType.FEEDBACK
            assert args[1] == "FB Subject"
            assert "FB msg" in args[2]


class TestConfigLoading:
    def test_load_config_returns_config_when_all_set(self, mock_settings_repo):
        svc = GitHubIssueService(mock_settings_repo)
        cfg = svc._load_config()
        assert cfg is not None
        assert cfg.token == "valid_token"
        assert cfg.repo_owner == "testowner"
        assert cfg.repo_name == "testrepo"

    def test_load_config_returns_none_when_token_missing(self):
        repo = MagicMock()
        repo.get_value.return_value = ""
        svc = GitHubIssueService(repo)
        assert svc._load_config() is None

    def test_load_config_returns_none_when_owner_missing(self):
        repo = MagicMock()
        repo.get_value.side_effect = lambda key, default="": {
            "github_token": "t",
            "github_repo_owner": "",
            "github_repo_name": "r",
        }.get(key, default)
        svc = GitHubIssueService(repo)
        assert svc._load_config() is None
