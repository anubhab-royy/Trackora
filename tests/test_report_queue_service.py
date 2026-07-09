"""Tests for ReportQueueService."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.support.report_queue_service import (
    QueueProcessResult,
    ReportQueueService,
)
from trackora.core.paths import BASE_DIR


def _minimal_crash_data() -> dict:
    """Return a minimal valid CrashReport field dict."""
    return {
        "report_id": "test-uuid",
        "timestamp": "2024-01-01T00:00:00",
        "app_version": "1.0.0",
        "os_version": "Linux-6.0",
        "os_platform": "Linux",
        "active_sessions": [],
        "tracked_games": 0,
        "stack_trace": None,
        "recent_log_entries": [],
        "crash_type": "unhandled_exception",
        "was_tracking": False,
    }


def _full_bug(title: str = "Test Bug") -> dict:
    """Return a fully valid BugReport data dict."""
    return {
        "title": title,
        "description": "Detailed description",
        "steps_to_reproduce": "1. Do X",
        "expected_behavior": "Y happens",
        "actual_behavior": "Z happens",
        "severity": "low",
    }


def _full_feature(title: str = "New Feature") -> dict:
    """Return a fully valid FeatureRequest data dict."""
    return {
        "title": title,
        "description": "Detailed description",
        "use_case": "Users need this",
        "priority": "medium",
    }


def _full_feedback(subject: str = "Great app") -> dict:
    """Return a fully valid FeedbackReport data dict."""
    return {
        "subject": subject,
        "message": "Loving it",
        "category": "praise",
    }

@pytest.fixture
def queue(tmp_path: Path) -> ReportQueueService:
    return ReportQueueService(storage_dir=tmp_path / "pending_reports")






class TestSaveReport:
    def test_save_creates_json_file(self, queue: ReportQueueService):
        path = queue.save_report("bug", {"title": "Test Bug"})
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_stores_correct_content(self, queue: ReportQueueService):
        data = {"title": "Crash", "severity": "high"}
        path = queue.save_report("bug", data)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["type"] == "bug"
        assert payload["data"]["title"] == "Crash"
        assert payload["data"]["severity"] == "high"
        assert "created_at" in payload

    def test_save_uses_atomic_write(self, queue: ReportQueueService):
        path = queue.save_report("feature", {"title": "Feat"})
        tmp_files = list(queue.get_storage_dir().glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_save_no_duplicate_filenames(self, queue: ReportQueueService):
        p1 = queue.save_report("bug", {"title": "A"})
        p2 = queue.save_report("bug", {"title": "B"})
        assert p1.name != p2.name

    def test_save_crash_creates_json(self, queue: ReportQueueService):
        path = queue.save_report("crash", _minimal_crash_data())
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_crash_has_correct_type(self, queue: ReportQueueService):
        path = queue.save_report("crash", _minimal_crash_data())
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["type"] == "crash"


class TestCountPending:
    def test_empty_queue_returns_zero(self, queue: ReportQueueService):
        assert queue.count_pending() == 0

    def test_after_save_returns_one(self, queue: ReportQueueService):
        queue.save_report("bug", {"title": "Bug"})
        assert queue.count_pending() == 1

    def test_multiple_reports(self, queue: ReportQueueService):
        queue.save_report("bug", {"title": "A"})
        queue.save_report("feature", {"title": "B"})
        queue.save_report("feedback", {"subject": "C"})
        assert queue.count_pending() == 3


class TestProcessQueue:
    def test_empty_queue_returns_zero_result(self, queue: ReportQueueService):
        result = queue.process_queue(lambda t, d: True)
        assert isinstance(result, QueueProcessResult)
        assert result.attempted == 0
        assert result.succeeded == 0

    def test_process_submits_all_reports(self, queue: ReportQueueService):
        queue.save_report("bug", _full_bug("A"))
        queue.save_report("feature", _full_feature("B"))
        submitted = []

        def submit(report_type: str, data: dict) -> bool:
            submitted.append((report_type, data["title"]))
            return True

        result = queue.process_queue(submit)
        assert result.attempted == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert ("bug", "A") in submitted
        assert ("feature", "B") in submitted

    def test_successful_submission_deletes_file(
        self, queue: ReportQueueService
    ):
        queue.save_report("bug", _full_bug())
        queue.process_queue(lambda t, d: True)
        assert queue.count_pending() == 0

    def test_failed_submission_keeps_file(self, queue: ReportQueueService):
        queue.save_report("bug", _full_bug())
        queue.process_queue(lambda t, d: False)
        assert queue.count_pending() == 1

    def test_partial_failure_counts(self, queue: ReportQueueService):
        queue.save_report("bug", _full_bug())
        queue.save_report("feature", _full_feature())
        queue.save_report("feedback", _full_feedback())

        call_count = [0]

        def submit(report_type: str, data: dict) -> bool:
            call_count[0] += 1
            return call_count[0] != 2  # second one fails

        result = queue.process_queue(submit)
        assert result.attempted == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.errors) == 1

    def test_invalid_json_handled_gracefully(
        self, queue: ReportQueueService
    ):
        (queue.get_storage_dir() / "bad.json").write_text(
            "not valid json", encoding="utf-8"
        )
        result = queue.process_queue(lambda t, d: True)
        assert result.attempted == 1
        assert result.succeeded == 0
        assert result.failed == 1

    def test_unknown_type_handled_gracefully(self, queue: ReportQueueService):
        queue.save_report("unknown_type", {"title": "A"})
        result = queue.process_queue(lambda t, d: True)
        assert result.attempted == 1
        assert result.succeeded == 0
        assert result.failed == 1

    def test_submit_fn_receives_correct_arguments(
        self, queue: ReportQueueService
    ):
        queue.save_report("feedback", {"subject": "FB", "message": "msg"})
        results = []

        def submit(report_type: str, data: dict) -> bool:
            results.append((report_type, data))
            return True

        queue.process_queue(submit)
        assert len(results) == 1
        assert results[0][0] == "feedback"
        assert results[0][1]["subject"] == "FB"
        assert results[0][1]["message"] == "msg"

    def test_process_queue_calls_submit_for_crash(self, queue: ReportQueueService):
        queue.save_report("crash", _minimal_crash_data())
        submitted = []

        def submit(report_type: str, data: dict) -> bool:
            submitted.append((report_type, data))
            return True

        result = queue.process_queue(submit)
        assert result.attempted == 1
        assert result.succeeded == 1
        assert submitted[0][0] == "crash"
        assert submitted[0][1]["report_id"] == "test-uuid"

    def test_mixed_queue_processes_all_types(self, queue: ReportQueueService):
        queue.save_report("bug", _full_bug())
        queue.save_report("feature", _full_feature())
        queue.save_report("feedback", _full_feedback())
        queue.save_report("crash", _minimal_crash_data())
        submitted = []

        def submit(report_type: str, data: dict) -> bool:
            submitted.append(report_type)
            return True

        result = queue.process_queue(submit)
        assert result.attempted == 4
        assert result.succeeded == 4
        assert set(submitted) == {"bug", "feature", "feedback", "crash"}


class TestClearAll:
    def test_clear_removes_all_files(self, queue: ReportQueueService):
        queue.save_report("bug", {"title": "A"})
        queue.save_report("feature", {"title": "B"})
        queue.clear_all()
        assert queue.count_pending() == 0

    def test_clear_also_removes_tmp_files(self, queue: ReportQueueService):
        (queue.get_storage_dir() / "orphan.tmp").write_text(
            "data", encoding="utf-8"
        )
        queue.clear_all()
        tmp_files = list(queue.get_storage_dir().glob("*.tmp"))
        assert len(tmp_files) == 0


class TestModelReconstruction:
    def test_reconstruct_bug_report(self):
        data = {
            "title": "Bug",
            "description": "desc",
            "steps_to_reproduce": "steps",
            "expected_behavior": "exp",
            "actual_behavior": "act",
            "severity": "high",
        }
        model = ReportQueueService.reconstruct_model("bug", data)
        from models.support.bug_report import BugReport
        assert isinstance(model, BugReport)
        assert model.title == "Bug"
        assert model.severity == "high"

    def test_reconstruct_feature_request(self):
        data = {
            "title": "Feature",
            "description": "desc",
            "use_case": "uc",
            "priority": "high",
        }
        model = ReportQueueService.reconstruct_model("feature", data)
        from models.support.feature_request import FeatureRequest
        assert isinstance(model, FeatureRequest)
        assert model.title == "Feature"

    def test_reconstruct_feedback(self):
        data = {
            "subject": "FB",
            "message": "msg",
            "category": "praise",
            "contact_ok": True,
        }
        model = ReportQueueService.reconstruct_model("feedback", data)
        from models.support.feedback_report import FeedbackReport
        assert isinstance(model, FeedbackReport)
        assert model.subject == "FB"
        assert model.contact_ok is True

    def test_unknown_type_returns_none(self):
        assert ReportQueueService.reconstruct_model("unknown", {}) is None

    def test_invalid_data_returns_none(self):
        data = {"title": "Bug"}  # missing required fields
        result = ReportQueueService.reconstruct_model("bug", data)
        assert result is None

    def test_reconstruct_crash_report(self):
        data = _minimal_crash_data()
        model = ReportQueueService.reconstruct_model("crash", data)
        from services.crash.diagnostic_service import CrashReport
        assert isinstance(model, CrashReport)
        assert model.report_id == "test-uuid"
        assert model.crash_type == "unhandled_exception"
        assert model.was_tracking is False

    def test_reconstruct_crash_invalid_data_returns_none(self):
        data = {"report_id": "missing-required-fields"}
        result = ReportQueueService.reconstruct_model("crash", data)
        assert result is None


class TestGetGitHubMethod:
    def test_bug_method(self):
        assert ReportQueueService.get_github_method("bug") == "submit_bug"

    def test_feature_method(self):
        assert ReportQueueService.get_github_method("feature") == "submit_feature"

    def test_feedback_method(self):
        assert ReportQueueService.get_github_method("feedback") == "submit_feedback"

    def test_unknown_returns_none(self):
        assert ReportQueueService.get_github_method("unknown") is None

    def test_crash_method(self):
        assert ReportQueueService.get_github_method("crash") == "submit_crash"


class TestOrphanedTmpCleanup:
    def test_orphaned_tmp_cleaned_on_init(self, tmp_path: Path):
        storage = tmp_path / "pending_reports"
        storage.mkdir(parents=True)
        (storage / "orphan.tmp").write_text("data", encoding="utf-8")
        (storage / "valid.json").write_text(
            json.dumps({"type": "bug", "data": {}}), encoding="utf-8"
        )
        svc = ReportQueueService(storage_dir=storage)
        assert svc.count_pending() == 1  # only .json
        tmp_files = list(storage.glob("*.tmp"))
        assert len(tmp_files) == 0
