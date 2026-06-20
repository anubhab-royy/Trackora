"""Tests for BackupManager — data classes, __init__, create_backup."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from trackora.core.schema_version import SchemaVersion
from trackora.core.schema_version_manager import SchemaVersionManager


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def schema_path(tmp_path: Path) -> Path:
    return tmp_path / "schema.json"


@pytest.fixture
def sv_manager(schema_path: Path) -> SchemaVersionManager:
    svm = SchemaVersionManager(schema_path=schema_path)
    svm.write(SchemaVersion(2, 0, 0), description="test")
    return svm


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "trackora.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    path = tmp_path / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def bm(
    sv_manager: SchemaVersionManager,
    db_path: Path,
    backup_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> type:
    from trackora.core.backup_manager import BackupManager
    from trackora.core import paths

    monkeypatch.setattr(paths, "DATABASE_PATH", db_path)
    return BackupManager(schema_version_manager=sv_manager, backup_dir=backup_dir)


# ── 1.1: Data Classes ──────────────────────────────────────────────


class TestBackupResult:
    def test_frozen(self) -> None:
        from trackora.core.backup_manager import BackupResult
        r = BackupResult(
            success=True,
            backup_id="test_123",
            backup_path=Path("/tmp/test.zip"),
            size_bytes=1024,
            file_count=4,
            created_at=datetime(2026, 6, 20, 12, 0, 0),
        )
        with pytest.raises(FrozenInstanceError):
            r.success = False  # type: ignore[misc]

    def test_fields(self) -> None:
        from trackora.core.backup_manager import BackupResult
        r = BackupResult(
            success=True,
            backup_id="backup_20260620_120000_abcd1234",
            backup_path=Path("/tmp/backup.zip"),
            size_bytes=2048,
            file_count=4,
            created_at=datetime(2026, 6, 20, 12, 0, 0),
        )
        assert r.success is True
        assert r.backup_id == "backup_20260620_120000_abcd1234"
        assert r.backup_path == Path("/tmp/backup.zip")
        assert r.size_bytes == 2048
        assert r.file_count == 4
        assert r.created_at == datetime(2026, 6, 20, 12, 0, 0)

    def test_error_default_none(self) -> None:
        from trackora.core.backup_manager import BackupResult
        r = BackupResult(
            success=True,
            backup_id="test_123",
            backup_path=None,
            size_bytes=0,
            file_count=0,
            created_at=datetime(2026, 6, 20, 12, 0, 0),
        )
        assert r.error is None

    def test_error_custom(self) -> None:
        from trackora.core.backup_manager import BackupResult
        r = BackupResult(
            success=False,
            backup_id="test_123",
            backup_path=None,
            size_bytes=0,
            file_count=0,
            created_at=datetime(2026, 6, 20, 12, 0, 0),
            error="Disk full",
        )
        assert r.error == "Disk full"


class TestRestoreResult:
    def test_frozen(self) -> None:
        from trackora.core.backup_manager import RestoreResult
        r = RestoreResult(success=True, backup_id="test_123")
        with pytest.raises(FrozenInstanceError):
            r.success = False  # type: ignore[misc]

    def test_fields(self) -> None:
        from trackora.core.backup_manager import RestoreResult
        r = RestoreResult(success=True, backup_id="test_123", safety_backup_id="safety_1")
        assert r.success is True
        assert r.backup_id == "test_123"
        assert r.safety_backup_id == "safety_1"

    def test_error_default(self) -> None:
        from trackora.core.backup_manager import RestoreResult
        r = RestoreResult(success=True, backup_id="test_123")
        assert r.error is None

    def test_safety_backup_default(self) -> None:
        from trackora.core.backup_manager import RestoreResult
        r = RestoreResult(success=False, backup_id="test_123", error="failed")
        assert r.safety_backup_id is None


class TestVerificationResult:
    def test_frozen(self) -> None:
        from trackora.core.backup_manager import VerificationResult
        r = VerificationResult(valid=True, backup_id="test_123")
        with pytest.raises(FrozenInstanceError):
            r.valid = False  # type: ignore[misc]

    def test_fields(self) -> None:
        from trackora.core.backup_manager import VerificationResult
        r = VerificationResult(valid=True, backup_id="test_123")
        assert r.valid is True
        assert r.backup_id == "test_123"

    def test_checksum_errors_default(self) -> None:
        from trackora.core.backup_manager import VerificationResult
        r = VerificationResult(valid=True, backup_id="test_123")
        assert r.checksum_errors == []

    def test_missing_files_default(self) -> None:
        from trackora.core.backup_manager import VerificationResult
        r = VerificationResult(valid=True, backup_id="test_123")
        assert r.missing_files == []

    def test_checksum_errors_custom(self) -> None:
        from trackora.core.backup_manager import VerificationResult
        r = VerificationResult(
            valid=False,
            backup_id="test_123",
            checksum_errors=["trackora.db"],
            missing_files=["schema.json"],
        )
        assert r.checksum_errors == ["trackora.db"]
        assert r.missing_files == ["schema.json"]


class TestBackupInfo:
    def test_frozen(self) -> None:
        from trackora.core.backup_manager import BackupInfo
        r = BackupInfo(
            backup_id="test_123",
            backup_path=Path("/tmp/test.zip"),
            size_bytes=1024,
            created_at=datetime(2026, 6, 20, 12, 0, 0),
            schema_version="2.0.0",
            trackora_version="2.0.0",
            backup_type="manual",
            file_count=4,
        )
        with pytest.raises(FrozenInstanceError):
            r.backup_id = "changed"  # type: ignore[misc]

    def test_fields(self) -> None:
        from trackora.core.backup_manager import BackupInfo
        r = BackupInfo(
            backup_id="backup_20260620_120000_abcd1234",
            backup_path=Path("/tmp/backup.zip"),
            size_bytes=4096,
            created_at=datetime(2026, 6, 20, 12, 0, 0),
            schema_version="2.0.0",
            trackora_version="2.0.0",
            backup_type="manual",
            file_count=4,
        )
        assert r.backup_id == "backup_20260620_120000_abcd1234"
        assert r.schema_version == "2.0.0"
        assert r.trackora_version == "2.0.0"
        assert r.backup_type == "manual"
        assert r.file_count == 4


# ── 1.2: __init__ ─────────────────────────────────────────────────


class TestInit:
    def test_init_default_backup_dir(self, sv_manager: SchemaVersionManager) -> None:
        from trackora.core.backup_manager import BackupManager
        from trackora.core.paths import BACKUPS_DIR
        bm = BackupManager(schema_version_manager=sv_manager)
        assert bm._backup_dir == BACKUPS_DIR

    def test_init_custom_backup_dir(self, sv_manager: SchemaVersionManager, tmp_path: Path) -> None:
        from trackora.core.backup_manager import BackupManager
        custom = tmp_path / "my_backups"
        bm = BackupManager(schema_version_manager=sv_manager, backup_dir=custom)
        assert bm._backup_dir == custom

    def test_init_stores_schema_version_manager(self, sv_manager: SchemaVersionManager) -> None:
        from trackora.core.backup_manager import BackupManager
        bm = BackupManager(schema_version_manager=sv_manager)
        assert bm._schema_version_manager is sv_manager

    def test_init_cleans_orphan_tmp(self, sv_manager: SchemaVersionManager, tmp_path: Path) -> None:
        from trackora.core.backup_manager import BackupManager
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True)
        orphan = backup_dir / "backup_20260620_120000_abcd1234.zip.tmp"
        orphan.write_text("garbage", encoding="utf-8")

        BackupManager(schema_version_manager=sv_manager, backup_dir=backup_dir)
        assert not orphan.exists()

    def test_init_cleans_orphan_restore_dirs(self, sv_manager: SchemaVersionManager, tmp_path: Path) -> None:
        from trackora.core.backup_manager import BackupManager
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True)
        orphan = backup_dir / ".restore_abcd1234"
        orphan.mkdir()
        (orphan / "trackora.db").write_text("garbage", encoding="utf-8")

        BackupManager(schema_version_manager=sv_manager, backup_dir=backup_dir)
        assert not orphan.exists()

    def test_init_cleans_orphan_tmp_failure_logged(
        self, sv_manager: SchemaVersionManager, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from trackora.core.backup_manager import BackupManager
        caplog.set_level(logging.WARNING)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True)
        orphan = backup_dir / "backup_test.zip.tmp"
        orphan.write_text("garbage", encoding="utf-8")
        backup_dir.chmod(0o555)

        try:
            BackupManager(schema_version_manager=sv_manager, backup_dir=backup_dir)
            assert any("orphan" in r.message.lower() for r in caplog.records)
        finally:
            backup_dir.chmod(0o755)

    def test_init_does_not_create_backup_dir(self, sv_manager: SchemaVersionManager, tmp_path: Path) -> None:
        from trackora.core.backup_manager import BackupManager
        non_existent = tmp_path / "non_existent"
        bm = BackupManager(schema_version_manager=sv_manager, backup_dir=non_existent)
        assert bm._backup_dir == non_existent
        assert not non_existent.exists()


# ── 2.1: Core backup creation ──────────────────────────────────────


class TestCreateBackup:
    def test_create_backup_file_created(self, bm, backup_dir: Path) -> None:
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.backup_path.suffix == ".zip"
        assert result.backup_path.parent == backup_dir

    def test_create_backup_naming(self, bm) -> None:
        result = bm.create_backup()
        assert result.backup_id.startswith("backup_")
        parts = result.backup_id.split("_")
        assert len(parts) == 4  # backup, YYYYMMDD, HHMMSS, uuid8
        assert len(parts[3]) == 8  # uuid4 first 8 chars
        assert result.backup_path is not None
        assert result.backup_path.name == f"{result.backup_id}.zip"

    def test_create_backup_atomic(self, bm, backup_dir: Path) -> None:
        result = bm.create_backup()
        assert result.success is True
        tmp_files = list(backup_dir.glob("*.zip.tmp"))
        assert tmp_files == []

    def test_create_backup_zip_contents(self, bm) -> None:
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        with ZipFile(result.backup_path, "r") as zf:
            names = zf.namelist()
        assert "MANIFEST.json" in names
        assert "trackora.db" in names
        assert "schema.json" in names
        assert "metadata.json" in names
        assert len(names) == 4

    def test_create_backup_manifest_present(self, bm) -> None:
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        with ZipFile(result.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
        assert manifest["manifest_version"] == "1.0"
        assert manifest["backup_version"] == 1
        assert manifest["backup_id"] == result.backup_id
        assert manifest["file_count"] == 4

    # ── 2.2: Manifest + checksums ───────────────────────────────

    def test_create_backup_manifest_stored(self, bm) -> None:
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        with ZipFile(result.backup_path, "r") as zf:
            info = zf.getinfo("MANIFEST.json")
        assert info.compress_type == ZIP_STORED

    def test_create_backup_manifest_checksums(self, bm) -> None:
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        with ZipFile(result.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
        files = manifest["files"]
        assert len(files) == 4
        for entry in files:
            assert "path" in entry
            assert "size" in entry
            assert "sha256" in entry
            assert isinstance(entry["sha256"], str)
            assert len(entry["sha256"]) == 64  # SHA-256 hex

    def test_create_backup_checksums_valid(self, bm) -> None:
        import hashlib
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        with ZipFile(result.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
            for entry in manifest["files"]:
                # MANIFEST.json's own checksum is self-referential
                # (circular by design); verified via ZIP CRC-32 instead.
                if entry["path"] == "MANIFEST.json":
                    continue
                data = zf.read(entry["path"])
                expected_sha = hashlib.sha256(data).hexdigest()
                assert entry["sha256"] == expected_sha, (
                    f"Checksum mismatch for {entry['path']}"
                )

    def test_create_backup_metadata(self, bm) -> None:
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        with ZipFile(result.backup_path, "r") as zf:
            metadata = json.loads(zf.read("metadata.json"))
        assert "environment" in metadata
        assert "platform" in metadata
        assert "python_version" in metadata
        assert "application_version" in metadata
        assert "backup_reason" in metadata
        assert "notes" in metadata
        assert metadata["backup_reason"] == "manual"

    def test_create_backup_backup_result(self, bm) -> None:
        from trackora.core.backup_manager import BackupResult
        result = bm.create_backup()
        assert isinstance(result, BackupResult)
        assert result.success is True
        assert isinstance(result.backup_id, str)
        assert isinstance(result.backup_path, Path)
        assert isinstance(result.size_bytes, int)
        assert result.size_bytes > 0
        assert isinstance(result.file_count, int)
        assert result.file_count == 4
        assert isinstance(result.created_at, datetime)
        assert result.error is None

    # ── 2.3: Error handling + edge cases ───────────────────────

    def test_create_backup_missing_db(self, sv_manager, backup_dir, tmp_path, monkeypatch) -> None:
        from trackora.core.backup_manager import BackupManager
        from trackora.core import paths
        missing_db = tmp_path / "nonexistent.db"
        monkeypatch.setattr(paths, "DATABASE_PATH", missing_db)
        bm = BackupManager(schema_version_manager=sv_manager, backup_dir=backup_dir)
        result = bm.create_backup()
        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower() or "does not exist" in result.error.lower()

    def test_create_backup_missing_schema(self, bm, sv_manager, caplog) -> None:
        caplog.set_level(logging.WARNING)
        sv_manager.delete()
        result = bm.create_backup()
        assert result.success is True
        warning_messages = [r.message for r in caplog.records]
        assert any("schema" in msg.lower() for msg in warning_messages)

    def test_create_backup_unicode_paths(self, sv_manager, db_path, tmp_path, monkeypatch) -> None:
        from trackora.core.backup_manager import BackupManager
        from trackora.core import paths
        backup_dir = tmp_path / "bäckups_データ"
        backup_dir.mkdir(parents=True)
        monkeypatch.setattr(paths, "DATABASE_PATH", db_path)
        bm = BackupManager(schema_version_manager=sv_manager, backup_dir=backup_dir)
        result = bm.create_backup()
        assert result.success is True
        assert result.backup_path is not None
        assert backup_dir in result.backup_path.parents
        # Verify we can read the ZIP
        with ZipFile(result.backup_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json"))
        assert manifest["file_count"] == 4

    def test_create_backup_concurrent(self, bm) -> None:
        ids = set()
        for _ in range(10):
            r = bm.create_backup()
            assert r.success is True
            ids.add(r.backup_id)
        assert len(ids) == 10  # All unique


# ── Helpers for verify/restore tests ──────────────────────────


def _make_valid_zip(backup_dir: Path, backup_id: str, db_bytes: bytes = b"db data") -> Path:
    """Create a valid backup ZIP with MANIFEST.json, trackora.db, schema.json, metadata.json."""
    import hashlib
    from zipfile import ZIP_STORED, ZipFile, ZipInfo

    schema_bytes = b'{"schema_version": "2.0.0"}'
    meta_bytes = b'{"environment": "test"}'

    db_sha = hashlib.sha256(db_bytes).hexdigest()
    schema_sha = hashlib.sha256(schema_bytes).hexdigest()
    meta_sha = hashlib.sha256(meta_bytes).hexdigest()

    files_no_manifest = [
        {"path": "trackora.db", "size": len(db_bytes), "sha256": db_sha},
        {"path": "schema.json", "size": len(schema_bytes), "sha256": schema_sha},
        {"path": "metadata.json", "size": len(meta_bytes), "sha256": meta_sha},
    ]

    base = {
        "manifest_version": "1.0",
        "backup_version": 1,
        "created_at": "2026-06-20T12:00:00.000000Z",
        "schema_version": "2.0.0",
        "trackora_version": "1.1.0",
        "backup_type": "manual",
        "backup_id": backup_id,
        "file_count": 4,
    }
    base_bytes = json.dumps({**base, "files": files_no_manifest}, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    manifest_sha = hashlib.sha256(base_bytes).hexdigest()

    final_files = [
        {"path": "MANIFEST.json", "size": len(base_bytes), "sha256": manifest_sha},
        *files_no_manifest,
    ]
    manifest_bytes = json.dumps({**base, "files": final_files}, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"

    zip_path = backup_dir / f"{backup_id}.zip"
    with ZipFile(zip_path, "w") as zf:
        zf.writestr(ZipInfo("MANIFEST.json"), manifest_bytes, compress_type=ZIP_STORED)
        zf.writestr("trackora.db", db_bytes)
        zf.writestr("schema.json", schema_bytes)
        zf.writestr("metadata.json", meta_bytes)
    return zip_path


def _make_minimal_zip_with_manifest(backup_dir: Path, backup_id: str, manifest: dict) -> Path:
    """Create a ZIP with a specific manifest dict."""
    from zipfile import ZIP_STORED, ZipFile, ZipInfo
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    zip_path = backup_dir / f"{backup_id}.zip"
    with ZipFile(zip_path, "w") as zf:
        zf.writestr(ZipInfo("MANIFEST.json"), manifest_bytes, compress_type=ZIP_STORED)
        zf.writestr("trackora.db", b"db data")
    return zip_path


# ── 3: verify_backup() ─────────────────────────────────────────


class TestVerifyBackup:
    def test_verify_valid_backup(self, bm) -> None:
        created = bm.create_backup()
        assert created.success is True
        result = bm.verify_backup(created.backup_id)
        assert result.valid is True
        assert result.error is None

    def test_verify_missing_backup(self, bm) -> None:
        result = bm.verify_backup("nonexistent_backup_id")
        assert result.valid is False
        assert result.error is not None

    def test_verify_corrupt_zip(self, bm, backup_dir: Path) -> None:
        created = bm.create_backup()
        assert created.backup_path is not None
        # Corrupt the ZIP by writing garbage
        created.backup_path.write_bytes(b"this is not a zip file")
        result = bm.verify_backup(created.backup_id)
        assert result.valid is False
        assert result.error is not None

    def test_verify_missing_manifest(self, backup_dir: Path) -> None:
        from zipfile import ZipFile
        backup_id = "test_no_manifest"
        zip_path = backup_dir / f"{backup_id}.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr("trackora.db", b"db data")
        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert "MANIFEST.json" in str(result.error or "")

    def test_verify_invalid_manifest_json(self, backup_dir: Path) -> None:
        from zipfile import ZIP_STORED, ZipFile, ZipInfo
        backup_id = "test_bad_json"
        zip_path = backup_dir / f"{backup_id}.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr(ZipInfo("MANIFEST.json"), b"not valid json{{{", compress_type=ZIP_STORED)
            zf.writestr("trackora.db", b"db data")
        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert result.error is not None

    def test_verify_manifest_not_a_dict(self, backup_dir: Path) -> None:
        """MANIFEST.json is valid JSON but not a dict (e.g. a list)."""
        from zipfile import ZIP_STORED, ZipFile, ZipInfo
        backup_id = "test_list_manifest"
        zip_path = backup_dir / f"{backup_id}.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr(ZipInfo("MANIFEST.json"), b'["not", "a", "dict"]', compress_type=ZIP_STORED)
            zf.writestr("trackora.db", b"db data")
        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert result.error is not None

    def test_verify_missing_required_field(self, backup_dir: Path) -> None:
        """MANIFEST.json is a dict but missing a required field."""
        from zipfile import ZIP_STORED, ZipFile, ZipInfo
        backup_id = "test_missing_field"
        manifest = {"manifest_version": "1.0"}  # missing backup_version, file_count, files
        m_bytes = json.dumps(manifest).encode("utf-8")
        zip_path = backup_dir / f"{backup_id}.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr(ZipInfo("MANIFEST.json"), m_bytes, compress_type=ZIP_STORED)
            zf.writestr("trackora.db", b"db data")
        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert result.error is not None
        assert "required field" in (result.error or "")

    def test_verify_missing_file(self, backup_dir: Path) -> None:
        """Manifest lists trackora.db but ZIP doesn't have it."""
        import hashlib
        backup_id = "test_missing_file"
        manifest = {
            "manifest_version": "1.0",
            "backup_version": 1,
            "created_at": "2026-06-20T12:00:00.000000Z",
            "schema_version": "2.0.0",
            "trackora_version": "1.1.0",
            "backup_type": "manual",
            "backup_id": backup_id,
            "file_count": 2,
            "files": [
                {"path": "MANIFEST.json", "size": 0, "sha256": "0" * 64},
                {"path": "trackora.db", "size": 6, "sha256": hashlib.sha256(b"db data").hexdigest()},
            ],
        }
        zip_path = _make_minimal_zip_with_manifest(backup_dir, backup_id, manifest)
        # Remove trackora.db from ZIP by rewriting
        from zipfile import ZipFile
        new_path = backup_dir / f"{backup_id}_fixed.zip"
        with ZipFile(zip_path, "r") as src:
            with ZipFile(new_path, "w") as dst:
                for name in src.namelist():
                    if name == "trackora.db":
                        continue  # skip it
                    dst.writestr(name, src.read(name))
        zip_path.unlink()
        new_path.rename(zip_path)

        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert "trackora.db" in result.missing_files

    def test_verify_checksum_mismatch(self, backup_dir: Path, bm) -> None:
        created = bm.create_backup()
        assert created.success is True
        assert created.backup_path is not None
        # Tamper with trackora.db inside the ZIP
        from zipfile import ZipFile
        import hashlib
        backup_id = created.backup_id
        zip_path = created.backup_path
        tampered_db = b"TAMPERED DATA"
        # Rewrite ZIP with tampered db
        new_path = backup_dir / f"{backup_id}_tampered.zip"
        with ZipFile(zip_path, "r") as src:
            with ZipFile(new_path, "w") as dst:
                for name in src.namelist():
                    data = src.read(name)
                    if name == "trackora.db":
                        data = tampered_db
                    dst.writestr(name, data)
        zip_path.unlink()
        new_path.rename(zip_path)

        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert "trackora.db" in result.checksum_errors

    def test_verify_wrong_file_count(self, backup_dir: Path) -> None:
        """Manifest says 4 files but ZIP has only 2."""
        from zipfile import ZipFile
        import hashlib
        backup_id = "test_wrong_count"
        manifest = {
            "manifest_version": "1.0",
            "backup_version": 1,
            "created_at": "2026-06-20T12:00:00.000000Z",
            "schema_version": "2.0.0",
            "trackora_version": "1.1.0",
            "backup_type": "manual",
            "backup_id": backup_id,
            "file_count": 4,
            "files": [
                {"path": "MANIFEST.json", "size": 0, "sha256": "0" * 64},
                {"path": "trackora.db", "size": 6, "sha256": hashlib.sha256(b"db data").hexdigest()},
            ],
        }
        zip_path = _make_minimal_zip_with_manifest(backup_dir, backup_id, manifest)
        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert result.error is not None

    def test_verify_empty_backup(self, backup_dir: Path) -> None:
        from zipfile import ZipFile
        backup_id = "test_empty"
        zip_path = backup_dir / f"{backup_id}.zip"
        ZipFile(zip_path, "w").close()
        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is False
        assert result.error is not None

    def test_verify_extra_file_ok(self, backup_dir: Path) -> None:
        """Extra files in ZIP not in manifest should be ignored."""
        import hashlib
        from zipfile import ZIP_STORED, ZipFile, ZipInfo
        backup_id = "test_extra_file"
        db_data = b"db data"
        db_sha = hashlib.sha256(db_data).hexdigest()
        manifest = {
            "manifest_version": "1.0",
            "backup_version": 1,
            "created_at": "2026-06-20T12:00:00.000000Z",
            "schema_version": "2.0.0",
            "trackora_version": "1.1.0",
            "backup_type": "manual",
            "backup_id": backup_id,
            "file_count": 2,
            "files": [
                {"path": "MANIFEST.json", "size": 0, "sha256": "0" * 64},
                {"path": "trackora.db", "size": len(db_data), "sha256": db_sha},
            ],
        }
        m_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        m_sha = hashlib.sha256(m_bytes).hexdigest()
        manifest["files"][0]["sha256"] = m_sha
        manifest["files"][0]["size"] = len(m_bytes)
        final_manifest = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"

        zip_path = backup_dir / f"{backup_id}.zip"
        with ZipFile(zip_path, "w") as zf:
            zf.writestr(ZipInfo("MANIFEST.json"), final_manifest, compress_type=ZIP_STORED)
            zf.writestr("trackora.db", db_data)
            zf.writestr("extra_file.txt", b"this is extra")

        from trackora.core.backup_manager import BackupManager
        from trackora.core.schema_version_manager import SchemaVersionManager
        bm = BackupManager(
            schema_version_manager=SchemaVersionManager(),
            backup_dir=backup_dir,
        )
        result = bm.verify_backup(backup_id)
        assert result.valid is True
        assert result.error is None


