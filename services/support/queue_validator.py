"""
QueueValidator — validates offline report queue files before retry processing.

T-232: Offline Queue Validation

Architecture:
    ReportQueueService
        └── QueueValidator (this module)
            └── Filesystem

Guarantees:
    - Valid JSON structure
    - Supported report type
    - Required fields present with correct types
    - Timestamp present
    - File readable and UTF-8 decodable
    - Empty file detection
    - Quarantine (not discard) of corrupted files

Corrupted files are moved to a quarantine subdirectory for developer inspection.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUBSYSTEM = "QueueValidator"

# ---------------------------------------------------------------------------
# Schema: required fields per report type
# ---------------------------------------------------------------------------

# Each entry maps report_type -> frozenset of required top-level data keys.
# Field *presence* is checked; deep type validation is lightweight by design.
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "bug": frozenset(
        {"title", "description", "steps_to_reproduce", "expected_behavior", "actual_behavior"}
    ),
    "feature": frozenset({"title", "description", "use_case"}),
    "feedback": frozenset({"subject", "message"}),
    "crash": frozenset(
        {
            "report_id",
            "timestamp",
            "app_version",
            "os_version",
            "os_platform",
            "active_sessions",
            "tracked_games",
            "crash_type",
            "was_tracking",
        }
    ),
}

# Required string fields (must be non-empty strings)
_STRING_FIELDS: dict[str, frozenset[str]] = {
    "bug": frozenset({"title", "description"}),
    "feature": frozenset({"title", "description", "use_case"}),
    "feedback": frozenset({"subject", "message"}),
    "crash": frozenset({"report_id", "app_version", "os_version", "os_platform", "crash_type"}),
}

QUARANTINE_SUBDIR = "invalid"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of validating a single queue file."""

    path: Path
    valid: bool
    reason: str = ""
    payload: dict[str, Any] | None = None

    @property
    def report_type(self) -> str | None:
        if self.payload is None:
            return None
        return self.payload.get("type")

    @property
    def data(self) -> dict[str, Any]:
        if self.payload is None:
            return {}
        return self.payload.get("data", {})

    @property
    def report_id(self) -> str | None:
        """Return the report_id from the data dict if present (used for dedup)."""
        return self.data.get("report_id")


