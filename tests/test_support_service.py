"""Tests for SupportService."""

from unittest.mock import MagicMock

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.support_service import (
    SupportService,
    SupportSubmitResult,
    UpcomingUpdate,
)


class TestSupportService:
    def test_submit_bug_report_returns_submit_result(self):
        svc = SupportService()
        report = BugReport(
            title="Test bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        result = svc.submit_bug_report(report)
        assert isinstance(result, SupportSubmitResult)
        assert result.local_stored is True

    def test_submit_bug_report_success_property(self):
        svc = SupportService()
        report = BugReport(
            title="Test bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        result = svc.submit_bug_report(report)
        assert result.success is True

    def test_submit_bug_report_assigns_id(self):
        svc = SupportService()
        report = BugReport(
            title="Test bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        svc.submit_bug_report(report)
        assert report.id is not None

    def test_submit_feature_request_returns_submit_result(self):
        svc = SupportService()
        req = FeatureRequest(
            title="Test feature",
            description="desc",
            use_case="use case",
        )
        result = svc.submit_feature_request(req)
        assert isinstance(result, SupportSubmitResult)
        assert result.local_stored is True

    def test_submit_feature_request_assigns_id(self):
        svc = SupportService()
        req = FeatureRequest(
            title="Test feature",
            description="desc",
            use_case="use case",
        )
        svc.submit_feature_request(req)
        assert req.id is not None

    def test_submit_feedback_returns_submit_result(self):
        svc = SupportService()
        fb = FeedbackReport(subject="Test", message="msg")
        result = svc.submit_feedback(fb)
        assert isinstance(result, SupportSubmitResult)
        assert result.local_stored is True

    def test_submit_feedback_assigns_id(self):
        svc = SupportService()
        fb = FeedbackReport(subject="Test", message="msg")
        svc.submit_feedback(fb)
        assert fb.id is not None

    def test_submit_without_github_has_no_github_result(self):
        svc = SupportService()
        report = BugReport(
            title="Test",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        result = svc.submit_bug_report(report)
        assert result.github_success is False
        assert result.github_url is None
        assert result.github_error is None

    def test_get_upcoming_updates_returns_list(self):
        svc = SupportService()
        updates = svc.get_upcoming_updates()
        assert isinstance(updates, list)
        assert len(updates) > 0

    def test_upcoming_updates_are_upcoming_update_instances(self):
        svc = SupportService()
        for item in svc.get_upcoming_updates():
            assert isinstance(item, UpcomingUpdate)

    def test_upcoming_updates_have_required_fields(self):
        svc = SupportService()
        for item in svc.get_upcoming_updates():
            assert hasattr(item, "title")
            assert hasattr(item, "description")
            assert hasattr(item, "version")
            assert hasattr(item, "is_published")


class TestSupportServiceWithGitHub:
    def test_submit_with_github_service_success(self):
        mock_github = MagicMock()
        mock_github.submit_bug.return_value = MagicMock(
            success=True, issue_url="https://github.com/issue/1", error_message=None
        )
        svc = SupportService(github_service=mock_github)
        report = BugReport(
            title="Test",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        result = svc.submit_bug_report(report)
        assert result.local_stored is True
        assert result.github_success is True
        assert result.github_url == "https://github.com/issue/1"
        assert result.github_error is None
        mock_github.submit_bug.assert_called_once_with(report)

    def test_submit_with_github_service_failure(self):
        mock_github = MagicMock()
        mock_github.submit_bug.return_value = MagicMock(
            success=False,
            issue_url=None,
            error_message="Rate limited",
        )
        svc = SupportService(github_service=mock_github)
        report = BugReport(
            title="Test",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        result = svc.submit_bug_report(report)
        assert result.local_stored is True
        assert result.github_success is False
        assert result.github_url is None
        assert result.github_error == "Rate limited"

    def test_submit_feature_with_github_service(self):
        mock_github = MagicMock()
        mock_github.submit_feature.return_value = MagicMock(
            success=True, issue_url="https://github.com/issue/2", error_message=None
        )
        svc = SupportService(github_service=mock_github)
        req = FeatureRequest(
            title="Feature", description="desc", use_case="uc"
        )
        result = svc.submit_feature_request(req)
        assert result.github_success is True
        assert result.github_url == "https://github.com/issue/2"
        mock_github.submit_feature.assert_called_once_with(req)

    def test_submit_feedback_with_github_service(self):
        mock_github = MagicMock()
        mock_github.submit_feedback.return_value = MagicMock(
            success=True, issue_url="https://github.com/issue/3", error_message=None
        )
        svc = SupportService(github_service=mock_github)
        fb = FeedbackReport(subject="Feedback", message="msg")
        result = svc.submit_feedback(fb)
        assert result.github_success is True
        assert result.github_url == "https://github.com/issue/3"
        mock_github.submit_feedback.assert_called_once_with(fb)

    def test_github_exception_handled_gracefully(self):
        mock_github = MagicMock()
        mock_github.submit_bug.side_effect = Exception("API failure")
        svc = SupportService(github_service=mock_github)
        report = BugReport(
            title="Test",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        result = svc.submit_bug_report(report)
        assert result.local_stored is True
        assert result.github_success is False
        assert result.github_error is not None