# ── 4: restore_backup() ────────────────────────────────────────


class TestRestoreBackup:
    def test_restore_valid_backup(self, bm, db_path: Path, schema_path: Path) -> None:
        import sqlite3
        created = bm.create_backup()
        assert created.success is True

        # Modify current database
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO test VALUES (2, 'modified')")
        conn.commit()
        conn.close()

        # Modify current schema.json
        schema_path.write_text('{"schema_version": "9.9.9", "app_version": "9.9.9", "updated_at": "now"}', encoding="utf-8")

        # Restore from backup
        result = bm.restore_backup(created.backup_id)
        assert result.success is True
        assert result.error is None

        # Verify database restored: id=2 should not exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT value FROM test WHERE id = 2")
        assert cursor.fetchone() is None
        # id=1 should still have original value
        cursor = conn.execute("SELECT value FROM test WHERE id = 1")
        assert cursor.fetchone()[0] == "hello"
        conn.close()

        # Verify schema.json restored
        import json as _json
        restored_schema = _json.loads(schema_path.read_text(encoding="utf-8"))
        assert restored_schema["schema_version"] == "2.0.0"

    def test_restore_creates_safety_backup(self, bm, backup_dir: Path) -> None:
        created = bm.create_backup()
        assert created.success is True

        result = bm.restore_backup(created.backup_id)
        assert result.success is True
        assert result.safety_backup_id is not None

        # Verify safety backup ZIP exists in backup dir
        safety_path = backup_dir / f"{result.safety_backup_id}.zip"
        assert safety_path.is_file()

    def test_restore_safety_backup_has_type(self, bm, backup_dir: Path) -> None:
        import json as _json
        from zipfile import ZipFile
        created = bm.create_backup()
        assert created.success is True

        result = bm.restore_backup(created.backup_id)
        assert result.success is True
        assert result.safety_backup_id is not None

        safety_path = backup_dir / f"{result.safety_backup_id}.zip"
        with ZipFile(safety_path, "r") as zf:
            manifest = _json.loads(zf.read("MANIFEST.json"))
        assert manifest["backup_type"] == "pre_restore"

    def test_restore_fails_corrupt_backup(self, bm) -> None:
        created = bm.create_backup()
        assert created.success is True
        assert created.backup_path is not None

        # Corrupt the backup
        created.backup_path.write_bytes(b"garbage")

        result = bm.restore_backup(created.backup_id)
        assert result.success is False
        assert result.error is not None

    def test_restore_fails_missing_backup(self, bm) -> None:
        result = bm.restore_backup("nonexistent_backup_id")
        assert result.success is False
        assert result.error is not None

    def test_restore_verifies_first(self, bm, backup_dir: Path) -> None:
        """If verify fails, restore should not proceed."""
        import json as _json
        from zipfile import ZipFile
        created = bm.create_backup()
        assert created.success is True

        # Tamper with a file inside the ZIP to make verify fail
        assert created.backup_path is not None
        from zipfile import ZipFile as ZF
        new_path = backup_dir / "tampered.zip"
        with ZF(created.backup_path, "r") as src:
            with ZF(new_path, "w") as dst:
                for name in src.namelist():
                    data = src.read(name)
                    if name == "trackora.db":
                        data = b"TAMPERED"
                    dst.writestr(name, data)
        created.backup_path.unlink()
        new_path.rename(created.backup_path)

        result = bm.restore_backup(created.backup_id)
        assert result.success is False
        assert result.error is not None

    def test_restore_staging_cleanup(self, bm, backup_dir: Path) -> None:
        """After successful restore, no .restore_* directories remain."""
        created = bm.create_backup()
        assert created.success is True

        result = bm.restore_backup(created.backup_id)
        assert result.success is True

        restore_dirs = [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith(".restore_")]
        assert restore_dirs == []

    def test_restore_replace_failure_rollback(self, bm, db_path: Path, backup_dir: Path) -> None:
        """If os.replace fails during restore, safety backup is restored."""
        import os

        created = bm.create_backup()
        assert created.success is True

        original_data = db_path.read_bytes()

        # Modify the database so we can detect rollback
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO test VALUES (99, 'will_be_rolled_back')")
        conn.commit()
        conn.close()

        # Monkeypatch os.replace to fail on the first trackora.db replace
        original_replace = os.replace
        replace_attempts = [0]

        def failing_replace(src: str, dst: str) -> None:
            if "trackora.db" in dst and replace_attempts[0] == 0:
                replace_attempts[0] += 1
                raise OSError("Simulated disk full during replace")
            return original_replace(src, dst)

        import trackora.core.backup_manager as bm_mod
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(bm_mod.os, "replace", failing_replace)
        try:
            result = bm.restore_backup(created.backup_id)
            assert result.success is False
            assert result.error is not None
        finally:
            monkeypatch.undo()

        # Verify original data is intact
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT id FROM test WHERE id = 99")
        assert cursor.fetchone() is not None  # Rolled back to pre-restore state
        conn.close()

    def test_restore_schema_json_replaced(self, bm, schema_path: Path) -> None:
        import json as _json
        created = bm.create_backup()
        assert created.success is True

        # Modify schema.json
        schema_path.write_text('{"schema_version": "9.9.9", "app_version": "9.9.9", "updated_at": "now"}', encoding="utf-8")

        result = bm.restore_backup(created.backup_id)
        assert result.success is True

        restored = _json.loads(schema_path.read_text(encoding="utf-8"))
        assert restored["schema_version"] == "2.0.0"

    def test_restore_trackora_db_replaced(self, bm, db_path: Path) -> None:
        import sqlite3
        created = bm.create_backup()
        assert created.success is True

        # Modify database
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE test")
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO test VALUES (100, 'new_data')")
        conn.commit()
        conn.close()

        result = bm.restore_backup(created.backup_id)
        assert result.success is True

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT value FROM test WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "hello"


