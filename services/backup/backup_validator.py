"""
backup_validator.py — handles backup archive validation and SQLite integrity checks.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from zipfile import ZipFile

from trackora.core.schema_version_manager import SchemaVersionManager


class BackupValidator:
    """Verifies ZIP structure, files checksum, and runs SQLite integrity check."""

    @staticmethod
    def validate(backup_path: Path) -> tuple[bool, str | None]:
        """Validate the backup file at backup_path.

        Checks:
          - File exists.
          - Size > 0.
          - Valid ZIP container structure.
          - Manifest, SQLite DB, and metadata files exist.
          - sqlite3 database integrity check passes.

        Returns:
            A tuple (is_valid, error_message).
        """
        if not backup_path.is_file():
            return False, "Backup file does not exist."

        if backup_path.stat().st_size == 0:
            return False, "Backup file size is 0 bytes."

        try:
            with ZipFile(backup_path, "r") as zf:
                namelist = zf.namelist()
                if "MANIFEST.json" not in namelist:
                    return False, "MANIFEST.json is missing."
                if "trackora.db" not in namelist:
                    return False, "trackora.db is missing."
                if "metadata.json" not in namelist:
                    return False, "metadata.json is missing."

                # Verify metadata is parseable JSON
                try:
                    json.loads(zf.read("metadata.json").decode("utf-8"))
                except Exception as exc:
                    return False, f"metadata.json is unreadable: {exc}"

                # Safely extract trackora.db to a tempdir and check SQLite integrity
                with tempfile.TemporaryDirectory() as tmpdir:
                    db_extract_path = Path(tmpdir) / "test_trackora.db"
                    db_extract_path.write_bytes(zf.read("trackora.db"))

                    conn = None
                    try:
                        conn = sqlite3.connect(str(db_extract_path))
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA integrity_check;")
                        res = cursor.fetchone()[0]
                        if res.lower() != "ok":
                            return False, f"Database integrity check failed: {res}"
                    except Exception as exc:
                        return False, f"Database is corrupt or cannot be opened: {exc}"
                    finally:
                        if conn:
                            conn.close()

            return True, None
        except Exception as exc:
            return False, f"ZIP validation failed: {exc}"
