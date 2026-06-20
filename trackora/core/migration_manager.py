"""Migration ABC — contract for all schema migrations.

Every migration in the system must subclass Migration and provide:
    - migration_id   (str)   — unique, matches ``^v\\d+_\\d+_\\d+_[a-z0-9_]+$``
    - description    (str)   — human-readable summary
    - app_version    (str)   — target app version after this migration
    - upgrade()              — apply the migration
    - downgrade()            — revert the migration

Architecture rules:
    - No database imports.
    - No service imports.
    - No UI imports.
    - Only depends on Python stdlib.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from trackora.core.schema_version import SchemaVersion

logger = logging.getLogger(__name__)

_MIGRATION_ID_PATTERN = re.compile(r"^v\d+_\d+_\d+_[a-z0-9_]+$")

_REQUIRED_CLASS_ATTRS = ("migration_id", "description", "app_version")


class Migration(ABC):
    """Base class for all schema migrations.

    Subclasses must define:
        migration_id : str   — unique identifier (see pattern above)
        description  : str   — human-readable description
        app_version  : str   — target app version (MAJOR.MINOR.PATCH)

    Subclasses must implement:
        upgrade(connection)   — apply the migration (idempotent)
        downgrade(connection) — revert the migration (idempotent)
    """

    # ── Overridable defaults ──────────────────────────────────────

    requires_backup: bool = True
    requires_downtime: bool = False

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        # Check required class-level attributes
        for attr in _REQUIRED_CLASS_ATTRS:
            if not hasattr(cls, attr):
                raise TypeError(
                    f"Migration subclass {cls.__name__!r} must define "
                    f"class attribute {attr!r}"
                )

        value = cls.migration_id  # type: ignore
        if not isinstance(value, str) or not _MIGRATION_ID_PATTERN.match(value):
            raise TypeError(
                f"Migration subclass {cls.__name__!r} has invalid "
                f"migration_id={value!r}. Must match "
                f"^v\\d+_\\d+_\\d+_[a-z0-9_]+$"
            )

    # ── Required: subclasses must implement these ─────────────────

    @abstractmethod
    def upgrade(self, connection: object) -> None:
        """Apply the migration.
        Must be idempotent — use IF NOT EXISTS, check columns, etc.
        """

    @abstractmethod
    def downgrade(self, connection: object) -> None:
        """Revert the migration.
        Must be idempotent.
        """

    # ── Optional: subclasses may override ─────────────────────────

    def verify(self, connection: object) -> list[str]:
        """Verify the migration was applied correctly.
        Return empty list on success, error messages on failure.
        Default: no verification.
        """
        return []

    # ── Built-in ──────────────────────────────────────────────────

    def source_checksum(self) -> str:
        """SHA-256 hex digest of this migration's source file.
        Used to detect tampering after the migration is recorded.
        """
        try:
            module_file = inspect.getfile(self.__class__)
            source = Path(module_file).read_bytes()
        except (TypeError, OSError):
            source = self.__class__.__name__.encode("utf-8")
        return hashlib.sha256(source).hexdigest()


# ── Result / tracking types ──────────────────────────────────────


@dataclass(frozen=True)
class AppliedMigration:
    """A migration that has been recorded in the _migrations table."""

    migration_id: str
    description: str
    app_version: str
    checksum: str
    applied_at: str
    duration_ms: int


@dataclass(frozen=True)
class MigrationAttempt:
    """Outcome of a single migration attempt."""

    migration_id: str
    description: str
    success: bool
    duration_ms: int
    error: str | None = None
    backup_id: str | None = None


@dataclass(frozen=True)
class MigrationResult:
    """Aggregated result of applying zero or more migrations."""

    success: bool
    applied_count: int
    failed_count: int
    results: list[MigrationAttempt] = field(default_factory=list)
    backup_id: str | None = None
    final_version: str | None = None


class MigrationVerificationError(Exception):
    """Raised when a migration's verify() step returns errors."""


# ── MigrationManager ─────────────────────────────────────────────