# ── 4b: Restore Validation Tests ────────────────────────────────────


class TestRestoreValidation:
    """Post-extraction validation in restore_backup()."""

    def test_restore_validates_staged_db_opens(self, bm, db_path, backup_dir):
        """A valid SQLite database in staging passes validation."""
        import json as _json
        import sqlite3
        from zipfile import ZipFile
        created = bm.create_backup()
        assert created.success is True

        result = bm.restore_backup(created.backup_id)
        assert result.success is True

    def test_restore_rejects_corrupt_staged_db(self, bm, db_path, backup_dir):
        """If staged trackora.db is not valid SQLite, restore fails without touching production."""
        import json as _json
        import sqlite3
        from zipfile import ZipFile

        created = bm.create_backup()
        assert created.success is True
        original_db_data = db_path.read_bytes()

        # We need to make the staging DB corrupt. Patch _validate_staging to inject
        # a corrupt file into staging before validation runs.
        import trackora.core.backup_manager as bm_mod
        original_validate = bm_mod.BackupManager._validate_staging

        def corrupt_validate(self, staging_dir, zip_path):
            # Corrupt the staged db before real validation
            staged_db = staging_dir / "trackora.db"
            if staged_db.exists():
                staged_db.write_bytes(b"NOT_A_SQLITE_DATABASE")
            return original_validate(self, staging_dir, zip_path)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(bm_mod.BackupManager, "_validate_staging", corrupt_validate)
        try:
            result = bm.restore_backup(created.backup_id)
            assert result.success is False
            assert result.error is not None
            assert "production files not modified" in result.error.lower() or "validation" in result.error.lower()
        finally:
            monkeypatch.undo()

        # Production file unchanged
        assert db_path.read_bytes() == original_db_data

    def test_restore_rejects_integrity_failure(self, bm, db_path, backup_dir):
        """A staged DB that fails PRAGMA integrity_check causes validation to fail."""
        import sqlite3
        import json as _json
        from zipfile import ZipFile

        created = bm.create_backup()
        assert created.success is True
        original_db_data = db_path.read_bytes()

        import trackora.core.backup_manager as bm_mod
        original_validate = bm_mod.BackupManager._validate_staging

        def corrupt_integrity_validate(self, staging_dir, zip_path):
            staged_db = staging_dir / "trackora.db"
            if staged_db.exists():
                conn = sqlite3.connect(str(staged_db))
                # Write bad data to trigger integrity failure
                conn.execute("PRAGMA writable_schema = ON;")
                conn.execute("UPDATE sqlite_master SET sql = 'BAD SQL';")
                conn.execute("PRAGMA writable_schema = OFF;")
                conn.commit()
                conn.close()
            return original_validate(self, staging_dir, zip_path)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(bm_mod.BackupManager, "_validate_staging", corrupt_integrity_validate)
        try:
            result = bm.restore_backup(created.backup_id)
            assert result.success is False
            assert result.error is not None
        finally:
            monkeypatch.undo()

        assert db_path.read_bytes() == original_db_data

    def test_restore_validates_checksums(self, bm, db_path, backup_dir):
        """SHA-256 mismatch between manifest and staged file causes validation failure."""
        import json as _json
        from zipfile import ZipFile

        created = bm.create_backup()
        assert created.success is True
        original_db_data = db_path.read_bytes()

        import trackora.core.backup_manager as bm_mod
        original_validate = bm_mod.BackupManager._validate_staging

        def corrupt_checksum_validate(self, staging_dir, zip_path):
            staged_db = staging_dir / "trackora.db"
            if staged_db.exists():
                staged_db.write_bytes(staged_db.read_bytes() + b"EXTRA_BYTES")
            return original_validate(self, staging_dir, zip_path)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(bm_mod.BackupManager, "_validate_staging", corrupt_checksum_validate)
        try:
            result = bm.restore_backup(created.backup_id)
            assert result.success is False
            assert result.error is not None
        finally:
            monkeypatch.undo()

        assert db_path.read_bytes() == original_db_data

    def test_restore_does_not_touch_production_on_validation_failure(self, bm, db_path, backup_dir):
        """Production files must remain unchanged when validation fails."""
        import json as _json
        import sqlite3

        created = bm.create_backup()
        assert created.success is True
        original_db_data = db_path.read_bytes()

        import trackora.core.backup_manager as bm_mod
        original_extract = bm_mod.BackupManager.restore_backup

        # Patch to inject a corrupt file post-extraction pre-validation
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                bm_mod.BackupManager, "_validate_staging",
                lambda self, staging_dir, zip_path: ["Simulated validation failure"],
            )
            result = bm.restore_backup(created.backup_id)
            assert result.success is False

        assert db_path.read_bytes() == original_db_data


