"""Integration tests for MongoDB support backend.

Uses mongomock to simulate MongoDB without a real server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models.support.bug_report import BugReport
from services.support.mongo_connection import MongoConnection
from services.support.mongo_report_service import MongoReportService
from services.support.reporting_interface import ReportType, SubmitResult


# ---------------------------------------------------------------------------
# Integration: MongoConnection via mongomock
# ---------------------------------------------------------------------------


def _mongomock_client():
    """Create a mongomock MongoClient if available, else skip."""
    pytest.importorskip("mongomock")
    import mongomock
    return mongomock.MongoClient("mongodb://localhost:27017/test")


class TestMongoConnectionIntegration:
    def test_connection_with_mongomock(self):
        client = _mongomock_client()
        conn = MongoConnection(uri="mongodb://localhost:27017/test")
        with patch("services.support.mongo_connection.MongoClient", return_value=client):
            assert conn.health_check() is True
            assert conn.is_available is True
            db = conn.database
            assert db is not None
            db.bug_reports.insert_one({"title": "test"})
            assert db.bug_reports.count_documents({}) == 1

    def test_insert_and_retrieve(self):
        client = _mongomock_client()
        conn = MongoConnection(uri="mongodb://localhost:27017/test")
        with patch("services.support.mongo_connection.MongoClient", return_value=client):
            db = conn.database
            db.bug_reports.insert_one({"title": "Bug A", "severity": "high"})
            db.bug_reports.insert_one({"title": "Bug B", "severity": "low"})
            results = list(db.bug_reports.find().sort("title"))
            assert len(results) == 2
            assert results[0]["title"] == "Bug A"
            assert results[1]["title"] == "Bug B"


class TestMongoReportServiceIntegration:
    def _ready_service(self):
        """Create a service backed by mongomock, health-checked and ready."""
        client = _mongomock_client()
        conn = MongoConnection(uri="mongodb://localhost:27017/test")
        with patch("services.support.mongo_connection.MongoClient", return_value=client):
            conn.health_check()
            service = MongoReportService(connection=conn)
            return service, conn, client

    def test_submit_bug_through_service(self):
        service, conn, _ = self._ready_service()

        report = BugReport(
            title="Integration Bug",
            description="desc",
            steps_to_reproduce="1. Step",
            expected_behavior="Work",
            actual_behavior="Fail",
        )
        result = service.submit_bug(report)
        assert result.success is True
        assert result.report_id is not None

        doc = conn.database["bug_reports"].find_one({"title": "Integration Bug"})
        assert doc is not None
        assert doc["schema_version"] == 1
        assert doc["source"] == "support_center"

    def test_submit_crash_through_service(self):
        service, conn, _ = self._ready_service()

        result = service.submit_report(
            ReportType.CRASH, "App crashed", "Stack trace..."
        )
        assert result.success is True

        doc = conn.database["crash_reports"].find_one({"title": "App crashed"})
        assert doc is not None
        assert doc["source"] == "crash_detector"
        assert doc["schema_version"] == 1

    def test_submit_all_types(self):
        service, conn, _ = self._ready_service()

        report = BugReport(title="Bug", description="d", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        assert service.submit_bug(report).success is True

        from models.support.feature_request import FeatureRequest
        req = FeatureRequest(title="Feature", description="d", use_case="uc")
        assert service.submit_feature(req).success is True

        from models.support.feedback_report import FeedbackReport
        fb = FeedbackReport(subject="FB", message="m", category="praise")
        assert service.submit_feedback(fb).success is True

        assert service.submit_report(ReportType.CRASH, "Crash", "body").success is True

        assert conn.database["bug_reports"].count_documents({}) == 1
        assert conn.database["feature_requests"].count_documents({}) == 1
        assert conn.database["feedback"].count_documents({}) == 1
        assert conn.database["crash_reports"].count_documents({}) == 1

    def test_offline_mode_queues(self, tmp_path):
        """Simulate offline flow: MongoDB unavailable → queue → process."""
        from services.support.report_queue_service import ReportQueueService

        conn = MongoConnection(uri="")
        assert conn.is_available is False

        queue = ReportQueueService(storage_dir=tmp_path / "queue")
        assert queue.count_pending() == 0

        report = BugReport(title="Offline Bug", description="d", steps_to_reproduce="s",
                           expected_behavior="e", actual_behavior="a")
        queue.save_report("bug", {
            "title": report.title,
            "description": report.description,
            "steps_to_reproduce": report.steps_to_reproduce,
            "expected_behavior": report.expected_behavior,
            "actual_behavior": report.actual_behavior,
        })

        assert queue.count_pending() == 1

        client = _mongomock_client()
        conn_online = MongoConnection(uri="mongodb://localhost:27017/test")
        with patch("services.support.mongo_connection.MongoClient", return_value=client):
            conn_online.health_check()
            service = MongoReportService(connection=conn_online)

            processed = []
            def submit(report_type: str, data: dict) -> bool:
                if report_type == "bug":
                    from models.support.bug_report import BugReport
                    model = BugReport(**data)
                    result = service.submit_bug(model)
                    processed.append((report_type, result.success))
                    return result.success
                return False

            queue_result = queue.process_queue(submit)
            assert queue_result.succeeded == 1
            assert processed[0] == ("bug", True)
