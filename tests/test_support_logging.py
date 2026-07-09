"""Tests for improved logging in services/support/ (T-233).

Verifies:
  - Correct log levels (DEBUG / INFO / WARNING / ERROR)
  - Subsystem tags ([MongoDB], [Support], [Queue], etc.)
  - Correlation ID propagation through workflows
  - Parameterized logging usage
  - No sensitive data exposure
  - Expected events are logged at each stage
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.crash.diagnostic_service import CrashReport
from services.support.mongo_connection import (
    MongoConnection,
    MongoValidationStatus,
)
from services.support.mongo_report_service import MongoReportService
from services.support.queue_validator import QueueValidator
from services.support.report_queue_service import ReportQueueService
from services.support.reporting_interface import ReportType, SubmitResult
from services.support.support_service import SupportService, _cid


# =========================================================================
# Helpers
# =========================================================================

def _assert_tag(records: list[logging.LogRecord], tag: str) -> None:
    """Assert every log record contains the subsystem tag."""
    for rec in records:
        assert tag in rec.getMessage(), f"Missing tag {tag!r} in: {rec.getMessage()}"


def _assert_no_pattern(records: list[logging.LogRecord], pattern: str) -> None:
    """Assert no log record matches the given regex pattern."""
    for rec in records:
        assert not re.search(pattern, rec.getMessage()), (
            f"Unexpected pattern {pattern!r} in: {rec.getMessage()}"
        )


def _assert_level(records: list[logging.LogRecord], level: int) -> None:
    """Assert all records are at the given level."""
    for rec in records:
        assert rec.levelno == level, (
            f"Expected level {level}, got {rec.levelno} in: {rec.getMessage()}"
        )


# =========================================================================
# MongoConnection logging
# =========================================================================

class TestMongoConnectionLogging:
    """Verify MongoConnection validation logs."""

    def test_validation_started_info(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MongoConnection(uri="mongodb://localhost:27017/test", database_name="test")
        caplog.set_level(logging.DEBUG)
        with patch.object(conn, "_get_or_create_client") as mock_client:
            mock_client.side_effect = Exception("connection refused")
            conn.validate(force=True)
        assert any("[MongoDB]" in rec.getMessage() for rec in caplog.records)
        assert any("Validation started" in rec.getMessage() for rec in caplog.records)

    def test_validation_debug_level(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MongoConnection(uri="mongodb://localhost:27017/test", database_name="test")
        caplog.set_level(logging.DEBUG)
        with patch.object(conn, "_get_or_create_client") as mock_client:
            mock_client.side_effect = Exception("connection refused")
            conn.validate(force=True)
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_records) >= 1

    def test_validation_config_missing_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MongoConnection(uri="", database_name="")
        caplog.set_level(logging.WARNING)
        conn.validate(force=True)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ConfigurationMissing" in r.getMessage() for r in warnings)

    def test_validation_invalid_uri_error(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MongoConnection(uri="not-a-valid-uri", database_name="test")
        caplog.set_level(logging.ERROR)
        conn.validate(force=True)
        assert any("InvalidURI" in r.getMessage() for r in caplog.records)

    def test_validation_success_info(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MongoConnection(uri="mongodb://localhost:27017/test", database_name="test")
        caplog.set_level(logging.INFO)
        with (
            patch.object(conn, "_get_or_create_client") as mock_client,
            patch("services.support.mongo_connection.MongoClient") as mock_mongo,
        ):
            mock_instance = MagicMock()
            mock_instance.admin.command.return_value = {"ok": 1}
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_db.__getitem__.return_value = mock_collection
            mock_instance.__getitem__.return_value = mock_db
            mock_instance.get_default_database.return_value = mock_db
            mock_mongo.return_value = mock_instance
            conn.validate(force=True)
        infos = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("Validation completed (Connected)" in r.getMessage() for r in infos)

    def test_no_uri_exposed(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MongoConnection(uri="mongodb://user:secret@localhost:27017/test", database_name="test")
        caplog.set_level(logging.DEBUG)
        with patch.object(conn, "_get_or_create_client") as mock_client:
            mock_client.side_effect = Exception("connection refused")
            conn.validate(force=True)
        _assert_no_pattern(caplog.records, r"mongodb://")
        _assert_no_pattern(caplog.records, r"secret")

    def test_subsystem_tag_present(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MongoConnection(uri="", database_name="")
        caplog.set_level(logging.DEBUG)
        conn.validate(force=True)
        _assert_tag(caplog.records, "[MongoDB]")

    def test_parameterized_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify logs use %-formatting, not f-strings."""
        conn = MongoConnection(uri="", database_name="")
        caplog.set_level(logging.DEBUG)
        conn.validate(force=True)
        for rec in caplog.records:
            args = rec.args or ()
            if not args:
                continue
            # Check the raw format string (rec.msg) uses %-style placeholders
            fmt = rec.msg
            assert "%s" in fmt or "%d" in fmt or "%r" in fmt
            # Check no f-string interpolation: the raw format string (rec.msg)
            # should NOT contain the arg values (it would if f-strings were used)
            for arg in args:
                if isinstance(arg, str) and arg.strip():
                    assert arg not in rec.msg, f"f-string suspected: arg {arg!r} in format {rec.msg!r}"