class TestAtomicRollback:
    """_restore_from_safety() must use staging + validation + atomic replace."""

    def test_restore_from_safety_uses_staging_dir(self, bm, backup_dir):
        """Safety rollback should create and clean up a staging directory."""
        import sqlite3
        # Create a backup
        created = bm.create_backup()
        assert created.success is True

        # Modify the database so we can detect rollback
        conn = sqlite3.connect(str(bm._backup_dir.parent / "trackora.db"))
        conn.execute("INSERT INTO test VALUES (99, 'rollback_test')")
        conn.commit()
        conn.close()

        # Trigger a restore failure to exercise rollback path
        import trackora.core.backup_manager as bm_mod
        import os
        original_replace = os.replace
        attempts = [0]
        def fail_on_replace(src, dst):
            if "trackora.db" in dst and attempts[0] == 0:
                attempts[0] += 1
                raise OSError("Simulated failure during replace")
            return original_replace(src, dst)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.os, "replace", fail_on_replace)
            result = bm.restore_backup(created.backup_id)

        assert result.success is False

        # Verify no .restore_* or .rollback_* staging dirs remain
        staging_dirs = [d for d in backup_dir.iterdir()
                        if d.is_dir() and (d.name.startswith(".restore_") or d.name.startswith(".rollback_"))]
        assert staging_dirs == [], f"Staging dirs left behind: {staging_dirs}"

    def test_restore_from_safety_atomic_replace(self, bm, backup_dir):
        """_restore_from_safety must use os.replace (atomic), not write_bytes."""
        created = bm.create_backup()
        assert created.success is True

        # Write directly to _restore_from_safety to check it uses os.replace
        import trackora.core.backup_manager as bm_mod
        import inspect
        source = inspect.getsource(bm_mod.BackupManager._restore_from_safety)
        # Should not contain write_bytes
        assert "write_bytes" not in source, "_restore_from_safety should not use write_bytes"
        assert "os.replace" in source or "replace(" in source, "_restore_from_safety should use os.replace"


