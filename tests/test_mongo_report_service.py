"""Tests for MongoReportService — RED phase."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.mongo_connection import MongoConnection
from services.support.mongo_report_service import (
    MongoReportService,
    _COLLECTION_MAP,
)
from services.support.reporting_interface import ReportType, SubmitResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_connection() -> MagicMock:
    conn = MagicMock(spec=MongoConnection)
    conn.is_available = True

    collections: dict[str, MagicMock] = {}

    def get_collection(name: str) -> MagicMock:
        if name not in collections:
            collections[name] = MagicMock()
        return collections[name]

    mock_db = MagicMock()
    mock_db.__getitem__.side_effect = get_collection
    conn.database = mock_db
    return conn


@pytest.fixture
def service(mock_connection: MagicMock) -> MongoReportService:
    return MongoReportService(connection=mock_connection)


@pytest.fixture
def unavailable_service() -> MongoReportService:
    conn = MagicMock(spec=MongoConnection)
    conn.is_available = False
    conn.database = None
    return MongoReportService(connection=conn)


_ALL_REPORT_TYPES = [
    ReportType.BUG,
    ReportType.FEATURE,
    ReportType.FEEDBACK,
    ReportType.CRASH,
]


class TestConstructor:
    def test_stores_connection(self, mock_connection: MagicMock):
        svc = MongoReportService(connection=mock_connection)
        assert svc._connection is mock_connection

    def test_indexes_not_created_on_init(self, mock_connection: MagicMock):
        svc = MongoReportService(connection=mock_connection)
        assert svc._indexes_created is False


class TestCollectionMap:
    def test_maps_all_report_types(self):
        assert set(_COLLECTION_MAP.keys()) == set(_ALL_REPORT_TYPES)

    def test_collection_names_are_strings(self):
        for name in _COLLECTION_MAP.values():
            assert isinstance(name, str)
            assert name


class TestSubmitBug:
    def test_returns_submit_result(self, service: MongoReportService):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        result = service.submit_bug(report)
        assert isinstance(result, SubmitResult)

    def test_success_when_mongodb_available(self, service: MongoReportService):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        result = service.submit_bug(report)
        assert result.success is True

    def test_inserts_into_bug_reports_collection(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        service.submit_bug(report)
        mock_connection.database["bug_reports"].insert_one.assert_called_once()

    def test_document_has_schema_version(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        service.submit_bug(report)
        doc = mock_connection.database["bug_reports"].insert_one.call_args[0][0]
        assert doc["schema_version"] == 1

    def test_document_has_submitted_at_timestamp(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        service.submit_bug(report)
        doc = mock_connection.database["bug_reports"].insert_one.call_args[0][0]
        assert "submitted_at" in doc

    def test_document_has_source_support_center(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        service.submit_bug(report)
        doc = mock_connection.database["bug_reports"].insert_one.call_args[0][0]
        assert doc["source"] == "support_center"

    def test_returns_error_when_unavailable(
        self, unavailable_service: MongoReportService
    ):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        result = unavailable_service.submit_bug(report)
        assert result.success is False

    def test_handles_insert_exception(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        mock_connection.database["bug_reports"].insert_one.side_effect = Exception(
            "connection lost"
        )
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        result = service.submit_bug(report)
        assert result.success is False
        assert result.error_message is not None


class TestSubmitFeature:
    def test_inserts_into_feature_requests(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        request = FeatureRequest(
            title="Feature",
            description="desc",
            use_case="uc",
        )
        service.submit_feature(request)
        mock_connection.database["feature_requests"].insert_one.assert_called_once()

    def test_success_when_mongodb_available(self, service: MongoReportService):
        request = FeatureRequest(
            title="Feature",
            description="desc",
            use_case="uc",
        )
        result = service.submit_feature(request)
        assert result.success is True

    def test_returns_error_when_unavailable(
        self, unavailable_service: MongoReportService
    ):
        request = FeatureRequest(
            title="Feature",
            description="desc",
            use_case="uc",
        )
        result = unavailable_service.submit_feature(request)
        assert result.success is False


class TestSubmitFeedback:
    def test_inserts_into_feedback(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        feedback = FeedbackReport(
            subject="FB",
            message="msg",
            category="praise",
        )
        service.submit_feedback(feedback)
        mock_connection.database["feedback"].insert_one.assert_called_once()

    def test_success_when_mongodb_available(self, service: MongoReportService):
        feedback = FeedbackReport(
            subject="FB",
            message="msg",
            category="praise",
        )
        result = service.submit_feedback(feedback)
        assert result.success is True

    def test_returns_error_when_unavailable(
        self, unavailable_service: MongoReportService
    ):
        feedback = FeedbackReport(
            subject="FB",
            message="msg",
            category="praise",
        )
        result = unavailable_service.submit_feedback(feedback)
        assert result.success is False


class TestSubmitReport:
    def test_crash_uses_crash_detector_source(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        service.submit_report(ReportType.CRASH, "Crash", "Stack trace...")
        doc = mock_connection.database["crash_reports"].insert_one.call_args[0][0]
        assert doc["source"] == "crash_detector"

    def test_bug_uses_support_center_source(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        service.submit_report(ReportType.BUG, "Bug", "Body")
        doc = mock_connection.database["bug_reports"].insert_one.call_args[0][0]
        assert doc["source"] == "support_center"

    def test_returns_report_id_on_success(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        mock_result = MagicMock()
        mock_result.inserted_id = MagicMock()
        mock_result.inserted_id.__str__.return_value = "abc123"
        mock_connection.database["crash_reports"].insert_one.return_value = mock_result

        result = service.submit_report(ReportType.CRASH, "Crash", "Body")
        assert result.success is True
        assert result.report_id == "abc123"

    def test_returns_error_when_unavailable(
        self, unavailable_service: MongoReportService
    ):
        result = unavailable_service.submit_report(
            ReportType.CRASH, "Crash", "Body"
        )
        assert result.success is False


class TestEnsureIndexes:
    def test_indexes_created_on_first_insert(
        self, service: MongoReportService, mock_connection: MagicMock
    ):
        assert service._indexes_created is False
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        service.submit_bug(report)
        assert service._indexes_created is True

    def test_indexes_created_once_only(
        self, service: MongoReportService
    ):
        report = BugReport(
            title="Bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="exp",
            actual_behavior="act",
        )
        service.submit_bug(report)
        assert service._indexes_created is True
        service.submit_bug(report)
        assert service._indexes_created is True


class TestContractCompliance:
    def test_is_instance_of_abstract(self):
        from services.support.reporting_interface import AbstractReportService

        conn = MagicMock(spec=MongoConnection)
        conn.is_available = True
        svc = MongoReportService(connection=conn)
        assert isinstance(svc, AbstractReportService)
