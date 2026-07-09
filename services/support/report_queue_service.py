"""
ReportQueueService — offline report queue for Trackora.

Saves support reports as JSON files when MongoDB is unreachable.
Processes the queue on application startup and background retries.

T-232: All queue files are validated by QueueValidator before entering the
retry pipeline.  Corrupt / invalid files are moved to a quarantine directory
(pending_reports/invalid/) for developer inspection rather than silently
discarded or retried indefinitely.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.crash.diagnostic_service import CrashReport
from services.support.queue_validator import QueueValidator
from trackora.core.paths import BASE_DIR

logger = logging.getLogger(__name__)

SUBSYSTEM = "Queue"

_REPORT_TYPE_MAP: dict[str, type] = {
    "bug": BugReport,
    "feature": FeatureRequest,
    "feedback": FeedbackReport,
    "crash": CrashReport,
}

_GITHUB_METHOD_MAP: dict[str, str] = {
    "bug": "submit_bug",
    "feature": "submit_feature",
    "feedback": "submit_feedback",
    "crash": "submit_crash",
}


def _default_storage_dir() -> Path:
    """Return BASE_DIR/pending_reports/ via trackora.core.paths."""
    return BASE_DIR / "pending_reports"


@dataclass
class QueueProcessResult:
    """Result of processing the offline report queue."""
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class ReportQueueService:
    """Persistent queue for support reports that failed to submit online.

    Args:
        storage_dir: Custom storage directory (for testing).
                     Defaults to %APPDATA%/Trackora/pending_reports/.
    """

    def __init__(
        self, storage_dir: str | Path | None = None
    ) -> None:
        self._storage_dir = Path(storage_dir) if storage_dir else _default_storage_dir()
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._clean_orphaned_tmp_files()

        # T-231: Concurrency and interruption controls
        self._processing_lock = threading.Lock()
        self._interrupted = False

        # T-232: Validator for queue integrity checking
        self._validator = QueueValidator(self._storage_dir)

        logger.info(
            "[%s] Queue initialised (storage=%s)",
            SUBSYSTEM, self._storage_dir,
        )

    def stop_processing(self) -> None:
        """Interrupts currently running process_queue loop."""
        self._interrupted = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_report(
        self, report_type: str, data: dict
    ) -> Path:
        """Save a report to the queue atomically.

        Args:
            report_type: One of 'bug', 'feature', 'feedback', 'crash'.
            data: Dictionary of model fields.

        Returns:
            Path to the saved JSON file.
        """
        # Prefix the filename with a high-resolution UTC timestamp to guarantee chronological sorting order
        timestamp_prefix = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp_prefix}_{uuid4()}.json"
        tmp_path = self._storage_dir / f"{filename}.tmp"
        final_path = self._storage_dir / filename

        payload = {
            "type": report_type,
            "data": data,
            "created_at": datetime.now(UTC).isoformat(),
        }

        try:
            tmp_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(final_path)
            logger.info(
                "[%s] Report saved to queue (%s, type=%s)", SUBSYSTEM, final_path.name, report_type
            )
            return final_path
        except OSError as exc:
            logger.error("[%s] Queue save failed (%s)", SUBSYSTEM, exc)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def process_queue(
        self, submit_fn: Callable[[str, dict], bool | str]
    ) -> QueueProcessResult:
        """Process all pending reports in the queue.

        T-232 validation gate:
            1. All queue files are validated by QueueValidator.
            2. Invalid files are quarantined (moved to invalid/ subdir).
            3. Only validated files reach the retry pipeline.

        For each valid file:
            - Call submit_fn(report_type, data).
            - True  → delete (submitted successfully).
            - False → retain (transient failure, retry later).
            - 'discard' → delete (permanent failure).
        """
        correlation_id = uuid4().hex[:8]

        # Ensure single concurrent retry worker only
        acquired = self._processing_lock.acquire(blocking=False)
        if not acquired:
            logger.warning("[%s][%s] Queue processing already in progress. Skipping.", SUBSYSTEM, correlation_id)
            return QueueProcessResult()

        self._interrupted = False
        result = QueueProcessResult()

        # Glob files and sort alphabetically (chronological timestamp prefix ensures chronological order)
        # Exclude the invalid/ quarantine subdirectory
        json_files = sorted(
            f for f in self._storage_dir.glob("*.json")
            if f.parent == self._storage_dir
        )

        if not json_files:
            logger.debug("[%s][%s] Queue empty, nothing to process", SUBSYSTEM, correlation_id)
            self._processing_lock.release()
            return result

        logger.info("[%s][%s] Queue processing started (%d file(s))", SUBSYSTEM, correlation_id, len(json_files))

        try:
            # ── T-232: Validate all files before retry pipeline ──────────
            summary = self._validator.validate_all(json_files)

            # Account for quarantined files in result counters
            for inv in summary.invalid:
                result.attempted += 1
                result.failed += 1
                result.errors.append(f"{inv.path.name}: {inv.reason}")

            logger.info(
                "[%s][%s] Processing %d valid report(s) (skipped %d invalid)",
                SUBSYSTEM, correlation_id, summary.valid_count, summary.invalid_count,
            )

            # ── Retry pipeline: only valid reports reach here ─────────────
            for vr in summary.valid:
                if self._interrupted:
                    logger.info("[%s][%s] Queue processing interrupted", SUBSYSTEM, correlation_id)
                    break

                filepath = vr.path
                report_type = vr.report_type
                data = vr.data
                result.attempted += 1

                try:
                    outcome = submit_fn(report_type, data)

                    if outcome is True or outcome == "success":
                        filepath.unlink(missing_ok=True)
                        result.succeeded += 1
                        logger.info("[%s][%s] Queue retry succeeded (%s)", SUBSYSTEM, correlation_id, filepath.name)
                    elif outcome == "discard" or outcome == "permanent":
                        filepath.unlink(missing_ok=True)
                        result.failed += 1
                        result.errors.append(f"{filepath.name}: permanent failure")
                        logger.info("[%s][%s] Queue discard permanent (%s)", SUBSYSTEM, correlation_id, filepath.name)
                    else:
                        # Retain in queue for retry later
                        result.failed += 1
                        result.errors.append(f"{filepath.name}: retryable failure")
                        logger.info("[%s][%s] Queue retry deferred (%s)", SUBSYSTEM, correlation_id, filepath.name)

                except OSError as exc:
                    logger.error("[%s][%s] Queue processing error (%s: %s)", SUBSYSTEM, correlation_id, filepath.name, exc)
                    result.failed += 1
                    result.errors.append(f"{filepath.name}: {exc}")

            logger.info("[%s][%s] Queue processing completed (%d succeeded, %d failed)", SUBSYSTEM, correlation_id, result.succeeded, result.failed)
        finally:
            self._processing_lock.release()

        return result

    def count_pending(self) -> int:
        """Return the number of valid JSON files in the main queue (excludes invalid/)."""
        return len([
            f for f in self._storage_dir.glob("*.json")
            if f.parent == self._storage_dir
        ])

    def count_quarantined(self) -> int:
        """Return the number of files currently in the quarantine directory."""
        return len(list(self._validator.quarantine_dir.glob("*")))

    def get_quarantine_dir(self) -> Path:
        """Return the quarantine directory path."""
        return self._validator.quarantine_dir

    def clear_all(self) -> None:
        """Remove all queued reports (for testing / manual purge)."""
        for f in self._storage_dir.glob("*.json"):
            if f.parent == self._storage_dir:
                f.unlink()
        self._clean_orphaned_tmp_files()
        logger.info("[%s] All queued reports cleared", SUBSYSTEM)

    def get_storage_dir(self) -> Path:
        """Return the storage directory path."""
        return self._storage_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clean_orphaned_tmp_files(self) -> None:
        """Remove any .tmp files left from crashes during atomic writes."""
        cleaned = 0
        for f in self._storage_dir.glob("*.tmp"):
            try:
                f.unlink()
                cleaned += 1
            except OSError:
                pass
        if cleaned:
            logger.info("[%s] Cleaned %d orphaned .tmp file(s)", SUBSYSTEM, cleaned)

    # ------------------------------------------------------------------
    # Static helpers for model reconstruction
    # ------------------------------------------------------------------

    @staticmethod
    def reconstruct_model(
        report_type: str, data: dict
    ) -> BugReport | FeatureRequest | FeedbackReport | CrashReport | None:
        """Reconstruct a domain model from queued JSON data."""
        cls = _REPORT_TYPE_MAP.get(report_type)
        if cls is None:
            return None
        try:
            return cls(**data)
        except (TypeError, ValueError) as exc:
            logger.error(
                "[%s] Model reconstruction failed (%s): %s", SUBSYSTEM, report_type, exc
            )
            return None

    @staticmethod
    def get_github_method(report_type: str) -> str | None:
        """Return the GitHubIssueService method name for a report type."""
        return _GITHUB_METHOD_MAP.get(report_type)
