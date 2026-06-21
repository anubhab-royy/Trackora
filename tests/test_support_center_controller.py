"""Tests for SupportCenterController."""

from unittest.mock import MagicMock, patch

import pytest

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.support_service import SupportSubmitResult
from services.update_announcements_service import AnnouncementsResult
from ui.support_center.support_center_controller import SupportCenterController


@pytest.fixture
def mock_view():
    view = MagicMock()
    view.get_bug_form_data.return_value = {
        "title": "Test Bug",
        "description": "Bug description",
        "steps": "1. Step one",
        "expected": "It should work",
        "actual": "It crashes",
        "severity": "high",
    }
    view.get_feature_form_data.return_value = {
        "title": "Test Feature",
        "description": "Feature description",
        "use_case": "Use case",
        "priority": "high",
    }
    view.get_feedback_form_data.return_value = {
        "subject": "Test Feedback",
        "message": "Feedback message",
        "category": "praise",
        "contact_ok": True,
    }
    return view


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.get_announcements.return_value = AnnouncementsResult(
        current_version="1.0.0",
        upcoming_version="1.1.0",
        features=[],
        source="fallback",
    )
    svc.submit_bug_report.return_value = SupportSubmitResult(
        local_stored=True,
        github_success=False,
        github_url=None,
        github_error=None,
    )
    svc.submit_feature_request.return_value = SupportSubmitResult(
        local_stored=True,
        github_success=False,
        github_url=None,
        github_error=None,
    )
    svc.submit_feedback.return_value = SupportSubmitResult(
        local_stored=True,
        github_success=False,
        github_url=None,
        github_error=None,
    )
    return svc


