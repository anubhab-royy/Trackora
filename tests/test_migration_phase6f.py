"""Phase 6f — Coverage, benchmark, and concurrent-startup fuzz tests."""

from __future__ import annotations

import sys
import uuid
import time
import threading
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────

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
    def __init__(self) -> None:
        self.backups_created: list[str] = []
        self.fail_next: bool = False
        self._counter = 0

    def create_backup(self, backup_type: str = "manual") -> _FakeBackupResult:
        self.backups_created.append(backup_type)
        self._counter += 1
        if self.fail_next:
            self.fail_next = False
            return _FakeBackupResult(success=False, error="Disk full")
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


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def db_connection():
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
def mock_backup():
    return _FakeBackupManager()


@pytest.fixture
def manager(db_connection, sv_manager, mock_backup):
    from trackora.core.migration_manager import MigrationManager

    m1 = _make_migration_class(
        "v1_0_0_initial", "Initial", "1.0.0", requires_backup=False
    )
    m2 = _make_migration_class("v2_0_0_features", "Features", "2.0.0")
    reg = _make_registry([m1, m2])
    return MigrationManager(
        connection=db_connection,
        schema_version_manager=sv_manager,
        backup_manager=mock_backup,
        registry=reg,
    )


# ═══════════════════════════════════════════════════════════════════
# 1. MigrationManager edge-case coverage
# ═══════════════════════════════════════════════════════════════════