class TestSafetyBackupVerification:
    """Safety backup must be verified before rollback."""

    def test_restore_verifies_safety_before_rollback(self, bm, db_path, backup_dir):
        """Exception handler must verify safety backup before attempting rollback."""
        # Create backup
        created = bm.create_backup()
        assert created.success is True
        original_db_data = db_path.read_bytes()

        # Track whether verify was called on the safety backup
        verified_backups = []

        import trackora.core.backup_manager as bm_mod
        original_verify = bm_mod.BackupManager.verify_backup

        def tracking_verify(self, backup_id):
            verified_backups.append(backup_id)
            return original_verify(self, backup_id)

        import os
        original_replace = os.replace
        attempts = [0]

        def fail_on_replace(src, dst):
            if "trackora.db" in dst and attempts[0] == 0:
                attempts[0] += 1
                raise OSError("Simulated replace failure")
            return original_replace(src, dst)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "verify_backup", tracking_verify)
            mp.setattr(bm_mod.os, "replace", fail_on_replace)
            result = bm.restore_backup(created.backup_id)

        assert result.success is False
        # verify_backup should have been called on the safety backup
        safety_id = result.safety_backup_id
        assert safety_id is not None
        assert safety_id in verified_backups, f"Safety backup {safety_id} was not verified before rollback"

    def test_restore_corrupt_safety_graceful_error(self, bm, db_path, backup_dir):
        """If safety backup is corrupt, return graceful error without attempting rollback."""
        import sqlite3
        import os as _os

        created = bm.create_backup()
        assert created.success is True
        original_db_data = db_path.read_bytes()

        import trackora.core.backup_manager as bm_mod
        original_replace = _os.replace
        attempts = [0]

        def fail_on_replace(src, dst):
            if "trackora.db" in dst and attempts[0] == 0:
                attempts[0] += 1
                raise OSError("Simulated replace failure")
            return original_replace(src, dst)

        # After the safety backup is created, corrupt it
        safety_created = [False]

        original_create = bm_mod.BackupManager.create_backup

        def create_and_corrupt(self, backup_type="manual"):
            result = original_create(self, backup_type)
            if result.success:
                safety_created[0] = result.backup_id
                # Corrupt the safety backup ZIP
                if result.backup_path is not None:
                    result.backup_path.write_bytes(b"CORRUPTED_SAFETY")
            return result

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bm_mod.BackupManager, "create_backup", create_and_corrupt)
            mp.setattr(bm_mod.os, "replace", fail_on_replace)
            result = bm.restore_backup(created.backup_id)

        assert result.success is False
        assert result.safety_backup_id is not None
        # The error message should mention the safety backup is available for manual restore
        assert result.error is not None
        assert "safety" in result.error.lower() or "manual" in result.error.lower()