class MigrationManager:
    """Discover, apply, and track database schema migrations.

    Args:
        connection: An open sqlite3.Connection to the Trackora database.
        schema_version_manager: Initialised SchemaVersionManager for
                                reading and writing schema.json.
        backup_manager: Optional BackupManager. If provided, a backup
                        is created before each migration that requires it.
        registry: Optional MigrationRegistry-like object. Must provide
                  ``discover() -> list[type[Migration]]`` and
                  ``get_by_id(migration_id) -> type[Migration] | None``.
                  Defaults to ``MigrationRegistry``.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        schema_version_manager: SchemaVersionManager,
        backup_manager: object | None = None,
        registry: object | None = None,
    ) -> None:
        self._conn = connection
        self._svm = schema_version_manager
        self._backup = backup_manager

        if registry is None:
            from trackora.core.migrations.registry import MigrationRegistry

            self._registry = MigrationRegistry
        else:
            self._registry = registry

        self._ensure_migrations_table()

    # ── Table management ──────────────────────────────────────────

    def _ensure_migrations_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                migration_id TEXT PRIMARY KEY,
                description  TEXT NOT NULL,
                app_version  TEXT NOT NULL,
                checksum     TEXT NOT NULL,
                applied_at   TEXT NOT NULL,
                duration_ms  INTEGER NOT NULL DEFAULT 0
            );
        """)
        self._conn.commit()

    # ── Query helpers ─────────────────────────────────────────────

    def get_applied_migrations(self) -> list[AppliedMigration]:
        """Return all migrations recorded in the _migrations table."""
        try:
            cursor = self._conn.execute(
                "SELECT migration_id, description, app_version, checksum, "
                "applied_at, duration_ms FROM _migrations ORDER BY migration_id"
            )
        except sqlite3.OperationalError:
            self._ensure_migrations_table()
            return []

        return [
            AppliedMigration(
                migration_id=row[0],
                description=row[1],
                app_version=row[2],
                checksum=row[3],
                applied_at=row[4],
                duration_ms=row[5],
            )
            for row in cursor.fetchall()
        ]

    def get_pending_migrations(self) -> list[type[Migration]]:
        """Return Migration subclasses that have not yet been applied."""
        all_migrations = self.get_all_migrations()
        applied_ids = {m.migration_id for m in self.get_applied_migrations()}
        return [m for m in all_migrations if m.migration_id not in applied_ids]

    def get_all_migrations(self) -> list[type[Migration]]:
        """Return all discovered Migration subclasses from the registry."""
        return self._registry.discover()

    def has_been_applied(self, migration_id: str) -> bool:
        """Return True if *migration_id* exists in _migrations."""
        cursor = self._conn.execute(
            "SELECT 1 FROM _migrations WHERE migration_id=?",
            (migration_id,),
        )
        return cursor.fetchone() is not None

    def get_migration_checksum(self, migration_id: str) -> str | None:
        """Return the stored checksum for *migration_id*, or None."""
        cursor = self._conn.execute(
            "SELECT checksum FROM _migrations WHERE migration_id=?",
            (migration_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    # ── Apply ─────────────────────────────────────────────────────

    def apply_all(self) -> MigrationResult:
        """Apply all pending migrations in discovery order.

        Creates a backup before each migration that requires it.
        On failure, rolls back the individual migration's savepoint
        and continues to the next pending migration.

        If all migrations succeed, writes the new schema version.
        """
        pending = self.get_pending_migrations()
        if not pending:
            return MigrationResult(
                success=True,
                applied_count=0,
                failed_count=0,
                results=[],
                backup_id=None,
                final_version=self._read_current_version(),
            )

        backup_id: str | None = None
        results: list[MigrationAttempt] = []
        applied_classes: list[type[Migration]] = []

        for migration_cls in pending:
            migration = migration_cls()

            # ── Backup ─────────────────────────────────────────
            mig_backup_id: str | None = None
            if migration.requires_backup and self._backup is not None:
                bk = self._backup.create_backup(backup_type="pre_migration")
                if not bk.success:
                    results.append(self._build_attempt(
                        migration, 0, f"Backup failed: {bk.error}"
                    ))
                    break
                mig_backup_id = bk.backup_id
                if backup_id is None:
                    backup_id = mig_backup_id

            # ── Apply within savepoint ─────────────────────────
            start = datetime.now(timezone.utc)
            sp = f"mig_{migration.migration_id}"
            try:
                self._conn.execute(f"SAVEPOINT {sp}")
                migration.upgrade(self._conn)

                errors = migration.verify(self._conn)
                if errors:
                    raise MigrationVerificationError(
                        f"Verification failed: {'; '.join(errors)}"
                    )

                checksum = migration.source_checksum()
                applied_at = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                )
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )

                self._conn.execute(
                    "INSERT INTO _migrations "
                    "(migration_id, description, app_version, checksum, "
                    "applied_at, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        migration.migration_id,
                        migration.description,
                        migration.app_version,
                        checksum,
                        applied_at,
                        duration,
                    ),
                )
                self._conn.execute(f"RELEASE SAVEPOINT {sp}")
                self._conn.commit()

                applied_classes.append(migration_cls)
                results.append(self._build_attempt(
                    migration, duration, None, mig_backup_id
                ))

            except Exception as exc:
                try:
                    self._conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                except sqlite3.OperationalError:
                    pass
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                results.append(self._build_attempt(
                    migration, duration, str(exc), mig_backup_id
                ))

        # ── Finalise ───────────────────────────────────────────
        all_ok = all(r.success for r in results)
        final_version = self._compute_final_version(applied_classes)

        if all_ok and final_version:
            self._svm.write(
                SchemaVersion.from_string(final_version),
                description=f"Migration to {final_version}",
            )

        applied = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        return MigrationResult(
            success=all_ok,
            applied_count=applied,
            failed_count=failed,
            results=results,
            backup_id=backup_id,
            final_version=final_version,
        )

    def apply_one(self, migration_id: str) -> MigrationResult:
        """Apply a single migration by ID.

        Returns:
            MigrationResult with one entry in ``results``.
        """
        migration_cls = self._registry.get_by_id(migration_id)
        if migration_cls is None:
            return MigrationResult(
                success=False,
                applied_count=0,
                failed_count=1,
                results=[
                    MigrationAttempt(
                        migration_id=migration_id,
                        description="Unknown migration",
                        success=False,
                        duration_ms=0,
                        error=f"Migration not found: {migration_id}",
                    )
                ],
                backup_id=None,
                final_version=self._read_current_version(),
            )

        if self.has_been_applied(migration_id):
            return MigrationResult(
                success=True,
                applied_count=0,
                failed_count=0,
                results=[],
                backup_id=None,
                final_version=self._read_current_version(),
            )

        # Delegate to internal apply
        result = self._apply_single(migration_cls)
        return result

    # ── Internals ────────────────────────────────────────────────

    def _apply_single(self, migration_cls: type[Migration]) -> MigrationResult:
        """Apply a single migration class, return a single-result summary."""
        migration = migration_cls()

        mig_backup_id: str | None = None
        if migration.requires_backup and self._backup is not None:
            bk = self._backup.create_backup(backup_type="pre_migration")
            if not bk.success:
                result = MigrationResult(
                    success=False,
                    applied_count=0,
                    failed_count=1,
                    results=[
                        self._build_attempt(
                            migration, 0, f"Backup failed: {bk.error}"
                        )
                    ],
                    backup_id=None,
                    final_version=self._read_current_version(),
                )
                return result
            mig_backup_id = bk.backup_id

        start = datetime.now(timezone.utc)
        sp = f"mig_{migration.migration_id}"
        try:
            self._conn.execute(f"SAVEPOINT {sp}")
            migration.upgrade(self._conn)
            errors = migration.verify(self._conn)
            if errors:
                raise MigrationVerificationError(
                    f"Verification failed: {'; '.join(errors)}"
                )

            checksum = migration.source_checksum()
            applied_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            self._conn.execute(
                "INSERT INTO _migrations "
                "(migration_id, description, app_version, checksum, "
                "applied_at, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    migration.migration_id,
                    migration.description,
                    migration.app_version,
                    checksum,
                    applied_at,
                    duration,
                ),
            )
            self._conn.execute(f"RELEASE SAVEPOINT {sp}")
            self._conn.commit()

            self._svm.write(
                SchemaVersion.from_string(migration.app_version),
                description=f"Migration to {migration.app_version}",
            )

            return MigrationResult(
                success=True,
                applied_count=1,
                failed_count=0,
                results=[
                    self._build_attempt(
                        migration, duration, None, mig_backup_id
                    )
                ],
                backup_id=mig_backup_id,
                final_version=migration.app_version,
            )

        except Exception as exc:
            try:
                self._conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except sqlite3.OperationalError:
                pass
            duration = int(
                (datetime.now(timezone.utc) - start).total_seconds() * 1000
            )
            return MigrationResult(
                success=False,
                applied_count=0,
                failed_count=1,
                results=[
                    self._build_attempt(
                        migration, duration, str(exc), mig_backup_id
                    )
                ],
                backup_id=mig_backup_id,
                final_version=self._read_current_version(),
            )

    @staticmethod
    def _build_attempt(
        migration: Migration,
        duration_ms: int,
        error: str | None,
        backup_id: str | None = None,
    ) -> MigrationAttempt:
        return MigrationAttempt(
            migration_id=migration.migration_id,
            description=migration.description,
            success=error is None,
            duration_ms=duration_ms,
            error=error,
            backup_id=backup_id,
        )

    def _read_current_version(self) -> str | None:
        try:
            v = self._svm.read()
            return str(v) if v is not None else None
        except Exception:
            return None

    def _compute_final_version(
        self, applied_classes: list[type[Migration]]
    ) -> str | None:
        if not applied_classes:
            return self._read_current_version()
        return applied_classes[-1].app_version