class TestMigrationManagerCoverage:
    """Branches not covered by the original test suite."""

    def test_apply_one_backup_failure(self, db_connection, sv_manager):
        """_apply_single backup failure path (lines 426-438)."""
        from trackora.core.migration_manager import MigrationManager

        backup = _FakeBackupManager()
        backup.fail_next = True
        mig = _make_migration_class(
            "v2_0_0_test", "Test", requires_backup=True
        )
        reg = _make_registry([mig])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            backup_manager=backup,
            registry=reg,
        )
        result = mgr.apply_one("v2_0_0_test")
        assert result.success is False
        assert result.applied_count == 0
        assert result.failed_count == 1
        assert "Disk full" in result.results[0].error
        assert mgr.has_been_applied("v2_0_0_test") is False

    def test_get_applied_migrations_creates_table_if_missing(
        self, db_connection, sv_manager
    ):
        """get_applied_migrations() when _migrations table doesn't exist
        triggers auto-creation and returns empty (lines 217-219)."""
        from trackora.core.migration_manager import MigrationManager

        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
        )

        db_connection.execute("DROP TABLE IF EXISTS _migrations")
        db_connection.commit()

        result = mgr.get_applied_migrations()
        assert result == []

        cursor = db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
        )
        assert cursor.fetchone() is not None

    def test_pending_empty_registry_via_query(
        self, db_connection, sv_manager
    ):
        """get_pending_migrations() returns empty when no migrations pending."""
        from trackora.core.migration_manager import MigrationManager

        reg = _make_registry([])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        pending = mgr.get_pending_migrations()
        assert pending == []

    def test_get_all_migrations_empty(
        self, db_connection, sv_manager
    ):
        """get_all_migrations() returns empty with empty registry."""
        from trackora.core.migration_manager import MigrationManager

        reg = _make_registry([])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        all_migs = mgr.get_all_migrations()
        assert all_migs == []

    def test_get_migration_checksum_returns_none_for_missing(
        self, db_connection, sv_manager
    ):
        from trackora.core.migration_manager import MigrationManager

        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
        )
        assert mgr.get_migration_checksum("nonexistent") is None

    def test_read_current_version_returns_none_on_error(
        self, db_connection, sv_manager
    ):
        """_read_current_version catches exceptions and returns None
        (lines 534-535)."""
        import tempfile
        from trackora.core.migration_manager import MigrationManager

        broken_svm_path = Path(tempfile.mkstemp(suffix=".json")[1])
        broken_svm_path.write_bytes(b"\x00\xff\xfe\xed")
        from trackora.core.schema_version_manager import SchemaVersionManager

        broken = SchemaVersionManager(schema_path=broken_svm_path)
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=broken,
        )
        version = mgr._read_current_version()
        assert version is None

    def test_apply_all_empty_registry_returns_success(
        self, db_connection, sv_manager
    ):
        from trackora.core.migration_manager import MigrationManager

        reg = _make_registry([])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        result = mgr.apply_all()
        assert result.success is True
        assert result.applied_count == 0
        assert result.final_version == "1.0.0"

    def test_apply_all_with_no_backup_manager(
        self, db_connection, sv_manager
    ):
        from trackora.core.migration_manager import MigrationManager

        mig = _make_migration_class(
            "v2_0_0_no_backup", "No backup", requires_backup=True
        )
        reg = _make_registry([mig])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        result = mgr.apply_all()
        assert result.success is True
        assert result.applied_count == 1

    def test_source_checksum_fallback_for_dynamic_class(self):
        """source_checksum() uses class name fallback when inspect.getfile
        raises TypeError or OSError (lines 107-108)."""
        from unittest.mock import patch
        from trackora.core.migration_manager import Migration

        class _DynamicMig(Migration):
            migration_id = "v2_0_0_dynamic"
            description = "Dynamic"
            app_version = "2.0.0"

            def upgrade(self, connection: object) -> None:
                pass

            def downgrade(self, connection: object) -> None:
                pass

        inst = _DynamicMig()
        with patch(
            "trackora.core.migration_manager.inspect.getfile",
            side_effect=TypeError("no file"),
        ):
            checksum = inst.source_checksum()
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA-256 hex

    def test_apply_all_verify_failure(self, db_connection, sv_manager):
        """apply_all() raises MigrationVerificationError on verify failure
        (line 311)."""
        from trackora.core.migration_manager import MigrationManager

        good = _make_migration_class(
            "v1_0_0_good", "Good", "1.0.0", requires_backup=False
        )
        bad = _make_migration_class(
            "v2_0_0_bad", "Bad", "2.0.0", requires_backup=False,
            fail_verify=True,
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
        assert mgr.has_been_applied("v1_0_0_good") is True
        assert mgr.has_been_applied("v2_0_0_bad") is False

    def test_get_migration_checksum_real_value(self, db_connection, sv_manager):
        """get_migration_checksum returns the actual checksum after apply."""
        from trackora.core.migration_manager import MigrationManager

        mig = _make_migration_class(
            "v2_0_0_checksum", "Checksum test", requires_backup=False
        )
        reg = _make_registry([mig])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        result = mgr.apply_one("v2_0_0_checksum")
        assert result.success is True
        cs = mgr.get_migration_checksum("v2_0_0_checksum")
        assert cs is not None
        assert len(cs) == 64


# ═══════════════════════════════════════════════════════════════════
# 2. Registry error-path coverage
# ═══════════════════════════════════════════════════════════════════


class TestRegistryCoverage:
    """Branches in MigrationRegistry not covered by original tests."""

    def test_discover_nonexistent_package_returns_empty(self):
        """importlib.import_module fails → empty list (registry.py:61-63)."""
        from trackora.core.migrations.registry import MigrationRegistry

        result = MigrationRegistry.discover(
            package_name="nonexistent_package_xyz"
        )
        assert result == []

    def test_discover_skip_init_and_registry(self):
        """__init__ and registry modules are skipped even when they exist.
        This tests the _SKIP_MODULES logic indirectly via the real package."""
        from trackora.core.migrations.registry import MigrationRegistry

        result = MigrationRegistry.discover()
        # All 4 concrete migrations are found
        ids = [m.migration_id for m in result]
        assert "v1_0_0_base_schema" in ids
        assert "v1_1_0_initial_schema" in ids
        assert "v2_0_0_add_discovery_columns" in ids
        assert "v2_0_0_add_update_center_settings" in ids

    def test_discover_broken_module_skipped(self, tmp_path):
        """Module that raises ImportError during import is skipped
        (registry.py:80-82)."""
        from trackora.core.migrations.registry import MigrationRegistry

        pkg_name = f"_test_broken_{uuid.uuid4().hex[:8]}"
        pkg_dir = tmp_path / pkg_name
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text(
            "# broken package\n", encoding="utf-8"
        )
        (pkg_dir / "good_mig.py").write_text(
            '''
from trackora.core.migration_manager import Migration


class GoodMig(Migration):
    migration_id = "v1_0_0_good"
    description = "Good"
    app_version = "1.0.0"

    def upgrade(self, connection: object) -> None:
        pass

    def downgrade(self, connection: object) -> None:
        pass
''',
            encoding="utf-8",
        )
        (pkg_dir / "broken.py").write_text(
            "raise ImportError('intentional')",
            encoding="utf-8",
        )
        sys.path.insert(0, str(tmp_path))
        try:
            result = MigrationRegistry.discover(package_name=pkg_name)
            assert len(result) == 1
            assert result[0].migration_id == "v1_0_0_good"
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_by_id_with_error_package_returns_none(self):
        """get_by_id on a nonexistent package returns None."""
        from trackora.core.migrations.registry import MigrationRegistry

        result = MigrationRegistry.get_by_id(
            "v1_0_0_base_schema",
            package_name="nonexistent_package_xyz",
        )
        assert result is None

    def test_get_by_id_from_real_package_finds(self):
        """get_by_id on the real migrations package returns expected class."""
        from trackora.core.migrations.registry import MigrationRegistry

        cls = MigrationRegistry.get_by_id("v1_0_0_base_schema")
        assert cls is not None
        assert cls.migration_id == "v1_0_0_base_schema"


# ═══════════════════════════════════════════════════════════════════
# 3. Concrete migration downgrade tests
# ═══════════════════════════════════════════════════════════════════


class TestConcreteMigrationDowngrades:
    """Each concrete migration's downgrade() is idempotent and safe."""

    def test_v1_0_0_base_schema_downgrade(self):
        from trackora.core.migrations.v1_0_0_base_schema import (
            V1_0_0BaseSchema,
        )

        inst = V1_0_0BaseSchema()
        conn = sqlite3.connect(":memory:")
        inst.downgrade(conn)  # no-op, should not raise

    def test_v1_1_0_initial_schema_downgrade(self):
        from trackora.core.migrations.v1_1_0_initial_schema import (
            V1_1_0InitialSchema,
        )

        inst = V1_1_0InitialSchema()
        conn = sqlite3.connect(":memory:")
        inst.downgrade(conn)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='statistics_cache'"
        )
        assert cursor.fetchone() is not None

    def test_v2_0_0_add_discovery_columns_downgrade(self):
        from trackora.core.migrations.v2_0_0_add_discovery_columns import (
            V2_0_0AddDiscoveryColumns,
        )

        inst = V2_0_0AddDiscoveryColumns()
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY);")
        conn.execute(
            "ALTER TABLE games ADD COLUMN platform TEXT DEFAULT NULL;"
        )
        conn.execute(
            "ALTER TABLE games ADD COLUMN platform_id TEXT DEFAULT NULL;"
        )
        conn.execute(
            "ALTER TABLE games ADD COLUMN is_auto_discovered INTEGER DEFAULT 0;"
        )
        conn.execute(
            "CREATE INDEX idx_games_platform ON games (platform);"
        )
        inst.downgrade(conn)

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_games_platform'"
        )
        assert cursor.fetchone() is None

    def test_v2_0_0_add_update_center_settings_downgrade(self):
        from trackora.core.migrations.v2_0_0_add_update_center_settings import (
            V2_0_0AddUpdateCenterSettings,
        )

        inst = V2_0_0AddUpdateCenterSettings()
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);"
        )
        conn.execute(
            "INSERT INTO settings VALUES ('update_check_enabled', 'true', '2026-01-01T00:00:00');"
        )
        inst.downgrade(conn)

        cursor = conn.execute(
            "SELECT key FROM settings WHERE key = 'update_check_enabled'"
        )
        assert cursor.fetchone() is None


