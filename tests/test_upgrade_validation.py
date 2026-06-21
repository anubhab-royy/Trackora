"""Phase 13D — Upgrade Validation.

Validates six key areas of the upgrade foundation:

1. Legacy upgrade (v1.x → v2.0.0)
2. Migration idempotency
3. Downgrade protection
4. Migration failure handling
5. Schema version updates
6. Migration record integrity

Each group is self-contained with its own fixtures.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trackora.core.schema_version import CompatibilityStatus, SchemaVersion, SchemaVersionError
from trackora.core.schema_version_manager import SchemaVersionManager


# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

_BASE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    process_name     TEXT    NOT NULL,
    executable_path  TEXT    NOT NULL,
    icon_path        TEXT    NOT NULL DEFAULT '',
    is_enabled       INTEGER NOT NULL DEFAULT 1,
    first_played     DATETIME,
    last_played      DATETIME,
    created_at       DATETIME NOT NULL,
    updated_at       DATETIME NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id          INTEGER  NOT NULL,
    start_time       DATETIME NOT NULL,
    end_time         DATETIME NOT NULL,
    duration_seconds INTEGER  NOT NULL,
    created_at       DATETIME NOT NULL,
    FOREIGN KEY (game_id) REFERENCES games (id)
);
CREATE TABLE IF NOT EXISTS active_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id    INTEGER  NOT NULL,
    process_id INTEGER  NOT NULL,
    start_time DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (game_id) REFERENCES games (id)
);
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT     PRIMARY KEY,
    value      TEXT     NOT NULL DEFAULT '',
    updated_at DATETIME NOT NULL
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
    """Dynamically create a concrete Migration subclass for testing."""
    from trackora.core.migration_manager import Migration

    _mid = migration_id
    _fail_up = fail_upgrade
    _fail_ver = fail_verify
    _req_backup = requires_backup

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
            "requires_backup": _req_backup,
            "upgrade": _upgrade,
            "downgrade": _downgrade,
            "verify": _verify,
        },
    )
    return cls


def _make_registry(migrations: list[type]) -> object:
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


def _populate_v1x_data(conn: sqlite3.Connection) -> None:
    """Insert realistic v1.x seed data into an empty base schema."""
    now = datetime.now(timezone.utc).isoformat()
    conn.executescript(_BASE_SCHEMA_SQL)

    conn.execute(
        "INSERT INTO games (name, process_name, executable_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Witcher 3", "witcher3.exe", "/games/witcher3/witcher3.exe", now, now),
    )
    conn.execute(
        "INSERT INTO games (name, process_name, executable_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Hades", "hades.exe", "/games/hades/hades.exe", now, now),
    )
    conn.execute(
        "INSERT INTO games (name, process_name, executable_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Elden Ring", "eldenring.exe", "/games/eldenring/eldenring.exe", now, now),
    )

    conn.execute(
        "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "2024-01-15T10:00:00", "2024-01-15T14:30:00", 16200, now),
    )
    conn.execute(
        "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "2024-01-16T09:00:00", "2024-01-16T11:00:00", 7200, now),
    )
    conn.execute(
        "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (2, "2024-02-20T15:00:00", "2024-02-20T17:30:00", 9000, now),
    )

    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("theme", "dark", now),
    )
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("language", "en", now),
    )
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("auto_start", "true", now),
    )
    conn.commit()


def _count_games(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]


def _count_sessions(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]


def _count_settings(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]


def _get_game_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM games ORDER BY id").fetchall()}


def _get_setting_keys(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT key FROM settings ORDER BY key").fetchall()}


def _get_migration_ids(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.execute(
        "SELECT migration_id FROM _migrations ORDER BY migration_id"
    )
    return [row[0] for row in cursor.fetchall()]


def _assert_iso8601(s: str) -> None:
    """Assert a string is valid ISO-8601 format."""
    try:
        datetime.fromisoformat(s)
    except (ValueError, TypeError):
        pytest.fail(f"Not a valid ISO-8601 datetime: {s!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# Group 1: Legacy Upgrade (v1.x → v2.0.0)
# ═══════════════════════════════════════════════════════════════════════════════

# Use the real production migrations to validate the actual upgrade path.
_REAL_MIGRATIONS_PACKAGE = "trackora.core.migrations"


class TestLegacyUpgradeV1ToV20:
    """Validate that a real v1.x database upgrades cleanly to v2.0.0."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        """Create a v1.x database and schema manager for each test."""
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.migrations.registry import MigrationRegistry

        self.db_path = tmp_path / "trackora.db"
        self.conn = sqlite3.connect(str(self.db_path))

        _populate_v1x_data(self.conn)

        self.schema_path = tmp_path / "schema.json"
        self.svm = SchemaVersionManager(schema_path=self.schema_path)
        self.svm.write(SchemaVersion(1, 0, 0), description="v1.0.0 baseline")

        self.registry = MigrationRegistry

    def teardown_method(self) -> None:
        self.conn.close()

    def _make_mgr(self, backup_manager: object | None = None):
        from trackora.core.migration_manager import MigrationManager

        return MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            backup_manager=backup_manager,
            registry=self.registry,
        )

    # TC1: Games preservation
    def test_games_preserved_after_upgrade(self) -> None:
        game_names_before = _get_game_names(self.conn)
        game_count_before = _count_games(self.conn)

        mm = self._make_mgr()
        result = mm.apply_all()
        assert result.success is True

        game_names_after = _get_game_names(self.conn)
        game_count_after = _count_games(self.conn)

        assert game_names_after == game_names_before
        assert game_count_after == game_count_before

    # TC2: Sessions preservation
    def test_sessions_preserved_after_upgrade(self) -> None:
        count_before = _count_sessions(self.conn)
        mm = self._make_mgr()
        result = mm.apply_all()
        assert result.success is True
        assert _count_sessions(self.conn) == count_before

    # TC3: Settings preservation
    def test_settings_preserved_after_upgrade(self) -> None:
        keys_before = _get_setting_keys(self.conn)
        count_before = _count_settings(self.conn)

        mm = self._make_mgr()
        result = mm.apply_all()
        assert result.success is True

        keys_after = _get_setting_keys(self.conn)
        # Original keys must be preserved
        assert keys_before.issubset(keys_after), f"Original keys {keys_before} not subset of {keys_after}"
        # New settings may be added by migrations, so count should be >=
        assert _count_settings(self.conn) >= count_before

    # TC4: All real migrations applied
    def test_all_real_migrations_applied(self) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        all_migrations = MigrationRegistry.discover()
        expected_count = len(all_migrations)

        mm = self._make_mgr()
        result = mm.apply_all()
        assert result.success is True
        assert result.applied_count == expected_count

        applied = _get_migration_ids(self.conn)
        expected_ids = [m.migration_id for m in all_migrations]
        assert applied == expected_ids

    # TC5: Discovery order matches application order
    def test_migration_discovery_order_preserved(self) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        all_migrations = MigrationRegistry.discover()
        expected_order = [m.migration_id for m in all_migrations]

        mm = self._make_mgr()
        mm.apply_all()

        applied = _get_migration_ids(self.conn)
        assert applied == expected_order

    # TC6: v1.1.0 → v2.0.0 real migration path
    def test_v1_1_to_v2_0_real_migration(self) -> None:
        self.svm.write(SchemaVersion(1, 1, 0), description="v1.1.0")

        compat = self.svm.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 1, 0))
        assert compat.can_proceed is True
        assert compat.status == "needs_migration"

        mm = self._make_mgr()
        result = mm.apply_all()
        assert result.success is True
        assert result.applied_count >= 1

        written = self.svm.read()
        assert written is not None
        assert str(written) == "2.0.0"


class TestLegacyUpgradeWithBackup:
    """Validate upgrade with a real BackupManager (not fake)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        from trackora.core.backup_manager import BackupManager
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.migrations.registry import MigrationRegistry
        from trackora.core import paths as core_paths

        self.schema_path = tmp_path / "schema.json"
        self.svm = SchemaVersionManager(schema_path=self.schema_path)
        self.svm.write(SchemaVersion(1, 0, 0))

        self.db_path = tmp_path / "trackora.db"
        self.conn = sqlite3.connect(str(self.db_path))
        _populate_v1x_data(self.conn)
        self.conn.close()

        self.backup_dir = tmp_path / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._orig_db_path = core_paths.DATABASE_PATH
        core_paths.DATABASE_PATH = self.db_path

        self.bm = BackupManager(
            schema_version_manager=self.svm,
            backup_dir=self.backup_dir,
        )

    def teardown_method(self) -> None:
        from trackora.core import paths as core_paths

        core_paths.DATABASE_PATH = self._orig_db_path
        if hasattr(self, "conn") and self.conn:
            self.conn.close()

    def test_upgrade_with_backup_verify(self) -> None:
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.migrations.registry import MigrationRegistry

        conn = sqlite3.connect(str(self.db_path))
        try:
            bk = self.bm.create_backup(backup_type="pre_migration")
            assert bk.success is True

            verify = self.bm.verify_backup(bk.backup_id)
            assert verify.valid is True

            mm = MigrationManager(
                connection=conn,
                schema_version_manager=self.svm,
                backup_manager=self.bm,
                registry=MigrationRegistry,
            )
            result = mm.apply_all()
            assert result.success is True
            assert result.applied_count >= 1

            backups = self.bm.list_backups()
            assert len(backups) >= 1

            assert str(self.svm.read()) == "2.0.0"
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Group 2: Migration Idempotency
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigrationIdempotency:
    """Apply_all must be safe to call any number of times."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        from trackora.core.migration_manager import MigrationManager

        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(_BASE_SCHEMA_SQL)
        self.conn.commit()

        self.svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        self.svm.write(SchemaVersion(1, 0, 0))

        m1 = _make_migration_class("v2_0_0_a", "Migration A", "2.0.0")
        m2 = _make_migration_class("v2_0_0_b", "Migration B", "2.0.0")
        registry = _make_registry([m1, m2])

        self.mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=registry,
        )

    def teardown_method(self) -> None:
        self.conn.close()

    def test_apply_all_twice_no_change(self) -> None:
        r1 = self.mm.apply_all()
        assert r1.applied_count == 2
        assert r1.success is True

        r2 = self.mm.apply_all()
        assert r2.applied_count == 0
        assert r2.success is True

    def test_apply_all_three_times_stable(self) -> None:
        self.mm.apply_all()
        self.mm.apply_all()
        r3 = self.mm.apply_all()
        assert r3.applied_count == 0
        assert r3.success is True

    def test_database_state_unchanged_after_reapply(self) -> None:
        self.mm.apply_all()
        cols_before = {
            r[1]
            for r in self.conn.execute("PRAGMA table_info(games)").fetchall()
        }

        self.mm.apply_all()
        self.mm.apply_all()

        cols_after = {
            r[1]
            for r in self.conn.execute("PRAGMA table_info(games)").fetchall()
        }
        assert cols_after == cols_before

    def test_schema_version_unchanged_on_reapply(self) -> None:
        self.mm.apply_all()
        v1 = self.svm.read()

        self.mm.apply_all()
        v2 = self.svm.read()

        assert v1 == v2

    def test_partial_apply_then_full(self) -> None:
        r1 = self.mm.apply_one("v2_0_0_a")
        assert r1.applied_count == 1

        pending = self.mm.get_pending_migrations()
        assert len(pending) == 1

        r2 = self.mm.apply_all()
        assert r2.applied_count == 1
        assert r2.success is True

        r3 = self.mm.apply_all()
        assert r3.applied_count == 0

    def test_apply_one_twice_is_no_op(self) -> None:
        r1 = self.mm.apply_one("v2_0_0_a")
        assert r1.applied_count == 1

        r2 = self.mm.apply_one("v2_0_0_a")
        assert r2.applied_count == 0
        assert r2.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# Group 3: Downgrade Protection
# ═══════════════════════════════════════════════════════════════════════════════


class TestDowngradeProtection:
    """Older app versions must be blocked from newer schema data."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.schema_path = tmp_path / "schema.json"
        self.svm = SchemaVersionManager(schema_path=self.schema_path)

    # TC8: Downgrade blocked — app v1.1.0 trying to read v2.0.0 data
    def test_downgrade_v1_app_blocked_from_v2_data(self) -> None:
        self.svm.write(SchemaVersion(2, 0, 0))
        data = self.svm.read()
        status = self.svm.is_compatible(SchemaVersion(1, 1, 0), data)
        assert status.can_proceed is False
        assert status.status == "newer_data"

    def test_downgrade_error_message_clear(self) -> None:
        self.svm.write(SchemaVersion(2, 0, 0))
        data = self.svm.read()
        status = self.svm.is_compatible(SchemaVersion(1, 1, 0), data)
        assert "requires Trackora" in status.message
        assert "2.0.0" in status.message

    def test_downgrade_major_version_blocked(self) -> None:
        self.svm.write(SchemaVersion(3, 0, 0))
        data = self.svm.read()
        status = self.svm.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is False

    def test_downgrade_minor_version_blocked(self) -> None:
        self.svm.write(SchemaVersion(2, 5, 0))
        data = self.svm.read()
        status = self.svm.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is False

    def test_same_version_not_blocked(self) -> None:
        self.svm.write(SchemaVersion(2, 0, 0))
        data = self.svm.read()
        status = self.svm.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "ok"

    def test_older_data_not_blocked(self) -> None:
        self.svm.write(SchemaVersion(1, 1, 0))
        data = self.svm.read()
        status = self.svm.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "needs_migration"

    def test_no_schema_not_blocked(self) -> None:
        data = self.svm.read()
        status = self.svm.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "first_run"


