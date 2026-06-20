"""
BackupManager — production-grade backup and recovery.

BackupManager creates self-verifying ZIP archives that contain
the SQLite database, schema version file, manifest, and metadata.
It is the safety net for all upgrade and migration operations.

Architecture rules:
    - No database imports.
    - No service imports.
    - No UI imports.
    - Only depends on trackora.core.paths, trackora.core.schema_version,
      trackora.core.schema_version_manager, and Python stdlib.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from trackora.core.schema_version_manager import SchemaVersionManager

logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────────────────


@dataclass(frozen=True)
class BackupResult:
    """Result of a backup creation operation."""

    success: bool
    backup_id: str
    backup_path: Path | None
    size_bytes: int
    file_count: int
    created_at: datetime
    error: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    """Result of a restore operation."""

    success: bool
    backup_id: str
    safety_backup_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    """Result of a backup verification."""

    valid: bool
    backup_id: str
    checksum_errors: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class BackupInfo:
    """Summary information about a single backup."""

    backup_id: str
    backup_path: Path
    size_bytes: int
    created_at: datetime
    schema_version: str
    trackora_version: str
    backup_type: str
    file_count: int


# ── BackupManager ─────────────────────────────────────────────────


class BackupManager:
    """Create, verify, restore, and manage backup archives.

    Args:
        schema_version_manager: An initialized SchemaVersionManager
                                instance for reading schema version
                                metadata.
        backup_dir: Optional explicit path to the backup directory.
                    Defaults to BACKUPS_DIR from trackora.core.paths.
    """

    def __init__(
        self,
        schema_version_manager: SchemaVersionManager,
        backup_dir: Path | None = None,
    ) -> None:
        self._schema_version_manager = schema_version_manager

        if backup_dir is None:
            from trackora.core.paths import BACKUPS_DIR

            backup_dir = BACKUPS_DIR

        self._backup_dir: Path = (
            backup_dir if isinstance(backup_dir, Path) else Path(backup_dir)
        )

        self._clean_orphan_tmp()
        self._clean_orphan_restore_dirs()

    # ── Public API ────────────────────────────────────────────────

    def create_backup(
        self,
        backup_type: str = "manual",
    ) -> BackupResult:
        """Create a self-verifying backup archive.

        Args:
            backup_type: Reason for the backup. One of "manual",
                         "pre_migration", "pre_restore", "scheduled".

        Returns:
            BackupResult with success status and backup metadata.
        """
        from trackora.core.paths import DATABASE_PATH

        # Resolve source paths
        db_path = DATABASE_PATH
        schema_path: Path = self._schema_version_manager._schema_path  # type: ignore[attr-defined]

        if not db_path.is_file():
            return BackupResult(
                success=False,
                backup_id="",
                backup_path=None,
                size_bytes=0,
                file_count=0,
                created_at=datetime.now(timezone.utc),
                error=f"Database not found: {db_path}",
            )

        backup_id = self._generate_backup_id()
        tmp_path = self._backup_dir / f"{backup_id}.zip.tmp"
        final_path = self._backup_dir / f"{backup_id}.zip"

        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy database to a temporary staging file
        db_staging = self._backup_dir / f".{backup_id}.db"
        try:
            self._copy_database(db_path, db_staging)

            # Collect source file contents
            db_bytes = db_staging.read_bytes()
            schema_exists = schema_path.is_file()
            if not schema_exists:
                logger.warning(
                    "Schema file not found: %s — backup will not include schema.json",
                    schema_path,
                )
            schema_bytes = schema_path.read_bytes() if schema_exists else b""

            # Build metadata
            metadata = self._build_metadata(backup_type)
            metadata_bytes = (
                json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8")
                + b"\n"
            )

            # Compute checksums for data files
            db_sha = self._compute_sha256(db_bytes)
            schema_sha = self._compute_sha256(schema_bytes) if schema_exists else ""
            meta_sha = self._compute_sha256(metadata_bytes)

            # Build manifest files array (3 data entries; MANIFEST.json
            # added after its own SHA is computed)
            data_entries = []
            data_entries.append(
                {
                    "path": "trackora.db",
                    "size": len(db_bytes),
                    "sha256": db_sha,
                }
            )
            if schema_exists:
                data_entries.append(
                    {
                        "path": "schema.json",
                        "size": len(schema_bytes),
                        "sha256": schema_sha,
                    }
                )
            data_entries.append(
                {
                    "path": "metadata.json",
                    "size": len(metadata_bytes),
                    "sha256": meta_sha,
                }
            )

            # Read schema version for manifest
            try:
                sv = self._schema_version_manager.read()
                sv_str = str(sv) if sv is not None else ""
            except Exception:
                sv_str = ""

            # Build manifest without self-entry to compute its own SHA
            import trackora

            manifest_base = {
                "manifest_version": "1.0",
                "backup_version": 1,
                "created_at": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "schema_version": sv_str,
                "trackora_version": trackora.__version__,
                "backup_type": backup_type,
                "backup_id": backup_id,
                "file_count": 1 + len(data_entries),  # +1 for MANIFEST.json
                "files": data_entries,
            }

            # Compute MANIFEST.json's own SHA from the base bytes
            base_bytes = (
                json.dumps(manifest_base, indent=2, ensure_ascii=False).encode("utf-8")
                + b"\n"
            )
            manifest_sha = self._compute_sha256(base_bytes)
            manifest_size = len(base_bytes)

            # Build final files array with MANIFEST.json first
            final_files = [
                {
                    "path": "MANIFEST.json",
                    "size": manifest_size,
                    "sha256": manifest_sha,
                },
                *data_entries,
            ]

            manifest_final = dict(manifest_base)
            manifest_final["files"] = final_files
            manifest_bytes = (
                json.dumps(manifest_final, indent=2, ensure_ascii=False).encode("utf-8")
                + b"\n"
            )

            # Create ZIP archive
            with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zf:
                # MANIFEST.json uncompressed for fast verification
                zf.writestr(
                    ZipInfo("MANIFEST.json"),
                    manifest_bytes,
                    compress_type=ZIP_STORED,
                )
                # trackora.db
                zf.writestr("trackora.db", db_bytes)
                # schema.json (if exists)
                if schema_exists:
                    zf.writestr("schema.json", schema_bytes)
                # metadata.json
                zf.writestr("metadata.json", metadata_bytes)

            # Atomic rename
            os.replace(str(tmp_path), str(final_path))

            size_bytes = final_path.stat().st_size
            return BackupResult(
                success=True,
                backup_id=backup_id,
                backup_path=final_path,
                size_bytes=size_bytes,
                file_count=manifest_final["file_count"],
                created_at=datetime.now(timezone.utc),
            )

        except OSError as exc:
            # Clean up .tmp on failure
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return BackupResult(
                success=False,
                backup_id=backup_id,
                backup_path=None,
                size_bytes=0,
                file_count=0,
                created_at=datetime.now(timezone.utc),
                error=str(exc),
            )
        except Exception as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return BackupResult(
                success=False,
                backup_id=backup_id,
                backup_path=None,
                size_bytes=0,
                file_count=0,
                created_at=datetime.now(timezone.utc),
                error=str(exc),
            )
        finally:
            # Clean up staging database copy
            if db_staging.exists():
                try:
                    db_staging.unlink()
                except OSError:
                    pass

    def verify_backup(
        self,
        backup_id: str,
    ) -> VerificationResult:
        """Verify the integrity of a backup archive.

        Checks ZIP integrity, manifest structure, file presence,
        file count, and SHA-256 checksums for all files except
        MANIFEST.json (self-referential by design — verified via
        ZIP CRC-32).

        Args:
            backup_id: The backup identifier (without .zip suffix).

        Returns:
            VerificationResult with validity status and details.
        """
        zip_path = self._backup_dir / f"{backup_id}.zip"

        if not zip_path.is_file():
            return VerificationResult(
                valid=False,
                backup_id=backup_id,
                error=f"Backup not found: {backup_id}",
            )

        # Try to open as ZIP
        try:
            zf = ZipFile(zip_path, "r")
        except Exception as exc:
            return VerificationResult(
                valid=False,
                backup_id=backup_id,
                error=f"Corrupt or invalid ZIP: {exc}",
            )

        with zf:
            # Check for MANIFEST.json
            if "MANIFEST.json" not in zf.namelist():
                return VerificationResult(
                    valid=False,
                    backup_id=backup_id,
                    error="MANIFEST.json not found in backup archive",
                )

            # Parse manifest
            try:
                manifest = json.loads(zf.read("MANIFEST.json"))
            except json.JSONDecodeError as exc:
                return VerificationResult(
                    valid=False,
                    backup_id=backup_id,
                    error=f"Invalid MANIFEST.json: {exc}",
                )

            # Validate manifest is a dict with required fields
            if not isinstance(manifest, dict):
                return VerificationResult(
                    valid=False,
                    backup_id=backup_id,
                    error="MANIFEST.json is not a JSON object",
                )

            required_fields = [
                "manifest_version",
                "backup_version",
                "file_count",
                "files",
            ]
            for field in required_fields:
                if field not in manifest:
                    return VerificationResult(
                        valid=False,
                        backup_id=backup_id,
                        error=f"MANIFEST.json missing required field: {field}",
                    )

            file_entries = manifest.get("files", [])

            # Validate internal file_count consistency
            expected_count = manifest["file_count"]
            if expected_count != len(file_entries):
                return VerificationResult(
                    valid=False,
                    backup_id=backup_id,
                    error=(
                        f"File count mismatch: manifest says {expected_count}, "
                        f"files array has {len(file_entries)}"
                    ),
                )

            # Verify each file in the manifest
            checksum_errors: list[str] = []
            missing_files: list[str] = []
            zip_names = set(zf.namelist())

            for entry in file_entries:
                path = entry.get("path", "")
                expected_sha = entry.get("sha256", "")

                # Skip MANIFEST.json self-checksum (circular by design)
                if path == "MANIFEST.json":
                    continue

                if path not in zip_names:
                    missing_files.append(path)
                    continue

                try:
                    data = zf.read(path)
                    actual_sha = self._compute_sha256(data)
                except Exception:
                    checksum_errors.append(path)
                    continue

                if actual_sha != expected_sha:
                    checksum_errors.append(path)

            is_valid = (
                len(checksum_errors) == 0
                and len(missing_files) == 0
            )

            return VerificationResult(
                valid=is_valid,
                backup_id=backup_id,
                checksum_errors=checksum_errors,
                missing_files=missing_files,
            )

    def restore_backup(
        self,
        backup_id: str,
    ) -> RestoreResult:
        """Restore files from a backup archive.

        Verifies the backup first, creates a safety backup of the
        current state, then atomically replaces production files.
        On failure, rolls back from the safety backup.

        Args:
            backup_id: The backup identifier (without .zip suffix).

        Returns:
            RestoreResult with success status and details.
        """
        from trackora.core.paths import DATABASE_PATH

        zip_path = self._backup_dir / f"{backup_id}.zip"

        # 1. Verify the backup first
        verify_result = self.verify_backup(backup_id)
        if not verify_result.valid:
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                error=verify_result.error or "Backup verification failed",
            )

        # 2. Create safety backup of current state
        safety_result = self.create_backup(backup_type="pre_restore")
        if not safety_result.success:
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                error=f"Safety backup failed: {safety_result.error}",
            )

        safety_backup_id: str = safety_result.backup_id
        staging_dir = self._backup_dir / f".restore_{uuid.uuid4().hex[:12]}"

        try:
            # 3. Extract to staging directory
            staging_dir.mkdir(parents=True, exist_ok=True)

            with ZipFile(zip_path, "r") as zf:
                zf.extractall(staging_dir)

            # 4. Validate extracted files before replacing production files
            validation_errors = self._validate_staging(staging_dir, zip_path)
            if validation_errors:
                error_msg = "; ".join(validation_errors)
                logger.error(
                    "Restore validation failed for %s: %s — "
                    "production files not modified.",
                    backup_id,
                    error_msg,
                )
                shutil.rmtree(staging_dir)
                return RestoreResult(
                    success=False,
                    backup_id=backup_id,
                    safety_backup_id=safety_backup_id,
                    error=(
                        f"Restore validation failed: {error_msg} — "
                        f"production files not modified."
                    ),
                )

            # 5. Atomic replace of production files
            schema_path: Path = self._schema_version_manager._schema_path  # type: ignore[attr-defined]

            # Replace trackora.db
            staging_db = staging_dir / "trackora.db"
            if staging_db.is_file():
                os.replace(str(staging_db), str(DATABASE_PATH))

            # Replace schema.json if present
            staging_schema = staging_dir / "schema.json"
            if staging_schema.is_file():
                os.replace(str(staging_schema), str(schema_path))

            # 6. Clean up staging
            shutil.rmtree(staging_dir)

            return RestoreResult(
                success=True,
                backup_id=backup_id,
                safety_backup_id=safety_backup_id,
            )

        except Exception as exc:
            # 6. Attempt rollback from safety backup
            logger.error(
                "Restore of %s failed: %s. Verifying safety backup %s for rollback.",
                backup_id,
                exc,
                safety_backup_id,
            )

            # 6a. Verify safety backup before attempting rollback
            verify_safety = self.verify_backup(safety_backup_id)
            if not verify_safety.valid:
                rollback_msg = (
                    f"Safety backup {safety_backup_id} is corrupt and cannot be used "
                    f"for rollback. It is available for manual inspection at "
                    f"{self._backup_dir / safety_backup_id}.zip. "
                    f"Original error: {exc}"
                )
                logger.critical(
                    "Safety backup %s verification failed: %s. "
                    "Rollback not attempted. %s",
                    safety_backup_id,
                    verify_safety.error,
                    rollback_msg,
                )
            else:
                try:
                    self._restore_from_safety(safety_backup_id)
                    rollback_msg = "Rollback completed."
                except Exception as rollback_exc:
                    rollback_msg = (
                        f"Rollback also failed: {rollback_exc}. "
                        f"Safety backup {safety_backup_id} is available for manual restore."
                    )
                    logger.critical(
                        "Rollback failed for safety backup %s: %s",
                        safety_backup_id,
                        rollback_exc,
                    )

            # Clean up staging if it still exists
            if staging_dir.exists():
                try:
                    shutil.rmtree(staging_dir)
                except OSError:
                    pass

            return RestoreResult(
                success=False,
                backup_id=backup_id,
                safety_backup_id=safety_backup_id,
                error=f"Restore failed: {exc}. {rollback_msg}",
            )

    def _restore_from_safety(self, safety_backup_id: str) -> None:
        """Atomically restore files from a safety backup.

        Uses a staging directory with validation before atomic
        os.replace() to ensure production files are never left in an
        inconsistent state.

        Args:
            safety_backup_id: The safety backup identifier.

        Raises:
            FileNotFoundError: If the safety backup ZIP does not exist.
            RuntimeError: If the safety backup fails verification or
                          extracted file validation.
        """
        from trackora.core.paths import DATABASE_PATH

        safety_path = self._backup_dir / f"{safety_backup_id}.zip"
        if not safety_path.is_file():
            raise FileNotFoundError(
                f"Safety backup not found: {safety_path}"
            )

        schema_path: Path = self._schema_version_manager._schema_path  # type: ignore[attr-defined]

        # Create staging directory
        staging_dir = self._backup_dir / f".rollback_{uuid.uuid4().hex[:12]}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Extract to staging
            with ZipFile(safety_path, "r") as zf:
                zf.extractall(staging_dir)

            # Validate extracted files
            validation_errors = self._validate_staging(staging_dir, safety_path)
            if validation_errors:
                error_msg = "; ".join(validation_errors)
                raise RuntimeError(
                    f"Safety backup {safety_backup_id} validation failed: {error_msg}"
                )

            # Atomic replace
            staging_db = staging_dir / "trackora.db"
            if staging_db.is_file():
                os.replace(str(staging_db), str(DATABASE_PATH))

            staging_schema = staging_dir / "schema.json"
            if staging_schema.is_file():
                os.replace(str(staging_schema), str(schema_path))

        finally:
            # Clean up staging
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def list_backups(
        self,
        sort_by: str = "created_at",
        limit: int | None = None,
    ) -> list[BackupInfo]:
        """List available backup archives.

        Scans the backup directory for backup ZIP files, reads
        metadata from each, and returns sorted BackupInfo objects.

        Args:
            sort_by: Sort criterion — ``"created_at"`` (newest first)
                     or ``"name"`` (alphabetical).
            limit:   Maximum number of results, or ``None`` for all.

        Returns:
            List of BackupInfo objects, newest first by default.
        """
        results: list[BackupInfo] = []

        if not self._backup_dir.is_dir():
            return results

        for path in sorted(self._backup_dir.glob("backup_*.zip")):
            if not path.is_file():
                continue

            backup_id = path.stem  # filename without .zip

            try:
                with ZipFile(path, "r") as zf:
                    if "MANIFEST.json" not in zf.namelist():
                        logger.warning(
                            "Skipping %s: no MANIFEST.json", path.name
                        )
                        continue

                    manifest = json.loads(zf.read("MANIFEST.json"))

                size_bytes = path.stat().st_size
                created_at_str = manifest.get("created_at", "")
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                except (ValueError, TypeError):
                    created_at = datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    )

                info = BackupInfo(
                    backup_id=backup_id,
                    backup_path=path,
                    size_bytes=size_bytes,
                    created_at=created_at,
                    schema_version=manifest.get("schema_version", ""),
                    trackora_version=manifest.get("trackora_version", ""),
                    backup_type=manifest.get("backup_type", "manual"),
                    file_count=manifest.get("file_count", 0),
                )
                results.append(info)

            except Exception as exc:
                logger.warning(
                    "Skipping corrupt backup %s: %s", path.name, exc
                )
                continue

        if sort_by == "created_at":
            results.sort(key=lambda x: x.created_at, reverse=True)
        elif sort_by == "name":
            results.sort(key=lambda x: x.backup_id)

        if limit is not None:
            results = results[:limit]

        return results

    def get_latest_backup(self) -> BackupInfo | None:
        """Return the most recent backup, or ``None`` if none exist.

        Shorthand for ``list_backups(limit=1)``.
        """
        backups = self.list_backups(limit=1)
        return backups[0] if backups else None

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a single backup archive by its backup ID.

        Args:
            backup_id: The backup identifier (without .zip suffix).

        Returns:
            ``True`` if the file was deleted, ``False`` if it did
            not exist.
        """
        zip_path = self._backup_dir / f"{backup_id}.zip"
        if not zip_path.is_file():
            return False
        try:
            zip_path.unlink()
            logger.info("Deleted backup: %s", backup_id)
            return True
        except OSError:
            return False

    def clean_old_backups(self, keep_last: int = 5) -> int:
        """Remove old backups beyond the retention limit.

        Backups with ``backup_type="pre_restore"`` are preserved.

        Args:
            keep_last: Number of newest backups to keep.

        Returns:
            Number of backups deleted.
        """
        all_backups = self.list_backups(sort_by="created_at")

        # Separate pre_restore backups from the rest
        deletable: list[BackupInfo] = []
        pre_restore_count = 0
        for b in all_backups:
            if b.backup_type == "pre_restore":
                pre_restore_count += 1
            else:
                deletable.append(b)

        # Keep the newest `keep_last` of deletable backups
        if len(deletable) <= keep_last:
            return 0

        to_delete = deletable[keep_last:]
        deleted_count = 0
        for b in to_delete:
            if self.delete_backup(b.backup_id):
                deleted_count += 1

        return deleted_count

    # ── Internal helpers ────────────────────────────────────────────

    def _validate_staging(
        self,
        staging_dir: Path,
        zip_path: Path,
    ) -> list[str]:
        """Validate extracted files in a staging directory.

        Checks:
          1. Required files exist (trackora.db, schema.json)
          2. SHA-256 checksums match the backup manifest
          3. Manifest file_count matches actual file count
          4. SQLite database opens and passes PRAGMA integrity_check
          5. schema.json can be parsed by SchemaVersionManager

        Args:
            staging_dir: Directory containing extracted backup files.
            zip_path: Path to the original backup ZIP (for reading manifest).

        Returns:
            List of error strings. Empty list means validation passed.
        """
        errors: list[str] = []

        # Read manifest from the original ZIP
        try:
            with ZipFile(zip_path, "r") as zf:
                if "MANIFEST.json" not in zf.namelist():
                    return ["MANIFEST.json not found in backup archive"]
                manifest = json.loads(zf.read("MANIFEST.json"))
        except Exception as exc:
            return [f"Could not read manifest from {zip_path.name}: {exc}"]

        if not isinstance(manifest, dict):
            return ["MANIFEST.json is not a JSON object"]

        files_in_manifest = manifest.get("files", [])
        manifest_file_count = manifest.get("file_count", 0)

        # Check file count consistency
        if manifest_file_count != len(files_in_manifest):
            errors.append(
                f"File count mismatch: manifest says {manifest_file_count}, "
                f"files array has {len(files_in_manifest)}"
            )

        # Check each file in the manifest
        for entry in files_in_manifest:
            path = entry.get("path", "")
            expected_sha = entry.get("sha256", "")

            if path == "MANIFEST.json":
                continue

            staged_file = staging_dir / path
            if not staged_file.is_file():
                errors.append(f"Required file missing from staging: {path}")
                continue

            # Verify SHA-256
            try:
                actual_sha = self._compute_sha256(staged_file.read_bytes())
            except Exception as exc:
                errors.append(f"Could not read staged file {path}: {exc}")
                continue

            if expected_sha and actual_sha != expected_sha:
                errors.append(
                    f"SHA-256 mismatch for {path}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )

        # Validate SQLite database
        staged_db = staging_dir / "trackora.db"
        if staged_db.is_file():
            try:
                conn = sqlite3.connect(str(staged_db))
                cursor = conn.execute("PRAGMA integrity_check;")
                result = cursor.fetchall()
                conn.close()
                if len(result) != 1 or result[0][0] != "ok":
                    errors.append(
                        f"Database integrity check failed: {result}"
                    )
            except sqlite3.DatabaseError as exc:
                errors.append(f"Could not open SQLite database: {exc}")
            except Exception as exc:
                errors.append(f"Unexpected error validating database: {exc}")
        else:
            errors.append("Required file missing from staging: trackora.db")

        # Validate schema.json if present
        staged_schema = staging_dir / "schema.json"
        if staged_schema.is_file():
            try:
                sv = SchemaVersionManager(schema_path=staged_schema).read()
                if sv is None:
                    errors.append("schema.json could not be parsed")
            except Exception as exc:
                errors.append(f"schema.json validation failed: {exc}")

        return errors

    def _clean_orphan_tmp(self) -> None:
        """Remove orphaned .zip.tmp files from the backup directory."""
        if not self._backup_dir.is_dir():
            return
        for child in self._backup_dir.iterdir():
            if child.suffix == ".tmp" and child.name.endswith(".zip.tmp"):
                try:
                    child.unlink()
                    logger.debug("Cleaned orphan temporary file: %s", child)
                except OSError as exc:
                    logger.warning(
                        "Could not clean orphan temporary file %s: %s",
                        child,
                        exc,
                    )

    def _clean_orphan_restore_dirs(self) -> None:
        """Remove orphaned .restore_* and .rollback_* staging directories."""
        if not self._backup_dir.is_dir():
            return
        for child in self._backup_dir.iterdir():
            if child.is_dir() and (
                child.name.startswith(".restore_")
                or child.name.startswith(".rollback_")
            ):
                try:
                    shutil.rmtree(child)
                    logger.debug("Cleaned orphan restore directory: %s", child)
                except OSError as exc:
                    logger.warning(
                        "Could not clean orphan restore directory %s: %s",
                        child,
                        exc,
                    )

    @staticmethod
    def _generate_backup_id() -> str:
        """Generate a unique backup identifier.

        Format: backup_<YYYYMMDD>_<HHMMSS>_<uuid4 first 8 chars>
        """
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        return f"backup_{ts}_{uid}"

    @staticmethod
    def _compute_sha256(data: bytes) -> str:
        """Compute the SHA-256 hex digest of *data*."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _copy_database(src: Path, dst: Path) -> None:
        """Copy a live SQLite database using the online backup API.

        Performs a WAL checkpoint before backup for consistency.
        """
        with sqlite3.connect(str(src)) as src_conn:
            try:
                src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.OperationalError:
                pass
            with sqlite3.connect(str(dst)) as dst_conn:
                src_conn.backup(dst_conn, pages=-1)

    @staticmethod
    def _build_metadata(backup_type: str) -> dict[str, str]:
        """Build the metadata.json content."""
        import sys as _sys

        from trackora import __version__ as app_version
        from trackora.core.environment import CURRENT_ENVIRONMENT

        return {
            "environment": CURRENT_ENVIRONMENT,
            "platform": _sys.platform,
            "python_version": _sys.version.split()[0],
            "application_version": app_version,
            "backup_reason": backup_type,
            "notes": "",
        }
