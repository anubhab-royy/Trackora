"""Tests for SupportCenterController.

Covers:
  - Initialisation and navigation
  - Submission flow for bug / feature / feedback
  - Result mapping: success, queued, auth failure, config failure,
    permission denied, validation failure, unexpected error, exception
  - Duplicate click prevention
  - Submit button disabled during processing
"""

from unittest.mock import MagicMock, patch

import pytest

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.support_service import SupportSubmitResult
from ui.support_center.support_center_controller import (
    SupportCenterController,
    _RESULT_TYPE_SUCCESS,
    _RESULT_TYPE_INFO,
    _RESULT_TYPE_WARNING,
    _RESULT_TYPE_ERROR,
)


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


# =========================================================================
# Initialisation & navigation
# =========================================================================

class TestSupportCenterController:
    def test_controller_initialises(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        assert ctrl is not None

    def test_navigate_to_calls_view_navigate_to(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        ctrl.navigate_to("report_bug")
        mock_view.navigate_to.assert_called_once_with("report_bug")



# =========================================================================
# Submission flow
# =========================================================================

class TestSubmissionFlow:
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

    def test_on_page_changed_clears_previous_result(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_page_changed("report_bug")
        mock_view.clear_submit_result.assert_called_once_with("report_bug")


# =========================================================================
# Result mapping — every supported outcome
# =========================================================================

class TestResultMapping:
    """Verify every possible SupportSubmitResult maps to the correct
    user-facing confirmation type and message."""

    # -- Success ----------------------------------------------------------

    def test_success_result_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(local_stored=True, github_success=True)
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_SUCCESS

    def test_success_message_user_friendly(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(local_stored=True, github_success=True)
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "submitted successfully" in msg.lower()
        assert "MongoDB" not in msg
        assert "implementation" not in msg.lower()

    # -- Queued -----------------------------------------------------------

    def test_queued_result_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=True,
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_INFO

    def test_queued_message_no_internet(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=True,
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "No internet connection" in msg
        assert "saved locally" in msg.lower()
        assert "error" not in msg.lower()

    # -- Auth failure -----------------------------------------------------

    def test_auth_failure_result_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Authentication failed",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_WARNING

    def test_auth_failure_message(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Authentication failed. Check your token.",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "authenticate" in msg.lower()
        assert "token" not in msg.lower()  # no implementation details

    # -- Config missing ---------------------------------------------------

    def test_config_missing_result_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="GitHub not configured.",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_WARNING

    def test_config_missing_message(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="GitHub not configured. Set github_token...",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "configuration is invalid" in msg.lower()
        assert "github" not in msg.lower()
        assert "token" not in msg.lower()

    # -- Permission denied ------------------------------------------------

    def test_permission_denied_result_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Permission denied",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_WARNING

    def test_forbidden_message(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Forbidden",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "access was denied" in msg.lower()

    # -- Invalid report ---------------------------------------------------

    def test_invalid_report_result_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Invalid payload",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_WARNING

    def test_invalid_report_message(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Unsupported report type",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "invalid information" in msg.lower()

    # -- Local storage failure --------------------------------------------

    def test_local_storage_failure_result_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(local_stored=False)
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_ERROR

    def test_local_storage_failure_message(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(local_stored=False)
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "unexpected error" in msg.lower()

    # -- Unknown error fallback -------------------------------------------

    def test_unknown_error_fallback_type(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Something strange happened",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        assert args[1] == _RESULT_TYPE_ERROR

    def test_unknown_error_fallback_message(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        result = SupportSubmitResult(
            local_stored=True, github_success=False, queued=False,
            github_error="Something strange happened",
        )
        ctrl._show_submit_result("report_bug", result)
        args, _ = mock_view.set_submit_result.call_args
        msg = args[2]
        assert "unexpected error" in msg.lower()


# =========================================================================
# Exception handling
# =========================================================================

class TestExceptionHandling:
    def test_exception_shows_generic_error(self, mock_view, mock_service):
        """Exceptions during submission must not expose exception details."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.submit_bug_report.side_effect = RuntimeError(
            "MongoDB connection timeout"
        )
        ctrl._on_submit("report_bug")
        args, _ = mock_view.set_submit_result.call_args
        result_type = args[1]
        msg = args[2]
        assert result_type == _RESULT_TYPE_ERROR
        assert "unexpected error" in msg.lower()
        assert "MongoDB" not in msg
        assert "timeout" not in msg.lower()

    def test_exception_logged_not_shown(self, mock_view, mock_service, caplog):
        """The exception details must go to logs, never to the user."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.submit_bug_report.side_effect = RuntimeError("secret-detail")
        caplog.set_level("ERROR")
        ctrl._on_submit("report_bug")
        assert "secret-detail" in caplog.text

    def test_submit_button_disabled_during_exception(self, mock_view, mock_service):
        """Button state must return to enabled even when an exception occurs."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.submit_bug_report.side_effect = RuntimeError("fail")
        ctrl._on_submit("report_bug")
        mock_view.set_submitting.assert_any_call("report_bug", True)
        mock_view.set_submitting.assert_any_call("report_bug", False)


# =========================================================================
# Duplicate click prevention
# =========================================================================

class TestDuplicatePrevention:
    def test_duplicate_submit_ignored(self, mock_view, mock_service):
        """Second click while submitting must be silently ignored."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()

        # Mark the page as already submitting
        ctrl._submitting_pages.add("report_bug")
        ctrl._on_submit("report_bug")

        # Service must NOT be called
        mock_service.submit_bug_report.assert_not_called()
        mock_view.set_submitting.assert_not_called()

    def test_submit_allowed_after_completion(self, mock_view, mock_service):
        """After a submission completes, the same page may be submitted again."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        mock_view.get_bug_form_data.return_value = {
            "title": "New Bug",
            "description": "New desc",
            "steps": "",
            "expected": "",
            "actual": "",
            "severity": "medium",
        }

        ctrl._on_submit("report_bug")
        assert "report_bug" not in ctrl._submitting_pages

    def test_submitting_flag_cleared_after_exception(self, mock_view, mock_service):
        """The submitting flag must be cleared even if an exception is raised."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.submit_bug_report.side_effect = RuntimeError("fail")
        ctrl._on_submit("report_bug")
        assert "report_bug" not in ctrl._submitting_pages

    def test_submit_button_disabled_while_processing(self, mock_view, mock_service):
        """set_submitting(True) must be called before the service call."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_submit("report_bug")
        mock_view.set_submitting.assert_any_call("report_bug", True)

    def test_submit_button_re_enabled_after_processing(self, mock_view, mock_service):
        """set_submitting(False) must be called after the service returns."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_submit("report_bug")
        mock_view.set_submitting.assert_any_call("report_bug", False)


# =========================================================================
# Confirmation message content
# =========================================================================

class TestConfirmationContent:
    def test_no_mongodb_terminology_in_any_message(self, mock_view, mock_service):
        """No user-facing message may contain MongoDB terminology."""
        ctrl = SupportCenterController(mock_view, mock_service)
        scenarios = [
            SupportSubmitResult(local_stored=True, github_success=True),
            SupportSubmitResult(local_stored=True, github_success=False, queued=True),
            SupportSubmitResult(
                local_stored=True, github_success=False,
                github_error="Authentication failed",
            ),
            SupportSubmitResult(
                local_stored=True, github_success=False,
                github_error="GitHub not configured",
            ),
            SupportSubmitResult(
                local_stored=True, github_success=False,
                github_error="Permission denied",
            ),
            SupportSubmitResult(
                local_stored=True, github_success=False,
                github_error="Invalid payload",
            ),
            SupportSubmitResult(local_stored=False),
            SupportSubmitResult(
                local_stored=True, github_success=False,
                github_error="Some weird error",
            ),
        ]
        for result in scenarios:
            mock_view.reset_mock()
            ctrl._show_submit_result("report_bug", result)
            if mock_view.set_submit_result.called:
                msg = mock_view.set_submit_result.call_args[0][2]
                assert "MongoDB" not in msg, f"MongoDB leak: {msg}"
                assert "mongo" not in msg.lower(), f"mongo leak: {msg}"

    def test_no_exception_messages_in_ui(self, mock_view, mock_service):
        """Exception details must never reach the user."""
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.submit_bug_report.side_effect = RuntimeError(
            "Connection refused: 127.0.0.1:27017"
        )
        ctrl._on_submit("report_bug")
        msg = mock_view.set_submit_result.call_args[0][2]
        assert "Connection refused" not in msg
        assert "127.0.0.1" not in msg
        assert "27017" not in msg


# =========================================================================
# Integration-style tests (mock backend)
# =========================================================================

class TestBackendIntegration:
    def test_submit_with_mocked_backend(self, mock_view, mock_service):
        """Verify submission flow with a mocked backend service."""
        mock_github_service = MagicMock()
        mock_github_service.submit_bug.return_value = MagicMock(
            success=True, issue_url="https://example.com/bug/123"
        )

        with patch.object(mock_service, "_github_service", mock_github_service):
            ctrl = SupportCenterController(mock_view, mock_service)
            mock_service.reset_mock()
            mock_view.reset_mock()

            mock_view.get_bug_form_data.return_value = {
                "title": "Integration Test Bug",
                "description": "Test desc",
                "steps": "1. Submit",
                "expected": "It should work",
                "actual": "It works",
                "severity": "critical",
            }

            ctrl._submit_bug()

            mock_service.submit_bug_report.assert_called_once()
            bug_report = mock_service.submit_bug_report.call_args[0][0]
            assert isinstance(bug_report, BugReport)
            assert bug_report.title == "Integration Test Bug"


# =========================================================================
# Legacy tests (preserved from original suite)
# =========================================================================

class TestLegacy:
    def test_database_name_from_env_vs_constructor(self, mock_view, mock_service):
        from services.support.mongo_connection import MongoConnection
        import os
        with patch.dict(os.environ, {"MONGODB_DATABASE": "env_database"}, clear=True):
            conn = MongoConnection(database_name="constructor_database")
            assert conn._database_name == "constructor_database"
            conn2 = MongoConnection()
            assert conn2._database_name == "env_database"

    def test_empty_database_name_handling(self, mock_view, mock_service):
        from services.support.mongo_connection import MongoConnection
        import os
        with patch.dict(os.environ, {"MONGODB_URI": "", "MONGODB_DATABASE": ""}):
            conn = MongoConnection(database_name="")
            assert conn._database_name == ""
            assert conn.database is None
        with patch.dict(os.environ, {}, clear=True):
            conn2 = MongoConnection()
            assert conn2._database_name == ""
            assert conn2.database is None