# ═══════════════════════════════════════════════════════════════════════════════
# Group 4: Migration Failure Handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigrationFailureHandling:
    """Migrations must roll back cleanly on failure without corrupting state."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        from trackora.core.migration_manager import MigrationManager

        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(_BASE_SCHEMA_SQL)
        self.conn.commit()

        self.svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        self.svm.write(SchemaVersion(1, 0, 0))

    def teardown_method(self) -> None:
        self.conn.close()

    def test_upgrade_exception_rolled_back(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        bad = _make_migration_class("v9_9_9_fail", "Fails", fail_upgrade=True)
        registry = _make_registry([bad])
        mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        result = mm.apply_all()
        assert result.success is False
        assert result.applied_count == 0
        assert mm.has_been_applied("v9_9_9_fail") is False

    def test_verify_failure_rolled_back(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        bad = _make_migration_class("v9_9_9_verify_fail", "Fails verify", fail_verify=True)
        registry = _make_registry([bad])
        mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        result = mm.apply_all()
        assert result.success is False
        assert mm.has_been_applied("v9_9_9_verify_fail") is False

    def test_backup_failure_blocks_migration(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        backup = _FakeBackupManager()
        backup.fail_next = True

        mig = _make_migration_class(
            "v2_0_0_needs_backup", "Needs backup", requires_backup=True
        )
        registry = _make_registry([mig])
        mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            backup_manager=backup,
            registry=registry,
        )
        result = mm.apply_all()
        assert result.success is False
        assert result.applied_count == 0
        assert mm.has_been_applied("v2_0_0_needs_backup") is False

    def test_good_then_bad_then_good(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        good_a = _make_migration_class(
            "v2_0_0_good_a", "Good A", "2.0.0", requires_backup=False
        )
        bad = _make_migration_class(
            "v2_0_0_bad", "Bad", "2.0.0", requires_backup=False, fail_upgrade=True
        )
        good_b = _make_migration_class(
            "v2_0_0_good_b", "Good B", "2.0.0", requires_backup=False
        )
        registry = _make_registry([good_a, bad, good_b])
        mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        result = mm.apply_all()
        # MigrationManager continues after a failure (best-effort)
        assert result.success is False
        assert result.applied_count == 2  # good_a and good_b succeed
        assert result.failed_count == 1  # bad fails
        assert mm.has_been_applied("v2_0_0_good_a") is True
        assert mm.has_been_applied("v2_0_0_bad") is False
        assert mm.has_been_applied("v2_0_0_good_b") is True

    def test_schema_version_not_updated_on_failure(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        self.svm.write(SchemaVersion(1, 0, 0))
        bad = _make_migration_class("v2_0_0_bad", "Bad", fail_upgrade=True)
        registry = _make_registry([bad])
        mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        mm.apply_all()
        assert self.svm.read() == SchemaVersion(1, 0, 0)

    def test_partial_failure_still_records_good_ones(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        good_a = _make_migration_class(
            "v2_0_0_good_a", "Good A", requires_backup=False
        )
        bad = _make_migration_class(
            "v2_0_0_bad", "Bad", fail_upgrade=True, requires_backup=False
        )
        registry = _make_registry([good_a, bad])
        mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        result = mm.apply_all()
        assert result.success is False
        assert result.applied_count == 1
        assert mm.has_been_applied("v2_0_0_good_a") is True

    def test_migration_error_contains_message(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        bad = _make_migration_class("v2_0_0_bad", "Bad", fail_upgrade=True)
        registry = _make_registry([bad])
        mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        result = mm.apply_all()
        assert result.results[0].error is not None
        assert "Intentional failure" in result.results[0].error


# ═══════════════════════════════════════════════════════════════════════════════
# Group 5: Schema Version Updates
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemaVersionUpdates:
    """Schema version must be written/updated correctly after migration events."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.schema_path = tmp_path / "schema.json"
        self.svm = SchemaVersionManager(schema_path=self.schema_path)

    def test_version_written_after_successful_migration(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        conn = sqlite3.connect(":memory:")
        conn.executescript(_BASE_SCHEMA_SQL)
        conn.commit()

        self.svm.write(SchemaVersion(1, 0, 0))
        mig = _make_migration_class(
            "v2_0_0_final", "Final migration", "2.0.0", requires_backup=False
        )
        registry = _make_registry([mig])
        mm = MigrationManager(
            connection=conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        result = mm.apply_all()
        assert result.success is True
        assert self.svm.read() == SchemaVersion(2, 0, 0)
        conn.close()

    def test_version_matches_last_migration(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        conn = sqlite3.connect(":memory:")
        conn.executescript(_BASE_SCHEMA_SQL)
        conn.commit()

        self.svm.write(SchemaVersion(1, 0, 0))
        m1 = _make_migration_class(
            "v2_0_0_a", "Mig A", "2.0.0", requires_backup=False
        )
        m2 = _make_migration_class(
            "v2_0_0_b", "Mig B", "2.0.0", requires_backup=False
        )
        registry = _make_registry([m1, m2])
        mm = MigrationManager(
            connection=conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        mm.apply_all()
        assert self.svm.read() == SchemaVersion(2, 0, 0)
        conn.close()

    def test_version_unchanged_on_no_op(self) -> None:
        from trackora.core.migration_manager import MigrationManager

        conn = sqlite3.connect(":memory:")
        conn.executescript(_BASE_SCHEMA_SQL)
        conn.commit()

        self.svm.write(SchemaVersion(2, 0, 0))

        mig = _make_migration_class(
            "v2_0_0_a", "Mig A", "2.0.0", requires_backup=False
        )
        registry = _make_registry([mig])
        mm = MigrationManager(
            connection=conn,
            schema_version_manager=self.svm,
            registry=registry,
        )
        mm.apply_one("v2_0_0_a")
        result = mm.apply_all()
        assert result.applied_count == 0
        assert self.svm.read() == SchemaVersion(2, 0, 0)
        conn.close()

    def test_version_persists_across_read_write_cycle(self) -> None:
        self.svm.write(SchemaVersion(2, 0, 0))
        v1 = self.svm.read()

        self.svm.write(v1)
        v2 = self.svm.read()
        assert v1 == v2 == SchemaVersion(2, 0, 0)

    def test_json_structure_correct(self) -> None:
        self.svm.write(SchemaVersion(2, 0, 0), description="test version")
        data = json.loads(self.schema_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "2.0.0"
        assert data["app_version"] == "2.0.0"
        assert "updated_at" in data and data["updated_at"].endswith("Z")
        assert data.get("description") == "test version"

    def test_first_run_writes_current_version(self) -> None:
        app_ver = SchemaVersion.current_app_version()
        assert self.svm.read() is None

        self.svm.write(app_ver)
        assert self.svm.read() == app_ver


# ═══════════════════════════════════════════════════════════════════════════════
# Group 6: Migration Record Integrity
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigrationRecordIntegrity:
    """Every applied migration must have a complete, valid record in _migrations."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        from trackora.core.migration_manager import MigrationManager

        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(_BASE_SCHEMA_SQL)
        self.conn.commit()

        self.svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        self.svm.write(SchemaVersion(1, 0, 0))

        self.migs = [
            _make_migration_class("v2_0_0_first", "First", "2.0.0", requires_backup=False),
            _make_migration_class("v2_0_0_second", "Second", "2.0.0", requires_backup=False),
            _make_migration_class("v2_0_0_third", "Third", "2.0.0", requires_backup=False),
        ]
        self.registry = _make_registry(self.migs)
        self.mm = MigrationManager(
            connection=self.conn,
            schema_version_manager=self.svm,
            registry=self.registry,
        )

    def teardown_method(self) -> None:
        self.conn.close()

    def _fetch_all_records(self) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT migration_id, description, app_version, checksum, "
            "applied_at, duration_ms FROM _migrations ORDER BY migration_id"
        )
        rows = cursor.fetchall()
        return [
            {
                "migration_id": r[0],
                "description": r[1],
                "app_version": r[2],
                "checksum": r[3],
                "applied_at": r[4],
                "duration_ms": r[5],
            }
            for r in rows
        ]

    def test_migration_id_unique(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        ids = [r["migration_id"] for r in records]
        assert len(ids) == len(set(ids))

    def test_all_required_fields_present(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        required = {"migration_id", "description", "app_version", "checksum", "applied_at", "duration_ms"}
        for record in records:
            assert required.issubset(record.keys()), f"Missing fields in {record['migration_id']}"

    def test_checksum_is_sha256(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        for r in records:
            assert len(r["checksum"]) == 64
            assert all(c in "0123456789abcdef" for c in r["checksum"])

    def test_applied_at_iso8601(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        for r in records:
            _assert_iso8601(r["applied_at"])

    def test_duration_ms_non_negative(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        for r in records:
            assert r["duration_ms"] >= 0

    def test_app_version_correct(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        for r in records:
            assert r["app_version"] == "2.0.0"

    def test_description_not_empty(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        for r in records:
            assert len(r["description"]) > 0

    def test_ordering_matches_discovery(self) -> None:
        self.mm.apply_all()
        records = self._fetch_all_records()
        ids = [r["migration_id"] for r in records]
        assert ids == ["v2_0_0_first", "v2_0_0_second", "v2_0_0_third"]

    def test_no_orphan_records(self) -> None:
        self.mm.apply_one("v2_0_0_first")
        records = self._fetch_all_records()
        assert len(records) == 1
        assert records[0]["migration_id"] == "v2_0_0_first"

    def test_records_survive_second_apply_no_change(self) -> None:
        self.mm.apply_all()
        records_before = self._fetch_all_records()
        self.mm.apply_all()
        records_after = self._fetch_all_records()
        assert records_before == records_after

    def test_checksum_stable_across_runs(self) -> None:
        self.mm.apply_one("v2_0_0_first")
        checksum_1 = self.mm.get_migration_checksum("v2_0_0_first")

        conn2 = sqlite3.connect(":memory:")
        conn2.executescript(_BASE_SCHEMA_SQL)
        conn2.commit()
        svm2 = SchemaVersionManager(schema_path=self.svm._schema_path.parent / "schema2.json")
        svm2.write(SchemaVersion(1, 0, 0))
        mm2 = type(self.mm)(
            connection=conn2,
            schema_version_manager=svm2,
            registry=self.registry,
        )
        mm2.apply_one("v2_0_0_first")
        checksum_2 = mm2.get_migration_checksum("v2_0_0_first")
        conn2.close()

        assert checksum_1 == checksum_2


class TestRealMigrationRecordIntegrity:
    """Validate _migrations records using real production migrations."""

    def test_real_migrations_have_valid_ids(self) -> None:
        from trackora.core.migrations.registry import MigrationRegistry
        import re

        pattern = re.compile(r"^v\d+_\d+_\d+_[a-z0-9_]+$")
        all_migs = MigrationRegistry.discover()
        for m in all_migs:
            assert pattern.match(m.migration_id), f"Invalid migration_id: {m.migration_id}"

    def test_real_migrations_have_descriptions(self) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        all_migs = MigrationRegistry.discover()
        for m in all_migs:
            assert len(m.description) > 0
            assert m.description is not None

    def test_real_migrations_have_valid_app_versions(self) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        all_migs = MigrationRegistry.discover()
        for m in all_migs:
            assert SchemaVersion.is_valid_format(m.app_version)

    def test_real_migrations_sorted_by_version(self) -> None:
        from trackora.core.migrations.registry import MigrationRegistry

        all_migs = MigrationRegistry.discover()
        ids = [m.migration_id for m in all_migs]
        assert ids == sorted(ids), f"Real migrations not sorted: {ids}"


# ═══════════════════════════════════════════════════════════════════════════════
# Group 7: End-to-End First Run Flow
# ═══════════════════════════════════════════════════════════════════════════════


class TestFirstRunFlow:
    """First run (no schema.json) must write current version and skip migrations
    by marking them as applied."""

    def test_first_run_writes_current_app_version(self, tmp_path: Path) -> None:
        svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        assert svm.read() is None

        app_ver = SchemaVersion.current_app_version()
        data_ver = svm.read()
        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.status == "first_run"

        svm.write(app_ver)
        assert svm.read() == app_ver

    def test_first_run_allows_normal_startup(self, tmp_path: Path) -> None:
        """After first-run write, compatibility check returns 'ok'."""
        svm = SchemaVersionManager(schema_path=tmp_path / "schema.json")
        svm.write(SchemaVersion.current_app_version())

        data_ver = svm.read()
        compat = svm.is_compatible(SchemaVersion.current_app_version(), data_ver)
        assert compat.can_proceed is True
        assert compat.status == "ok"


class TestSchemaCreateIndexRegression:
    """Regression tests for RB-9: v1.1.0→v2.0.0 schema upgrade path.

    Verifies that _create_schema() no longer creates idx_games_platform
    (that index belongs in the migration), and that a v1.1.0 database
    without platform columns survives the initialise() path.
    """

    _V1_DDL = """
        CREATE TABLE IF NOT EXISTS games (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            process_name     TEXT    NOT NULL,
            executable_path  TEXT    NOT NULL DEFAULT '',
            icon_path        TEXT             DEFAULT NULL,
            is_enabled       INTEGER NOT NULL DEFAULT 1,
            first_played     DATETIME         DEFAULT NULL,
            last_played      DATETIME         DEFAULT NULL,
            created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id          INTEGER NOT NULL REFERENCES games(id),
            start_time       DATETIME NOT NULL,
            end_time         DATETIME NOT NULL,
            duration_seconds INTEGER  NOT NULL DEFAULT 0,
            created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS active_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id     INTEGER NOT NULL REFERENCES games(id),
            process_id  INTEGER NOT NULL,
            start_time  DATETIME NOT NULL,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """

    @pytest.fixture(autouse=True)
    def _tmpdir(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path

    def _create_v1_db(self) -> sqlite3.Connection:
        """Create and return a v1.1.0-style database (no platform columns)."""
        db_path = self.tmp_path / "trackora_v1.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(self._V1_DDL)
        conn.commit()
        return conn

    def _create_schema_db(self) -> sqlite3.Connection:
        """Create a DatabaseManager instance, call _create_schema, return connection."""
        from database.database_manager import DatabaseManager
        db_path = self.tmp_path / "trackora_test.db"
        dm = DatabaseManager(str(db_path))
        dm.initialize()

        cursor = dm.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_games_platform'"
        )
        exists = cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='games'"
        )
        games_exists = cursor.fetchone() is not None
        cursor.execute("PRAGMA table_info(games)")
        columns = {row[1] for row in cursor.fetchall()}
        dm.connection.close()
        return dm, exists, games_exists, columns

    def test_create_schema_does_not_create_idx_games_platform(self) -> None:
        dm, idx_exists, _, _ = self._create_schema_db()
        assert idx_exists is False, (
            "idx_games_platform should NOT be created by _create_schema(); "
            "it belongs in migration v2_0_0_add_discovery_columns"
        )

    def test_create_schema_creates_games_table(self) -> None:
        _, _, games_exists, columns = self._create_schema_db()
        assert games_exists is True
        assert "platform" in columns
        assert "platform_id" in columns
        assert "is_auto_discovered" in columns

    def test_v1_database_survives_create_schema(self) -> None:
        conn = self._create_v1_db()
        conn.close()
        from database.database_manager import DatabaseManager
        db_path = self.tmp_path / "trackora_v1.db"
        dm = DatabaseManager(str(db_path))
        dm.initialize()
        cursor = dm.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        dm.connection.close()

    def test_v1_database_gets_migrations_table(self) -> None:
        conn = self._create_v1_db()
        conn.close()
        from database.database_manager import DatabaseManager
        db_path = self.tmp_path / "trackora_v1.db"
        dm = DatabaseManager(str(db_path))
        dm.initialize()
        cursor = dm.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='_migrations'"
        )
        assert cursor.fetchone() is not None
        dm.connection.close()

    def test_v1_database_migrates_to_v2_successfully(self) -> None:
        conn = self._create_v1_db()
        conn.close()
        db_path = self.tmp_path / "trackora_v1.db"
        schema_path = self.tmp_path / "schema.json"

        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager
        svm = SchemaVersionManager(schema_path=schema_path)
        svm.write(SchemaVersion(1, 1, 0), description="v1.1.0 baseline")

        from database.database_manager import DatabaseManager
        dm = DatabaseManager(str(db_path))
        dm.initialize()

        from trackora.core.migration_manager import MigrationManager
        from trackora.core.backup_manager import BackupManager
        backup_dir = self.tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        from trackora.core import paths
        import trackora.core.paths as core_paths
        original_path = core_paths.DATABASE_PATH
        core_paths.DATABASE_PATH = db_path
        try:
            bm = BackupManager(
                schema_version_manager=svm,
                backup_dir=backup_dir,
            )
            mm = MigrationManager(
                connection=dm.connection,
                schema_version_manager=svm,
                backup_manager=bm,
            )

            result = mm.apply_all()

            assert result.success, (
                f"Migration failed: {result.results}"
            )
            cursor = dm.connection.cursor()
            cursor.execute("PRAGMA table_info(games)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "platform" in columns, (
                "platform column should exist after migration"
            )
            assert "platform_id" in columns
            assert "is_auto_discovered" in columns
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='idx_games_platform'"
            )
            assert cursor.fetchone() is not None, (
                "idx_games_platform should exist after migration"
            )
        finally:
            core_paths.DATABASE_PATH = original_path
            dm.connection.close()

    def test_v1_database_migration_preserves_existing_data(self) -> None:
        conn = self._create_v1_db()
        conn.execute(
            "INSERT INTO games (name, process_name, executable_path, "
            "first_played, last_played, created_at, updated_at) "
            "VALUES ('Witcher 3', 'witcher3.exe', '/games/witcher3/witcher3.exe', "
            "'2024-01-15T10:00:00', '2024-02-20T18:00:00', "
            "'2024-01-01T00:00:00', '2024-02-20T18:00:00')"
        )
        conn.execute(
            "INSERT INTO games (name, process_name, executable_path, "
            "first_played, last_played, created_at, updated_at) "
            "VALUES ('Hades', 'hades.exe', '/games/hades/hades.exe', "
            "'2024-03-01T09:00:00', '2024-04-10T21:30:00', "
            "'2024-03-01T09:00:00', '2024-04-10T21:30:00')"
        )
        conn.execute(
            "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds) "
            "VALUES (1, '2024-01-15T10:00:00', '2024-01-15T14:30:00', 16200)"
        )
        conn.execute(
            "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds) "
            "VALUES (2, '2024-03-01T10:00:00', '2024-03-01T12:00:00', 7200)"
        )
        conn.commit()
        conn.close()

        db_path = self.tmp_path / "trackora_v1.db"
        schema_path = self.tmp_path / "schema.json"

        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager
        svm = SchemaVersionManager(schema_path=schema_path)
        svm.write(SchemaVersion(1, 1, 0))

        from database.database_manager import DatabaseManager
        dm = DatabaseManager(str(db_path))
        dm.initialize()

        from trackora.core.migration_manager import MigrationManager
        from trackora.core.backup_manager import BackupManager
        backup_dir = self.tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        from trackora.core import paths as core_paths
        original_path = core_paths.DATABASE_PATH
        core_paths.DATABASE_PATH = db_path
        try:
            bm = BackupManager(
                schema_version_manager=svm,
                backup_dir=backup_dir,
            )
            mm = MigrationManager(
                connection=dm.connection,
                schema_version_manager=svm,
                backup_manager=bm,
            )
            result = mm.apply_all()
            assert result.success

            cursor = dm.connection.cursor()
            rows = cursor.execute(
                "SELECT name, platform, platform_id, is_auto_discovered "
                "FROM games ORDER BY id"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0][0] == "Witcher 3"
            assert rows[0][1] is None
            assert rows[0][2] is None
            assert rows[0][3] == 0
            assert rows[1][0] == "Hades"

            sessions = cursor.execute(
                "SELECT COUNT(*) FROM sessions"
            ).fetchone()[0]
            assert sessions == 2
        finally:
            core_paths.DATABASE_PATH = original_path
            dm.connection.close()
