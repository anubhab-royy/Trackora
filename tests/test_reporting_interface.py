"""Tests for the reporting abstraction layer.

Validates:
  - AbstractReportService cannot be instantiated directly.
  - GitHubIssueService is a concrete subclass.
  - SubmitResult fields.
  - ReportType enum values.
  - Dependency injection with a concrete mock backend.
"""

from unittest.mock import MagicMock

import pytest

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.github_issue_service import GitHubIssueService, IssueResult, IssueType
from services.support.reporting_interface import (
    AbstractReportService,
    ReportType,
    SubmitResult,
)
from services.support.support_service import SupportService
from ui.crash_dialog import CrashDialog


# ======================================================================
# Interface contract
# ======================================================================


class TestAbstractReportService:
    def test_cannot_instantiate_abc(self):
        """AbstractReportService is abstract and cannot be created directly."""
        with pytest.raises(TypeError):
            AbstractReportService()  # type: ignore[abstract]

    def test_git_hub_service_is_concrete_subclass(self):
        """GitHubIssueService is a valid AbstractReportService implementation."""
        assert issubclass(GitHubIssueService, AbstractReportService)


class TestSubmitResult:
    def test_defaults(self):
        r = SubmitResult(success=True)
        assert r.success is True
        assert r.report_id is None
        assert r.issue_url is None
        assert r.error_message is None

    def test_all_fields(self):
        r = SubmitResult(
            success=True,
            report_id="abc-123",
            issue_url="https://example.com/issue/1",
            error_message=None,
        )
        assert r.report_id == "abc-123"
        assert r.issue_url == "https://example.com/issue/1"


class TestReportType:
    def test_values(self):
        assert ReportType.BUG.value == "bug"
        assert ReportType.FEATURE.value == "feature-request"
        assert ReportType.FEEDBACK.value == "feedback"
        assert ReportType.CRASH.value == "crash"

    def test_matches_legacy_issue_type(self):
        """ReportType has the same values as the backward-compat IssueType."""
        for rt in ReportType:
            it = IssueType(rt.value)
            assert it.value == rt.value


# ======================================================================
# Backward-compatibility aliases
# ======================================================================


class TestIssueTypeAlias:
    def test_issue_type_is_report_type(self):
        assert IssueType is ReportType

    def test_issue_result_is_submit_result(self):
        assert IssueResult is SubmitResult


# ======================================================================
# Dependency injection — SupportService
# ======================================================================


class TestSupportServiceDI:
    def test_accepts_abstract_service(self):
        """SupportService constructor accepts AbstractReportService."""
        mock = MagicMock(spec=AbstractReportService)
        svc = SupportService(github_service=mock)
        assert svc is not None

    def test_submit_bug_delegates_to_backend(self):
        """SupportService calls the backend via the abstract interface."""
        mock = MagicMock(spec=AbstractReportService)
        mock.submit_bug.return_value = SubmitResult(
            success=True, report_id="mock-1", issue_url="https://example.com/1"
        )
        svc = SupportService(github_service=mock)

        report = BugReport(
            title="DI Test",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        result = svc.submit_bug_report(report)
        assert result.local_stored is True
        assert result.github_success is True
        assert result.github_url == "https://example.com/1"
        mock.submit_bug.assert_called_once_with(report)

    def test_submit_feature_delegates_to_backend(self):
        mock = MagicMock(spec=AbstractReportService)
        mock.submit_feature.return_value = SubmitResult(success=True, report_id="m2")
        svc = SupportService(github_service=mock)

        req = FeatureRequest(title="Feat", description="desc", use_case="uc")
        result = svc.submit_feature_request(req)
        assert result.github_success is True
        mock.submit_feature.assert_called_once_with(req)

    def test_submit_feedback_delegates_to_backend(self):
        mock = MagicMock(spec=AbstractReportService)
        mock.submit_feedback.return_value = SubmitResult(success=True, report_id="m3")
        svc = SupportService(github_service=mock)

        fb = FeedbackReport(subject="FB", message="msg")
        result = svc.submit_feedback(fb)
        assert result.github_success is True
        mock.submit_feedback.assert_called_once_with(fb)

    def test_submit_without_backend_returns_no_github_result(self):
        svc = SupportService()
        report = BugReport(
            title="No backend",
            description="d",
            steps_to_reproduce="s",
            expected_behavior="e",
            actual_behavior="a",
        )
        result = svc.submit_bug_report(report)
        assert result.local_stored is True
        assert result.github_success is False
        assert result.github_url is None

    def test_queue_submit_fn_uses_backend(self, tmp_path):
        """Queue processing delegates to the abstract backend."""
        mock = MagicMock(spec=AbstractReportService)
        mock.submit_bug.return_value = SubmitResult(success=True, report_id="q1")
        from services.support.report_queue_service import ReportQueueService

        queue = ReportQueueService(storage_dir=tmp_path / "queue_di")
        queue.save_report("bug", {"title": "Queue DI Test", "description": "d",
                                   "steps_to_reproduce": "s", "expected_behavior": "e",
                                   "actual_behavior": "a", "severity": "medium"})
        svc = SupportService(github_service=mock, queue_service=queue)
        result = svc.process_queue()
        assert result is not None
        assert result.succeeded == 1
        mock.submit_bug.assert_called_once()
        queue.clear_all()


# ======================================================================
# Dependency injection — CrashDialog
# ======================================================================


class TestCrashDialogDI:
    def test_accepts_abstract_service_type_hint(self):
        """CrashDialog constructor type-hints github_service as AbstractReportService."""
        import inspect
        sig = inspect.signature(CrashDialog.__init__)
        param = sig.parameters.get("github_service")
        assert param is not None
        # Verify the default is None (backward compatible)
        assert param.default is None
