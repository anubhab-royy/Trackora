"""
ReportQueueService — offline report queue for Trackora.

Saves support reports as JSON files when GitHub is unreachable.
Processes the queue on application startup.

Storage path: %APPDATA%/Trackora/pending_reports/ (Windows)
Fallback:     ~/.local/share/Trackora/pending_reports/  (other platforms)

Guarantees:
- Atomic writes (write to .tmp, then rename to .json)
- Crash-safe (partial .tmp files are cleaned on scan)
- No duplication (UUID-based filenames)
- Retry support (failed reports stay in queue)
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from trackora.core.paths import BASE_DIR

logger = logging.getLogger(__name__)

_REPORT_TYPE_MAP: dict[str, type] = {
    "bug": BugReport,
    "feature": FeatureRequest,
    "feedback": FeedbackReport,
}

_GITHUB_METHOD_MAP: dict[str, str] = {
    "bug": "submit_bug",
    "feature": "submit_feature",
    "feedback": "submit_feedback",
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
        logger.info(
            "ReportQueueService initialised (storage=%s).",
            self._storage_dir,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_report(
        self, report_type: str, data: dict
    ) -> Path:
        """Save a report to the queue atomically.

        Args:
            report_type: One of 'bug', 'feature', 'feedback'.
            data: Dictionary of model fields.

        Returns:
            Path to the saved JSON file.
        """
        filename = f"{uuid4()}.json"
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
                "Report queued: %s (%s)", final_path.name, report_type
            )
            return final_path
        except OSError as exc:
            logger.error("Failed to queue report: %s", exc)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def process_queue(
        self, submit_fn: Callable[[str, dict], bool]
    ) -> QueueProcessResult:
        """Process all pending reports in the queue.

        For each JSON file:
        1. Load and validate the payload.
        2. Call submit_fn(report_type, data).
        3. If submit_fn returns True, delete the file.
        4. If submit_fn returns False, keep the file for next retry.

        Args:
            submit_fn: Callable accepting (report_type, data_dict)
                       and returning True on success.

        Returns:
            QueueProcessResult with counts and errors.
        """
        result = QueueProcessResult()
        json_files = sorted(self._storage_dir.glob("*.json"))

        if not json_files:
            logger.info("No pending reports to process.")
            return result

        logger.info(
            "Processing %d pending report(s)...", len(json_files)
        )

        for filepath in json_files:
            result.attempted += 1
            try:
                payload = json.loads(filepath.read_text(encoding="utf-8"))
                report_type = payload.get("type", "")
                data = payload.get("data", {})

                if report_type not in _REPORT_TYPE_MAP:
                    logger.warning(
                        "Unknown report type in %s: %r",
                        filepath.name,
                        report_type,
                    )
                    result.failed += 1
                    result.errors.append(
                        f"{filepath.name}: unknown type '{report_type}'"
                    )
                    continue

                success = submit_fn(report_type, data)
                if success:
                    filepath.unlink()
                    result.succeeded += 1
                    logger.info(
                        "Queued report submitted and removed: %s",
                        filepath.name,
                    )
                else:
                    result.failed += 1
                    error_msg = f"{filepath.name}: submission failed (will retry)"
                    result.errors.append(error_msg)
                    logger.warning(
                        "Queued report submission failed, keeping: %s",
                        filepath.name,
                    )
            except json.JSONDecodeError as exc:
                logger.error(
                    "Invalid JSON in %s: %s", filepath.name, exc
                )
                result.failed += 1
                result.errors.append(f"{filepath.name}: invalid JSON")
            except OSError as exc:
                logger.error(
                    "Error reading %s: %s", filepath.name, exc
                )
                result.failed += 1
                result.errors.append(f"{filepath.name}: {exc}")

        logger.info(
            "Queue processing complete: %d attempted, "
            "%d succeeded, %d failed.",
            result.attempted,
            result.succeeded,
            result.failed,
        )
        return result

    def count_pending(self) -> int:
        """Return the number of JSON files currently in the queue."""
        return len(list(self._storage_dir.glob("*.json")))

    def clear_all(self) -> None:
        """Remove all queued reports (for testing / manual purge)."""
        for f in self._storage_dir.glob("*.json"):
            f.unlink()
        self._clean_orphaned_tmp_files()
        logger.info("All queued reports cleared.")

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
            logger.info("Cleaned %d orphaned .tmp file(s).", cleaned)

    # ------------------------------------------------------------------
    # Static helpers for model reconstruction
    # ------------------------------------------------------------------

    @staticmethod
    def reconstruct_model(
        report_type: str, data: dict
    ) -> BugReport | FeatureRequest | FeedbackReport | None:
        """Reconstruct a domain model from queued JSON data."""
        cls = _REPORT_TYPE_MAP.get(report_type)
        if cls is None:
            return None
        try:
            return cls(**data)
        except (TypeError, ValueError) as exc:
            logger.error(
                "Failed to reconstruct %s model: %s", report_type, exc
            )
            return None

    @staticmethod
    def get_github_method(report_type: str) -> str | None:
        """Return the GitHubIssueService method name for a report type."""
        return _GITHUB_METHOD_MAP.get(report_type)
