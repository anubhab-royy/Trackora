"""
SchemaVersionManager — manages the schema.json lifecycle.

This is the single source of truth for the schema version of
user data on disk.  It lives in trackora.core because it must be
usable before the database layer is initialised.

The manager stores version metadata in a single JSON file at
BASE_DIR / "schema.json".  All writes are atomic (write to .tmp,
then os.replace) to prevent partial-file reads after crashes.

Architecture rules:
    - No database imports.
    - No service imports.
    - No UI imports.
    - Only depends on trackora.core.paths, trackora.core.schema_version,
      and Python stdlib.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from trackora.core.schema_version import (
    CompatibilityStatus,
    SchemaVersion,
    SchemaVersionError,
)

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("schema_version", "app_version", "updated_at")


class SchemaVersionManager:
    """Manages the schema.json lifecycle.

    Args:
        schema_path: Optional explicit path to schema.json.
                     Defaults to BASE_DIR / 'schema.json'
                     where BASE_DIR comes from trackora.core.paths.
    """

    def __init__(
        self,
        schema_path: Path | None = None,
    ) -> None:
        if schema_path is None:
            from trackora.core.paths import BASE_DIR

            schema_path = BASE_DIR / "schema.json"

        self._schema_path: Path = (
            schema_path if isinstance(schema_path, Path) else Path(schema_path)
        )

        self._clean_orphan_tmp()

    # ── Public API ──────────────────────────────────────────────

    def read(self) -> SchemaVersion | None:
        """Read the schema version from schema.json.

        Returns:
            SchemaVersion if the file exists and is valid.
            None if the file does not exist (first run).

        Raises:
            SchemaVersionError: If the file exists but is corrupt,
                                has invalid format, or is unreadable.
        """
        path = self._schema_path

        if not path.exists():
            logger.info("Schema file not found: %s", path)
            return None

        if not path.is_file():
            logger.error("Schema path exists but is not a file: %s", path)
            raise SchemaVersionError(
                f"Schema path exists but is not a file: {path}"
            )

        # Read raw content
        try:
            raw_text = path.read_text(encoding="utf-8-sig")
        except PermissionError:
            logger.error("Permission denied reading schema file: %s", path)
            raise SchemaVersionError(
                "Permission denied reading schema file"
            )
        except FileNotFoundError:
            # Race condition — deleted between existence check and read
            return None
        except OSError as exc:
            logger.error("Cannot read schema file: %s", exc)
            raise SchemaVersionError(f"Cannot read schema file: {exc}")

        # Parse JSON
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            self._rename_corrupt(raw_text, f"invalid JSON: {exc}")
            raise SchemaVersionError(
                f"Schema file contains invalid JSON: {exc}"
            )

        # Must be a JSON object
        if not isinstance(data, dict):
            self._rename_corrupt(
                raw_text, f"expected JSON object, got {type(data).__name__}"
            )
            raise SchemaVersionError("Schema file is not a JSON object")

        # Validate required fields
        for field in _REQUIRED_FIELDS:
            if field not in data:
                self._rename_corrupt(
                    raw_text, f"missing required field: {field}"
                )
                raise SchemaVersionError(
                    f"Schema file is missing required field: {field}"
                )
            if not isinstance(data[field], str):
                self._rename_corrupt(
                    raw_text, f"field '{field}' is not a string"
                )
                raise SchemaVersionError(
                    f"Field '{field}' must be a string, "
                    f"got {type(data[field]).__name__}"
                )

        # Parse and validate schema_version
        try:
            version = SchemaVersion.from_string(data["schema_version"])
        except ValueError as exc:
            self._rename_corrupt(
                raw_text,
                f"invalid schema_version: {data['schema_version']!r}",
            )
            raise SchemaVersionError(str(exc))

        logger.debug("Schema version read: %s", version)
        return version

    def write(
        self,
        version: SchemaVersion,
        description: str = "",
    ) -> None:
        """Atomically write schema version to schema.json.

        Uses ``.tmp`` + ``os.replace`` pattern for crash safety.
        If the process crashes during the write, either the old
        schema.json is intact or the new one is fully written —
        never a partial/corrupt file.

        Args:
            version: The SchemaVersion to write.
            description: Optional human-readable description
                         of this version (e.g. migration notes).

        Raises:
            TypeError: If *version* is not a SchemaVersion or
                       *description* is not a string.
            OSError: If the file cannot be written (disk full,
                     permissions, etc.).
        """
        if not isinstance(version, SchemaVersion):
            raise TypeError(
                f"Expected SchemaVersion, got {type(version).__name__}"
            )
        if not isinstance(description, str):
            raise TypeError(
                f"Expected str for description, got {type(description).__name__}"
            )

        # Build JSON payload
        payload: dict[str, str] = {
            "schema_version": str(version),
            "app_version": str(version),
            "updated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
        }
        if description:
            payload["description"] = description

        self._write_atomic(payload)

    def is_compatible(
        self,
        app_version: SchemaVersion,
        data_version: SchemaVersion | None,
    ) -> CompatibilityStatus:
        """Determine whether the application can run with this data version.

        Args:
            app_version:  The schema version this application supports.
            data_version: The schema version of the user data on disk,
                          or None if no schema.json exists.

        Returns:
            CompatibilityStatus with can_proceed, status, and message.
        """
        if not isinstance(app_version, SchemaVersion):
            raise TypeError(
                f"Expected SchemaVersion for app_version, "
                f"got {type(app_version).__name__}"
            )
        if data_version is not None and not isinstance(data_version, SchemaVersion):
            raise TypeError(
                f"Expected SchemaVersion for data_version or None, "
                f"got {type(data_version).__name__}"
            )

        if data_version is None:
            return CompatibilityStatus(
                can_proceed=True,
                status="first_run",
                message="No schema file found — first run detected.",
            )

        if data_version == app_version:
            return CompatibilityStatus(
                can_proceed=True,
                status="ok",
                message="",
            )

        if data_version < app_version:
            return CompatibilityStatus(
                can_proceed=True,
                status="needs_migration",
                message=f"Data schema version {data_version} is older than "
                f"app version {app_version}. Migration required.",
            )

        return CompatibilityStatus(
            can_proceed=False,
            status="newer_data",
            message=f"This database requires Trackora {data_version} or newer. "
            f"Please update Trackora.",
        )

    @staticmethod
    def compare(a: SchemaVersion, b: SchemaVersion) -> int:
        """Compare two schema versions.

        Returns:
            -1 if a < b, 0 if a == b, 1 if a > b.
        """
        if a < b:
            return -1
        if a == b:
            return 0
        return 1

    def delete(self) -> None:
        """Delete schema.json.

        Intended for testing and recovery.
        Does not raise if the file does not exist.
        """
        self._schema_path.unlink(missing_ok=True)

    def exists(self) -> bool:
        """Return True if schema.json exists on disk."""
        return self._schema_path.is_file()

    # ── Internal helpers ────────────────────────────────────────

    def _write_atomic(self, payload: dict[str, str]) -> None:
        """Write JSON payload to schema.json using atomic .tmp + rename.

        Creates parent directories if they do not exist.
        Raises OSError on failure (disk full, permissions, etc.).
        """
        path = self._schema_path
        tmp_path = path.with_suffix(".json.tmp")

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            tmp_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(str(tmp_path), str(path))
        except OSError:
            # Attempt cleanup of .tmp on failure
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        logger.info(
            "Schema version updated: %s%s",
            payload.get("schema_version", "unknown"),
            f" ({payload['description']})" if "description" in payload else "",
        )

    def _rename_corrupt(self, content: str, reason: str) -> None:
        """Rename the current schema.json to schema.json.corrupt.<timestamp>.

        Preserves the original content for forensic analysis.
        If the rename fails (permissions, etc.), the error is logged
        but not propagated — the caller will raise SchemaVersionError
        regardless.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = (
            self._schema_path.parent
            / f"schema.json.corrupt.{timestamp}"
        )
        try:
            self._schema_path.rename(target)
            logger.warning(
                "Corrupt schema file renamed to %s (reason: %s)",
                target,
                reason,
            )
            logger.warning(
                "Corrupt content (first 200 chars): %s",
                content[:200],
            )
        except OSError as exc:
            logger.error(
                "Could not rename corrupt schema file %s to %s: %s",
                self._schema_path,
                target,
                exc,
            )

    def _clean_orphan_tmp(self) -> None:
        """Delete orphaned schema.json.tmp file if it exists.

        Called once during __init__.
        Failures are logged but never propagated.
        """
        tmp_path = self._schema_path.with_suffix(".json.tmp")
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
                logger.debug("Cleaned orphan temporary file: %s", tmp_path)
            except OSError as exc:
                logger.warning(
                    "Could not clean orphan temporary file %s: %s",
                    tmp_path,
                    exc,
                )