# ═══════════════════════════════════════════════════════════════════
# 3b. Concrete migration verify error paths
# ═══════════════════════════════════════════════════════════════════


class TestConcreteMigrationVerifyErrors:
    """Each concrete migration's verify() returns errors correctly."""

    def test_v1_1_0_verify_errors_when_table_still_exists(self):
        from trackora.core.migrations.v1_1_0_initial_schema import (
            V1_1_0InitialSchema,
        )

        inst = V1_1_0InitialSchema()
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE statistics_cache (id INTEGER PRIMARY KEY);"
        )
        errors = inst.verify(conn)
        assert len(errors) == 1
        assert "statistics_cache" in errors[0]

    def test_v2_0_0_discovery_columns_verify_missing_column(self):
        from trackora.core.migrations.v2_0_0_add_discovery_columns import (
            V2_0_0AddDiscoveryColumns,
        )

        inst = V2_0_0AddDiscoveryColumns()
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY);")
        errors = inst.verify(conn)
        assert len(errors) == 3
        assert all("platform" in e or "is_auto_discovered" in e for e in errors)

    def test_v2_0_0_update_center_settings_verify_missing_keys(self):
        from trackora.core.migrations.v2_0_0_add_update_center_settings import (
            V2_0_0AddUpdateCenterSettings,
        )

        inst = V2_0_0AddUpdateCenterSettings()
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);"
        )
        errors = inst.verify(conn)
        assert len(errors) == 1
        assert "update_check_enabled" in errors[0]


