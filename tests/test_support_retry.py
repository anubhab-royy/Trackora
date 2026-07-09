"""
Tests for Support Centre Retry Pipeline (T-231)
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from models.support.bug_report import BugReport
from services.support.report_queue_service import ReportQueueService, QueueProcessResult
from services.support.mongo_connection import MongoConnection, MongoValidationStatus
from services.support.reporting_interface import SubmitResult
from services.support.support_service import SupportService


def _valid_bug_data(title: str = "Test Title") -> dict:
    return {
        "title": title,
        "description": "Test Description",
        "steps_to_reproduce": "Steps",
        "expected_behavior": "Expected",
        "actual_behavior": "Actual",
        "severity": "low",
    }


@pytest.fixture
def temp_queue(tmp_path: Path) -> ReportQueueService:
    return ReportQueueService(storage_dir=tmp_path / "pending_reports")


def test_empty_queue(temp_queue):
    mock_submit = MagicMock(return_value=True)
    res = temp_queue.process_queue(mock_submit)
    assert res.attempted == 0
    assert res.succeeded == 0
    assert res.failed == 0


def test_chronological_ordering_preserved(temp_queue):
    # Save reports sequentially. Alpha sort on timestamp prefixes must yield chronological order.
    p1 = temp_queue.save_report("bug", _valid_bug_data("First"))
    time.sleep(0.01)
    p2 = temp_queue.save_report("bug", _valid_bug_data("Second"))
    time.sleep(0.01)
    p3 = temp_queue.save_report("bug", _valid_bug_data("Third"))
    
    files = sorted(temp_queue.get_storage_dir().glob("*.json"))
    assert files[0] == p1
    assert files[1] == p2
    assert files[2] == p3
    
    submitted_titles = []
    def submit_fn(report_type: str, data: dict) -> bool:
        submitted_titles.append(data["title"])
        return True
        
    temp_queue.process_queue(submit_fn)
    assert submitted_titles == ["First", "Second", "Third"]


def test_transient_failure_retained(temp_queue):
    temp_queue.save_report("bug", _valid_bug_data("Transient"))
    
    # submit_fn returns False (representing a transient/retryable failure)
    res = temp_queue.process_queue(lambda t, d: False)
    assert res.attempted == 1
    assert res.succeeded == 0
    assert res.failed == 1
    
    # Verify file is retained in queue
    assert temp_queue.count_pending() == 1


def test_permanent_failure_discarded(temp_queue):
    temp_queue.save_report("bug", _valid_bug_data("Permanent"))
    
    # submit_fn returns "discard" (representing a permanent failure)
    res = temp_queue.process_queue(lambda t, d: "discard")
    assert res.attempted == 1
    assert res.succeeded == 0
    assert res.failed == 1
    
    # Verify file is discarded (deleted) from queue
    assert temp_queue.count_pending() == 0


def test_invalid_json_discarded(temp_queue):
    # Manually write an invalid JSON file to the queue
    path = temp_queue.get_storage_dir() / "invalid.json"
    path.write_text("invalid json content", encoding="utf-8")
    assert temp_queue.count_pending() == 1
    
    res = temp_queue.process_queue(lambda t, d: True)
    assert res.attempted == 1
    assert res.succeeded == 0
    assert res.failed == 1
    
    # Verify the poison-pill file is discarded (deleted)
    assert temp_queue.count_pending() == 0


def test_duplicate_protection_prevent_overlap(temp_queue):
    # Lock the processing lock to simulate an active processing worker
    temp_queue._processing_lock.acquire()
    
    # Second attempt to process queue should skip and return empty result immediately
    res = temp_queue.process_queue(lambda t, d: True)
    assert res.attempted == 0
    assert res.succeeded == 0
    assert res.failed == 0
    
    temp_queue._processing_lock.release()


def test_worker_interruption(temp_queue):
    temp_queue.save_report("bug", _valid_bug_data("One"))
    temp_queue.save_report("bug", _valid_bug_data("Two"))
    
    submitted = []
    def submit_fn(report_type: str, data: dict) -> bool:
        submitted.append(data["title"])
        temp_queue.stop_processing()  # Trigger interruption immediately after first report
        return True
        
    res = temp_queue.process_queue(submit_fn)
    assert res.attempted == 1
    assert res.succeeded == 1
    assert len(submitted) == 1
    assert temp_queue.count_pending() == 1  # Second one remains in queue


def test_startup_retry_respects_validation_offline(temp_queue):
    # Create support service with mock connections
    mock_conn = MagicMock(spec=MongoConnection)
    mock_conn.is_available = False  # offline
    
    mock_backend = MagicMock()
    mock_backend.connection = mock_conn
    
    svc = SupportService(github_service=mock_backend, queue_service=temp_queue)
    temp_queue.save_report("bug", _valid_bug_data("A"))
    
    res = svc.process_queue()
    # Should skip queue processing
    assert res is None
    assert temp_queue.count_pending() == 1


def test_startup_retry_respects_validation_online(temp_queue):
    mock_conn = MagicMock(spec=MongoConnection)
    mock_conn.is_available = True  # online
    
    mock_backend = MagicMock()
    mock_backend.connection = mock_conn
    mock_backend.submit_bug.return_value = SubmitResult(success=True)
    
    svc = SupportService(github_service=mock_backend, queue_service=temp_queue)
    temp_queue.save_report("bug", _valid_bug_data("A"))
    
    res = svc.process_queue()
    assert res is not None
    assert res.attempted == 1
    assert res.succeeded == 1
    assert temp_queue.count_pending() == 0