# ── 5: list_backups() + get_latest_backup() ────────────────────


class TestListBackups:
    def test_list_empty_dir(self, bm) -> None:
        backups = bm.list_backups()
        assert backups == []

    def test_list_mixed_files(self, bm, backup_dir: Path) -> None:
        # Create a backup and some non-backup files
        bm.create_backup()
        (backup_dir / "not_a_backup.zip").write_text("not a backup", encoding="utf-8")
        (backup_dir / "readme.txt").write_text("hello", encoding="utf-8")

        backups = bm.list_backups()
        assert len(backups) == 1
        for b in backups:
            assert isinstance(b.backup_id, str)
            assert b.backup_id.startswith("backup_")

    def test_list_sorted_by_date(self, bm) -> None:
        # Create 3 backups with known order
        r1 = bm.create_backup()
        import time
        time.sleep(0.01)
        r2 = bm.create_backup()
        time.sleep(0.01)
        r3 = bm.create_backup()

        backups = bm.list_backups(sort_by="created_at")
        assert len(backups) == 3
        # Newest first
        assert backups[0].backup_id == r3.backup_id
        assert backups[1].backup_id == r2.backup_id
        assert backups[2].backup_id == r1.backup_id

    def test_list_sorted_by_name(self, bm) -> None:
        r1 = bm.create_backup()
        r2 = bm.create_backup()
        r3 = bm.create_backup()

        backups = bm.list_backups(sort_by="name")
        assert len(backups) == 3
        ids = [b.backup_id for b in backups]
        assert ids == sorted(ids)

    def test_list_limit(self, bm) -> None:
        bm.create_backup()
        bm.create_backup()
        bm.create_backup()

        backups = bm.list_backups(limit=2)
        assert len(backups) == 2

    def test_list_limit_none(self, bm) -> None:
        bm.create_backup()
        bm.create_backup()
        bm.create_backup()

        backups = bm.list_backups(limit=None)
        assert len(backups) == 3

    def test_list_filters_backup_id(self, bm) -> None:
        result = bm.create_backup()
        backups = bm.list_backups()
        assert len(backups) == 1
        assert backups[0].backup_id == result.backup_id

    def test_list_creates_backup_info(self, bm) -> None:
        from trackora.core.backup_manager import BackupInfo
        result = bm.create_backup()
        backups = bm.list_backups()
        assert len(backups) == 1
        b = backups[0]
        assert isinstance(b, BackupInfo)
        assert isinstance(b.backup_path, Path)
        assert b.backup_path.is_file()
        assert isinstance(b.size_bytes, int)
        assert b.size_bytes > 0
        assert isinstance(b.created_at, datetime)
        assert isinstance(b.schema_version, str)
        assert isinstance(b.trackora_version, str)
        assert isinstance(b.backup_type, str)
        assert isinstance(b.file_count, int)
        assert b.file_count == 4


