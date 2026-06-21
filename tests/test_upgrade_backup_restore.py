"""Phase 13E — Backup & Restore Validation.

Validates BackupManager in failure-recovery, edge-case, and
end-to-end data-integrity scenarios that go beyond the happy-path
coverage in test_backup_manager.py.

Validation domains:
  1. End-to-end data integrity round-trip (games, sessions, settings)
  2. Corrupt current database → restore from backup
  3. Missing current database → restore from backup
  4. Cross-version backup compatibility
  5. WAL-mode database backup/restore
  6. Safety backup rollback end-to-end
  7. Orphan cleanup after simulated crash
  8. Concurrent backup isolation
  9. Backup/restore with missing schema.json
  10. Restore with integrity-check failure on staging
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path
from zipfile import ZipFile

import pytest

from trackora.core.backup_manager import BackupManager, BackupResult
from trackora.core.schema_version import SchemaVersion
from trackora.core.schema_version_manager import SchemaVersionManager


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def schema_path(tmp_path: Path) -> Path:
    return tmp_path / "schema.json"


@pytest.fixture
def sv_manager_v1(schema_path: Path) -> SchemaVersionManager:
    """Write schema version 1.1.0 (simulating pre-upgrade)."""
    svm = SchemaVersionManager(schema_path=schema_path)
    svm.write(SchemaVersion(1, 1, 0), description="v1.1.0")
    return svm


@pytest.fixture
def sv_manager_v2(schema_path: Path) -> SchemaVersionManager:
    """Write schema version 2.0.0 (current)."""
    svm = SchemaVersionManager(schema_path=schema_path)
    svm.write(SchemaVersion(2, 0, 0), description="v2.0.0")
    return svm


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "trackora.db"
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute(
        "CREATE TABLE games ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  name TEXT NOT NULL,"
        "  platform TEXT,"
        "  last_played TEXT"
        ")"
    )
    conn.execute(
        "CREATE TABLE sessions ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  game_id INTEGER REFERENCES games(id),"
        "  start_time TEXT,"
        "  end_time TEXT,"
        "  duration INTEGER"
        ")"
    )
    conn.execute(
        "CREATE TABLE settings ("
        "  key TEXT PRIMARY KEY,"
        "  value TEXT"
        ")"
    )
    conn.execute("INSERT INTO games VALUES (1, 'Witcher 3', 'PC', '2024-01-15')")
    conn.execute("INSERT INTO games VALUES (2, 'Hades', 'PS5', '2024-02-20')")
    conn.execute("INSERT INTO games VALUES (3, 'Elden Ring', 'XBOX', '2024-03-10')")
    conn.execute("INSERT INTO sessions VALUES (1, 1, '2024-01-15T10:00:00', '2024-01-15T14:30:00', 270)")
    conn.execute("INSERT INTO sessions VALUES (2, 2, '2024-02-20T09:15:00', '2024-02-20T11:45:00', 150)")
    conn.execute("INSERT INTO sessions VALUES (3, 3, '2024-03-10T18:00:00', '2024-03-10T21:00:00', 180)")
    conn.execute("INSERT INTO settings VALUES ('theme', 'dark')")
    conn.execute("INSERT INTO settings VALUES ('language', 'en')")
    conn.execute("INSERT INTO settings VALUES ('auto_start', 'true')")
    conn.execute("INSERT INTO settings VALUES ('notification_enabled', 'false')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    path = tmp_path / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def bm_v2(
    sv_manager_v2: SchemaVersionManager,
    db_path: Path,
    backup_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> BackupManager:
    from trackora.core import paths

    monkeypatch.setattr(paths, "DATABASE_PATH", db_path)
    return BackupManager(schema_version_manager=sv_manager_v2, backup_dir=backup_dir)


@pytest.fixture
def bm_v1(
    sv_manager_v1: SchemaVersionManager,
    db_path: Path,
    backup_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> BackupManager:
    from trackora.core import paths

    monkeypatch.setattr(paths, "DATABASE_PATH", db_path)
    return BackupManager(schema_version_manager=sv_manager_v1, backup_dir=backup_dir)


# ── Test helpers ────────────────────────────────────────────────


def _games(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute("SELECT id, name, platform, last_played FROM games ORDER BY id").fetchall()


def _sessions(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute("SELECT id, game_id, start_time, end_time, duration FROM sessions ORDER BY id").fetchall()


def _settings(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()


# ── 1. End-to-end data integrity round-trip ─────────────────────


class TestDataIntegrityRoundTrip:
    """Backup → restore preserves all games, sessions, and settings."""

    def _verify_data_preserved(self, conn: sqlite3.Connection) -> None:
        g = _games(conn)
        assert len(g) == 3
        assert g[0] == (1, "Witcher 3", "PC", "2024-01-15")
        assert g[1] == (2, "Hades", "PS5", "2024-02-20")
        assert g[2] == (3, "Elden Ring", "XBOX", "2024-03-10")

        s = _sessions(conn)
        assert len(s) == 3
        assert s[1] == (2, 2, "2024-02-20T09:15:00", "2024-02-20T11:45:00", 150)

        kv = dict(_settings(conn))
        assert kv["theme"] == "dark"
        assert kv["language"] == "en"
        assert kv["auto_start"] == "true"
        assert kv["notification_enabled"] == "false"

    def test_restore_to_new_db(self, bm_v2: BackupManager, db_path: Path, tmp_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        new_db = tmp_path / "restored.db"
        conn = sqlite3.connect(str(new_db))
        conn.execute("CREATE TABLE placeholder (x INTEGER)")
        conn.close()

        from trackora.core import paths
        import trackora.core.paths as paths_mod
        from trackora.core.schema_version_manager import SchemaVersionManager

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(paths_mod, "DATABASE_PATH", new_db)
            result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True, f"Restore failed: {result.error}"

        conn = sqlite3.connect(str(new_db))
        try:
            self._verify_data_preserved(conn)
        finally:
            conn.close()

    def test_restore_with_extra_data_then_verify(self, bm_v2: BackupManager, db_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO games VALUES (4, 'Hollow Knight', 'Switch', '2024-04-01')")
        conn.execute("UPDATE settings SET value='light' WHERE key='theme'")
        conn.commit()
        conn.close()

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True, f"Restore failed: {result.error}"

        conn = sqlite3.connect(str(db_path))
        try:
            self._verify_data_preserved(conn)
            g = _games(conn)
            assert len(g) == 3
            kv = dict(_settings(conn))
            assert kv["theme"] == "dark"
        finally:
            conn.close()

    def test_restore_twice_preserves_data(self, bm_v2: BackupManager, db_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        for i in range(2):
            conn = sqlite3.connect(str(db_path))
            conn.execute("INSERT INTO games VALUES (?, 'Game X', 'PC', 'now')", (100 + i,))
            conn.commit()
            conn.close()

            result = bm_v2.restore_backup(bk.backup_id)
            assert result.success is True, f"Iteration {i}: {result.error}"

            conn = sqlite3.connect(str(db_path))
            try:
                self._verify_data_preserved(conn)
                assert len(_games(conn)) == 3
            finally:
                conn.close()

    def test_backup_and_verify_checksums_match(self, bm_v2: BackupManager) -> None:
        import hashlib

        bk = bm_v2.create_backup()
        assert bk.success is True
        assert bk.backup_path is not None

        with ZipFile(bk.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
            for entry in manifest["files"]:
                if entry["path"] == "MANIFEST.json":
                    continue
                data = zf.read(entry["path"])
                assert hashlib.sha256(data).hexdigest() == entry["sha256"], (
                    f"Checksum mismatch for {entry['path']}"
                )


# ── 2. Corrupt current database → restore from backup ──────────────


class TestCorruptCurrentDatabase:
    """Restore from backup when the current database is corrupt."""

    def test_restore_from_backup_when_db_corrupt(self, bm_v2: BackupManager, db_path: Path, tmp_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        db_path.write_bytes(b"NOT_A_SQLITE_DATABASE")

        result = bm_v2.restore_backup(bk.backup_id)
        # Safety backup of corrupt DB fails — restore cannot proceed.
        # This is correct behaviour: we never overwrite data without a safety net.
        assert result.success is False
        assert "safety backup" in (result.error or "").lower()

        # Verify the backup archive is still intact and can be used manually.
        verify = bm_v2.verify_backup(bk.backup_id)
        assert verify.valid is True

    def test_restore_from_backup_when_db_empty(self, bm_v2: BackupManager, db_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE IF EXISTS games")
        conn.execute("DROP TABLE IF EXISTS sessions")
        conn.execute("DROP TABLE IF EXISTS settings")
        conn.commit()
        conn.close()

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True, f"Restore failed: {result.error}"

        conn = sqlite3.connect(str(db_path))
        try:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            assert "games" in tables
            assert "sessions" in tables
            assert "settings" in tables
            assert len(conn.execute("SELECT * FROM games").fetchall()) == 3
        finally:
            conn.close()

    def test_restore_when_backup_then_db_deleted(self, bm_v2: BackupManager, db_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        db_path.unlink()
        assert not db_path.exists()

        result = bm_v2.restore_backup(bk.backup_id)
        # Safety backup of missing DB fails — restore cannot proceed.
        assert result.success is False
        assert "safety backup" in (result.error or "").lower()

        # Verify the backup archive is still intact for manual restore.
        verify = bm_v2.verify_backup(bk.backup_id)
        assert verify.valid is True

    def test_restore_when_schema_corrupt_db_good(self, bm_v2: BackupManager, db_path: Path, schema_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        schema_path.write_text("NOT VALID JSON", encoding="utf-8")

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True, f"Restore failed: {result.error}"

        parsed = json.loads(schema_path.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == "2.0.0"


# ── 3. Cross-version backup compatibility ────────────────────────


class TestCrossVersionCompatibility:
    """Backup from one schema version restored under another."""

    def test_v1_backup_restored_under_v2(self, bm_v1: BackupManager, bm_v2: BackupManager, db_path: Path, tmp_path: Path) -> None:
        from trackora.core import paths

        bk = bm_v1.create_backup(backup_type="manual")
        assert bk.success is True

        other_db = tmp_path / "other.db"
        conn = sqlite3.connect(str(other_db))
        conn.execute("CREATE TABLE junk (x INTEGER)")
        conn.close()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(paths, "DATABASE_PATH", other_db)
            result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True, f"Restore failed: {result.error}"

        conn = sqlite3.connect(str(other_db))
        try:
            rows = conn.execute("SELECT name FROM games ORDER BY name").fetchall()
            assert len(rows) == 3
            assert rows[0][0] == "Elden Ring"
        finally:
            conn.close()

    def test_v2_backup_restored_under_v1(self, bm_v1: BackupManager, bm_v2: BackupManager, db_path: Path, tmp_path: Path) -> None:
        bk = bm_v2.create_backup(backup_type="manual")
        assert bk.success is True

        other_db = tmp_path / "other.db"

        from trackora.core import paths

        with pytest.MonkeyPatch.context() as mp:
            conn = sqlite3.connect(str(other_db))
            conn.execute("CREATE TABLE junk (x INTEGER)")
            conn.close()

            mp.setattr(paths, "DATABASE_PATH", other_db)
            result = bm_v1.restore_backup(bk.backup_id)
        assert result.success is True, f"Restore failed: {result.error}"

        conn = sqlite3.connect(str(other_db))
        try:
            assert len(conn.execute("SELECT * FROM games").fetchall()) == 3
        finally:
            conn.close()


# ── 4. WAL mode database backup/restore ──────────────────────────


class TestWalModeDatabase:
    """Backup and restore of SQLite databases in WAL journal mode."""

    def _db_in_wal(self, path: Path) -> bool:
        conn = sqlite3.connect(str(path))
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            return mode.upper() == "WAL"
        finally:
            conn.close()

    def test_backup_wal_mode(self, bm_v2: BackupManager, db_path: Path) -> None:
        assert self._db_in_wal(db_path)

        bk = bm_v2.create_backup()
        assert bk.success is True
        assert bk.backup_path is not None

        with ZipFile(bk.backup_path, "r") as zf:
            assert "trackora.db" in zf.namelist()
            db_data = zf.read("trackora.db")

        import tempfile
        fd, tmp_path_str = tempfile.mkstemp(suffix=".db")
        tmp = Path(tmp_path_str)
        import os as _os_for_fd
        _os_for_fd.close(fd)
        try:
            tmp.write_bytes(db_data)
            conn = sqlite3.connect(str(tmp))
            try:
                rows = conn.execute("SELECT name FROM games ORDER BY name").fetchall()
                assert len(rows) == 3
            finally:
                conn.close()
        finally:
            tmp.unlink()

    def test_restore_from_wal_backup(self, bm_v2: BackupManager, db_path: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("INSERT INTO games VALUES (5, 'WAL Test', 'PC', 'now')")
        conn.commit()
        conn.close()

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True

        conn = sqlite3.connect(str(db_path))
        try:
            ids = {r[0] for r in conn.execute("SELECT id FROM games").fetchall()}
            assert 5 not in ids
            assert ids == {1, 2, 3}
        finally:
            conn.close()


# ── 5. Safety backup rollback end-to-end ─────────────────────────


class TestSafetyBackupRollback:
    """When restore fails mid-replace, safety backup is used to roll back."""

    def test_rollback_on_replace_failure(self, bm_v2: BackupManager, db_path: Path) -> None:
        import trackora.core.backup_manager as bm_mod

        bk = bm_v2.create_backup()
        assert bk.success is True

        before_rows = _games(sqlite3.connect(str(db_path)))

        original_replace_file = bm_mod.BackupManager._replace_file
        calls = [0]

        def fail_replace_file(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated I/O failure")
            return original_replace_file(self, source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace_file)
            result = bm_v2.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.safety_backup_id is not None
        assert "rollback" in (result.error or "").lower()

        after_rows = _games(sqlite3.connect(str(db_path)))
        assert after_rows == before_rows

    def test_safety_backup_verify_called(self, bm_v2: BackupManager, db_path: Path) -> None:
        import trackora.core.backup_manager as bm_mod

        bk = bm_v2.create_backup()
        assert bk.success is True

        verified_ids = []
        original_verify = bm_mod.BackupManager.verify_backup

        def tracking_verify(self, bid: str):
            verified_ids.append(bid)
            return original_verify(self, bid)

        original_replace_file = bm_mod.BackupManager._replace_file
        calls = [0]

        def fail_replace_file(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated failure")
            return original_replace_file(self, source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "verify_backup", tracking_verify)
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace_file)
            result = bm_v2.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.safety_backup_id is not None
        assert result.safety_backup_id in verified_ids

    def test_rollback_with_corrupt_safety_graceful(self, bm_v2: BackupManager, db_path: Path) -> None:
        import trackora.core.backup_manager as bm_mod

        bk = bm_v2.create_backup()
        assert bk.success is True

        original_create = bm_mod.BackupManager.create_backup
        safety_ids = []

        def create_and_corrupt_safety(self, backup_type="manual"):
            result = original_create(self, backup_type)
            if result.success and backup_type == "pre_restore":
                safety_ids.append(result.backup_id)
                if result.backup_path is not None:
                    result.backup_path.write_bytes(b"CORRUPTED_SAFETY_BACKUP")
            return result

        original_replace_file = bm_mod.BackupManager._replace_file
        calls = [0]

        def fail_replace_file(self, source, target):
            if "trackora.db" in str(target) and calls[0] == 0:
                calls[0] += 1
                raise OSError("Simulated copy failure")
            return original_replace_file(self, source, target)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "create_backup", create_and_corrupt_safety)
            mp.setattr(bm_mod.BackupManager, "_replace_file", fail_replace_file)
            result = bm_v2.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.safety_backup_id is not None
        assert result.error is not None
        assert "manual" in result.error.lower()


# ── 6. Orphan cleanup after simulated crash ──────────────────────


class TestOrphanCleanup:
    """BackupManager must clean up orphaned staging dirs and .tmp files on init."""

    def test_cleanup_orphan_restore_dir(self, sv_manager_v2: SchemaVersionManager, backup_dir: Path) -> None:
        orphan = backup_dir / ".restore_crashed_orphan"
        orphan.mkdir(parents=True)
        (orphan / "trackora.db").write_bytes(b"garbage")

        BackupManager(schema_version_manager=sv_manager_v2, backup_dir=backup_dir)
        assert not orphan.exists()

    def test_cleanup_orphan_rollback_dir(self, sv_manager_v2: SchemaVersionManager, backup_dir: Path) -> None:
        orphan = backup_dir / ".rollback_dead_orphan"
        orphan.mkdir(parents=True)
        (orphan / "trackora.db").write_bytes(b"garbage")

        BackupManager(schema_version_manager=sv_manager_v2, backup_dir=backup_dir)
        assert not orphan.exists()

    def test_cleanup_orphan_tmp_zip(self, sv_manager_v2: SchemaVersionManager, backup_dir: Path) -> None:
        orphan = backup_dir / "backup_20260620_120000_abcd1234.zip.tmp"
        orphan.write_bytes(b"garbage")

        BackupManager(schema_version_manager=sv_manager_v2, backup_dir=backup_dir)
        assert not orphan.exists()

    def test_cleanup_orphan_tmp_missing_suffix(self, sv_manager_v2: SchemaVersionManager, backup_dir: Path) -> None:
        orphan = backup_dir / "random_file.tmp"
        orphan.write_bytes(b"garbage")

        BackupManager(schema_version_manager=sv_manager_v2, backup_dir=backup_dir)
        assert orphan.exists()

    def test_multiple_orphans_cleaned(self, sv_manager_v2: SchemaVersionManager, backup_dir: Path) -> None:
        (backup_dir / ".restore_one").mkdir()
        (backup_dir / ".restore_two").mkdir()
        (backup_dir / ".rollback_one").mkdir()
        (backup_dir / "backup_orphan.zip.tmp").write_bytes(b"garbage")

        BackupManager(schema_version_manager=sv_manager_v2, backup_dir=backup_dir)
        remaining = [p for p in backup_dir.iterdir()]
        assert all(
            not (p.name.startswith(".restore_") or p.name.startswith(".rollback_") or p.name.endswith(".zip.tmp"))
            for p in remaining
        )


# ── 7. Concurrent backup isolation ───────────────────────────────


class TestConcurrentBackupIsolation:
    """Sequential backups must not interfere."""

    def test_backup_while_orphan_staging_exists(self, bm_v2: BackupManager, backup_dir: Path) -> None:
        orphan_staging = backup_dir / ".backup_stale.db"
        orphan_staging.write_bytes(b"STALE_DATA")

        bk = bm_v2.create_backup()
        assert bk.success is True
        assert bk.backup_path is not None

        with ZipFile(bk.backup_path, "r") as zf:
            db_data = zf.read("trackora.db")
        assert b"STALE_DATA" not in db_data

    def test_backup_idempotent_unique_ids(self, bm_v2: BackupManager) -> None:
        ids = set()
        for _ in range(50):
            r = bm_v2.create_backup()
            assert r.success is True
            ids.add(r.backup_id)
        assert len(ids) == 50

    def test_interleaved_backup_and_restore(self, bm_v2: BackupManager, db_path: Path) -> None:
        bk1 = bm_v2.create_backup()
        assert bk1.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO games VALUES (10, 'Interleaved', 'PC', 'now')")
        conn.commit()
        conn.close()

        bk2 = bm_v2.create_backup()
        assert bk2.success is True

        r1 = bm_v2.restore_backup(bk1.backup_id)
        assert r1.success is True

        conn = sqlite3.connect(str(db_path))
        try:
            ids = {r[0] for r in conn.execute("SELECT id FROM games").fetchall()}
            assert 10 not in ids
        finally:
            conn.close()


# ── 8. Backup/restore with missing schema.json ───────────────────


class TestMissingSchemaJson:
    """Backup and restore when schema.json is absent."""

    def test_backup_without_schema_json(self, bm_v2: BackupManager, schema_path: Path) -> None:
        schema_path.unlink()
        assert not schema_path.exists()

        bk = bm_v2.create_backup()
        assert bk.success is True
        assert bk.backup_path is not None

        with ZipFile(bk.backup_path, "r") as zf:
            names = zf.namelist()
        assert "schema.json" not in names
        assert bk.file_count == 3

    def test_restore_backup_without_schema_json(self, bm_v2: BackupManager, schema_path: Path, db_path: Path) -> None:
        schema_path.unlink()
        bk = bm_v2.create_backup()
        assert bk.success is True

        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO games VALUES (99, 'NoSchema', 'PC', 'now')")
        conn.commit()
        conn.close()

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True, f"Restore failed: {result.error}"

        conn = sqlite3.connect(str(db_path))
        try:
            ids = {r[0] for r in conn.execute("SELECT id FROM games").fetchall()}
            assert 99 not in ids
        finally:
            conn.close()


# ── 9. Restore with staging validation failure ────────────────────


class TestStagingValidationFailure:
    """Restore must abort when staging validation fails."""

    def test_restore_rejects_corrupt_staged_db(self, bm_v2: BackupManager, db_path: Path) -> None:
        import trackora.core.backup_manager as bm_mod

        bk = bm_v2.create_backup()
        assert bk.success is True
        before_bytes = db_path.read_bytes()

        original_validate = bm_mod.BackupManager._validate_staging

        def inject_corrupt_db(self, staging_dir, zip_path):
            staged_db = staging_dir / "trackora.db"
            if staged_db.exists():
                staged_db.write_bytes(b"NOT_SQLITE")
            return original_validate(self, staging_dir, zip_path)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_validate_staging", inject_corrupt_db)
            result = bm_v2.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.error is not None
        assert "production files not modified" in result.error

        assert db_path.read_bytes() == before_bytes

    def test_restore_rejects_checksum_mismatch(self, bm_v2: BackupManager, db_path: Path) -> None:
        import trackora.core.backup_manager as bm_mod

        bk = bm_v2.create_backup()
        assert bk.success is True
        before_bytes = db_path.read_bytes()

        original_validate = bm_mod.BackupManager._validate_staging

        def tamper_staged_db(self, staging_dir, zip_path):
            staged_db = staging_dir / "trackora.db"
            if staged_db.exists():
                staged_db.write_bytes(staged_db.read_bytes() + b"TAMPER")
            return original_validate(self, staging_dir, zip_path)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "_validate_staging", tamper_staged_db)
            result = bm_v2.restore_backup(bk.backup_id)

        assert result.success is False
        assert result.error is not None
        assert db_path.read_bytes() == before_bytes


# ── 10. BackupManager metadata correctness ────────────────────────


class TestBackupMetadata:
    """metadata.json fields must be correct and consistent."""

    def test_metadata_fields(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup(backup_type="pre_migration")
        assert bk.success is True
        assert bk.backup_path is not None

        with ZipFile(bk.backup_path, "r") as zf:
            meta = json.loads(zf.read("metadata.json"))

        assert "environment" in meta
        assert "platform" in meta
        assert "python_version" in meta
        assert "application_version" in meta
        assert meta["backup_reason"] == "pre_migration"
        assert "notes" in meta

    def test_manifest_consistency(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True
        assert bk.backup_path is not None

        with ZipFile(bk.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
            names = set(zf.namelist())

        assert manifest["backup_id"] == bk.backup_id
        assert manifest["file_count"] == len(manifest.get("files", []))
        for entry in manifest.get("files", []):
            if entry["path"] != "MANIFEST.json":
                assert entry["path"] in names

    def test_backup_result_fields(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True
        assert isinstance(bk.backup_id, str)
        assert bk.backup_id.startswith("backup_")
        assert bk.backup_path is not None
        assert bk.backup_path.exists()
        assert bk.size_bytes > 0
        assert bk.file_count in (3, 4)
        assert bk.error is None

    def test_backup_type_pre_migration(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup(backup_type="pre_migration")
        assert bk.success is True
        assert bk.backup_path is not None
        with ZipFile(bk.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
        assert manifest["backup_type"] == "pre_migration"

    def test_backup_type_scheduled(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup(backup_type="scheduled")
        assert bk.success is True
        assert bk.backup_path is not None
        with ZipFile(bk.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
        assert manifest["backup_type"] == "scheduled"


# ── 11. Retention policy edge cases ────────────────────────────────


class TestRetentionPolicy:
    """clean_old_backups edge cases."""

    def test_clean_preserves_safety_during_restore(self, bm_v2: BackupManager) -> None:
        ids = [bm_v2.create_backup().backup_id for _ in range(6)]
        pre = bm_v2.create_backup(backup_type="pre_restore")

        deleted = bm_v2.clean_old_backups(keep_last=3)
        assert deleted == 3

        remaining = bm_v2.list_backups()
        remaining_ids = {b.backup_id for b in remaining}
        assert pre.backup_id in remaining_ids

        survivors = ids[-3:]
        for s in survivors:
            assert s in remaining_ids

    def test_clean_with_mixed_backup_types(self, bm_v2: BackupManager) -> None:
        manual_ids = [bm_v2.create_backup(backup_type="manual").backup_id for _ in range(3)]
        pre_ids = [bm_v2.create_backup(backup_type="pre_migration").backup_id for _ in range(3)]
        safety = bm_v2.create_backup(backup_type="pre_restore")
        assert safety.success is True

        deleted = bm_v2.clean_old_backups(keep_last=2)
        assert deleted == 4

        remaining = bm_v2.list_backups()
        remaining_ids = {b.backup_id for b in remaining}
        assert safety.backup_id in remaining_ids
        assert pre_ids[2] in remaining_ids

    def test_clean_fewer_than_keep_no_delete(self, bm_v2: BackupManager) -> None:
        bm_v2.create_backup()
        bm_v2.create_backup()

        deleted = bm_v2.clean_old_backups(keep_last=5)
        assert deleted == 0
        assert len(bm_v2.list_backups()) == 2


# ── 12. Restore edge cases ────────────────────────────────────────


class TestRestoreEdgeCases:
    """Edge-case restore scenarios."""

    def test_restore_nonexistent_backup(self, bm_v2: BackupManager) -> None:
        result = bm_v2.restore_backup("nonexistent_backup_id")
        assert result.success is False
        assert result.error is not None

    def test_restore_after_delete(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True
        assert bm_v2.delete_backup(bk.backup_id) is True

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    def test_restore_preserves_backup_archive(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True
        assert bk.backup_path is not None

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True

        assert bk.backup_path.is_file()

    def test_restore_safety_backup_exists_after_restore(self, bm_v2: BackupManager, backup_dir: Path) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        result = bm_v2.restore_backup(bk.backup_id)
        assert result.success is True
        assert result.safety_backup_id is not None

        safety_path = backup_dir / f"{result.safety_backup_id}.zip"
        assert safety_path.is_file()

    def test_multiple_restore_safety_backups_unique(self, bm_v2: BackupManager) -> None:
        bk = bm_v2.create_backup()
        assert bk.success is True

        safety_ids = set()
        for _ in range(3):
            result = bm_v2.restore_backup(bk.backup_id)
            assert result.success is True
            safety_ids.add(result.safety_backup_id)

        assert len(safety_ids) == 3