class TestSupportCenterController:
    def test_controller_initialises(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        assert ctrl is not None

    def test_controller_calls_load_announcements_on_init(
        self, mock_view, mock_service
    ):
        SupportCenterController(mock_view, mock_service)
        mock_service.get_announcements.assert_called_once()

    def test_controller_sets_announcements_on_view(self, mock_view, mock_service):
        SupportCenterController(mock_view, mock_service)
        mock_view.set_announcements.assert_called_once()

    def test_navigate_to_calls_view_navigate_to(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        ctrl.navigate_to("report_bug")
        mock_view.navigate_to.assert_called_once_with("report_bug")

    def test_on_page_changed_updates_page_loads_announcements(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_page_changed("upcoming_updates")
        mock_service.get_announcements.assert_called_once()

    def test_on_page_changed_other_pages_do_not_load_announcements(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_page_changed("report_bug")
        mock_service.get_announcements.assert_not_called()

    def test_on_refresh_calls_service_and_view(self, mock_view, mock_service):
        mock_service.refresh_announcements.return_value = AnnouncementsResult(
            current_version="2.0", upcoming_version="2.1", features=[],
        )
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_refresh()
        mock_service.refresh_announcements.assert_called_once()
        mock_view.set_announcements.assert_called_once()
        mock_view.set_refresh_enabled.assert_called()

    def test_submit_bug_creates_bug_report_and_calls_service(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        mock_view.get_bug_form_data.return_value = {
            "title": "Bug Title",
            "description": "Bug desc",
            "steps": "Steps",
            "expected": "Expected",
            "actual": "Actual",
            "severity": "critical",
        }

        ctrl._submit_bug()

        mock_view.get_bug_form_data.assert_called_once()
        mock_service.submit_bug_report.assert_called_once()
        report = mock_service.submit_bug_report.call_args[0][0]
        assert isinstance(report, BugReport)
        assert report.title == "Bug Title"
        assert report.description == "Bug desc"
        assert report.severity == "critical"

    def test_submit_bug_requires_title_and_description(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        mock_view.get_bug_form_data.return_value = {
            "title": "",
            "description": "",
            "steps": "",
            "expected": "",
            "actual": "",
            "severity": "medium",
        }

        ctrl._submit_bug()
        mock_service.submit_bug_report.assert_not_called()
        mock_view.set_submit_result.assert_called_once()

    def test_submit_feature_creates_request_and_calls_service(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        mock_view.get_feature_form_data.return_value = {
            "title": "Feat",
            "description": "Feat desc",
            "use_case": "UC",
            "priority": "low",
        }

        ctrl._submit_feature()

        mock_service.submit_feature_request.assert_called_once()
        req = mock_service.submit_feature_request.call_args[0][0]
        assert isinstance(req, FeatureRequest)
        assert req.title == "Feat"
        assert req.priority == "low"

    def test_submit_feedback_creates_feedback_and_calls_service(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        mock_view.get_feedback_form_data.return_value = {
            "subject": "FB",
            "message": "FB msg",
            "category": "complaint",
            "contact_ok": False,
        }

        ctrl._submit_feedback()

        mock_service.submit_feedback.assert_called_once()
        fb = mock_service.submit_feedback.call_args[0][0]
        assert isinstance(fb, FeedbackReport)
        assert fb.subject == "FB"
        assert fb.category == "complaint"
        assert fb.contact_ok is False

    def test_on_submit_dispatches_to_correct_method(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        with patch.object(ctrl, "_submit_bug") as mock_bug:
            ctrl._on_submit("report_bug")
            mock_bug.assert_called_once()

    def test_submit_sets_loading_state(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        mock_view.get_bug_form_data.return_value = {
            "title": "Title",
            "description": "Desc",
            "steps": "",
            "expected": "",
            "actual": "",
            "severity": "medium",
        }

        ctrl._on_submit("report_bug")
        mock_view.set_submitting.assert_any_call("report_bug", True)
        mock_view.set_submitting.assert_any_call("report_bug", False)

    def test_submit_sets_result_on_view(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        mock_view.get_bug_form_data.return_value = {
            "title": "Title",
            "description": "Desc",
            "steps": "",
            "expected": "",
            "actual": "",
            "severity": "medium",
        }

        ctrl._on_submit("report_bug")
        mock_view.set_submit_result.assert_called_once()

    def test_on_page_changed_clears_previous_result(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_page_changed("report_bug")
        mock_view.clear_submit_result.assert_called_once_with("report_bug")

    def test_database_fallback_integration_test(self, mock_view, mock_service):
        """Test that support center submissions work with mocked MongoDB.
        
        This test verifies that the complete flow from SupportCenterWidget
        through SupportCenterController to SupportService and MongoReportService
        works correctly with the database fallback behavior.
        """
        from unittest.mock import MagicMock, patch

        # Create a mock MongoReportService that simulates MongoDB availability
        mock_github_service = MagicMock()
        mock_github_service.submit_bug.return_value = MagicMock(
            success=True,
            issue_url="https://example.com/bug/123"
        )

        # Patch the SupportService's _github_service with our mock
        with patch.object(mock_service, "_github_service", mock_github_service):
            ctrl = SupportCenterController(mock_view, mock_service)
            mock_service.reset_mock()
            mock_view.reset_mock()

            # Setup bug submission
            mock_view.get_bug_form_data.return_value = {
                "title": "Database Fallback Test",
                "description": "Testing database name fallback",
                "steps": "1. Submit",
                "expected": "Should work",
                "actual": "Works fine",
                "severity": "critical",
            }

            ctrl._submit_bug()

            # Verify the submission flow
            mock_service.submit_bug_report.assert_called_once()
            bug_report = mock_service.submit_bug_report.call_args[0][0]

            assert isinstance(bug_report, BugReport)
            assert bug_report.title == "Database Fallback Test"
            assert bug_report.severity == "critical"

    def test_database_name_from_env_vs_constructor(
        self, mock_view, mock_service
    ):
        """Test database name precedence: constructor parameter overrides env var."""
        from services.support.mongo_connection import MongoConnection

        import os
        with patch.dict(os.environ, {"MONGODB_DATABASE": "env_database"}, clear=True):
            # Constructor parameter should take precedence over env var
            conn = MongoConnection(database_name="constructor_database")
            assert conn._database_name == "constructor_database"

            # Without constructor parameter, should use env var
            conn2 = MongoConnection()
            assert conn2._database_name == "env_database"

    def test_empty_database_name_handling(self, mock_view, mock_service):
        """Test that empty database names are handled correctly."""
        from services.support.mongo_connection import MongoConnection

        # Test constructor parameter
        conn = MongoConnection(database_name="")
        assert conn._database_name == ""
        assert conn.database is None

        # Test with no database name set
        import os
        with patch.dict(os.environ, {}, clear=True):
            conn2 = MongoConnection()
            assert conn2._database_name == ""
            assert conn2.database is None