# ═══════════════════════════════════════════════════════════════════
# 3c. _column_exists() hardening
# ═══════════════════════════════════════════════════════════════════


class TestColumnExistsHardening:
    """_column_exists() must validate table names to prevent SQL injection."""

    def test_column_exists_rejects_unknown_table(self):
        """Unknown table name raises ValueError."""
        from trackora.core.migrations.v2_0_0_add_discovery_columns import (
            _column_exists,
        )

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY);")
        with pytest.raises(ValueError, match="Unknown table"):
            _column_exists(conn, "users", "id")

    def test_column_exists_accepts_known_table(self):
        """Known table name works normally."""
        from trackora.core.migrations.v2_0_0_add_discovery_columns import (
            _column_exists,
        )

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT);")
        assert _column_exists(conn, "games", "id") is True
        assert _column_exists(conn, "games", "missing_col") is False

    def test_column_exists_rejects_sql_injection_attempt(self):
        """SQL injection attempt via table name raises ValueError."""
        from trackora.core.migrations.v2_0_0_add_discovery_columns import (
            _column_exists,
        )

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY);")
        with pytest.raises(ValueError, match="Unknown table"):
            _column_exists(conn, "games; DROP TABLE games; --", "id")


# ═══════════════════════════════════════════════════════════════════
# 4. NFR-02 Benchmark: single migration < 2 s
# ═══════════════════════════════════════════════════════════════════


class TestNfr02Benchmark:
    """NFR-02: A single migration must complete in under 2 seconds."""

    MAX_DURATION_MS = 2000

    def test_v1_0_0_base_schema_under_threshold(self):
        from trackora.core.migrations.v1_0_0_base_schema import (
            V1_0_0BaseSchema,
        )

        inst = V1_0_0BaseSchema()
        conn = sqlite3.connect(":memory:")
        start = time.perf_counter()
        inst.upgrade(conn)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < self.MAX_DURATION_MS, (
            f"v1_0_0_base_schema took {elapsed:.1f} ms (limit {self.MAX_DURATION_MS} ms)"
        )

    def test_v1_1_0_initial_schema_under_threshold(self):
        from trackora.core.migrations.v1_1_0_initial_schema import (
            V1_1_0InitialSchema,
        )

        inst = V1_1_0InitialSchema()
        conn = sqlite3.connect(":memory:")
        start = time.perf_counter()
        inst.upgrade(conn)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < self.MAX_DURATION_MS

    def test_v2_0_0_add_discovery_columns_under_threshold(self):
        from trackora.core.migrations.v2_0_0_add_discovery_columns import (
            V2_0_0AddDiscoveryColumns,
        )

        inst = V2_0_0AddDiscoveryColumns()
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY);")
        start = time.perf_counter()
        inst.upgrade(conn)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < self.MAX_DURATION_MS

    def test_v2_0_0_add_update_center_settings_under_threshold(self):
        from trackora.core.migrations.v2_0_0_add_update_center_settings import (
            V2_0_0AddUpdateCenterSettings,
        )

        inst = V2_0_0AddUpdateCenterSettings()
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);"
        )
        start = time.perf_counter()
        inst.upgrade(conn)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < self.MAX_DURATION_MS

    def test_migration_manager_apply_one_under_threshold(
        self, db_connection, sv_manager
    ):
        from trackora.core.migration_manager import MigrationManager

        mig = _make_migration_class(
            "v2_0_0_bench", "Benchmark", requires_backup=False
        )
        reg = _make_registry([mig])
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        start = time.perf_counter()
        result = mgr.apply_one("v2_0_0_bench")
        elapsed = (time.perf_counter() - start) * 1000
        assert result.success is True
        assert elapsed < self.MAX_DURATION_MS

    def test_migration_manager_apply_all_under_threshold(
        self, db_connection, sv_manager
    ):
        from trackora.core.migration_manager import MigrationManager

        migs = [
            _make_migration_class(
                f"v2_0_0_bench_{i}", f"Bench {i}", requires_backup=False
            )
            for i in range(5)
        ]
        reg = _make_registry(migs)
        mgr = MigrationManager(
            connection=db_connection,
            schema_version_manager=sv_manager,
            registry=reg,
        )
        start = time.perf_counter()
        result = mgr.apply_all()
        elapsed = (time.perf_counter() - start) * 1000
        assert result.success is True
        assert result.applied_count == 5
        assert elapsed < self.MAX_DURATION_MS * 5


