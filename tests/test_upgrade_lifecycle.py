"""Integration tests for the upgrade lifecycle — SchemaVersionManager,
BackupManager, and MigrationManager wired together.

Tests first-run detection, version upgrade, newer-data blocking,
corrupt file recovery, environment isolation, and the full
backup → migrate → version-write flow.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from trackora.core.schema_version import SchemaVersion, SchemaVersionError
from trackora.core.schema_version_manager import SchemaVersionManager


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def manager(tmp_path: Path) -> SchemaVersionManager:
    return SchemaVersionManager(schema_path=tmp_path / "schema.json")


@pytest.fixture
def existing_v1_database(tmp_path: Path) -> Path:
    """Create a schema.json representing a v1.1.0 installation."""
    schema_path = tmp_path / "schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "app_version": "1.1.0",
                "updated_at": "2026-01-15T00:00:00Z",
                "description": "Initial v1.1.0 installation",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def real_paths_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SchemaVersionManager:
    """Integration fixture using real paths.py resolution with tmp_path as BASE_DIR."""
    monkeypatch.setattr("trackora.core.paths.BASE_DIR", tmp_path)
    from trackora.core.paths import BASE_DIR

    return SchemaVersionManager(schema_path=BASE_DIR / "schema.json")


# ── First Run ─────────────────────────────────────────────────────


class TestFirstRunLifecycle:
    def test_no_file_read_returns_none(self, manager: SchemaVersionManager) -> None:
        assert manager.read() is None

    def test_no_file_is_compatible_first_run(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), None)
        assert result.can_proceed is True
        assert result.status == "first_run"

    def test_first_run_write_creates_file(self, manager: SchemaVersionManager) -> None:
        version = SchemaVersion(2, 0, 0)
        manager.write(version)
        assert manager._schema_path.is_file()

    def test_first_run_write_then_read(self, manager: SchemaVersionManager) -> None:
        version = SchemaVersion(2, 0, 0)
        manager.write(version)
        assert manager.read() == version

    def test_first_run_full_flow(self, manager: SchemaVersionManager) -> None:
        """Complete first-run scenario: read → is_compatible → write."""
        data = manager.read()
        assert data is None

        status = manager.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "first_run"

        manager.write(SchemaVersion(2, 0, 0))
        assert manager.read() == SchemaVersion(2, 0, 0)


# ── Upgrade ───────────────────────────────────────────────────────


class TestUpgradeLifecycle:
    def test_existing_v1_readable(self, existing_v1_database: Path) -> None:
        mgr = SchemaVersionManager(
            schema_path=existing_v1_database / "schema.json"
        )
        assert mgr.read() == SchemaVersion(1, 1, 0)

    def test_existing_v1_needs_migration(self, existing_v1_database: Path) -> None:
        mgr = SchemaVersionManager(
            schema_path=existing_v1_database / "schema.json"
        )
        data = mgr.read()
        status = mgr.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "needs_migration"

    def test_existing_v1_upgrade_write(self, existing_v1_database: Path) -> None:
        mgr = SchemaVersionManager(
            schema_path=existing_v1_database / "schema.json"
        )
        mgr.write(SchemaVersion(2, 0, 0))
        assert mgr.read() == SchemaVersion(2, 0, 0)

    def test_upgrade_flow_complete(self, existing_v1_database: Path) -> None:
        """Full upgrade scenario: read v1 → is_compatible → needs_migration → write v2."""
        mgr = SchemaVersionManager(
            schema_path=existing_v1_database / "schema.json"
        )
        data = mgr.read()
        assert data == SchemaVersion(1, 1, 0)

        status = mgr.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "needs_migration"

        mgr.write(SchemaVersion(2, 0, 0))
        assert mgr.read() == SchemaVersion(2, 0, 0)


# ── Block Newer Data ──────────────────────────────────────────────


class TestBlockNewerData:
    def test_newer_patch_readable(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "app_version": "2.1.0",
                    "updated_at": "2026-06-20T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        mgr = SchemaVersionManager(schema_path=schema_path)
        assert mgr.read() == SchemaVersion(2, 1, 0)

    def test_newer_patch_blocked(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "app_version": "2.1.0",
                    "updated_at": "2026-06-20T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        mgr = SchemaVersionManager(schema_path=schema_path)
        data = mgr.read()
        status = mgr.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is False
        assert status.status == "newer_data"

    def test_newer_major_blocked(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "3.0.0",
                    "app_version": "3.0.0",
                    "updated_at": "2026-06-20T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        mgr = SchemaVersionManager(schema_path=schema_path)
        data = mgr.read()
        status = mgr.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is False
        assert status.status == "newer_data"

    def test_downgrade_rejected(self, tmp_path: Path) -> None:
        """App version older than data version — blocked."""
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "app_version": "2.0.0",
                    "updated_at": "2026-06-20T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        mgr = SchemaVersionManager(schema_path=schema_path)
        data = mgr.read()
        status = mgr.is_compatible(SchemaVersion(1, 1, 0), data)
        assert status.can_proceed is False
        assert status.status == "newer_data"


# ── Same Version ──────────────────────────────────────────────────


class TestSameVersion:
    def test_same_version_ok(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "app_version": "2.0.0",
                    "updated_at": "2026-06-20T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        mgr = SchemaVersionManager(schema_path=schema_path)
        data = mgr.read()
        status = mgr.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "ok"

    def test_same_version_skip_migration(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "schema_version": "2.0.0",
                    "app_version": "2.0.0",
                    "updated_at": "2026-06-20T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        mgr = SchemaVersionManager(schema_path=schema_path)
        data = mgr.read()
        status = mgr.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.status == "ok"


# ── Corrupt File Recovery ─────────────────────────────────────────


class TestCorruptRecovery:
    def test_corrupt_file_raises_on_read(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("{garbage}", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            manager.read()

    def test_corrupt_file_is_renamed(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("{garbage}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        assert not manager._schema_path.exists()

    def test_corrupt_recovery_to_first_run(self, manager: SchemaVersionManager) -> None:
        """After corrupt file is renamed, read returns None (first run)."""
        manager._schema_path.write_text("{garbage}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        assert manager.read() is None

    def test_corrupt_then_first_run_flow(self, manager: SchemaVersionManager) -> None:
        """Corrupt → rename → read None → is_compatible → first_run → write."""
        manager._schema_path.write_text("{garbage}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass

        data = manager.read()
        assert data is None

        status = manager.is_compatible(SchemaVersion(2, 0, 0), data)
        assert status.can_proceed is True
        assert status.status == "first_run"

        manager.write(SchemaVersion(2, 0, 0))
        assert manager.read() == SchemaVersion(2, 0, 0)

    def test_corrupt_back_to_back_recovery(self, manager: SchemaVersionManager) -> None:
        """Multiple corrupt files in sequence should each be renamed."""
        for content in ("{first}", "{second}", "{third}"):
            manager._schema_path.write_text(content, encoding="utf-8")
            try:
                manager.read()
            except SchemaVersionError:
                pass

        parent = manager._schema_path.parent
        corrupt = [f for f in parent.iterdir() if f.name.startswith("schema.json.corrupt.")]
        assert len(corrupt) >= 3


# ── Environment Isolation ─────────────────────────────────────────


class TestEnvironmentIsolation:
    def test_real_paths_creates_schema(self, real_paths_integration: SchemaVersionManager) -> None:
        real_paths_integration.write(SchemaVersion(2, 0, 0))
        assert real_paths_integration._schema_path.is_file()

    def test_real_paths_read_write_roundtrip(
        self, real_paths_integration: SchemaVersionManager
    ) -> None:
        real_paths_integration.write(SchemaVersion(2, 0, 0))
        assert real_paths_integration.read() == SchemaVersion(2, 0, 0)

    def test_real_paths_isolation(self, real_paths_integration: SchemaVersionManager) -> None:
        """Verify the schema.json is created in the monkeypatched BASE_DIR, not the real one."""
        from trackora.core.paths import BASE_DIR

        expected = BASE_DIR / "schema.json"
        assert real_paths_integration._schema_path == expected
        real_paths_integration.write(SchemaVersion(2, 0, 0))
        assert expected.exists()

    def test_real_paths_file_has_correct_content(
        self, real_paths_integration: SchemaVersionManager
    ) -> None:
        real_paths_integration.write(SchemaVersion(2, 0, 0))
        data = json.loads(
            real_paths_integration._schema_path.read_text(encoding="utf-8")
        )
        assert data["schema_version"] == "2.0.0"
        assert data["app_version"] == "2.0.0"


# ── Backup/BackupManager Integration ────────────────────────────


@pytest.fixture
def bm_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """BackupManager with isolated paths for integration testing."""
    import sqlite3

    from trackora.core import paths as core_paths
    from trackora.core.backup_manager import BackupManager
    from trackora.core.schema_version import SchemaVersion
    from trackora.core.schema_version_manager import SchemaVersionManager

    # Create test database
    db_path = tmp_path / "trackora.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'alice')")
    conn.execute("INSERT INTO users VALUES (2, 'bob')")
    conn.commit()
    conn.close()

    # Create schema version
    sv_manager = SchemaVersionManager(schema_path=tmp_path / "schema.json")
    sv_manager.write(SchemaVersion(2, 0, 0))

    # Monkeypatch DATABASE_PATH
    monkeypatch.setattr(core_paths, "DATABASE_PATH", db_path)

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    bm = BackupManager(schema_version_manager=sv_manager, backup_dir=backup_dir)
    return bm, db_path, sv_manager


class TestBackupManagerIntegration:
    def test_backup_restore_roundtrip(self, bm_integration) -> None:
        import sqlite3
        bm, db_path, sv_manager = bm_integration

        # Create backup
        created = bm.create_backup()
        assert created.success is True

        # Modify the database
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM users WHERE id = 2")
        conn.execute("INSERT INTO users VALUES (3, 'charlie')")
        conn.commit()
        conn.close()

        # Restore from backup
        result = bm.restore_backup(created.backup_id)
        assert result.success is True

        # Verify data fidelity
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT id, name FROM users ORDER BY id")
        rows = cursor.fetchall()
        conn.close()
        assert rows == [(1, "alice"), (2, "bob")]

    def test_backup_verify_lifecycle(self, bm_integration) -> None:
        bm, db_path, sv_manager = bm_integration

        # Create backup
        created = bm.create_backup()
        assert created.success is True

        # Verify → valid
        verify_result = bm.verify_backup(created.backup_id)
        assert verify_result.valid is True

        # Delete backup
        deleted = bm.delete_backup(created.backup_id)
        assert deleted is True

        # Verify → backup not found
        verify_result = bm.verify_backup(created.backup_id)
        assert verify_result.valid is False
        assert verify_result.error is not None

    def test_corrupt_backup_detection_in_restore(self, bm_integration) -> None:
        import sqlite3
        bm, db_path, sv_manager = bm_integration

        # Capture original data before backup
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO users VALUES (99, 'original')")
        conn.commit()
        conn.close()

        original_data = db_path.read_bytes()

        # Create backup
        created = bm.create_backup()
        assert created.success is True

        # Change data
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE users SET name = 'tampered' WHERE id = 99")
        conn.commit()
        conn.close()

        # Corrupt the backup ZIP
        assert created.backup_path is not None
        created.backup_path.write_bytes(b"GARBAGE DATA")

        # Try restore → should fail
        result = bm.restore_backup(created.backup_id)
        assert result.success is False
        assert result.error is not None

        # Verify no files changed (revert did not happen because
        # restore never got past verification to make a safety backup)
        assert db_path.read_bytes() != original_data

    def test_backup_with_real_schema_manager(self, bm_integration) -> None:
        import json as _json
        from zipfile import ZipFile

        bm, db_path, sv_manager = bm_integration

        # Create backup
        created = bm.create_backup()
        assert created.success is True

        # Verify manifest contains correct schema_version
        assert created.backup_path is not None
        with ZipFile(created.backup_path, "r") as zf:
            manifest = _json.loads(zf.read("MANIFEST.json"))

        assert manifest["schema_version"] == "2.0.0"
        assert manifest["trackora_version"] is not None
        assert manifest["backup_type"] == "manual"
        assert manifest["file_count"] == 4

    def test_restore_mid_failure_rollback_integration(self, bm_integration) -> None:
        """Verify _restore_from_safety() is called when os.replace
        fails mid-restore, and production files return to their
        pre-restore state."""
        import os
        import sqlite3

        import trackora.core.backup_manager as bm_mod

        bm, db_path, sv_manager = bm_integration

        # Capture initial state
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO users VALUES (10, 'initial_pre_backup')")
        conn.commit()
        conn.close()

        # Create backup (captures: alice, bob, initial_pre_backup)
        created = bm.create_backup()
        assert created.success is True

        # Modify the DB to a distinct "current" state
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO users VALUES (20, 'current_state_before_restore')")
        conn.commit()
        conn.close()

        # Monkeypatch os.replace to fail on the first trackora.db replace
        original_replace = os.replace
        replace_attempts = [0]

        def failing_replace(src: str, dst: str) -> None:
            if "trackora.db" in dst and replace_attempts[0] == 0:
                replace_attempts[0] += 1
                raise OSError("Simulated I/O error during replace")
            return original_replace(src, dst)

        mp = pytest.MonkeyPatch()
        mp.setattr(bm_mod.os, "replace", failing_replace)
        try:
            result = bm.restore_backup(created.backup_id)
        finally:
            mp.undo()

        # Restore should have failed
        assert result.success is False
        assert result.error is not None

        # _restore_from_safety() should have restored the pre-restore
        # state (current state captured by safety backup), NOT the
        # backed-up state.
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
        conn.close()
        # Verify pre-restore data is present (rolled back from safety backup)
        row_ids = {r[0] for r in rows}
        assert 10 in row_ids  # initial_pre_backup — from before backup
        assert 20 in row_ids  # current_state_before_restore — rolled back
        # Verify the backed-up state is NOT present (restore failed mid-way)
        assert len(rows) >= 4  # alice, bob, initial_pre_backup, current_state_before_restore


# ── Helpers for full lifecycle tests ──────────────────────────────


def _make_test_migration(
    migration_id: str,
    description: str,
    app_version: str = "2.0.0",
) -> type:
    """Create a Migration subclass that adds a column to the games table."""
    from trackora.core.migration_manager import Migration

    def _upgrade(self: object, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(games)")
        cols = {row[1] for row in cursor.fetchall()}
        if migration_id.replace(".", "_") not in cols:
            col = migration_id.replace(".", "_").replace("-", "_")
            conn.execute(f"ALTER TABLE games ADD COLUMN {col} TEXT DEFAULT NULL")

    def _downgrade(self: object, conn: sqlite3.Connection) -> None:
        pass

    return type(
        "_TestMig",
        (Migration,),
        {
            "migration_id": migration_id,
            "description": description,
            "app_version": app_version,
            "requires_backup": True,
            "upgrade": _upgrade,
            "downgrade": _downgrade,
        },
    )


def _make_registry(migrations: list[type]) -> object:
    class _R:
        _m = migrations

        @classmethod
        def discover(cls) -> list[type]:
            return list(cls._m)

        @classmethod
        def get_by_id(cls, mid: str) -> type | None:
            for m in cls._m:
                if m.migration_id == mid:
                    return m
            return None

    return _R


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
INSERT INTO games (name, process_name, executable_path, created_at, updated_at)
VALUES ('Test Game', 'test.exe', '/usr/bin/test', '2026-01-01', '2026-01-01');
"""


