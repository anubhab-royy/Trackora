"""
DatabaseMigrationService — Robust, reusable migration from previous appdata paths.

Design (per architecture.md / AGENTS.md):
  - Runs BEFORE DatabaseManager.initialize()
  - Works at the file level — copies whole databases
  - Never deletes user data automatically
  - Creates migration backups
  - Logs every step
  - Validates after migration
  - Idempotent — safe to call multiple times
  - Extensible — add new source paths for future renames

Supported scenarios (from bug report):
  A. Old GameTracker exists, no Trackora               → auto-migrate
  B. Trackora folder exists, DB doesn't                 → auto-migrate
  C. Trackora DB exists but is empty                    → auto-migrate
  D. Trackora DB exists with valid data                 → NO action
  E. Partial failed migration                           → retry
  F. Both exist with data                               → use DB with most data, never destroy
  G. WAL / SHM present                                  → flush before copy
  H. Future rename                                      → add path to SOURCE_DIRS
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable source directories for future renames.
# Each entry is a subdirectory name under the platform appdata root.
# Order matters — first wins when multiple sources have equal data.
# ---------------------------------------------------------------------------
SOURCE_DIRS: list[str] = ["GameTracker"]

# Tables that must contain user data to consider a DB "non-empty".
_DATA_TABLES = ["games", "sessions", "settings"]


@dataclass
class MigrationResult:
    """
    Describes the outcome of a migration attempt.

    Attributes:
        action: One of "migrated", "skipped_no_source", "skipped_has_data",
                "failed", "validation_failed", "error".
        source_path:  Path to the source database that was migrated (if any).
        backup_path:  Path to the backup file created before migration (if any).
        tables_before: Row counts per table in the source DB.
        tables_after:  Row counts per table in the target DB after migration.
        errors:       Human-readable error messages.
    """
    action: str = "none"
    source_path: Path | None = None
    backup_path: Path | None = None
    tables_before: dict[str, int] = field(default_factory=dict)
    tables_after: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.action == "migrated"


# ---------------------------------------------------------------------------
# Platform-aware appdata root
# ---------------------------------------------------------------------------

def _get_appdata_root() -> Path:
    """Return the platform-specific application data root directory.

    Windows: %APPDATA%
    Linux/macOS: ~/.local/share  (XDG_DATA_HOME)
    """
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DatabaseMigrationService:
    """
    Scans known old application data directories and migrates their
    SQLite databases to the current application's data path.

    Usage:
        svc = DatabaseMigrationService(target_db_path)
        result = svc.migrate_if_needed()
        if result.success:
            logger.info("Migrated from %s", result.source_path)
    """

    def __init__(self, target_db_path: str | Path) -> None:
        """
        Args:
            target_db_path: Full path to the current application's database file
                            (e.g. %APPDATA%\\Trackora\\trackora.db).
        """
        self._target = Path(target_db_path)
        self._target_dir = self._target.parent
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def migrate_if_needed(self) -> MigrationResult:
        """
        Evaluate all known source paths and migrate if safe.

        Safe to call repeatedly — returns MigrationResult with action="skip_*"
        when no migration is necessary.

        Returns:
            A MigrationResult describing what happened.
        """
        result = MigrationResult()

        # ALWAYS check target first — if it already has user data, never touch it.
        if self._target_exists_and_has_data():
            self._logger.info("Target database already has data — skipping migration.")
            result.action = "skipped_has_data"
            return result

        sources = self._find_sources()
        if not sources:
            self._logger.info("No previous appdata sources found — no migration needed.")
            result.action = "skipped_no_source"
            return result

        # Pick the best source (first valid with most data).
        source = self._pick_best_source(sources)
        if source is None:
            self._logger.warning("Found source directories but none contain valid data.")
            result.action = "skipped_no_source"
            return result

        result.source_path = source

        # If source and target are the same file (shouldn't happen, but be safe).
        if source.resolve() == self._target.resolve():
            self._logger.info("Source and target are the same file — no migration needed.")
            result.action = "skipped_has_data"
            return result

        # If the target path exists, check if it is a valid SQLite DB.
        if self._target.exists():
            integrity_ok = self._check_integrity(self._target)
            if not integrity_ok:
                self._logger.warning("Target database is corrupted — will re-migrate.")
                # Remove corrupted file so copy can proceed.
                try:
                    self._target.unlink()
                    self._remove_wal_shm(self._target)
                except OSError as exc:
                    msg = f"Cannot remove corrupted target DB: {exc}"
                    self._logger.error(msg)
                    result.action = "error"
                    result.errors.append(msg)
                    return result

        # Record row counts before migration (from source).
        result.tables_before = self._count_rows(source)

        # Create a backup of the source database.
        backup = self._create_backup(source)
        result.backup_path = backup

        # Perform the copy.
        ok = self._copy_db(source, self._target)
        if not ok:
            result.action = "failed"
            result.errors.append(f"Failed to copy {source} to {self._target}")
            self._try_restore_backup(backup, self._target)
            return result

        # Validate the result.
        result.tables_after = self._count_rows(self._target)
        if self._validate_migration(result.tables_before, result.tables_after):
            self._logger.info(
                "Migration successful: %s → %s", source, self._target
            )
            result.action = "migrated"
        else:
            self._logger.error("Migration validation failed — restoring backup.")
            result.action = "validation_failed"
            result.errors.append(
                f"Row count mismatch before={result.tables_before} "
                f"after={result.tables_after}"
            )
            self._try_restore_backup(backup, self._target)

        return result

    # ------------------------------------------------------------------
    # Source discovery
    # ------------------------------------------------------------------

    def _find_sources(self) -> list[Path]:
        """Return paths to existing source database files.

        Scans :data:`SOURCE_DIRS` under the platform appdata root and
        returns paths to any ``*.db`` files found.
        """
        root = _get_appdata_root()
        found: list[Path] = []
        for subdir in SOURCE_DIRS:
            candidate = root / subdir
            if not candidate.is_dir():
                continue
            for db_file in candidate.glob("*.db"):
                if db_file.is_file():
                    found.append(db_file)
        return found

    # ------------------------------------------------------------------
    # Data checks
    # ------------------------------------------------------------------

    def _target_exists_and_has_data(self) -> bool:
        """Return True if the target database exists and contains user data."""
        if not self._target.exists():
            return False
        return self._has_data(self._target)

    def _has_data(self, db_path: Path) -> bool:
        """Check whether *db_path* is a valid SQLite file with user data.

        A database is considered to have data if any of the core tables
        (games, sessions, settings) contains at least one row.
        """
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            for table in _DATA_TABLES:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    if cursor.fetchone()[0] > 0:
                        return True
                except sqlite3.OperationalError:
                    continue
            return False
        except sqlite3.DatabaseError:
            return False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _count_rows(self, db_path: Path) -> dict[str, int]:
        """Return a dict mapping table name → row count for *db_path*.

        Tables that don't exist or can't be read are omitted.
        """
        counts: dict[str, int] = {}
        if not db_path.exists():
            return counts
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row["name"] for row in cursor.fetchall()]
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
                    counts[table] = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    continue
        except sqlite3.DatabaseError as exc:
            self._logger.warning("Cannot count rows in %s: %s", db_path, exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        return counts

    def _check_integrity(self, db_path: Path) -> bool:
        """Run ``PRAGMA integrity_check``; return True if OK."""
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            return result == "ok"
        except sqlite3.DatabaseError:
            return False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Source selection
    # ------------------------------------------------------------------

    def _pick_best_source(self, sources: list[Path]) -> Path | None:
        """Return the source with the most total rows across data tables.

        Filters out invalid or empty databases first.
        """
        valid: list[tuple[Path, int]] = []
        for src in sources:
            if not src.exists():
                continue
            if not self._is_valid_sqlite(src):
                self._logger.debug("Skipping invalid source DB: %s", src)
                continue
            total = sum(
                v for k, v in self._count_rows(src).items()
                if k in _DATA_TABLES
            )
            if total > 0:
                valid.append((src, total))

        if not valid:
            return None
        # Return the source with the most data.
        valid.sort(key=lambda x: x[1], reverse=True)
        return valid[0][0]

    def _is_valid_sqlite(self, db_path: Path) -> bool:
        """Check if *db_path* is a valid SQLite database."""
        if not db_path.exists() or db_path.stat().st_size == 0:
            return False
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            return True
        except sqlite3.DatabaseError:
            return False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def _create_backup(self, source: Path) -> Path | None:
        """Copy *source* to ``<source>.backup`` and return the backup path.

        If a backup already exists, it is NOT overwritten.
        Returns None on failure.
        """
        backup = source.with_suffix(source.suffix + ".backup")
        if backup.exists():
            self._logger.info("Backup already exists: %s", backup)
            return backup
        try:
            shutil.copy2(str(source), str(backup))
            self._logger.info("Backup created: %s", backup)
            return backup
        except OSError as exc:
            self._logger.error("Failed to create backup %s: %s", backup, exc)
            return None

    def _try_restore_backup(self, backup: Path | None, target: Path) -> None:
        """Restore *backup* to *target* if backup exists."""
        if backup is None or not backup.exists():
            self._logger.warning("No backup available to restore.")
            return
        try:
            self._remove_wal_shm(target)
            shutil.copy2(str(backup), str(target))
            self._logger.info("Restored backup: %s → %s", backup, target)
        except OSError as exc:
            self._logger.error("Failed to restore backup %s: %s", backup, exc)

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _copy_db(self, source: Path, target: Path) -> bool:
        """Flush WAL on *source* then copy it to *target*.

        Also copies any WAL / SHM files associated with *source*
        so consistency is preserved.
        """
        try:
            self._flush_wal(source)
            self._ensure_target_dir(target)
            shutil.copy2(str(source), str(target))
            # Also copy WAL and SHM if they exist (preserves consistency).
            for ext in ("-wal", "-shm"):
                src_ext = source.with_name(source.name + ext)
                if src_ext.exists():
                    tgt_ext = target.with_name(target.name + ext)
                    shutil.copy2(str(src_ext), str(tgt_ext))
            self._logger.info("Copied %s → %s", source, target)
            return True
        except OSError as exc:
            self._logger.error("Copy failed: %s", exc)
            return False

    def _flush_wal(self, db_path: Path) -> None:
        """Flush any pending WAL content into the main database file."""
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError as exc:
            self._logger.warning("WAL checkpoint failed (non-fatal): %s", exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _ensure_target_dir(self, target: Path) -> None:
        """Create the parent directory for *target* if it doesn't exist."""
        target.parent.mkdir(parents=True, exist_ok=True)

    def _remove_wal_shm(self, db_path: Path) -> None:
        """Remove any -wal and -shm files associated with *db_path*."""
        for ext in ("-wal", "-shm"):
            p = db_path.with_name(db_path.name + ext)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_migration(
        tables_before: dict[str, int],
        tables_after: dict[str, int],
    ) -> bool:
        """Return True if row counts after migration match before.

        Only checks tables in _DATA_TABLES (core user data).
        """
        for table in _DATA_TABLES:
            before = tables_before.get(table, 0)
            after = tables_after.get(table, 0)
            if before != after:
                logger.error(
                    "Row count mismatch for %s: before=%d after=%d",
                    table, before, after,
                )
                return False
        return True