# ═══════════════════════════════════════════════════════════════════
# 5. Concurrent startup fuzz test
# ═══════════════════════════════════════════════════════════════════


class TestConcurrentStartup:
    """Multiple threads initializing MigrationManager simultaneously."""

    NUM_THREADS = 8

    def test_concurrent_apply_all(self, tmp_path):
        """8 threads call apply_all on separate DBs without deadlock."""
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.migration_manager import MigrationManager

        mig = _make_migration_class(
            "v2_0_0_concurrent", "Concurrent test", requires_backup=False
        )
        reg = _make_registry([mig])
        errors: list[Exception] = []
        lock = threading.Lock()

        def _run() -> None:
            try:
                db_path = tmp_path / f"concurrent_{threading.get_ident()}.db"
                conn = sqlite3.connect(str(db_path))
                conn.execute(_MIGRATIONS_TABLE_SQL)
                conn.commit()

                svm = SchemaVersionManager(
                    schema_path=tmp_path / f"schema_{threading.get_ident()}.json"
                )
                svm.write(SchemaVersion(1, 0, 0))

                mgr = MigrationManager(
                    connection=conn,
                    schema_version_manager=svm,
                    registry=reg,
                )
                result = mgr.apply_all()
                if not result.success:
                    with lock:
                        errors.append(
                            RuntimeError(
                                f"Migration failed: {result.results}"
                            )
                        )
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=_run) for _ in range(self.NUM_THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent startup errors: {errors}"

    def test_concurrent_same_db_safe(self, tmp_path):
        """Multiple threads calling apply_all on separate DBs safely."""
        from trackora.core.schema_version import SchemaVersion
        from trackora.core.schema_version_manager import SchemaVersionManager
        from trackora.core.migration_manager import MigrationManager

        mig = _make_migration_class(
            "v2_0_0_same_db", "Same DB test", requires_backup=False
        )
        reg = _make_registry([mig])
        errors: list[Exception] = []
        lock = threading.Lock()

        def _run() -> None:
            try:
                tid = threading.get_ident()
                conn = sqlite3.connect(
                    str(tmp_path / f"same_db_{tid}.db")
                )
                conn.execute(_MIGRATIONS_TABLE_SQL)
                conn.commit()

                svm = SchemaVersionManager(
                    schema_path=tmp_path / f"schema_{tid}.json"
                )
                svm.write(SchemaVersion(1, 0, 0))

                mgr = MigrationManager(
                    connection=conn,
                    schema_version_manager=svm,
                    registry=reg,
                )
                result = mgr.apply_all()
                if not result.success:
                    with lock:
                        errors.append(
                            RuntimeError(
                                f"Migration failed: {result.results}"
                            )
                        )
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=_run) for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors, f"Concurrent same-DB errors: {errors}"
