"""Tests for MigrationManager — apply, track, rollback, and query."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ── Test helpers ──────────────────────────────────────────────────


_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _migrations (
    migration_id TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    app_version  TEXT NOT NULL,
    checksum     TEXT NOT NULL,
    applied_at   TEXT NOT NULL,
    duration_ms  INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class _FakeBackupResult:
    success: bool
    backup_id: str = ""
    error: str | None = None


class _FakeBackupManager:
    """Records backup calls without touching filesystem."""

    def __init__(self) -> None:
        self.backups_created: list[str] = []
        self.fail_next: bool = False
        self._counter = 0

    def create_backup(self, backup_type: str = "manual") -> _FakeBackupResult:
        self.backups_created.append(backup_type)
        self._counter += 1
        if self.fail_next:
            self.fail_next = False
            return _FakeBackupResult(success=False)
        return _FakeBackupResult(
            success=True, backup_id=f"backup_{self._counter:04d}"
        )


def _make_migration_class(
    migration_id: str,
    description: str,
    app_version: str = "2.0.0",
    requires_backup: bool = True,
    fail_upgrade: bool = False,
    fail_verify: bool = False,
) -> type:
    """Dynamically create a concrete Migration subclass for testing.
    Uses ``type()`` to bypass ``__init_subclass__`` validation.
    """
    from trackora.core.migration_manager import Migration

    _mid = migration_id
    _fail_up = fail_upgrade
    _fail_ver = fail_verify

    def _upgrade(self: object, connection: object) -> None:
        if _fail_up:
            raise RuntimeError(f"Intentional failure in {_mid}")

    def _downgrade(self: object, connection: object) -> None:
        pass

    def _verify(self: object, connection: object) -> list[str]:
        if _fail_ver:
            return [f"Verification failed for {_mid}"]
        return []

    cls = type(
        "_TestMigration",
        (Migration,),
        {
            "migration_id": migration_id,
            "description": description,
            "app_version": app_version,
            "requires_backup": requires_backup,
            "applied": [],
            "upgrade": _upgrade,
            "downgrade": _downgrade,
            "verify": _verify,
        },
    )
    return cls





def _make_registry(
    migrations: list[type],
) -> object:
    """Create a minimal MigrationRegistry-like object for testing."""

    class _TestRegistry:
        _migrations = migrations

        @classmethod
        def discover(cls) -> list[type]:
            return list(cls._migrations)

        @classmethod
        def get_by_id(cls, migration_id: str) -> type | None:
            for m in cls._migrations:
                if m.migration_id == migration_id:
                    return m
            return None

    return _TestRegistry


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(_MIGRATIONS_TABLE_SQL)
    conn.commit()
    return conn


@pytest.fixture
def sv_manager(tmp_path: Path):
    from trackora.core.schema_version import SchemaVersion
    from trackora.core.schema_version_manager import SchemaVersionManager

    svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
    svm.write(SchemaVersion(1, 0, 0), description="test baseline")
    return svm


@pytest.fixture
def mock_backup() -> _FakeBackupManager:
    return _FakeBackupManager()


@pytest.fixture
def sample_migrations():
    m1 = _make_migration_class(
        "v1_0_0_initial", "Initial schema", "1.0.0", requires_backup=False
    )
    m2 = _make_migration_class(
        "v2_0_0_add_features", "Add features", "2.0.0"
    )
    m3 = _make_migration_class(
        "v2_0_0_add_settings", "Add settings", "2.0.0"
    )
    return [m1, m2, m3]


@pytest.fixture
def registry(sample_migrations):
    return _make_registry(sample_migrations)


@pytest.fixture
def manager(db_connection, sv_manager, mock_backup, registry):
    from trackora.core.migration_manager import MigrationManager

    return MigrationManager(
        connection=db_connection,
        schema_version_manager=sv_manager,
        backup_manager=mock_backup,
        registry=registry,
    )


# ── Init ──────────────────────────────────────────────────────────


class TestInit:
    def test_requires_connection(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        with pytest.raises(TypeError):
            MigrationManager()  # type: ignore[call-arg]

    def test_accepts_backup_manager(self, manager) -> None:
        assert manager is not None

    def test_creates_migrations_table_on_access(self, db_connection) -> None:
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.schema_version import SchemaVersion

        svm = SchemaVersionManager(
            schema_path=Path("/nonexistent/schema.json")
        )
        mm = MigrationManager(
            connection=db_connection,
            schema_version_manager=svm,
        )
        # Trigger table creation by accessing applied
        result = mm.get_applied_migrations()
        assert result == []
        # Verify table exists
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
        )
        assert cursor.fetchone() is not None


# ── get_applied_migrations ────────────────────────────────────────


class TestGetAppliedMigrations:
    def test_empty_returns_empty_list(self, manager) -> None:
        assert manager.get_applied_migrations() == []

    def test_single_applied(self, db_connection, manager) -> None:
        db_connection.execute(
            "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)",
            (
                "v1_0_0_initial",
                "Initial schema",
                "1.0.0",
                "abc123",
                "2026-06-20T12:00:00Z",
                0,
            ),
        )
        db_connection.commit()
        result = manager.get_applied_migrations()
        assert len(result) == 1
        assert result[0].migration_id == "v1_0_0_initial"
        assert result[0].checksum == "abc123"

    def test_multiple_applied(self, db_connection, manager) -> None:
        rows = [
            ("v1_0_0_a", "A", "1.0.0", "chk1", "2026-01-01T00:00:00Z", 100),
            ("v2_0_0_b", "B", "2.0.0", "chk2", "2026-06-01T00:00:00Z", 200),
            ("v2_0_0_c", "C", "2.0.0", "chk3", "2026-06-15T00:00:00Z", 150),
        ]
        db_connection.executemany(
            "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)", rows
        )
        db_connection.commit()
        result = manager.get_applied_migrations()
        assert len(result) == 3
        ids = [r.migration_id for r in result]
        assert ids == ["v1_0_0_a", "v2_0_0_b", "v2_0_0_c"]

    def test_applied_migration_has_all_fields(self, db_connection, manager) -> None:
        db_connection.execute(
            "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)",
            ("v1_0_0_x", "Test migration", "1.0.0", "sha256:xyz", "2026-06-20T12:00:00Z", 42),
        )
        db_connection.commit()
        result = manager.get_applied_migrations()
        entry = result[0]
        assert entry.migration_id == "v1_0_0_x"
        assert entry.description == "Test migration"
        assert entry.app_version == "1.0.0"
        assert entry.checksum == "sha256:xyz"
        assert entry.applied_at == "2026-06-20T12:00:00Z"
        assert entry.duration_ms == 42


# ── get_pending_migrations ────────────────────────────────────────


class TestGetPending:
    def test_all_pending_when_no_applied(self, manager) -> None:
        pending = manager.get_pending_migrations()
        assert len(pending) == 3
        assert [m.migration_id for m in pending] == [
            "v1_0_0_initial",
            "v2_0_0_add_features",
            "v2_0_0_add_settings",
        ]

    def test_some_pending(self, db_connection, manager) -> None:
        db_connection.execute(
            "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)",
            ("v1_0_0_initial", "done", "1.0.0", "chk", "2026-01-01T00:00:00Z", 0),
        )
        db_connection.commit()
        pending = manager.get_pending_migrations()
        assert len(pending) == 2
        assert [m.migration_id for m in pending] == [
            "v2_0_0_add_features",
            "v2_0_0_add_settings",
        ]

    def test_none_pending_when_all_applied(self, db_connection, manager) -> None:
        for mid in ["v1_0_0_initial", "v2_0_0_add_features", "v2_0_0_add_settings"]:
            db_connection.execute(
                "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)",
                (mid, "done", "2.0.0", "chk", "2026-06-01T00:00:00Z", 0),
            )
        db_connection.commit()
        assert manager.get_pending_migrations() == []

    def test_pending_empty_registry(self, db_connection, sv_manager) -> None:
        from trackora.core.migration_manager import MigrationManager

        empty_registry = _make_registry([])
        mm = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=empty_registry,
        )
        assert mm.get_pending_migrations() == []


# ── get_all_migrations ────────────────────────────────────────────


class TestGetAll:
    def test_returns_all_from_registry(self, manager) -> None:
        all_m = manager.get_all_migrations()
        assert len(all_m) == 3
        assert [m.migration_id for m in all_m] == [
            "v1_0_0_initial",
            "v2_0_0_add_features",
            "v2_0_0_add_settings",
        ]


# ── has_been_applied ──────────────────────────────────────────────


class TestHasBeenApplied:
    def test_true_when_applied(self, db_connection, manager) -> None:
        db_connection.execute(
            "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)",
            ("v1_0_0_initial", "done", "1.0.0", "chk", "2026-01-01T00:00:00Z", 0),
        )
        db_connection.commit()
        assert manager.has_been_applied("v1_0_0_initial") is True

    def test_false_when_not_applied(self, manager) -> None:
        assert manager.has_been_applied("nonexistent") is False

    def test_false_when_partially_applied(self, db_connection, manager) -> None:
        db_connection.execute(
            "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)",
            ("v1_0_0_initial", "done", "1.0.0", "chk", "2026-01-01T00:00:00Z", 0),
        )
        db_connection.commit()
        assert manager.has_been_applied("v2_0_0_add_features") is False


# ── get_migration_checksum ────────────────────────────────────────


class TestGetMigrationChecksum:
    def test_returns_checksum_when_found(self, db_connection, manager) -> None:
        db_connection.execute(
            "INSERT INTO _migrations VALUES (?, ?, ?, ?, ?, ?)",
            ("v1_0_0_initial", "done", "1.0.0", "sha256:abc123", "2026-01-01T00:00:00Z", 0),
        )
        db_connection.commit()
        assert manager.get_migration_checksum("v1_0_0_initial") == "sha256:abc123"

    def test_returns_none_when_not_found(self, manager) -> None:
        assert manager.get_migration_checksum("nonexistent") is None


# ── apply_one ─────────────────────────────────────────────────────


class TestApplyOne:
    def test_apply_one_success(self, manager) -> None:
        result = manager.apply_one("v1_0_0_initial")
        assert result.success is True
        assert result.applied_count == 1
        assert result.failed_count == 0

    def test_applied_migration_appears_in_applied(self, manager) -> None:
        manager.apply_one("v1_0_0_initial")
        assert manager.has_been_applied("v1_0_0_initial") is True

    def test_apply_one_already_applied_returns_zero(self, manager) -> None:
        manager.apply_one("v1_0_0_initial")
        result = manager.apply_one("v1_0_0_initial")
        assert result.success is True
        assert result.applied_count == 0
        assert result.failed_count == 0

    def test_apply_one_unknown_migration_returns_failure(self, manager) -> None:
        result = manager.apply_one("nonexistent")
        assert result.success is False
        assert result.applied_count == 0

    def test_apply_one_records_checksum(self, db_connection, manager) -> None:
        manager.apply_one("v1_0_0_initial")
        cursor = db_connection.execute(
            "SELECT checksum, duration_ms FROM _migrations WHERE migration_id=?",
            ("v1_0_0_initial",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert len(row[0]) == 64  # SHA-256 hex
        assert row[1] >= 0

    def test_apply_one_rolls_back_on_upgrade_failure(
        self, db_connection, manager, sample_migrations
    ) -> None:
        bad_migration = sample_migrations[0]
        original_id = bad_migration.migration_id
        bad_migration._fail_upgrade = True
        # We need a migration that fails during upgrade
        # Use a fresh one with fail_upgrade=True
        fail_cls = _make_migration_class(
            "v9_9_9_fail", "Failing migration", fail_upgrade=True
        )
        fail_registry = _make_registry([fail_cls])
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.schema_version import SchemaVersion
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        svm = SchemaVersionManager(
            schema_path=Path(tmp_path)
        )
        svm.write(SchemaVersion(1, 0, 0))
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=svm,
            registry=fail_registry,
        )
        result = mgr.apply_one("v9_9_9_fail")
        assert result.success is False
        assert result.results[0].error is not None
        assert "Intentional failure" in result.results[0].error

    def test_apply_one_rolls_back_on_verify_failure(
        self, db_connection
    ) -> None:
        import tempfile
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.schema_version import SchemaVersion

        fail_cls = _make_migration_class(
            "v9_9_9_verify_fail", "Verify fail", fail_verify=True
        )
        fail_registry = _make_registry([fail_cls])
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        svm = SchemaVersionManager(
            schema_path=Path(tmp_path)
        )
        svm.write(SchemaVersion(1, 0, 0))
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=svm,
            registry=fail_registry,
        )
        result = mgr.apply_one("v9_9_9_verify_fail")
        assert result.success is False
        # Migration should NOT be in applied after verify failure
        assert mgr.has_been_applied("v9_9_9_verify_fail") is False

    def test_apply_one_backup_created_when_required(
        self, manager, mock_backup
    ) -> None:
        # v2_0_0_add_features has requires_backup=True (default)
        manager.apply_one("v2_0_0_add_features")
        assert len(mock_backup.backups_created) == 1
        assert mock_backup.backups_created[0] == "pre_migration"

    def test_apply_one_no_backup_when_not_required(
        self, manager, mock_backup
    ) -> None:
        # v1_0_0_initial has requires_backup=False
        manager.apply_one("v1_0_0_initial")
        assert len(mock_backup.backups_created) == 0

    def test_apply_one_backup_id_in_result(self, manager) -> None:
        result = manager.apply_one("v2_0_0_add_features")
        assert result.backup_id is not None
        assert result.backup_id.startswith("backup_")


# ── apply_all ─────────────────────────────────────────────────────


class TestApplyAll:
    def test_no_pending_returns_success(self, db_connection, manager) -> None:
        # Apply all first
        manager.apply_all()
        result = manager.apply_all()
        assert result.success is True
        assert result.applied_count == 0

    def test_apply_all_success_multiple(self, manager) -> None:
        result = manager.apply_all()
        assert result.success is True
        assert result.applied_count == 3
        assert result.failed_count == 0
        assert result.final_version == "2.0.0"

    def test_apply_all_records_all_in_database(self, db_connection, manager) -> None:
        manager.apply_all()
        cursor = db_connection.execute(
            "SELECT migration_id FROM _migrations ORDER BY migration_id"
        )
        rows = cursor.fetchall()
        assert [r[0] for r in rows] == [
            "v1_0_0_initial",
            "v2_0_0_add_features",
            "v2_0_0_add_settings",
        ]

    def test_apply_all_idempotent(self, manager) -> None:
        manager.apply_all()
        # Apply again — nothing should change
        result = manager.apply_all()
        assert result.success is True
        assert result.applied_count == 0

    def test_apply_all_writes_schema_version(self, manager, sv_manager) -> None:
        manager.apply_all()
        version = sv_manager.read()
        assert version is not None
        assert str(version) == "2.0.0"

    def test_apply_all_backup_before_each_migration(
        self, manager, mock_backup
    ) -> None:
        manager.apply_all()
        # 2 migrations with requires_backup=True, 1 with False
        assert len(mock_backup.backups_created) == 2
        for bt in mock_backup.backups_created:
            assert bt == "pre_migration"

    def test_apply_all_aborts_on_backup_failure(
        self, db_connection, sample_migrations, sv_manager
    ) -> None:
        from trackora.core.migration_manager import MigrationManager

        backup = _FakeBackupManager()
        backup.fail_next = True
        # Only one migration with requires_backup=True
        single_mig = _make_migration_class(
            "v2_0_0_only", "Single migration", requires_backup=True
        )
        reg = _make_registry([single_mig])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            backup_manager=backup,
            registry=reg,
        )
        result = mgr.apply_all()
        assert result.success is False
        assert result.applied_count == 0
        assert mgr.has_been_applied("v2_0_0_only") is False

    def test_apply_all_returns_result_with_attempts(self, manager) -> None:
        result = manager.apply_all()
        assert len(result.results) == 3
        for attempt in result.results:
            assert attempt.success is True
            assert attempt.duration_ms >= 0


# ── Edge Cases and Error Handling ─────────────────────────────────


class TestEdgeCases:
    def test_handles_schema_not_written(self, db_connection) -> None:
        """Should not crash if schema version has not been written yet."""
        import tempfile
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.schema_version_manager import SchemaVersionManager

        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        svm = SchemaVersionManager(
            schema_path=Path(tmp_path)
        )
        single = _make_migration_class(
            "v1_0_0_test", "Test migration", requires_backup=False
        )
        reg = _make_registry([single])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=svm,
            registry=reg,
        )
        # read() returns None (never written) — should still work
        result = mgr.apply_all()
        assert result.success is True
        # migration defaults to app_version="2.0.0"
        assert result.final_version == "2.0.0"

    def test_handles_autocreate_migrations_table(self, db_connection) -> None:
        """Drop the _migrations table; manager should recreate it."""
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.schema_version import SchemaVersion
        import tempfile

        db_connection.execute("DROP TABLE IF EXISTS _migrations")
        db_connection.commit()

        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        svm = SchemaVersionManager(
            schema_path=Path(tmp_path)
        )
        svm.write(SchemaVersion(1, 0, 0))
        single = _make_migration_class(
            "v1_0_0_test", "Test migration", requires_backup=False
        )
        reg = _make_registry([single])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=svm,
            registry=reg,
        )
        result = mgr.apply_all()
        assert result.success is True
        assert result.applied_count == 1
        # Verify table was recreated
        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
        )
        assert cursor.fetchone() is not None

    def test_schema_version_not_updated_on_partial_failure(
        self, db_connection, sv_manager
    ) -> None:
        import tempfile
        from trackora.core.migration_manager import MigrationManager

        good = _make_migration_class(
            "v1_0_0_good", "Good migration", "1.0.0", requires_backup=False
        )
        bad = _make_migration_class(
            "v2_0_0_bad", "Bad migration", "2.0.0",
            requires_backup=False, fail_upgrade=True,
        )
        reg = _make_registry([good, bad])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        result = mgr.apply_all()
        assert result.success is False
        assert result.applied_count == 1
        assert result.failed_count == 1
        # Good migration should be applied
        assert mgr.has_been_applied("v1_0_0_good") is True
        # Bad migration should NOT be applied
        assert mgr.has_been_applied("v2_0_0_bad") is False
        # Schema version should remain at original (1.0.0)
        assert str(sv_manager.read()) == "1.0.0"