class TestGetLatestBackup:
    def test_get_latest_empty(self, bm) -> None:
        result = bm.get_latest_backup()
        assert result is None

    def test_get_latest_single(self, bm) -> None:
        created = bm.create_backup()
        latest = bm.get_latest_backup()
        assert latest is not None
        assert latest.backup_id == created.backup_id

    def test_get_latest_multiple(self, bm) -> None:
        bm.create_backup()
        import time
        time.sleep(0.01)
        r2 = bm.create_backup()
        time.sleep(0.01)
        r3 = bm.create_backup()

        latest = bm.get_latest_backup()
        assert latest is not None
        assert latest.backup_id == r3.backup_id

    def test_get_latest_ignores_other_files(self, bm, backup_dir: Path) -> None:
        """Non-backup .zip files should not be considered."""
        (backup_dir / "random.zip").write_text("not a backup", encoding="utf-8")
        latest = bm.get_latest_backup()
        assert latest is None

        # After creating a real backup, it should be found
        created = bm.create_backup()
        latest = bm.get_latest_backup()
        assert latest is not None
        assert latest.backup_id == created.backup_id


# ── 6: delete_backup() + clean_old_backups() ──────────────────


class TestDeleteBackup:
    def test_delete_existing(self, bm) -> None:
        created = bm.create_backup()
        assert created.backup_path is not None
        assert created.backup_path.is_file()

        deleted = bm.delete_backup(created.backup_id)
        assert deleted is True
        assert not created.backup_path.exists()

    def test_delete_missing(self, bm) -> None:
        deleted = bm.delete_backup("nonexistent_backup_id")
        assert deleted is False

    def test_delete_only_target_file(self, bm) -> None:
        r1 = bm.create_backup()
        r2 = bm.create_backup()

        assert bm.delete_backup(r1.backup_id) is True
        assert not r1.backup_path.exists()
        assert r2.backup_path is not None
        assert r2.backup_path.exists()

    def test_delete_twice(self, bm) -> None:
        created = bm.create_backup()
        assert bm.delete_backup(created.backup_id) is True
        assert bm.delete_backup(created.backup_id) is False


