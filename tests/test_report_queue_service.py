"""Tests for ReportQueueService."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.support.report_queue_service import (
    QueueProcessResult,
    ReportQueueService,
    _default_storage_dir,
)


@pytest.fixture
def queue(tmp_path: Path) -> ReportQueueService:
    return ReportQueueService(storage_dir=tmp_path / "pending_reports")


class TestDefaultStorageDir:
    def test_uses_appdata_when_set(self):
        import os
        os.environ["APPDATA"] = "C:\\Users\\Test\\AppData\\Roaming"
        path = _default_storage_dir()
        assert "AppData\\Roaming\\Trackora\\pending_reports" in str(path)

    def test_falls_back_when_appdata_not_set(self):
        import os
        saved = os.environ.pop("APPDATA", None)
        try:
            path = _default_storage_dir()
            assert "Trackora" in str(path)
            assert "pending_reports" in str(path)
        finally:
            if saved is not None:
                os.environ["APPDATA"] = saved


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
        queue.save_report("bug", {"title": "A"})
        queue.save_report("feature", {"title": "B"})
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
        queue.save_report("bug", {"title": "A"})
        queue.process_queue(lambda t, d: True)
        assert queue.count_pending() == 0

    def test_failed_submission_keeps_file(self, queue: ReportQueueService):
        queue.save_report("bug", {"title": "A"})
        queue.process_queue(lambda t, d: False)
        assert queue.count_pending() == 1

    def test_partial_failure_counts(self, queue: ReportQueueService):
        queue.save_report("bug", {"title": "A"})
        queue.save_report("feature", {"title": "B"})
        queue.save_report("feedback", {"subject": "C"})

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


class TestGetGitHubMethod:
    def test_bug_method(self):
        assert ReportQueueService.get_github_method("bug") == "submit_bug"

    def test_feature_method(self):
        assert ReportQueueService.get_github_method("feature") == "submit_feature"

    def test_feedback_method(self):
        assert ReportQueueService.get_github_method("feedback") == "submit_feedback"

    def test_unknown_returns_none(self):
        assert ReportQueueService.get_github_method("unknown") is None


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
