"""Tests for SupportService."""

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.support_service import SupportService, UpcomingUpdate


class TestSupportService:
    def test_submit_bug_report_returns_true(self):
        svc = SupportService()
        report = BugReport(
            title="Test bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        assert svc.submit_bug_report(report) is True

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

    def test_submit_feature_request_returns_true(self):
        svc = SupportService()
        req = FeatureRequest(
            title="Test feature",
            description="desc",
            use_case="use case",
        )
        assert svc.submit_feature_request(req) is True

    def test_submit_feature_request_assigns_id(self):
        svc = SupportService()
        req = FeatureRequest(
            title="Test feature",
            description="desc",
            use_case="use case",
        )
        svc.submit_feature_request(req)
        assert req.id is not None

    def test_submit_feedback_returns_true(self):
        svc = SupportService()
        fb = FeedbackReport(subject="Test", message="msg")
        assert svc.submit_feedback(fb) is True

    def test_submit_feedback_assigns_id(self):
        svc = SupportService()
        fb = FeedbackReport(subject="Test", message="msg")
        svc.submit_feedback(fb)
        assert fb.id is not None

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