# ── Full Upgrade Lifecycle: SchemaVersionManager + BackupManager + MigrationManager ──


class TestFullUpgradeLifecycle:
    """End-to-end upgrade lifecycle with all three managers wired together."""

    @pytest.fixture
    def v1_db(self, tmp_path: Path) -> sqlite3.Connection:
        """Create a v1.1.0 database with base tables + data."""
        conn = sqlite3.connect(":memory:")
        conn.executescript(_BASE_SCHEMA_SQL)
        conn.commit()
        return conn

    @pytest.fixture
    def v1_schema(self, tmp_path: Path) -> Path:
        """Create a schema.json at v1.0.0 (older than current app v1.1.0)."""
        p = tmp_path / "schema.json"
        p.write_text(
            json.dumps({
                "schema_version": "1.0.0",
                "app_version": "1.0.0",
                "updated_at": "2026-01-01T00:00:00Z",
            }),
            encoding="utf-8",
        )
        return p

    @pytest.fixture
    def svm(self, v1_schema: Path) -> SchemaVersionManager:
        return SchemaVersionManager(schema_path=v1_schema)

    @pytest.fixture
    def backup_dir(self, tmp_path: Path) -> Path:
        p = tmp_path / "backups"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def test_full_upgrade_v1_to_v2(
        self, v1_db: sqlite3.Connection, svm: SchemaVersionManager,
        backup_dir: Path,
    ) -> None:
        """v1.1.0 database → backup → migrate → version written."""
        from trackora.core.backup_manager import BackupManager
        from trackora.core.migration_manager import MigrationManager
        from trackora.core.paths import DATABASE_PATH
        import os

        from trackora import __version__ as app_ver_str

        migration_target_version = app_ver_str

        # Create the migration
        m1 = _make_test_migration(
            "v1_1_0_add_test_flag", "Add test_flag column",
            migration_target_version,
        )
        registry = _make_registry([m1])

        # Need a real DB path for BackupManager
        real_db = backup_dir.parent / "trackora.db"
        v1_db_path = real_db  # BackupManager needs file path
        # Copy in-memory db to file
        src_conn = v1_db
        file_conn = sqlite3.connect(str(real_db))
        src_conn.backup(file_conn)
        file_conn.close()

        # Patch DATABASE_PATH for BackupManager
        from trackora.core import paths as core_paths

        original_db_path = core_paths.DATABASE_PATH
        core_paths.DATABASE_PATH = real_db  # type: ignore[assignment]

        try:
            bm = BackupManager(
                schema_version_manager=svm,
                backup_dir=backup_dir,
            )
            mm = MigrationManager(
                connection=sqlite3.connect(str(real_db)),
                schema_version_manager=svm,
                backup_manager=bm,
                registry=registry,
            )

            # Verify initial state
            app_ver = SchemaVersion.current_app_version()
            data_ver = svm.read()
            assert data_ver == SchemaVersion(1, 0, 0)

            compat = svm.is_compatible(app_ver, data_ver)
            assert compat.status == "needs_migration"

            # Apply all migrations
            bk = bm.create_backup(backup_type="pre_migration")
            assert bk.success is True

            result = mm.apply_all()
            assert result.success is True
            assert result.applied_count == 1
            assert result.final_version == app_ver_str

            # Verify backup was created
            backups = bm.list_backups()
            assert len(backups) >= 1

            # Verify schema version was written
            new_ver = svm.read()
            assert new_ver == SchemaVersion.from_string(app_ver_str)

            # Verify migration column exists
            conn = sqlite3.connect(str(real_db))
            cursor = conn.execute("PRAGMA table_info(games)")
            cols = {row[1] for row in cursor.fetchall()}
            conn.close()
            assert "v1_1_0_add_test_flag" in cols

        finally:
            core_paths.DATABASE_PATH = original_db_path  # type: ignore[assignment]

    def test_first_run_no_migration_needed(
        self, tmp_path: Path,
    ) -> None:
        """No schema.json → first-run → schema written, no migration."""
        from trackora.core.backup_manager import BackupManager
        from trackora.core.migration_manager import MigrationManager

        schema_path = tmp_path / "schema.json"
        svm = SchemaVersionManager(schema_path=schema_path)

        # First-run: read() returns None
        data_ver = svm.read()
        assert data_ver is None

        app_ver = SchemaVersion.current_app_version()
        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.status == "first_run"

        # Write schema version (as __main__.py would)
        svm.write(app_ver)
        assert svm.read() == app_ver

        # Create in-memory DB with base schema
        conn = sqlite3.connect(":memory:")
        conn.executescript(_BASE_SCHEMA_SQL)
        conn.commit()

        # MigrationManager discovers 4 pending migrations and applies them
        mm = MigrationManager(
            connection=conn,
            schema_version_manager=svm,
        )
        result = mm.apply_all()
        assert result.success is True
        assert result.applied_count == 4

    def test_newer_data_blocks_startup(self, tmp_path: Path) -> None:
        """schema_version > app_version → blocked."""
        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps({
                "schema_version": "99.0.0",
                "app_version": "99.0.0",
                "updated_at": "2026-06-20T00:00:00Z",
            }),
            encoding="utf-8",
        )
        svm = SchemaVersionManager(schema_path=schema_path)

        data_ver = svm.read()
        assert data_ver == SchemaVersion(99, 0, 0)

        app_ver = SchemaVersion.current_app_version()
        compat = svm.is_compatible(app_ver, data_ver)
        assert compat.can_proceed is False
        assert compat.status == "newer_data"

    def test_idempotent_upgrade(
        self, v1_db: sqlite3.Connection, svm: SchemaVersionManager,
        backup_dir: Path,
    ) -> None:
        """Running upgrade twice is a no-op on the second run."""
        from trackora.core.backup_manager import BackupManager
        from trackora.core.migration_manager import MigrationManager
        from trackora.core import paths as core_paths

        from trackora import __version__ as app_ver_str

        m1 = _make_test_migration(
            "v1_1_0_idempotent", "Idempotent test", app_ver_str
        )
        registry = _make_registry([m1])
        real_db = backup_dir.parent / "trackora.db"
        conn1 = sqlite3.connect(str(real_db))
        v1_db.backup(conn1)
        conn1.close()

        original_path = core_paths.DATABASE_PATH
        core_paths.DATABASE_PATH = real_db  # type: ignore[assignment]

        try:
            # First run
            bm = BackupManager(schema_version_manager=svm, backup_dir=backup_dir)
            mm = MigrationManager(
                connection=sqlite3.connect(str(real_db)),
                schema_version_manager=svm,
                backup_manager=bm,
                registry=registry,
            )
            result1 = mm.apply_all()
            assert result1.applied_count == 1
            assert result1.success is True

            # Second run — no pending migrations
            bm2 = BackupManager(schema_version_manager=svm, backup_dir=backup_dir)
            mm2 = MigrationManager(
                connection=sqlite3.connect(str(real_db)),
                schema_version_manager=svm,
                backup_manager=bm2,
                registry=registry,
            )
            result2 = mm2.apply_all()
            assert result2.applied_count == 0
            assert result2.success is True
        finally:
            core_paths.DATABASE_PATH = original_path  # type: ignore[assignment]