@dataclass
class ValidationSummary:
    """Aggregate result from validating the full queue."""

    valid: list[ValidationResult] = field(default_factory=list)
    invalid: list[ValidationResult] = field(default_factory=list)
    quarantined: list[Path] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.valid) + len(self.invalid)

    @property
    def valid_count(self) -> int:
        return len(self.valid)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class QueueValidator:
    """Validates all JSON files in a queue directory before processing.

    Args:
        storage_dir: The queue storage directory (same as ReportQueueService._storage_dir).
    """

    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._quarantine_dir = storage_dir / QUARANTINE_SUBDIR
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def quarantine_dir(self) -> Path:
        """Return the quarantine directory path."""
        return self._quarantine_dir

    def validate_all(self, json_files: list[Path]) -> ValidationSummary:
        """Validate all given queue files.

        Files that fail validation are quarantined (moved to the invalid/ subdir).
        Duplicate report_ids are detected; only the oldest is kept; duplicates
        are quarantined.

        Args:
            json_files: Sorted list of .json paths to validate (chronological order).

        Returns:
            ValidationSummary with lists of valid and invalid results.
        """
        summary = ValidationSummary()
        logger.debug("[%s] Validation started (%d file(s))", SUBSYSTEM, len(json_files))

        # First pass: validate each file individually
        for filepath in json_files:
            result = self._validate_file(filepath)
            if result.valid:
                summary.valid.append(result)
                logger.debug("[%s] File validated: %s", SUBSYSTEM, filepath.name)
            else:
                summary.invalid.append(result)
                quarantined = self._quarantine(filepath, result.reason)
                if quarantined:
                    summary.quarantined.append(quarantined)

        # Second pass: deduplicate by report_id among valid results
        # Files are already in chronological order; keep first occurrence
        seen_ids: dict[str, ValidationResult] = {}
        deduplicated: list[ValidationResult] = []

        for vr in summary.valid:
            rid = vr.report_id
            if rid is None:
                # No report_id (bug/feature/feedback) — always keep
                deduplicated.append(vr)
                continue

            if rid in seen_ids:
                # Duplicate detected — quarantine the newer copy
                logger.warning(
                    "[%s] Duplicate report quarantined (%s in %s, keeping %s)",
                    SUBSYSTEM, rid, vr.path.name, seen_ids[rid].path.name,
                )
                reason = f"Duplicate report_id={rid}"
                quarantined = self._quarantine(vr.path, reason)
                if quarantined:
                    summary.quarantined.append(quarantined)
                dup_result = ValidationResult(
                    path=vr.path, valid=False, reason=reason, payload=vr.payload
                )
                summary.invalid.append(dup_result)
            else:
                seen_ids[rid] = vr
                deduplicated.append(vr)

        summary.valid = deduplicated

        logger.info(
            "[%s] Validation completed (%d valid, %d invalid, %d quarantined)",
            SUBSYSTEM, summary.valid_count, summary.invalid_count, len(summary.quarantined),
        )
        return summary

    def validate_file(self, filepath: Path) -> ValidationResult:
        """Validate a single queue file (public, non-quarantining).

        Quarantining is only done by validate_all(). This method is
        useful for testing individual files.
        """
        return self._validate_file(filepath)

    # ------------------------------------------------------------------
    # Internal validation
    # ------------------------------------------------------------------

    def _validate_file(self, filepath: Path) -> ValidationResult:
        """Validate a single queue file. Returns ValidationResult."""
        # 1. Readability check
        if not filepath.exists():
            return ValidationResult(
                path=filepath, valid=False, reason="File does not exist"
            )

        # 2. Empty file check
        try:
            size = filepath.stat().st_size
        except OSError as exc:
            return ValidationResult(
                path=filepath, valid=False, reason=f"Cannot stat file: {exc}"
            )
        if size == 0:
            return ValidationResult(path=filepath, valid=False, reason="Empty file")

        # 3. UTF-8 decode + JSON parse (single read)
        try:
            raw = filepath.read_bytes()
        except OSError as exc:
            return ValidationResult(
                path=filepath, valid=False, reason=f"Cannot read file: {exc}"
            )

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return ValidationResult(
                path=filepath, valid=False, reason=f"Invalid UTF-8 encoding: {exc}"
            )

        try:
            payload: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            return ValidationResult(
                path=filepath, valid=False, reason=f"Invalid JSON: {exc}"
            )

        # 4. Top-level structure
        if not isinstance(payload, dict):
            return ValidationResult(
                path=filepath, valid=False, reason="Payload is not a JSON object"
            )

        # 5. Timestamp present
        if "created_at" not in payload:
            return ValidationResult(
                path=filepath, valid=False, reason="Missing 'created_at' field"
            )

        # 6. Report type present and supported
        report_type = payload.get("type", "")
        if not isinstance(report_type, str) or not report_type:
            return ValidationResult(
                path=filepath, valid=False, reason="Missing or empty 'type' field"
            )
        if report_type not in _REQUIRED_FIELDS:
            return ValidationResult(
                path=filepath,
                valid=False,
                reason=f"Unsupported report type: '{report_type}'",
            )

        # 7. Data dict present
        data = payload.get("data")
        if not isinstance(data, dict):
            return ValidationResult(
                path=filepath,
                valid=False,
                reason="'data' field is missing or not a JSON object",
            )

        # 8. Required field presence
        required = _REQUIRED_FIELDS[report_type]
        missing = required - data.keys()
        if missing:
            return ValidationResult(
                path=filepath,
                valid=False,
                reason=f"Missing required fields: {sorted(missing)}",
            )

        # 9. Required string fields must be non-empty strings
        string_fields = _STRING_FIELDS.get(report_type, frozenset())
        for fname in string_fields:
            val = data.get(fname)
            if not isinstance(val, str) or not val.strip():
                return ValidationResult(
                    path=filepath,
                    valid=False,
                    reason=f"Field '{fname}' must be a non-empty string",
                )

        return ValidationResult(path=filepath, valid=True, payload=payload)

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    def _quarantine(self, filepath: Path, reason: str) -> Path | None:
        """Move a file to the quarantine directory.

        Args:
            filepath: Source file to quarantine.
            reason:   Human-readable reason for quarantine (logged).

        Returns:
            Destination path if successful, None otherwise.
        """
        dest = self._quarantine_dir / filepath.name
        # Avoid overwriting an existing quarantine file with the same name
        if dest.exists():
            stem = filepath.stem
            suffix = filepath.suffix
            dest = self._quarantine_dir / f"{stem}_dup{suffix}"

        try:
            shutil.move(str(filepath), str(dest))
            logger.warning(
                "[%s] File quarantined (%s → invalid/): %s", SUBSYSTEM, filepath.name, reason
            )
            return dest
        except OSError as exc:
            logger.error(
                "[%s] Quarantine failed (%s): %s", SUBSYSTEM, filepath.name, exc
            )
            return None
