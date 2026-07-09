"""
Tests for T-232: Offline Queue Validation
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from services.support.queue_validator import (
    QueueValidator,
    ValidationResult,
    ValidationSummary,
    QUARANTINE_SUBDIR,
)
from services.support.report_queue_service import ReportQueueService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_bug_payload(title: str = "A bug") -> dict:
    return {
        "type": "bug",
        "created_at": "2026-01-01T00:00:00+00:00",
        "data": {
            "title": title,
            "description": "Detailed description",
            "steps_to_reproduce": "1. Do X",
            "expected_behavior": "Y",
            "actual_behavior": "Z",
            "severity": "low",
        },
    }


def _valid_feature_payload() -> dict:
    return {
        "type": "feature",
        "created_at": "2026-01-01T00:00:00+00:00",
        "data": {
            "title": "New feature",
            "description": "Detailed description",
            "use_case": "Users need this",
            "priority": "medium",
        },
    }


def _valid_feedback_payload() -> dict:
    return {
        "type": "feedback",
        "created_at": "2026-01-01T00:00:00+00:00",
        "data": {
            "subject": "Great app",
            "message": "Loving the UI",
            "category": "praise",
        },
    }


def _valid_crash_payload(report_id: str = "uuid-1234") -> dict:
    return {
        "type": "crash",
        "created_at": "2026-01-01T00:00:00+00:00",
        "data": {
            "report_id": report_id,
            "timestamp": "2026-01-01T00:00:00",
            "app_version": "1.0.0",
            "os_version": "Windows-10",
            "os_platform": "Windows",
            "active_sessions": [],
            "tracked_games": 0,
            "stack_trace": None,
            "recent_log_entries": [],
            "crash_type": "unhandled_exception",
            "was_tracking": False,
        },
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def storage(tmp_path: Path) -> Path:
    d = tmp_path / "queue"
    d.mkdir()
    return d


@pytest.fixture
def validator(storage: Path) -> QueueValidator:
    return QueueValidator(storage)


@pytest.fixture
def queue_svc(storage: Path) -> ReportQueueService:
    return ReportQueueService(storage_dir=storage)


# ---------------------------------------------------------------------------
# QueueValidator unit tests
# ---------------------------------------------------------------------------


class TestValidateFileValid:
    def test_valid_bug(self, validator: QueueValidator, storage: Path):
        f = _write_json(storage / "bug.json", _valid_bug_payload())
        r = validator.validate_file(f)
        assert r.valid
        assert r.report_type == "bug"

    def test_valid_feature(self, validator: QueueValidator, storage: Path):
        f = _write_json(storage / "feat.json", _valid_feature_payload())
        r = validator.validate_file(f)
        assert r.valid
        assert r.report_type == "feature"

    def test_valid_feedback(self, validator: QueueValidator, storage: Path):
        f = _write_json(storage / "fb.json", _valid_feedback_payload())
        r = validator.validate_file(f)
        assert r.valid
        assert r.report_type == "feedback"

    def test_valid_crash(self, validator: QueueValidator, storage: Path):
        f = _write_json(storage / "crash.json", _valid_crash_payload())
        r = validator.validate_file(f)
        assert r.valid
        assert r.report_type == "crash"

    def test_report_id_extracted_for_crash(self, validator: QueueValidator, storage: Path):
        f = _write_json(storage / "crash.json", _valid_crash_payload("my-uuid-999"))
        r = validator.validate_file(f)
        assert r.valid
        assert r.report_id == "my-uuid-999"

    def test_report_id_is_none_for_bug(self, validator: QueueValidator, storage: Path):
        f = _write_json(storage / "bug.json", _valid_bug_payload())
        r = validator.validate_file(f)
        assert r.valid
        assert r.report_id is None  # bugs have no report_id


class TestValidateFileInvalid:
    def test_invalid_json(self, validator: QueueValidator, storage: Path):
        f = storage / "bad.json"
        f.write_text("{not valid json", encoding="utf-8")
        r = validator.validate_file(f)
        assert not r.valid
        assert "JSON" in r.reason

    def test_empty_file(self, validator: QueueValidator, storage: Path):
        f = storage / "empty.json"
        f.write_bytes(b"")
        r = validator.validate_file(f)
        assert not r.valid
        assert "Empty" in r.reason

    def test_missing_type_field(self, validator: QueueValidator, storage: Path):
        payload = _valid_bug_payload()
        del payload["type"]
        f = _write_json(storage / "notype.json", payload)
        r = validator.validate_file(f)
        assert not r.valid
        assert "type" in r.reason.lower()

    def test_unknown_report_type(self, validator: QueueValidator, storage: Path):
        payload = _valid_bug_payload()
        payload["type"] = "unknown_type"
        f = _write_json(storage / "unk.json", payload)
        r = validator.validate_file(f)
        assert not r.valid
        assert "unknown_type" in r.reason

    def test_missing_required_field_bug(self, validator: QueueValidator, storage: Path):
        payload = _valid_bug_payload()
        del payload["data"]["description"]
        f = _write_json(storage / "miss.json", payload)
        r = validator.validate_file(f)
        assert not r.valid
        assert "description" in r.reason

    def test_missing_required_field_crash(self, validator: QueueValidator, storage: Path):
        payload = _valid_crash_payload()
        del payload["data"]["report_id"]
        f = _write_json(storage / "miss_crash.json", payload)
        r = validator.validate_file(f)
        assert not r.valid
        assert "report_id" in r.reason

    def test_missing_created_at(self, validator: QueueValidator, storage: Path):
        payload = _valid_bug_payload()
        del payload["created_at"]
        f = _write_json(storage / "notime.json", payload)
        r = validator.validate_file(f)
        assert not r.valid
        assert "created_at" in r.reason

    def test_data_not_a_dict(self, validator: QueueValidator, storage: Path):
        payload = _valid_bug_payload()
        payload["data"] = ["not", "a", "dict"]
        f = _write_json(storage / "baddata.json", payload)
        r = validator.validate_file(f)
        assert not r.valid

    def test_empty_title_string(self, validator: QueueValidator, storage: Path):
        payload = _valid_bug_payload()
        payload["data"]["title"] = "   "  # whitespace only
        f = _write_json(storage / "emptystr.json", payload)
        r = validator.validate_file(f)
        assert not r.valid
        assert "title" in r.reason

    def test_corrupted_utf8(self, validator: QueueValidator, storage: Path):
        f = storage / "badenc.json"
        f.write_bytes(b"\x80\x81\x82 not utf-8")
        r = validator.validate_file(f)
        assert not r.valid
        assert "UTF-8" in r.reason or "encoding" in r.reason.lower()

    def test_nonexistent_file(self, validator: QueueValidator, storage: Path):
        f = storage / "ghost.json"
        r = validator.validate_file(f)
        assert not r.valid
        assert "not exist" in r.reason.lower()


class TestQuarantineBehaviour:
    def test_invalid_file_quarantined(self, validator: QueueValidator, storage: Path):
        f = storage / "bad.json"
        f.write_text("not json", encoding="utf-8")

        summary = validator.validate_all([f])
        assert summary.invalid_count == 1
        assert len(summary.quarantined) == 1
        # Original file is gone
        assert not f.exists()
        # Quarantine copy exists
        q = validator.quarantine_dir / f.name
        assert q.exists()

    def test_valid_file_not_quarantined(self, validator: QueueValidator, storage: Path):
        f = _write_json(storage / "ok.json", _valid_bug_payload())
        summary = validator.validate_all([f])
        assert summary.valid_count == 1
        assert len(summary.quarantined) == 0
        # File remains in place
        assert f.exists()

    def test_quarantine_dir_created(self, validator: QueueValidator):
        assert validator.quarantine_dir.exists()
        assert validator.quarantine_dir.name == QUARANTINE_SUBDIR

    def test_quarantine_does_not_overwrite(self, validator: QueueValidator, storage: Path):
        # Place a file in quarantine already
        qdir = validator.quarantine_dir
        existing = qdir / "bad.json"
        existing.write_text("existing", encoding="utf-8")

        f = storage / "bad.json"
        f.write_text("not json", encoding="utf-8")

        summary = validator.validate_all([f])
        # Both should exist (with _dup suffix for the new one)
        assert existing.exists()
        assert len(summary.quarantined) == 1


class TestDuplicateDetection:
    def test_duplicate_crash_id_quarantined(self, validator: QueueValidator, storage: Path):
        # Write two crash reports with the same report_id
        f1 = _write_json(storage / "crash_a.json", _valid_crash_payload("same-id"))
        time.sleep(0.01)
        f2 = _write_json(storage / "crash_b.json", _valid_crash_payload("same-id"))

        summary = validator.validate_all(sorted([f1, f2]))
        # Oldest kept, newest quarantined
        assert summary.valid_count == 1
        assert summary.invalid_count == 1
        assert summary.valid[0].path == f1
        assert len(summary.quarantined) == 1
        assert not f2.exists()

    def test_unique_crash_ids_both_kept(self, validator: QueueValidator, storage: Path):
        f1 = _write_json(storage / "crash_a.json", _valid_crash_payload("id-001"))
        f2 = _write_json(storage / "crash_b.json", _valid_crash_payload("id-002"))

        summary = validator.validate_all(sorted([f1, f2]))
        assert summary.valid_count == 2
        assert len(summary.quarantined) == 0

    def test_no_report_id_not_deduplicated(self, validator: QueueValidator, storage: Path):
        # Bug reports have no report_id — two identical bugs should both be kept
        f1 = _write_json(storage / "bug_a.json", _valid_bug_payload("Bug A"))
        f2 = _write_json(storage / "bug_b.json", _valid_bug_payload("Bug A"))
        summary = validator.validate_all(sorted([f1, f2]))
        assert summary.valid_count == 2


class TestValidateAll:
    def test_mixed_valid_and_invalid(self, validator: QueueValidator, storage: Path):
        valid_f = _write_json(storage / "ok.json", _valid_bug_payload())
        bad_f = storage / "bad.json"
        bad_f.write_text("{{", encoding="utf-8")

        summary = validator.validate_all(sorted([valid_f, bad_f]))
        assert summary.valid_count == 1
        assert summary.invalid_count == 1
        assert summary.total == 2

    def test_empty_list(self, validator: QueueValidator):
        summary = validator.validate_all([])
        assert summary.valid_count == 0
        assert summary.invalid_count == 0

    def test_all_invalid_produces_empty_valid_list(self, validator: QueueValidator, storage: Path):
        for i in range(3):
            f = storage / f"bad_{i}.json"
            f.write_bytes(b"")
        files = sorted(storage.glob("*.json"))
        summary = validator.validate_all(files)
        assert summary.valid_count == 0
        assert summary.invalid_count == 3


# ---------------------------------------------------------------------------
# Integration: ReportQueueService + QueueValidator
# ---------------------------------------------------------------------------


class TestReportQueueServiceValidation:
    def test_invalid_json_quarantined_not_retried(self, queue_svc: ReportQueueService):
        """Malformed JSON file → quarantined, not retried, queue continues."""
        bad = queue_svc.get_storage_dir() / "corrupt.json"
        bad.write_text("{{bad json", encoding="utf-8")

        submitted = []
        result = queue_svc.process_queue(lambda t, d: submitted.append((t, d)) or True)

        assert result.attempted == 1
        assert result.failed == 1
        assert len(submitted) == 0
        assert queue_svc.count_quarantined() == 1

    def test_empty_file_quarantined(self, queue_svc: ReportQueueService):
        empty = queue_svc.get_storage_dir() / "empty.json"
        empty.write_bytes(b"")

        result = queue_svc.process_queue(lambda t, d: True)

        assert result.failed == 1
        assert queue_svc.count_quarantined() == 1

    def test_valid_report_processed_normally(self, queue_svc: ReportQueueService):
        queue_svc.save_report("bug", {
            "title": "X", "description": "D", "steps_to_reproduce": "S",
            "expected_behavior": "E", "actual_behavior": "A", "severity": "low",
        })
        result = queue_svc.process_queue(lambda t, d: True)
        assert result.succeeded == 1
        assert queue_svc.count_pending() == 0
        assert queue_svc.count_quarantined() == 0

    def test_mixed_valid_invalid_continues(self, queue_svc: ReportQueueService):
        """Bad file quarantined, then valid one submitted — processing continues."""
        bad = queue_svc.get_storage_dir() / "aaa_bad.json"
        bad.write_text("{broken", encoding="utf-8")

        queue_svc.save_report("bug", {
            "title": "OK", "description": "D", "steps_to_reproduce": "S",
            "expected_behavior": "E", "actual_behavior": "A", "severity": "low",
        })

        submitted = []
        result = queue_svc.process_queue(lambda t, d: submitted.append(t) or True)

        assert result.failed >= 1  # the bad file
        assert result.succeeded == 1  # the valid bug
        assert "bug" in submitted
        assert queue_svc.count_quarantined() == 1

    def test_unknown_type_quarantined(self, queue_svc: ReportQueueService):
        payload = {
            "type": "unknown_garbage",
            "created_at": "2026-01-01T00:00:00+00:00",
            "data": {"foo": "bar"},
        }
        f = queue_svc.get_storage_dir() / "unknown.json"
        f.write_text(json.dumps(payload), encoding="utf-8")

        result = queue_svc.process_queue(lambda t, d: True)
        assert result.failed == 1
        assert queue_svc.count_quarantined() == 1

    def test_duplicate_crash_quarantined(self, queue_svc: ReportQueueService):
        """Duplicate crash report_id: oldest kept, newer quarantined."""
        data = {
            "report_id": "dup-id",
            "timestamp": "2026-01-01T00:00:00",
            "app_version": "1.0.0",
            "os_version": "Win",
            "os_platform": "Windows",
            "active_sessions": [],
            "tracked_games": 0,
            "stack_trace": None,
            "recent_log_entries": [],
            "crash_type": "unhandled_exception",
            "was_tracking": False,
        }
        queue_svc.save_report("crash", data)
        time.sleep(0.01)
        queue_svc.save_report("crash", data)

        submitted = []
        result = queue_svc.process_queue(lambda t, d: submitted.append(t) or True)

        assert result.succeeded == 1
        assert queue_svc.count_quarantined() == 1

    def test_quarantine_dir_inside_storage(self, queue_svc: ReportQueueService):
        qdir = queue_svc.get_quarantine_dir()
        assert qdir.parent == queue_svc.get_storage_dir()
        assert qdir.name == QUARANTINE_SUBDIR

    def test_count_quarantined(self, queue_svc: ReportQueueService):
        assert queue_svc.count_quarantined() == 0
        bad = queue_svc.get_storage_dir() / "bad.json"
        bad.write_bytes(b"")
        queue_svc.process_queue(lambda t, d: True)
        assert queue_svc.count_quarantined() == 1

    def test_startup_invalid_does_not_crash(self, queue_svc: ReportQueueService):
        """Startup with corrupt queue should not raise — just quarantine and continue."""
        for i in range(5):
            f = queue_svc.get_storage_dir() / f"corrupt_{i}.json"
            f.write_text("NOT JSON", encoding="utf-8")

        # Should not raise
        result = queue_svc.process_queue(lambda t, d: True)
        assert result.failed == 5
        assert result.succeeded == 0
        assert queue_svc.count_quarantined() == 5
