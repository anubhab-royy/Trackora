"""
Integration tests for Trackora's Crash Reporting Pipeline.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from services.crash.diagnostic_service import CrashReport
from services.support.reporting_interface import AbstractReportService, ReportType, SubmitResult
from services.support.report_queue_service import ReportQueueService
from services.support.support_service import SupportService, SupportSubmitResult

class MockReportBackend(AbstractReportService):
    def __init__(self) -> None:
        self.submissions = []
        self.should_fail = False
        self.error_to_return = "Timeout"

    def submit_bug(self, report):
        return SubmitResult(success=True)

    def submit_feature(self, request):
        return SubmitResult(success=True)

    def submit_feedback(self, feedback):
        return SubmitResult(success=True)

    def submit_report(self, report_type: ReportType, title: str, body: str) -> SubmitResult:
        if self.should_fail:
            return SubmitResult(success=False, error_message=self.error_to_return)
        self.submissions.append((report_type, title, body))
        return SubmitResult(success=True, report_id="mongo-id-1234", issue_url="https://db/crash-1234")

class TestCrashReportingIntegration:
    def _make_report(self) -> CrashReport:
        return CrashReport(
            report_id="crash-5555",
            timestamp="2026-07-06T19:00:00Z",
            app_version="2.0.1",
            os_version="Windows 11",
            os_platform="Windows",
            active_sessions=[{"game_id": 100, "game_name": "Portal 2", "process_id": 1234}],
            tracked_games=10,
            stack_trace="Traceback: NullPointerError",
            recent_log_entries=["Initiating startup", "Error encountered"],
            crash_type="unhandled_exception",
            was_tracking=True,
        )

    def test_pipeline_submits_to_backend_successfully(self):
        backend = MockReportBackend()
        queue = MagicMock(spec=ReportQueueService())
        support = SupportService(github_service=backend, queue_service=queue)

        report = self._make_report()
        result = support.submit_crash_report(report)

        assert result.github_success is True
        assert result.github_url == "https://db/crash-1234"
        assert len(backend.submissions) == 1
        
        # Verify correct formatting of body and title
        report_type, title, body = backend.submissions[0]
        assert report_type == ReportType.CRASH
        assert "unhandled_exception" in title
        assert "2026-07-06T19:00:00Z" in title
        assert "NullPointerError" in body
        assert "Portal 2" in body

    def test_pipeline_queues_on_transient_failure_and_retries_successfully(self):
        backend = MockReportBackend()
        backend.should_fail = True

        queue = ReportQueueService()  # Use actual queue service for file writes
        support = SupportService(github_service=backend, queue_service=queue)

        report = self._make_report()
        
        # 1. Submit with transient error
        with patch.object(queue, "save_report", wraps=queue.save_report) as mock_save:
            result = support.submit_crash_report(report)
            assert result.github_success is False
            assert result.queued is True
            mock_save.assert_called_once()

        # 2. Re-enable backend
        backend.should_fail = False
        assert len(backend.submissions) == 0

        # 3. Process/Retry Queue (should deserialize CrashReport and call submit_crash successfully)
        process_result = support.process_queue()
        assert process_result is not None
        
        # Verify retry successfully forwarded to backend
        assert len(backend.submissions) == 1
        report_type, title, body = backend.submissions[0]
        assert report_type == ReportType.CRASH
        assert "NullPointerError" in body
