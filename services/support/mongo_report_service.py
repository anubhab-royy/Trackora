"""MongoReportService — MongoDB backend for report submissions.

Submits bug reports, feature requests, feedback, and crash reports
to MongoDB collections via MongoConnection.

Implements *AbstractReportService* from *reporting_interface*.
"""

from __future__ import annotations

import logging
import platform
import traceback
from datetime import UTC, datetime
from typing import Any

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from pymongo import IndexModel, ASCENDING
from services.support.mongo_connection import MongoConnection
from services.support.reporting_interface import (
    AbstractReportService,
    ReportType,
    SubmitResult,
)
from trackora import __version__

logger = logging.getLogger(__name__)

SUBSYSTEM = "MongoDB"

_COLLECTION_MAP: dict[ReportType, str] = {
    ReportType.BUG: "bug_reports",
    ReportType.FEATURE: "feature_requests",
    ReportType.FEEDBACK: "feedback",
    ReportType.CRASH: "crash_reports",
}

_SOURCE_MAP: dict[ReportType, str] = {
    ReportType.BUG: "support_center",
    ReportType.FEATURE: "support_center",
    ReportType.FEEDBACK: "support_center",
    ReportType.CRASH: "crash_detector",
}


class MongoReportService(AbstractReportService):
    """Submits reports to MongoDB collections.

    Args:
        connection: A ``MongoConnection`` instance.
    """

    def __init__(self, connection: MongoConnection) -> None:
        self._connection = connection
        self._indexes_created = False

    # ------------------------------------------------------------------
    # AbstractReportService — typed convenience methods
    # ------------------------------------------------------------------

    def submit_bug(self, report: BugReport) -> SubmitResult:
        doc = {
            "type": ReportType.BUG.value,
            "title": report.title,
            "description": report.description,
            "payload": {
                "steps_to_reproduce": report.steps_to_reproduce,
                "expected_behavior": report.expected_behavior,
                "actual_behavior": report.actual_behavior,
                "severity": report.severity,
            },
        }
        return self._insert(ReportType.BUG, doc)

    def submit_feature(self, request: FeatureRequest) -> SubmitResult:
        doc = {
            "type": ReportType.FEATURE.value,
            "title": request.title,
            "description": request.description,
            "payload": {
                "use_case": request.use_case,
                "priority": request.priority,
            },
        }
        return self._insert(ReportType.FEATURE, doc)

    def submit_feedback(self, feedback: FeedbackReport) -> SubmitResult:
        doc = {
            "type": ReportType.FEEDBACK.value,
            "title": feedback.subject,
            "description": feedback.message,
            "payload": {
                "category": feedback.category,
                "contact_ok": feedback.contact_ok,
            },
        }
        return self._insert(ReportType.FEEDBACK, doc)

    def submit_report(
        self, report_type: ReportType, title: str, body: str
    ) -> SubmitResult:
        doc = {
            "type": report_type.value,
            "title": title,
            "description": body,
            "payload": {},
        }
        return self._insert(report_type, doc)

    # ------------------------------------------------------------------
    # Internal: single write path
    # ------------------------------------------------------------------

    def _insert(self, report_type: ReportType, doc: dict[str, Any]) -> SubmitResult:
        if not self._connection.is_available:
            logger.debug("[%s] Health check triggered", SUBSYSTEM)
            self._connection.health_check()
            if not self._connection.is_available:
                status = getattr(self._connection, "validation_status", None)
                logger.error("[%s] Submit failed (ConnectionUnavailable: %s)", SUBSYSTEM, status.value if status else "Unknown")
                msg = f"MongoDB connection failed: {status.value if status else 'Unknown Error'}."
                return SubmitResult(
                    success=False,
                    error_message=msg,
                )
        
        try:
            db = self._connection.database
            if db is None:
                status = getattr(self._connection, "validation_status", None)
                logger.error("[%s] Submit failed (DatabaseNotConfigured: %s)", SUBSYSTEM, status.value if status else "Configuration Missing")
                msg = f"MongoDB not configured: {status.value if status else 'Configuration Missing'}."
                return SubmitResult(
                    success=False,
                    error_message=msg,
                )
        except Exception as e:
            logger.error(
                "[%s] Submit failed (%s: %s)\n%s",
                SUBSYSTEM, e.__class__.__name__, e, traceback.format_exc(),
            )
            return SubmitResult(
                success=False,
                error_message=f"MongoDB connection failed: {e}",
            )

        try:
            self._ensure_indexes()
        except Exception as e:
            logger.error(
                "[%s] Index creation failed (%s: %s)\n%s",
                SUBSYSTEM, e.__class__.__name__, e, traceback.format_exc(),
            )

        doc["schema_version"] = 1
        doc["app_version"] = __version__
        doc["os"] = platform.platform()
        doc["submitted_at"] = datetime.now(UTC).isoformat()
        doc["source"] = _SOURCE_MAP[report_type]

        collection_name = _COLLECTION_MAP[report_type]
        try:
            result = db[collection_name].insert_one(doc)
            report_id = str(result.inserted_id)
            logger.info(
                "[%s] Report submitted (type=%s id=%s)",
                SUBSYSTEM, report_type.value, report_id,
            )
            return SubmitResult(success=True, report_id=report_id)
        except Exception as exc:
            logger.error(
                "[%s] Insert failed (%s: %s)\n%s",
                SUBSYSTEM, exc.__class__.__name__, exc, traceback.format_exc(),
            )
            return SubmitResult(
                success=False,
                error_message=f"MongoDB insert failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _ensure_indexes(self) -> None:
        if self._indexes_created:
            return
        db = self._connection.database
        collection_names = set(_COLLECTION_MAP.values())
        indexes = [
            IndexModel([("submitted_at", ASCENDING)]),
            IndexModel([("source", ASCENDING)]),
            IndexModel([("type", ASCENDING)]),
        ]
        for name in collection_names:
            try:
                db[name].create_indexes(indexes)
            except Exception:
                logger.exception("[%s] Index creation failed on %s", SUBSYSTEM, name)
        self._indexes_created = True
