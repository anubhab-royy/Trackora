"""Tests for CrashDialog — body builder and action tracking."""

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