# =========================================================================
# MongoReportService logging
# =========================================================================

class TestMongoReportServiceLogging:
    """Verify MongoReportService submission logs."""

    def test_insert_success_info(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MagicMock(spec=MongoConnection)
        type(conn).is_available = PropertyMock(return_value=True)
        conn.database = MagicMock()
        conn.database.__getitem__.return_value.insert_one.return_value = MagicMock(inserted_id="abc123")
        svc = MongoReportService(conn)
        caplog.set_level(logging.INFO)
        doc = {"type": "bug", "title": "Test", "description": "desc"}
        svc._insert(ReportType.BUG, doc)
        assert any("[MongoDB]" in r.getMessage() for r in caplog.records)
        assert any("Report submitted" in r.getMessage() for r in caplog.records)

    def test_insert_failure_error(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MagicMock(spec=MongoConnection)
        type(conn).is_available = PropertyMock(return_value=True)
        db = MagicMock()
        db.__getitem__.return_value.insert_one.side_effect = Exception("insert failed")
        conn.database = db
        svc = MongoReportService(conn)
        caplog.set_level(logging.ERROR)
        doc = {"type": "bug", "title": "Test", "description": "desc"}
        svc._insert(ReportType.BUG, doc)
        assert any("Insert failed" in r.getMessage() for r in caplog.records)

    def test_health_check_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MagicMock(spec=MongoConnection)
        type(conn).is_available = PropertyMock(return_value=False)
        svc = MongoReportService(conn)
        caplog.set_level(logging.DEBUG)
        doc = {"type": "bug", "title": "Test", "description": "desc"}
        svc._insert(ReportType.BUG, doc)
        assert any("Health check triggered" in r.getMessage() for r in caplog.records)

    def test_connection_unavailable_error(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MagicMock(spec=MongoConnection)
        type(conn).is_available = PropertyMock(return_value=False)
        svc = MongoReportService(conn)
        caplog.set_level(logging.ERROR)
        doc = {"type": "bug", "title": "Test", "description": "desc"}
        svc._insert(ReportType.BUG, doc)
        assert any("ConnectionUnavailable" in r.getMessage() for r in caplog.records)

    def test_index_failure_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MagicMock(spec=MongoConnection)
        type(conn).is_available = PropertyMock(return_value=True)
        db = MagicMock()
        col = MagicMock()
        col.create_indexes.side_effect = Exception("index error")
        db.__getitem__.return_value = col
        conn.database = db
        svc = MongoReportService(conn)
        caplog.set_level(logging.ERROR)
        svc._indexes_created = False
        doc = {"type": "bug", "title": "Test", "description": "desc"}
        svc._insert(ReportType.BUG, doc)
        assert any("Index creation failed" in r.getMessage() for r in caplog.records)

    def test_subsystem_tag(self, caplog: pytest.LogCaptureFixture) -> None:
        conn = MagicMock(spec=MongoConnection)
        type(conn).is_available = PropertyMock(return_value=True)
        conn.database = MagicMock()
        conn.database.__getitem__.return_value.insert_one.return_value = MagicMock(inserted_id="abc")
        svc = MongoReportService(conn)
        caplog.set_level(logging.INFO)
        doc = {"type": "bug", "title": "Test", "description": "desc"}
        svc._insert(ReportType.BUG, doc)
        _assert_tag(caplog.records, "[MongoDB]")


# =========================================================================
# SupportService logging
# =========================================================================

class TestSupportServiceLogging:
    """Verify SupportService logs include correlation IDs and subsystem tags."""

    def test_submission_started_info(self, caplog: pytest.LogCaptureFixture) -> None:
        svc = SupportService()
        caplog.set_level(logging.INFO)
        report = BugReport(title="Bug", description="desc", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        svc.submit_bug_report(report)
        recs = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("[Support]" in r.getMessage() for r in recs)
        assert any("Submission started" in r.getMessage() for r in recs)

    def test_correlation_id_in_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        svc = SupportService()
        caplog.set_level(logging.INFO)
        report = BugReport(title="Bug", description="desc", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        svc.submit_bug_report(report)
        pattern = re.compile(r"\[Support\]\[[0-9a-f]{8}\]")
        assert any(pattern.search(r.getMessage()) for r in caplog.records)

    def test_correlation_id_propagates_through_flow(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify the same correlation ID appears across related log lines."""
        mock_github = MagicMock()
        mock_github.submit_bug.return_value = SubmitResult(
            success=False, error_message="Connection refused"
        )
        svc = SupportService(github_service=mock_github)
        caplog.set_level(logging.INFO)
        report = BugReport(title="Bug", description="desc", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        svc.submit_bug_report(report)
        # Extract all correlation IDs from logs
        ids = set()
        for rec in caplog.records:
            m = re.search(r"\[([0-9a-f]{8})\]", rec.getMessage())
            if m:
                ids.add(m.group(1))
        assert len(ids) == 1, f"Expected one correlation ID across logs, got {ids}"

    def test_feature_request_correlation(self, caplog: pytest.LogCaptureFixture) -> None:
        svc = SupportService()
        caplog.set_level(logging.INFO)
        req = FeatureRequest(title="Feature", description="desc", use_case="uc")
        svc.submit_feature_request(req)
        pattern = re.compile(r"\[Support\]\[[0-9a-f]{8}\]")
        assert any(pattern.search(r.getMessage()) for r in caplog.records)
        assert any("Submission started (feature:" in r.getMessage() for r in caplog.records)

    def test_feedback_correlation(self, caplog: pytest.LogCaptureFixture) -> None:
        svc = SupportService()
        caplog.set_level(logging.INFO)
        fb = FeedbackReport(subject="Feedback", message="msg")
        svc.submit_feedback(fb)
        pattern = re.compile(r"\[Support\]\[[0-9a-f]{8}\]")
        assert any(pattern.search(r.getMessage()) for r in caplog.records)
        assert any("Submission started (feedback:" in r.getMessage() for r in caplog.records)

    def test_crash_report_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        svc = SupportService()
        caplog.set_level(logging.INFO)
        report = CrashReport(report_id="crash-1", timestamp="2024-01-01",
                             app_version="1.0", os_version="Win10",
                             os_platform="Windows", active_sessions=[],
                             tracked_games=0, stack_trace=None,
                             recent_log_entries=[], crash_type="unhandled",
                             was_tracking=False)
        svc.submit_crash_report(report)
        recs = [r.getMessage() for r in caplog.records]
        assert any("Crash submission started" in r for r in recs)
        assert any("[Support]" in r for r in recs)

    def test_queue_retry_skipped_offline(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_conn = MagicMock()
        type(mock_conn).is_available = PropertyMock(return_value=False)
        mock_backend = MagicMock()
        mock_backend.connection = mock_conn
        svc = SupportService(github_service=mock_backend, queue_service=MagicMock())
        caplog.set_level(logging.INFO)
        svc.process_queue()
        assert any("Queue retry skipped (offline)" in r.getMessage() for r in caplog.records)

    def test_queue_retry_no_queue_service(self, caplog: pytest.LogCaptureFixture) -> None:
        svc = SupportService()
        caplog.set_level(logging.INFO)
        svc.process_queue()
        assert any("no queue service" in r.getMessage().lower() for r in caplog.records)

    def test_backend_submit_success(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_github = MagicMock()
        mock_github.submit_bug.return_value = SubmitResult(
            success=True, issue_url="https://example.com/issue/1"
        )
        svc = SupportService(github_service=mock_github)
        caplog.set_level(logging.INFO)
        report = BugReport(title="Bug", description="desc", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        svc.submit_bug_report(report)
        assert any("Report submitted to backend" in r.getMessage() for r in caplog.records)

    def test_backend_submit_failure_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_github = MagicMock()
        mock_github.submit_bug.return_value = SubmitResult(
            success=False, error_message="Rate limited"
        )
        svc = SupportService(github_service=mock_github)
        caplog.set_level(logging.WARNING)
        report = BugReport(title="Bug", description="desc", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        svc.submit_bug_report(report)
        assert any("Backend submission failed" in r.getMessage() for r in caplog.records)

    def test_backend_exception_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_github = MagicMock()
        mock_github.submit_bug.side_effect = Exception("API failure")
        svc = SupportService(github_service=mock_github)
        caplog.set_level(logging.ERROR)
        report = BugReport(title="Bug", description="desc", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        svc.submit_bug_report(report)
        assert any("Backend submission error" in r.getMessage() for r in caplog.records)


# =========================================================================
# ReportQueueService logging
# =========================================================================

class TestReportQueueServiceLogging:
    """Verify queue processing logs."""

    def test_queue_init_log(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        caplog.set_level(logging.INFO)
        ReportQueueService(storage_dir=tmp_path / "queue")
        assert any("[Queue]" in r.getMessage() for r in caplog.records)
        assert any("Queue initialised" in r.getMessage() for r in caplog.records)

    def test_save_report_log(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        caplog.set_level(logging.INFO)
        queue.save_report("bug", {"title": "Test"})
        assert any("Report saved to queue" in r.getMessage() for r in caplog.records)

    def test_save_report_failure_log(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        caplog.set_level(logging.ERROR)
        with patch.object(Path, "write_text") as mock_write:
            mock_write.side_effect = OSError("disk full")
            with pytest.raises(OSError):
                queue.save_report("bug", {"title": "Test"})
        assert any("Queue save failed" in r.getMessage() for r in caplog.records)

    def test_process_queue_has_correlation_id(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        queue.save_report("bug", {"title": "Test", "description": "desc",
                                   "steps_to_reproduce": "s", "expected_behavior": "e",
                                   "actual_behavior": "a", "severity": "low"})
        caplog.set_level(logging.INFO)
        queue.process_queue(lambda t, d: True)
        pattern = re.compile(r"\[Queue\]\[[0-9a-f]{8}\]")
        assert any(pattern.search(r.getMessage()) for r in caplog.records)

    def test_queue_processing_started(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        queue.save_report("bug", {"title": "Test", "description": "desc",
                                   "steps_to_reproduce": "s", "expected_behavior": "e",
                                   "actual_behavior": "a", "severity": "low"})
        caplog.set_level(logging.INFO)
        queue.process_queue(lambda t, d: True)
        assert any("Queue processing started" in r.getMessage() for r in caplog.records)
        assert any("Queue processing completed" in r.getMessage() for r in caplog.records)

    def test_queue_retry_succeeded_log(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        queue.save_report("bug", {"title": "Test", "description": "desc",
                                   "steps_to_reproduce": "s", "expected_behavior": "e",
                                   "actual_behavior": "a", "severity": "low"})
        caplog.set_level(logging.INFO)
        queue.process_queue(lambda t, d: True)
        assert any("Queue retry succeeded" in r.getMessage() for r in caplog.records)

    def test_queue_retry_deferred_log(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        queue.save_report("bug", {"title": "Test", "description": "desc",
                                   "steps_to_reproduce": "s", "expected_behavior": "e",
                                   "actual_behavior": "a", "severity": "low"})
        caplog.set_level(logging.INFO)
        queue.process_queue(lambda t, d: False)
        assert any("Queue retry deferred" in r.getMessage() for r in caplog.records)

    def test_queue_permanent_discard_log(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        queue.save_report("bug", {"title": "Test", "description": "desc",
                                   "steps_to_reproduce": "s", "expected_behavior": "e",
                                   "actual_behavior": "a", "severity": "low"})
        caplog.set_level(logging.INFO)
        queue.process_queue(lambda t, d: "discard")
        assert any("Queue discard permanent" in r.getMessage() for r in caplog.records)

    def test_queue_empty_debug(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        caplog.set_level(logging.DEBUG)
        queue.process_queue(lambda t, d: True)
        assert any("Queue empty" in r.getMessage() for r in caplog.records)

    def test_concurrent_queue_skipped(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        queue._processing_lock.acquire()
        caplog.set_level(logging.WARNING)
        queue.process_queue(lambda t, d: True)
        queue._processing_lock.release()
        assert any("already in progress" in r.getMessage() for r in caplog.records)

    def test_clear_all_logged(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        caplog.set_level(logging.INFO)
        queue.clear_all()
        assert any("All queued reports cleared" in r.getMessage() for r in caplog.records)

    def test_clean_tmp_files_logged(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        (tmp_path / "queue").mkdir(parents=True, exist_ok=True)
        (tmp_path / "queue" / "orphan.tmp").write_text("data")
        caplog.set_level(logging.INFO)
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        assert any("orphaned" in r.getMessage() for r in caplog.records)


# =========================================================================
# QueueValidator logging
# =========================================================================

class TestQueueValidatorLogging:
    """Verify queue validation logs."""

    def test_validation_started(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        validator = QueueValidator(tmp_path)
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({
            "type": "bug", "data": {"title": "T", "description": "D",
                                     "steps_to_reproduce": "s", "expected_behavior": "e",
                                     "actual_behavior": "a"},
            "created_at": "2024-01-01T00:00:00",
        }))
        caplog.set_level(logging.DEBUG)
        validator.validate_all([json_file])
        assert any("[QueueValidator]" in r.getMessage() for r in caplog.records)
        assert any("Validation started" in r.getMessage() for r in caplog.records)

    def test_validation_completed(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        validator = QueueValidator(tmp_path)
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({
            "type": "bug", "data": {"title": "T", "description": "D",
                                     "steps_to_reproduce": "s", "expected_behavior": "e",
                                     "actual_behavior": "a"},
            "created_at": "2024-01-01T00:00:00",
        }))
        caplog.set_level(logging.INFO)
        validator.validate_all([json_file])
        assert any("Validation completed" in r.getMessage() for r in caplog.records)

    def test_file_validated_debug(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        validator = QueueValidator(tmp_path)
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({
            "type": "bug", "data": {"title": "T", "description": "D",
                                     "steps_to_reproduce": "s", "expected_behavior": "e",
                                     "actual_behavior": "a"},
            "created_at": "2024-01-01T00:00:00",
        }))
        caplog.set_level(logging.DEBUG)
        validator.validate_all([json_file])
        assert any("File validated" in r.getMessage() for r in caplog.records)

    def test_quarantine_logged(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        validator = QueueValidator(tmp_path)
        json_file = tmp_path / "bad.json"
        json_file.write_text("invalid json")
        caplog.set_level(logging.WARNING)
        validator.validate_all([json_file])
        assert any("File quarantined" in r.getMessage() for r in caplog.records)

    def test_duplicate_quarantine_logged(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        validator = QueueValidator(tmp_path)
        payload = {
            "type": "crash", "data": {"report_id": "dup1", "timestamp": "2024-01-01",
                                       "app_version": "1.0", "os_version": "Win",
                                       "os_platform": "Win", "active_sessions": [],
                                       "tracked_games": 0, "crash_type": "x",
                                       "was_tracking": False},
            "created_at": "2024-01-01T00:01:00",
        }
        f1 = tmp_path / "first.json"
        f1.write_text(json.dumps(payload))
        f2 = tmp_path / "second.json"
        f2.write_text(json.dumps(payload))
        caplog.set_level(logging.WARNING)
        validator.validate_all([f1, f2])
        assert any("Duplicate report quarantined" in r.getMessage() for r in caplog.records)


# =========================================================================
# GitHubIssueService logging
# =========================================================================

class TestGitHubIssueServiceLogging:
    """Verify GitHub issue submission logs."""

    def test_issue_created_info(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import github_issue_service as gis
        settings = MagicMock()
        settings.get_value.side_effect = ["token123", "owner", "repo"]
        svc = gis.GitHubIssueService(settings)
        caplog.set_level(logging.INFO)
        with patch.object(gis, "urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"html_url": "https://github.com/issue/1"}).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            svc.submit_report(gis.IssueType.BUG, "Title", "Body")
        recs = [r.getMessage() for r in caplog.records]
        assert any("Issue created" in r for r in recs)
        assert any("[GitHub]" in r for r in recs)

    def test_auth_failure_error(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import github_issue_service as gis
        settings = MagicMock()
        settings.get_value.side_effect = ["token123", "owner", "repo"]
        svc = gis.GitHubIssueService(settings)
        caplog.set_level(logging.ERROR)
        with patch.object(gis, "urlopen") as mock_urlopen:
            from urllib.error import HTTPError
            mock_urlopen.side_effect = HTTPError(
                "url", 401, "Unauthorized", {}, None
            )
            svc.submit_report(gis.IssueType.BUG, "Title", "Body")
        assert any("AuthenticationFailed" in r.getMessage() for r in caplog.records)

    def test_network_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import github_issue_service as gis
        settings = MagicMock()
        settings.get_value.side_effect = ["token123", "owner", "repo"]
        svc = gis.GitHubIssueService(settings)
        caplog.set_level(logging.ERROR)
        with patch.object(gis, "urlopen") as mock_urlopen:
            from urllib.error import URLError
            mock_urlopen.side_effect = URLError("connection refused")
            svc.submit_report(gis.IssueType.BUG, "Title", "Body")
        assert any("ConnectionError" in r.getMessage() for r in caplog.records)

    def test_config_incomplete_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import github_issue_service as gis
        settings = MagicMock()
        settings.get_value.side_effect = ["", "", ""]
        svc = gis.GitHubIssueService(settings)
        caplog.set_level(logging.WARNING)
        svc.submit_report(gis.IssueType.BUG, "Title", "Body")
        recs = [r.getMessage() for r in caplog.records]
        assert any("Config incomplete" in r for r in recs)
        assert any("[GitHub]" in r for r in recs)

    def test_no_token_exposed(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import github_issue_service as gis
        settings = MagicMock()
        settings.get_value.side_effect = ["supersecrettoken", "owner", "repo"]
        svc = gis.GitHubIssueService(settings)
        caplog.set_level(logging.DEBUG)
        with patch.object(gis, "urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("error")
            svc.submit_report(gis.IssueType.BUG, "Title", "Body")
        _assert_no_pattern(caplog.records, r"supersecrettoken")
        for rec in caplog.records:
            msg = rec.getMessage()
            assert "supersecrettoken" not in msg, f"Token leaked: {msg}"


# =========================================================================
# SupabaseReportService logging
# =========================================================================

class TestSupabaseReportServiceLogging:
    """Verify Supabase report submission logs."""

    def test_report_submitted_info(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import supabase_report_service as srs
        svc = srs.SupabaseReportService(supabase_url="https://test.supabase.co", anon_key="test-key")
        caplog.set_level(logging.INFO)
        with patch.object(srs, "urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            svc.submit_report(srs.ReportType.BUG, "Title", "Body")
        assert any("[Supabase]" in r.getMessage() for r in caplog.records)
        assert any("Report submitted" in r.getMessage() for r in caplog.records)

    def test_network_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import supabase_report_service as srs
        svc = srs.SupabaseReportService(supabase_url="https://test.supabase.co", anon_key="test-key")
        caplog.set_level(logging.ERROR)
        with patch.object(srs, "urlopen") as mock_urlopen:
            from urllib.error import URLError
            mock_urlopen.side_effect = URLError("connection refused")
            svc.submit_report(srs.ReportType.BUG, "Title", "Body")
        assert any("NetworkError" in r.getMessage() for r in caplog.records)

    def test_auth_failure_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import supabase_report_service as srs
        svc = srs.SupabaseReportService(supabase_url="https://test.supabase.co", anon_key="test-key")
        caplog.set_level(logging.ERROR)
        with patch.object(srs, "urlopen") as mock_urlopen:
            from urllib.error import HTTPError
            mock_urlopen.side_effect = HTTPError(
                "url", 401, "Unauthorized", {}, None
            )
            svc.submit_report(srs.ReportType.BUG, "Title", "Body")
        assert any("AuthFailed" in r.getMessage() for r in caplog.records)

    def test_conflict_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import supabase_report_service as srs
        svc = srs.SupabaseReportService(supabase_url="https://test.supabase.co", anon_key="test-key")
        caplog.set_level(logging.WARNING)
        with patch.object(srs, "urlopen") as mock_urlopen:
            from urllib.error import HTTPError
            mock_urlopen.side_effect = HTTPError(
                "url", 409, "Conflict", {}, None
            )
            svc.submit_report(srs.ReportType.BUG, "Title", "Body")
        assert any("Conflict" in r.getMessage() for r in caplog.records)
        assert any("[Supabase]" in r.getMessage() for r in caplog.records)

    def test_no_anon_key_exposed(self, caplog: pytest.LogCaptureFixture) -> None:
        from services.support import supabase_report_service as srs
        svc = srs.SupabaseReportService(supabase_url="https://test.supabase.co", anon_key="secret-anon-key-12345")
        caplog.set_level(logging.DEBUG)
        with patch.object(srs, "urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("error")
            svc.submit_report(srs.ReportType.BUG, "Title", "Body")
        for rec in caplog.records:
            msg = rec.getMessage()
            assert "secret-anon-key-12345" not in msg, f"Anon key leaked: {msg}"


# =========================================================================
# Correlation ID consistency
# =========================================================================

class TestCorrelationIDConsistency:
    """Verify correlation IDs are unique per operation and consistent within a flow."""

    def test_different_submissions_have_different_ids(self) -> None:
        ids = {_cid() for _ in range(20)}
        assert len(ids) == 20, "Correlation IDs should be unique"

    def test_correlation_id_is_8_hex_chars(self) -> None:
        cid = _cid()
        assert re.match(r"^[0-9a-f]{8}$", cid), f"Expected 8 hex chars, got {cid!r}"


# =========================================================================
# Log level enforcement
# =========================================================================

class TestLogLevelEnforcement:
    """Verify correct log levels per the T-233 spec."""

    def test_info_no_error_for_offline_conditions(self, caplog: pytest.LogCaptureFixture) -> None:
        """Offline/expected conditions should not log at ERROR."""
        svc = SupportService()
        caplog.set_level(logging.INFO)
        report = BugReport(title="Bug", description="desc", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        svc.submit_bug_report(report)
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 0, f"Expected no ERROR logs, got: {[r.getMessage() for r in errors]}"

    def test_queue_empty_is_debug_not_info(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        caplog.set_level(logging.DEBUG)
        queue.process_queue(lambda t, d: True)
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("Queue empty" in r.getMessage() for r in debug_records), "Should be DEBUG"
        assert not any("No pending" in r.getMessage() for r in info_records)