class TestCleanOldBackups:
    def test_clean_keeps_last_5(self, bm) -> None:
        ids = []
        for _ in range(7):
            r = bm.create_backup()
            ids.append(r.backup_id)

        deleted_count = bm.clean_old_backups(keep_last=5)
        assert deleted_count == 2

        remaining = bm.list_backups()
        assert len(remaining) == 5
        # The newest 5 should remain
        remaining_ids = {b.backup_id for b in remaining}
        assert remaining_ids == set(ids[-5:])

    def test_clean_custom_keep(self, bm) -> None:
        ids = []
        for _ in range(10):
            r = bm.create_backup()
            ids.append(r.backup_id)

        deleted_count = bm.clean_old_backups(keep_last=3)
        assert deleted_count == 7

        remaining = bm.list_backups()
        assert len(remaining) == 3
        remaining_ids = {b.backup_id for b in remaining}
        assert remaining_ids == set(ids[-3:])

    def test_clean_preserves_pre_restore(self, bm) -> None:
        # Create manual backups
        ids = []
        for _ in range(4):
            r = bm.create_backup()
            ids.append(r.backup_id)
        # Create a pre_restore backup
        pre = bm.create_backup(backup_type="pre_restore")

        deleted = bm.clean_old_backups(keep_last=2)
        # Should delete 2 of the manual ones, keep pre_restore
        assert deleted == 2

        remaining = bm.list_backups()
        remaining_ids = {b.backup_id for b in remaining}
        assert pre.backup_id in remaining_ids

    def test_clean_empty_dir(self, bm) -> None:
        count = bm.clean_old_backups()
        assert count == 0

    def test_clean_fewer_than_keep(self, bm) -> None:
        for _ in range(3):
            bm.create_backup()
        count = bm.clean_old_backups(keep_last=5)
        assert count == 0

        remaining = bm.list_backups()
        assert len(remaining) == 3

    def test_clean_returns_count(self, bm) -> None:
        for _ in range(6):
            bm.create_backup()
        count = bm.clean_old_backups(keep_last=2)
        assert count == 4
        assert isinstance(count, int)
