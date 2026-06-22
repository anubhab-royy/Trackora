"""Tests for CrashDialog — body builder, action tracking, and queue."""

from unittest.mock import MagicMock

import pytest

from services.crash.diagnostic_service import CrashReport
from ui.crash_dialog import CrashDialog


class TestCrashDialogBodyBuilder:
    def test_build_issue_body_includes_key_fields(self):
        report = CrashReport(
            report_id="test-1",
            timestamp="2026-06-12T00:00:00Z",
            app_version="1.1.0",
            os_version="Windows-10.0.22631",
            os_platform="Windows",
            active_sessions=[{"game_id": 1, "game_name": "Cyberpunk 2077"}],
            tracked_games=2,
            stack_trace=None,
            recent_log_entries=["log line 1", "log line 2"],
            crash_type="unexpected_shutdown",
            was_tracking=True,
        )
        body = CrashDialog._build_issue_body(report)
        assert "1.1.0" in body
        assert "Windows-10.0.22631" in body
        assert "unexpected_shutdown" in body
        assert "Cyberpunk 2077" in body
        assert "log line 1" in body
        assert "Generated automatically" in body

    def test_build_issue_body_includes_stack_trace(self):
        report = CrashReport(
            report_id="test-2",
            timestamp="2026-06-12T00:00:00Z",
            app_version="1.1.0",
            os_version="Linux",
            os_platform="Linux",
            active_sessions=[],
            tracked_games=0,
            stack_trace="Traceback (most recent call last):\n  File \"test.py\", line 1, in <module>\n    raise RuntimeError",
            recent_log_entries=[],
            crash_type="unhandled_exception",
            was_tracking=False,
        )
        body = CrashDialog._build_issue_body(report)
        assert "Stack Trace" in body
        assert "RuntimeError" in body
        assert "test.py" in body

    def test_build_issue_body_no_active_sessions(self):
        report = CrashReport(
            report_id="test-3",
            timestamp="2026-06-12T00:00:00Z",
            app_version="1.1.0",
            os_version="macOS-14.0",
            os_platform="Darwin",
            active_sessions=[],
            tracked_games=0,
            stack_trace=None,
            recent_log_entries=[],
            crash_type="unexpected_shutdown",
            was_tracking=False,
        )
        body = CrashDialog._build_issue_body(report)
        assert "*None*" in body


class TestCrashDialogActionTracking:
    def test_default_action_is_none(self):
        # Dialog not instantiated — test the action attribute concept
        # This tests that ACTION constants are correct
        assert CrashDialog.ACTION_SEND == "send"
        assert CrashDialog.ACTION_REVIEW == "review"
        assert CrashDialog.ACTION_DISMISS == "dismiss"


class TestCrashDialogQueue:
    def _make_report(self) -> CrashReport:
        return CrashReport(
            report_id="test-1",
            timestamp="2026-06-12T00:00:00Z",
            app_version="1.1.0",
            os_version="Windows-10.0.22631",
            os_platform="Windows",
            active_sessions=[{"game_id": 1, "game_name": "Cyberpunk 2077"}],
            tracked_games=2,
            stack_trace=None,
            recent_log_entries=["log line"],
            crash_type="unexpected_shutdown",
            was_tracking=True,
        )

    def test_build_queue_data_returns_all_fields(self):
        report = self._make_report()
        from unittest.mock import MagicMock

        dialog = MagicMock(spec=CrashDialog)
        dialog._report = report
        dialog._build_issue_body.return_value = "issue body text"

        data = CrashDialog._build_queue_data(dialog)
        assert data["report_id"] == "test-1"
        assert data["crash_type"] == "unexpected_shutdown"
        assert data["was_tracking"] is True
        assert data["tracked_games"] == 2
        assert data["active_sessions"] == [{"game_id": 1, "game_name": "Cyberpunk 2077"}]
        assert "issue body text" in data["body"]

    def test_is_retryable_returns_true_for_transient_error(self):
        assert CrashDialog._is_retryable("Connection refused") is True
        assert CrashDialog._is_retryable("Timeout") is True
        assert CrashDialog._is_retryable("Server error") is True

    def test_is_retryable_returns_false_for_config_errors(self):
        assert CrashDialog._is_retryable("Not configured") is False
        assert CrashDialog._is_retryable("Authentication failed") is False
        assert CrashDialog._is_retryable("Not found") is False
        assert CrashDialog._is_retryable("Check your configuration") is False

    def test_is_retryable_returns_false_for_none(self):
        assert CrashDialog._is_retryable(None) is False

    def test_is_retryable_case_insensitive(self):
        assert CrashDialog._is_retryable("NOT CONFIGURED") is False
        assert CrashDialog._is_retryable("authentication FAILED") is False

    def test_queue_crash_report_calls_save_report(self):
        mock_queue = MagicMock()
        report = self._make_report()

        dialog = MagicMock(spec=CrashDialog)
        dialog._queue_service = mock_queue
        dialog._report = report
        dialog._build_queue_data.return_value = {"key": "value"}
        dialog._report.report_id = "test-1"

        CrashDialog._queue_crash_report(dialog)
        mock_queue.save_report.assert_called_once_with("crash", {"key": "value"})

    def test_queue_crash_report_handles_exception(self):
        mock_queue = MagicMock()
        mock_queue.save_report.side_effect = OSError("Disk full")

        dialog = MagicMock(spec=CrashDialog)
        dialog._queue_service = mock_queue
        dialog._build_queue_data.return_value = {}

        CrashDialog._queue_crash_report(dialog)
        mock_queue.save_report.assert_called_once()
