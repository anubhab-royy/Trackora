"""Phase 13F — Recovery Validation.

Validates the recovery mechanisms that protect user data after
crashes, corrupt files, interrupted operations, and partial failures.

Validation domains:
  1. Schema recovery — corrupt schema.json → rename → first-run → write
  2. Migration resume — partial apply → new manager → remaining applied
  3. Safety backup recovery — safety backup verifiable after failed restore
  4. Pre-migration backup persistence — backup survives crash
  5. Orphan cleanup — .tmp files cleaned on init, don't block writes
  6. Multiple crash-resume cycles
  7. Clean-shutdown state tracking
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from zipfile import ZipFile

import pytest

from trackora.core.schema_version import SchemaVersion, SchemaVersionError
from trackora.core.schema_version_manager import SchemaVersionManager


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def schema_path(tmp_path: Path) -> Path:
    return tmp_path / "schema.json"


@pytest.fixture
def svm(schema_path: Path) -> SchemaVersionManager:
    return SchemaVersionManager(schema_path=schema_path)


@pytest.fixture
def svm_with_version(schema_path: Path) -> SchemaVersionManager:
    svm = SchemaVersionManager(schema_path=schema_path)
    svm.write(SchemaVersion(2, 0, 0), description="test")
    return svm


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "trackora.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'alpha')")
    conn.execute("INSERT INTO test VALUES (2, 'beta')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    path = tmp_path / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def bm(svm_with_version: SchemaVersionManager, db_path: Path, backup_dir: Path, monkeypatch):
    from trackora.core.backup_manager import BackupManager
    from trackora.core import paths

    monkeypatch.setattr(paths, "DATABASE_PATH", db_path)
    return BackupManager(schema_version_manager=svm_with_version, backup_dir=backup_dir)


# ── Migration test helpers ──────────────────────────────────────


def _make_migration(migration_id: str, app_version: str = "2.0.0", description: str = ""):
    """Create a simple Migration subclass."""
    from trackora.core.migration_manager import Migration

    table_name = f"tbl_{migration_id.replace('.', '_').replace('-', '_')}"

    cls = type(
        migration_id,
        (Migration,),
        {
            "migration_id": migration_id,
            "description": description or f"Migration {migration_id}",
            "app_version": app_version,
            "requires_backup": False,
            "upgrade": staticmethod(lambda conn, _tn=table_name: conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_tn} (x INTEGER)"
            )),
            "downgrade": staticmethod(lambda conn, _tn=table_name: conn.execute(
                f"DROP TABLE IF EXISTS {_tn}"
            )),
            "verify": staticmethod(lambda conn: []),
            "source_checksum": staticmethod(lambda: "abc123"),
        },
    )
    return cls


class _FakeBackupManager:
    def __init__(self):
        self.backups = []
        self._counter = [0]

    def create_backup(self, backup_type="manual"):
        bk_id = f"bk_{self._counter[0]:04d}"
        self._counter[0] += 1
        self.backups.append(bk_id)
        from trackora.core.backup_manager import BackupResult
        return BackupResult(
            success=True,
            backup_id=bk_id,
            backup_path=None,
            size_bytes=0,
            file_count=0,
            created_at=__import__("datetime").datetime.now(),
        )


@pytest.fixture
def migration_registry():
    from trackora.core.migrations.registry import MigrationRegistry

    class _TestRegistry(MigrationRegistry):
        def __init__(self):
            self._classes = []

        def register(self, cls):
            self._classes.append(cls)

        def discover(self):
            return list(self._classes)

        def get_by_id(self, migration_id):
            for cls in self._classes:
                if cls.migration_id == migration_id:
                    return cls
            return None

    return _TestRegistry()


# ── 1. Schema recovery ──────────────────────────────────────────


class TestSchemaRecovery:
    """Corrupt schema.json → rename → first-run → write succeeds."""

    def test_corrupt_schema_then_write_new(self, svm: SchemaVersionManager, schema_path: Path) -> None:
        schema_path.write_text("{invalid json!!!}", encoding="utf-8")

        with pytest.raises(SchemaVersionError, match="invalid JSON"):
            svm.read()

        svm.write(SchemaVersion(2, 0, 0), description="recovery")
        result = svm.read()
        assert result == SchemaVersion(2, 0, 0)

    def test_corrupt_renamed_content_preserved(self, svm: SchemaVersionManager, schema_path: Path) -> None:
        original = '{{{garbage json content}}}'
        schema_path.write_text(original, encoding="utf-8")

        with pytest.raises(SchemaVersionError):
            svm.read()

        parent = schema_path.parent
        corrupt_files = sorted(parent.glob("schema.json.corrupt.*"))
        assert len(corrupt_files) >= 1
        assert corrupt_files[0].read_text(encoding="utf-8") == original

    def test_corrupt_then_read_returns_none(self, svm: SchemaVersionManager, schema_path: Path) -> None:
        schema_path.write_text("null", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            svm.read()

        result = svm.read()
        assert result is None

    def test_write_after_corrupt_recovery(self, svm: SchemaVersionManager, schema_path: Path) -> None:
        schema_path.write_text("{}", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            svm.read()

        svm.write(SchemaVersion(2, 0, 0), description="recovered")
        assert schema_path.is_file()
        parsed = json.loads(schema_path.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == "2.0.0"

    def test_orphan_tmp_cleaned_on_init(self, schema_path: Path) -> None:
        tmp_path = schema_path.with_suffix(".json.tmp")
        tmp_path.write_text('{"garbage": true}', encoding="utf-8")

        SchemaVersionManager(schema_path=schema_path)
        assert not tmp_path.exists()

    def test_orphan_tmp_doesnt_block_write(self, svm: SchemaVersionManager, schema_path: Path) -> None:
        tmp_path = schema_path.with_suffix(".json.tmp")
        tmp_path.write_text("stale data", encoding="utf-8")

        svm.write(SchemaVersion(2, 0, 0), description="after_orphan")
        result = svm.read()
        assert result == SchemaVersion(2, 0, 0)

    def test_multiple_corrupt_files_preserved(self, svm: SchemaVersionManager, schema_path: Path) -> None:
        for _ in range(3):
            schema_path.write_text("{{{corrupt}}}", encoding="utf-8")
            try:
                svm.read()
            except SchemaVersionError:
                pass

        parent = schema_path.parent
        corrupt_files = sorted(parent.glob("schema.json.corrupt.*"))
        assert len(corrupt_files) == 3


# ── 2. Migration resume recovery ────────────────────────────────


class TestMigrationResumeRecovery:
    """Crash mid-migration → on restart, remaining migrations applied."""

    def test_resume_after_partial_apply(self, db_path: Path, migration_registry) -> None:
        from trackora.core.migration_manager import MigrationManager

        m1 = _make_migration("v2_0_0_m1", "2.0.0", "First")
        m2 = _make_migration("v2_0_0_m2", "2.0.0", "Second")
        m3 = _make_migration("v2_0_0_m3", "2.0.0", "Third")
        migration_registry.register(m1)
        migration_registry.register(m2)
        migration_registry.register(m3)

        conn = sqlite3.connect(str(db_path))
        mm1 = MigrationManager(
            connection=conn,
            schema_version_manager=SchemaVersionManager(schema_path=db_path.parent / "schema.json"),
            registry=migration_registry,
        )
        mm1._backup = _FakeBackupManager()

        result1 = mm1.apply_all()
        assert result1.applied_count == 3
        assert result1.success is True

        conn2 = sqlite3.connect(str(db_path))
        mm2 = MigrationManager(
            connection=conn2,
            schema_version_manager=SchemaVersionManager(schema_path=db_path.parent / "schema.json"),
            registry=migration_registry,
        )
        mm2._backup = _FakeBackupManager()

        result2 = mm2.apply_all()
        assert result2.applied_count == 0
        assert result2.success is True

        conn2.close()
        conn.close()

    def test_resume_with_one_pending(self, db_path: Path, migration_registry) -> None:
        from trackora.core.migration_manager import MigrationManager

        m1 = _make_migration("v2_0_0_ra", "2.0.0", "First")
        m2 = _make_migration("v2_0_0_rb", "2.0.0", "Second")
        migration_registry.register(m1)
        migration_registry.register(m2)

        conn = sqlite3.connect(str(db_path))
        mm1 = MigrationManager(
            connection=conn,
            schema_version_manager=SchemaVersionManager(schema_path=db_path.parent / "schema.json"),
            registry=migration_registry,
        )
        mm1._backup = _FakeBackupManager()

        mm1._ensure_migrations_table()
        conn.execute(
            "INSERT INTO _migrations (migration_id, description, app_version, checksum, applied_at, duration_ms) "
            "VALUES ('v2_0_0_ra', 'First', '2.0.0', 'abc', '2026-06-20T12:00:00.000000Z', 10)"
        )
        conn.commit()

        pending = mm1.get_pending_migrations()
        assert len(pending) == 1
        assert pending[0].migration_id == "v2_0_0_rb"

        result = mm1.apply_all()
        assert result.applied_count == 1
        assert result.success is True

        conn2 = sqlite3.connect(str(db_path))
        mm2 = MigrationManager(
            connection=conn2,
            schema_version_manager=SchemaVersionManager(schema_path=db_path.parent / "schema.json"),
            registry=migration_registry,
        )
        mm2._backup = _FakeBackupManager()
        assert len(mm2.get_pending_migrations()) == 0
        conn2.close()
        conn.close()

    def test_resume_after_all_applied_before_version_write(self, db_path: Path, migration_registry) -> None:
        from trackora.core.migration_manager import MigrationManager

        m1 = _make_migration("v2_0_0_x1", "2.0.0", "First")
        migration_registry.register(m1)

        schema_path = db_path.parent / "schema.json"
        svm = SchemaVersionManager(schema_path=schema_path)

        conn = sqlite3.connect(str(db_path))
        mm = MigrationManager(
            connection=conn,
            schema_version_manager=svm,
            registry=migration_registry,
        )
        mm._backup = _FakeBackupManager()

        result = mm.apply_all()
        assert result.applied_count == 1
        assert result.success is True
        assert result.final_version == "2.0.0"

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["schema_version"] == "2.0.0"

    def test_repeated_crash_resume_cycles(self, db_path: Path, migration_registry) -> None:
        from trackora.core.migration_manager import MigrationManager

        migrations = [_make_migration(f"v2_0_0_c{i:02d}", "2.0.0", f"Cycle {i}") for i in range(5)]
        for m in migrations:
            migration_registry.register(m)

        schema_path = db_path.parent / "schema.json"
        svm = SchemaVersionManager(schema_path=schema_path)

        for cycle in range(5):
            conn = sqlite3.connect(str(db_path))
            mm = MigrationManager(
                connection=conn,
                schema_version_manager=svm,
                registry=migration_registry,
            )
            mm._backup = _FakeBackupManager()

            mm._ensure_migrations_table()

            conn.execute("DELETE FROM _migrations")
            for i in range(cycle):
                mid = f"v2_0_0_c{i:02d}"
                conn.execute(
                    "INSERT INTO _migrations (migration_id, description, app_version, checksum, applied_at, duration_ms) "
                    "VALUES (?, ?, '2.0.0', 'abc', '2026-06-20T12:00:00.000000Z', 10)",
                    (mid, f"Cycle {i}"),
                )
            conn.commit()

            result = mm.apply_all()
            remaining = 5 - cycle
            assert result.applied_count == remaining, (
                f"Cycle {cycle}: expected {remaining} applied, got {result.applied_count}"
            )
            conn.close()

        assert svm.read() == SchemaVersion(2, 0, 0)


# ── 3. Safety backup recovery ───────────────────────────────────


class TestSafetyBackupRecovery:
    """Safety backup must be verifiable and contain correct data after restore failure."""

    def test_safety_backup_verifiable_after_failed_restore(self, bm, db_path: Path) -> None:
        bk = bm.create_backup()
        assert bk.success is True

        import trackora.core.backup_manager as bm_mod
        import os as _os

        original_replace = _os.replace
        calls = [0]

        def fail_replace(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated failure")
            return original_replace(source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace)
            result = bm.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.safety_backup_id is not None

        verify = bm.verify_backup(result.safety_backup_id)
        assert verify.valid is True, f"Safety backup verification failed: {verify.error}"

    def test_safety_backup_contains_correct_pre_restore_data(self, bm, db_path: Path, tmp_path: Path) -> None:
        bk = bm.create_backup()
        assert bk.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO test VALUES (99, 'safety_check')")
        conn.commit()
        conn.close()

        import trackora.core.backup_manager as bm_mod
        import os as _os

        original_replace = _os.replace
        calls = [0]

        def fail_replace(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated failure")
            return original_replace(source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace)
            result = bm.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.safety_backup_id is not None

        safety_path = bm._backup_dir / f"{result.safety_backup_id}.zip"
        assert safety_path.is_file()

        extract_dir = tmp_path / "safety_extract"
        extract_dir.mkdir()
        with ZipFile(safety_path, "r") as zf:
            zf.extractall(extract_dir)

        safety_db = extract_dir / "trackora.db"
        conn2 = sqlite3.connect(str(safety_db))
        try:
            rows = conn2.execute("SELECT id, value FROM test").fetchall()
            ids = {r[0] for r in rows}
            assert 99 in ids, "Safety backup should include the pre-restore state with id=99"
        finally:
            conn2.close()

    def test_safety_backup_created_before_restore(self, bm) -> None:
        bk = bm.create_backup()
        assert bk.success is True

        result = bm.restore_backup(bk.backup_id)
        assert result.success is True
        assert result.safety_backup_id is not None

    def test_safety_backup_pre_restore_type(self, bm) -> None:
        bk = bm.create_backup()
        assert bk.success is True

        result = bm.restore_backup(bk.backup_id)
        assert result.success is True
        assert result.safety_backup_id is not None

        safety_path = bm._backup_dir / f"{result.safety_backup_id}.zip"
        with ZipFile(safety_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
        assert manifest["backup_type"] == "pre_restore"


# ── 4. Pre-migration backup persistence ─────────────────────────


class TestPreMigrationBackup:
    """Pre-migration backup is verifiable and contains correct data."""

    def test_pre_migration_backup_verifiable(self, bm, db_path: Path) -> None:
        bk = bm.create_backup(backup_type="pre_migration")
        assert bk.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO test VALUES (10, 'post_backup')")
        conn.commit()
        conn.close()

        verify = bm.verify_backup(bk.backup_id)
        assert verify.valid is True, f"Pre-migration backup verification failed: {verify.error}"

    def test_pre_migration_backup_immutable(self, bm, db_path: Path, tmp_path: Path) -> None:
        bk = bm.create_backup(backup_type="pre_migration")
        assert bk.success is True
        assert bk.backup_path is not None

        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO test VALUES (11, 'should_not_be_in_backup')")
        conn.commit()
        conn.close()

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        with ZipFile(bk.backup_path, "r") as zf:
            zf.extractall(extract_dir)

        extracted_db = extract_dir / "trackora.db"
        conn2 = sqlite3.connect(str(extracted_db))
        try:
            ids = {r[0] for r in conn2.execute("SELECT id FROM test").fetchall()}
            assert 11 not in ids
            assert ids == {1, 2}
        finally:
            conn2.close()

    def test_pre_migration_backup_manifest_type(self, bm) -> None:
        bk = bm.create_backup(backup_type="pre_migration")
        assert bk.success is True
        assert bk.backup_path is not None

        with ZipFile(bk.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
        assert manifest["backup_type"] == "pre_migration"
        assert manifest["schema_version"] == "2.0.0"


# ── 5. Orphan recovery ──────────────────────────────────────────


class TestOrphanRecovery:
    """Orphaned temporary files must not block recovery."""

    def test_schema_json_tmp_doesnt_block_read(self, svm_with_version: SchemaVersionManager, schema_path: Path) -> None:
        tmp_path = schema_path.with_suffix(".json.tmp")
        tmp_path.write_text('{"schema_version": "9.9.9", "app_version": "9.9.9", "updated_at": "now"}', encoding="utf-8")

        result = svm_with_version.read()
        assert result == SchemaVersion(2, 0, 0)

    def test_multiple_tmp_files_cleaned_on_init(self, schema_path: Path) -> None:
        tmp_path = schema_path.with_suffix(".json.tmp")
        tmp_path.write_text("stale", encoding="utf-8")

        svm = SchemaVersionManager(schema_path=schema_path)
        assert not tmp_path.exists()

        svm.write(SchemaVersion(2, 0, 0), description="fresh")
        assert schema_path.is_file()

    def test_orphan_dir_doesnt_block_backup(self, bm, backup_dir: Path) -> None:
        orphan_dir = backup_dir / ".restore_orphan"
        orphan_dir.mkdir()

        bk = bm.create_backup()
        assert bk.success is True

    def test_orphan_tmp_doesnt_block_create(self, bm, backup_dir: Path) -> None:
        orphan_tmp = backup_dir / "backup_stale.zip.tmp"
        orphan_tmp.write_bytes(b"stale")

        bk = bm.create_backup()
        assert bk.success is True


# ── 6. Safety-backup rollback chain ─────────────────────────────


class TestSafetyBackupRollbackChain:
    """Full rollback: failed restore → verify safety → rollback → original data intact."""

    def test_rollback_preserves_pre_restore_state(self, bm, db_path: Path) -> None:
        import trackora.core.backup_manager as bm_mod
        import os as _os

        bk = bm.create_backup()
        assert bk.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO test VALUES (99, 'MALICIOUS')")
        conn.commit()
        conn.close()

        pre_restore_values = [
            r[0] for r in sqlite3.connect(str(db_path)).execute("SELECT value FROM test ORDER BY id").fetchall()
        ]

        original_replace = _os.replace
        calls = [0]

        def fail_replace(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated I/O error")
            return original_replace(source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace)
            result = bm.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.safety_backup_id is not None

        after_values = [
            r[0] for r in sqlite3.connect(str(db_path)).execute("SELECT value FROM test ORDER BY id").fetchall()
        ]
        assert after_values == pre_restore_values

    def test_safety_backup_exists_and_verified_after_rollback(self, bm, db_path: Path) -> None:
        import trackora.core.backup_manager as bm_mod
        import os as _os

        bk = bm.create_backup()
        assert bk.success is True

        original_replace = _os.replace
        calls = [0]

        def fail_replace(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated failure")
            return original_replace(source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace)
            result = bm.restore_backup(bk.backup_id)

        assert result.safety_backup_id is not None
        verify = bm.verify_backup(result.safety_backup_id)
        assert verify.valid is True

    def test_rollback_chain_no_staging_dirs_left(self, bm, db_path: Path, backup_dir: Path) -> None:
        import trackora.core.backup_manager as bm_mod
        import os as _os

        bk = bm.create_backup()
        assert bk.success is True

        original_replace = _os.replace
        calls = [0]

        def fail_replace(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated failure")
            return original_replace(source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace)
            result = bm.restore_backup(bk.backup_id)

        assert result.success is False

        staging = [
            d for d in backup_dir.iterdir()
            if d.is_dir() and (d.name.startswith(".restore_") or d.name.startswith(".rollback_"))
        ]
        assert staging == [], f"Staging dirs left behind: {staging}"


# ── 7. Clean-shutdown state ─────────────────────────────────────


class TestCleanShutdownState:
    """Marking clean shutdown persists and can be verified."""

    def test_new_manager_after_clean_shutdown(self, svm_with_version: SchemaVersionManager, schema_path: Path) -> None:
        svm_with_version.write(SchemaVersion(2, 0, 0), description="clean shutdown")
        result = svm_with_version.read()
        assert result == SchemaVersion(2, 0, 0)

    def test_clean_shutdown_metadata_structure(self, svm_with_version: SchemaVersionManager, schema_path: Path) -> None:
        svm_with_version.write(SchemaVersion(2, 0, 0), description="normal shutdown")
        parsed = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "schema_version" in parsed
        assert "app_version" in parsed
        assert "updated_at" in parsed
        assert "description" in parsed
        assert parsed["app_version"] == "2.0.0"


# ── 8. Backup verification after creation ───────────────────────


class TestBackupVerification:
    """Backup must pass self-verification immediately after creation."""

    def test_backup_verify_after_create(self, bm) -> None:
        bk = bm.create_backup()
        assert bk.success is True

        verify = bm.verify_backup(bk.backup_id)
        assert verify.valid is True
        assert len(verify.checksum_errors) == 0
        assert len(verify.missing_files) == 0

    def test_multiple_backups_all_verifiable(self, bm) -> None:
        ids = []
        for _ in range(10):
            r = bm.create_backup()
            assert r.success is True
            ids.append(r.backup_id)

        for bid in ids:
            verify = bm.verify_backup(bid)
            assert verify.valid is True, f"Backup {bid} failed verification"

    def test_backup_verify_then_delete_then_verify_fails(self, bm) -> None:
        bk = bm.create_backup()
        assert bk.success is True
        assert bm.verify_backup(bk.backup_id).valid is True

        bm.delete_backup(bk.backup_id)
        verify = bm.verify_backup(bk.backup_id)
        assert verify.valid is False
        assert "not found" in (verify.error or "").lower()
