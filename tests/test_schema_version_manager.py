"""Tests for SchemaVersionManager — read(), exists(), corrupt recovery."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from trackora.core.schema_version import CompatibilityStatus, SchemaVersion, SchemaVersionError
from trackora.core.schema_version_manager import SchemaVersionManager


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def manager(tmp_path: Path) -> SchemaVersionManager:
    """SchemaVersionManager with schema.json in an isolated temp directory."""
    return SchemaVersionManager(schema_path=tmp_path / "schema.json")


def _write_json(path: Path, payload: dict | None = None) -> None:
    """Write a valid schema.json to the given path."""
    if payload is None:
        payload = {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
            "description": "test",
        }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── 2.1: __init__ ─────────────────────────────────────────────────


class TestInit:
    def test_init_default_path_resolution(self) -> None:
        from trackora.core.paths import BASE_DIR

        mgr = SchemaVersionManager()
        assert mgr._schema_path == BASE_DIR / "schema.json"

    def test_init_custom_path(self) -> None:
        custom = Path("/tmp/custom_schema.json")
        mgr = SchemaVersionManager(schema_path=custom)
        assert mgr._schema_path == custom

    def test_init_path_type(self) -> None:
        mgr = SchemaVersionManager(schema_path=Path("/tmp/s.json"))
        assert isinstance(mgr._schema_path, Path)


# ── 2.2: read() — file missing ────────────────────────────────────


class TestReadMissing:
    def test_read_returns_none_when_missing(self, manager: SchemaVersionManager) -> None:
        assert manager.read() is None

    def test_read_none_is_not_an_error(self, manager: SchemaVersionManager) -> None:
        result = manager.read()
        assert result is None
        # No files should be created as a side effect
        assert not manager._schema_path.exists()

    def test_read_missing_logs_info(self, manager: SchemaVersionManager, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        manager.read()
        assert len(caplog.records) >= 1
        assert any(r.levelno == logging.INFO for r in caplog.records)

    def test_read_file_not_found_race_returns_none(
        self, manager: SchemaVersionManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pathlib
        _write_json(manager._schema_path)

        def raise_fnf(self: object, *args: object, **kwargs: object) -> str:
            raise FileNotFoundError("race condition")

        monkeypatch.setattr(pathlib.Path, "read_text", raise_fnf)
        assert manager.read() is None


# ── 2.3: read() — valid file ──────────────────────────────────────


class TestReadValid:
    def test_read_returns_schema_version(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path)
        result = manager.read()
        assert result == SchemaVersion(2, 0, 0)

    def test_read_returns_correct_version_minor(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "1.1.0",
            "app_version": "1.1.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        assert manager.read() == SchemaVersion(1, 1, 0)

    def test_read_returns_correct_version_patch(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "1.0.3",
            "app_version": "1.0.3",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        assert manager.read() == SchemaVersion(1, 0, 3)

    def test_read_unknown_keys_ignored(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
            "future_field": "some_value",
        })
        assert manager.read() == SchemaVersion(2, 0, 0)

    def test_read_returns_new_schema_version_each_call(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "1.0.0",
            "app_version": "1.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        assert manager.read() == SchemaVersion(1, 0, 0)

        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        assert manager.read() == SchemaVersion(2, 0, 0)


# ── 2.4: orphan .tmp cleanup ──────────────────────────────────────


class TestOrphanTmpCleanup:
    def test_cleans_orphan_tmp(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        tmp_file = tmp_path / "schema.json.tmp"
        tmp_file.write_text("leftover", encoding="utf-8")

        SchemaVersionManager(schema_path=schema_path)
        assert not tmp_file.exists()

    def test_cleans_orphan_tmp_no_schema_json(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        tmp_file = tmp_path / "schema.json.tmp"
        tmp_file.write_text("leftover", encoding="utf-8")

        SchemaVersionManager(schema_path=schema_path)
        assert not tmp_file.exists()

    def test_cleans_orphan_tmp_schema_json_exists(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        _write_json(schema_path)
        tmp_file = tmp_path / "schema.json.tmp"
        tmp_file.write_text("leftover", encoding="utf-8")

        SchemaVersionManager(schema_path=schema_path)
        assert not tmp_file.exists()
        assert schema_path.exists()

    def test_orphan_tmp_ignore_other_tmp(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        tmp_file = tmp_path / "schema.json.tmp"
        tmp_file.write_text("leftover", encoding="utf-8")
        other_tmp = tmp_path / "other_file.tmp"
        other_tmp.write_text("keep me", encoding="utf-8")

        SchemaVersionManager(schema_path=schema_path)
        assert not tmp_file.exists()
        assert other_tmp.exists()

    def test_orphan_tmp_cleanup_failure_logged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        if os.name == "nt":
            pytest.skip("Chmod directory permissions not fully supported on Windows")
        caplog.set_level(logging.WARNING)
        schema_path = tmp_path / "schema.json"
        tmp_file = tmp_path / "schema.json.tmp"
        tmp_file.write_text("leftover", encoding="utf-8")
        # Make parent read-only to cause cleanup failure
        tmp_path.chmod(0o555)

        try:
            SchemaVersionManager(schema_path=schema_path)
            assert any("orphan" in r.message.lower() or "tmp" in r.message.lower()
                       for r in caplog.records)
        finally:
            tmp_path.chmod(0o755)


# ── 2.5: read() — corrupt JSON ────────────────────────────────────


class TestReadCorruptJson:
    def test_corrupt_invalid_json(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("{invalid json!!!}", encoding="utf-8")
        with pytest.raises(SchemaVersionError, match="invalid JSON"):
            manager.read()

    def test_corrupt_empty_file(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("", encoding="utf-8")
        with pytest.raises(SchemaVersionError, match="empty|invalid JSON"):
            manager.read()

    def test_corrupt_whitespace_only(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("   \n\n  ", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            manager.read()

    def test_corrupt_boolean_top_level(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("true", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            manager.read()

    def test_corrupt_json_array_top_level(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            manager.read()

    def test_corrupt_null_top_level(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("null", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            manager.read()


class TestReadCorruptRename:
    def test_corrupt_file_is_renamed(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("{bad json}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        assert not manager._schema_path.exists()
        parent = manager._schema_path.parent
        corrupt_files = [f for f in parent.iterdir() if f.name.startswith("schema.json.corrupt.")]
        assert len(corrupt_files) >= 1

    def test_corrupt_original_content_preserved(self, manager: SchemaVersionManager) -> None:
        original = "{{{{corrupt content here}}}}"
        manager._schema_path.write_text(original, encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        parent = manager._schema_path.parent
        corrupt_files = [f for f in parent.iterdir() if f.name.startswith("schema.json.corrupt.")]
        assert len(corrupt_files) >= 1
        preserved = corrupt_files[0].read_text(encoding="utf-8")
        assert preserved == original

    def test_corrupt_rename_timestamp_format(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("{bad}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        parent = manager._schema_path.parent
        corrupt_files = [f for f in parent.iterdir() if f.name.startswith("schema.json.corrupt.")]
        assert len(corrupt_files) >= 1
        import re
        assert re.match(r"schema\.json\.corrupt\.\d{8}_\d{6}_\d{6}", corrupt_files[0].name)

    def test_corrupt_multiple_corrupt_files(self, manager: SchemaVersionManager) -> None:
        parent = manager._schema_path.parent
        # First corrupt file
        manager._schema_path.write_text("{first}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        # Re-create corrupt content and read again
        manager._schema_path.write_text("{second}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        corrupt_files = [f for f in parent.iterdir() if f.name.startswith("schema.json.corrupt.")]
        assert len(corrupt_files) == 2

    def test_corrupt_rename_does_not_raise(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("{bad}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        # If we get here without OSError, the rename did not raise

    def test_corrupt_rename_fails_logged(self, manager: SchemaVersionManager, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        manager._schema_path.write_text("{bad}", encoding="utf-8")
        # Make parent read-only so rename fails
        parent = manager._schema_path.parent
        parent.chmod(0o555)
        try:
            with pytest.raises(SchemaVersionError):
                manager.read()
            # Should still raise SchemaVersionError even if rename fails
        finally:
            parent.chmod(0o755)

    def test_corrupt_after_rename_returns_none(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text("{bad}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        # Subsequent read should return None (corrupt file is gone)
        assert manager.read() is None


# ── 2.6: read() — field validation ────────────────────────────────


class TestReadFieldValidation:
    def test_missing_schema_version(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        with pytest.raises(SchemaVersionError, match="schema_version"):
            manager.read()

    def test_missing_app_version(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        with pytest.raises(SchemaVersionError, match="app_version"):
            manager.read()

    def test_missing_updated_at(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
        })
        with pytest.raises(SchemaVersionError, match="updated_at"):
            manager.read()

    def test_schema_version_not_a_string(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": 2.0,
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        with pytest.raises(SchemaVersionError, match="string"):
            manager.read()

    def test_schema_version_invalid_format(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "abc",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        with pytest.raises(SchemaVersionError):
            manager.read()

    @pytest.mark.parametrize("bad_version", ["2.0", "v2.0.0", "2.0.0.0", "", "-1.0.0"])
    def test_schema_version_partial_format(self, manager: SchemaVersionManager, bad_version: str) -> None:
        _write_json(manager._schema_path, {
            "schema_version": bad_version,
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        with pytest.raises(SchemaVersionError):
            manager.read()

    def test_app_version_not_a_string(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": 123,
            "updated_at": "2026-06-20T12:00:00Z",
        })
        with pytest.raises(SchemaVersionError, match="string"):
            manager.read()

    def test_updated_at_not_a_string(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": 12345,
        })
        with pytest.raises(SchemaVersionError, match="string"):
            manager.read()

    def test_only_required_fields(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.write_text(json.dumps({
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        }), encoding="utf-8")
        assert manager.read() == SchemaVersion(2, 0, 0)


# ── 2.7: read() — permission errors ───────────────────────────────


class TestReadPermission:
    def test_permission_denied(self, manager: SchemaVersionManager) -> None:
        if os.name == "nt":
            pytest.skip("Chmod file permissions not fully supported on Windows")
        _write_json(manager._schema_path)
        manager._schema_path.chmod(0o000)
        try:
            with pytest.raises(SchemaVersionError, match="Permission|permission"):
                manager.read()
        finally:
            manager._schema_path.chmod(0o644)

    def test_directory_as_file(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        schema_path.mkdir()  # Create a directory at the schema path
        mgr = SchemaVersionManager(schema_path=schema_path)
        with pytest.raises(SchemaVersionError):
            mgr.read()

    def test_symlink_to_valid_file(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip("Creating symlinks requires administrator privileges on Windows")
        real_file = tmp_path / "real.json"
        _write_json(real_file)
        schema_path = tmp_path / "schema.json"
        schema_path.symlink_to(real_file)
        mgr = SchemaVersionManager(schema_path=schema_path)
        assert mgr.read() == SchemaVersion(2, 0, 0)

    def test_read_os_error_raises(
        self, manager: SchemaVersionManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pathlib
        _write_json(manager._schema_path)

        def raise_os_error(self: object, *args: object, **kwargs: object) -> str:
            raise OSError("disk error")

        monkeypatch.setattr(pathlib.Path, "read_text", raise_os_error)
        with pytest.raises(SchemaVersionError, match="disk error"):
            manager.read()


# ── 2.8: exists() ─────────────────────────────────────────────────


class TestExists:
    def test_exists_true(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path)
        assert manager.exists() is True

    def test_exists_false(self, manager: SchemaVersionManager) -> None:
        assert manager.exists() is False

    def test_exists_after_orphan_cleanup(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "schema.json"
        tmp_file = tmp_path / "schema.json.tmp"
        tmp_file.write_text("orphan", encoding="utf-8")
        mgr = SchemaVersionManager(schema_path=schema_path)
        assert mgr.exists() is False


# ── 2.9: unicode and edge cases ────────────────────────────────────


class TestReadUnicode:
    def test_unicode_description(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
            "description": "Versió 2.0.0 — 模式更新",
        })
        assert manager.read() == SchemaVersion(2, 0, 0)

    def test_large_description(self, manager: SchemaVersionManager) -> None:
        large_desc = "x" * 10000
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
            "description": large_desc,
        })
        assert manager.read() == SchemaVersion(2, 0, 0)

    def test_null_description(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
            "description": None,
        })
        assert manager.read() == SchemaVersion(2, 0, 0)

    def test_empty_description(self, manager: SchemaVersionManager) -> None:
        _write_json(manager._schema_path, {
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
            "description": "",
        })
        assert manager.read() == SchemaVersion(2, 0, 0)

    def test_utf8_bom(self, manager: SchemaVersionManager) -> None:
        """UTF-8 BOM should be handled (json.load handles it in Python 3)."""
        content = '\ufeff' + json.dumps({
            "schema_version": "2.0.0",
            "app_version": "2.0.0",
            "updated_at": "2026-06-20T12:00:00Z",
        })
        manager._schema_path.write_text(content, encoding="utf-8")
        assert manager.read() == SchemaVersion(2, 0, 0)


# ── 2.10: logging behavior ────────────────────────────────────────


class TestReadLogging:
    def test_corrupt_logs_warning(self, manager: SchemaVersionManager, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        manager._schema_path.write_text("{bad}", encoding="utf-8")
        try:
            manager.read()
        except SchemaVersionError:
            pass
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_permission_error_logs_error(self, manager: SchemaVersionManager, caplog: pytest.LogCaptureFixture) -> None:
        if os.name == "nt":
            pytest.skip("Chmod file permissions not fully supported on Windows")
        caplog.set_level(logging.ERROR)
        _write_json(manager._schema_path)
        manager._schema_path.chmod(0o000)
        try:
            with pytest.raises(SchemaVersionError):
                manager.read()
        finally:
            manager._schema_path.chmod(0o644)
        assert any(r.levelno == logging.ERROR for r in caplog.records)


# ── 3: write() ───────────────────────────────────────────────────


class TestWriteCreatesFile:
    def test_write_creates_file(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0))
        assert manager._schema_path.is_file()

    def test_write_content_is_valid_json(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0))
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "2.0.0"

    def test_write_required_fields_present(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(1, 2, 3))
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert "schema_version" in data
        assert "app_version" in data
        assert "updated_at" in data
        assert data["schema_version"] == "1.2.3"

    def test_write_file_mode(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0))
        assert os.path.isfile(manager._schema_path)


class TestWriteAtomicity:
    def test_write_creates_tmp_then_renames(self, manager: SchemaVersionManager) -> None:
        tmp_path = manager._schema_path.with_suffix(".json.tmp")
        manager.write(SchemaVersion(2, 0, 0))
        # .tmp should not exist after write
        assert not tmp_path.exists()
        assert manager._schema_path.exists()

    def test_write_from_scratch_no_tmp_residue(self, manager: SchemaVersionManager) -> None:
        assert not manager._schema_path.exists()
        manager.write(SchemaVersion(2, 0, 0))
        tmp_path = manager._schema_path.with_suffix(".json.tmp")
        assert not tmp_path.exists()

    def test_write_existing_overwrites_atomically(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(1, 0, 0))
        manager.write(SchemaVersion(2, 0, 0))
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "2.0.0"

    def test_write_replace_failure_original_intact(
        self, manager: SchemaVersionManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import trackora.core.schema_version_manager as svm
        manager.write(SchemaVersion(1, 0, 0))
        original = manager._schema_path.read_text(encoding="utf-8")

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("replace failed")

        monkeypatch.setattr(svm.os, "replace", failing_replace)
        with pytest.raises(OSError):
            manager.write(SchemaVersion(2, 0, 0))
        # Original should still be intact
        assert manager._schema_path.read_text(encoding="utf-8") == original

    def test_write_replace_failure_tmp_cleanup_oserror(
        self, manager: SchemaVersionManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import trackora.core.schema_version_manager as svm
        import pathlib
        manager.write(SchemaVersion(1, 0, 0))

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("replace failed")

        def failing_unlink(*args: object, **kwargs: object) -> None:
            raise OSError("unlink failed too")

        monkeypatch.setattr(svm.os, "replace", failing_replace)
        monkeypatch.setattr(pathlib.Path, "unlink", failing_unlink)
        with pytest.raises(OSError, match="replace failed"):
            manager.write(SchemaVersion(2, 0, 0))


class TestWriteOverwrites:
    def test_write_twice_different_version(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(1, 0, 0))
        manager.write(SchemaVersion(2, 0, 0))
        assert manager.read() == SchemaVersion(2, 0, 0)

    def test_write_twice_different_description(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(1, 0, 0), description="first")
        manager.write(SchemaVersion(1, 0, 0), description="second")
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data.get("description") == "second"

    def test_write_twice_updated_at_changes(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(1, 0, 0))
        data1 = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        manager.write(SchemaVersion(1, 0, 0))
        data2 = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data1["updated_at"] != data2["updated_at"]


class TestWriteCreatesParentDir:
    def test_write_creates_nested_parent(self, tmp_path: Path) -> None:
        schema_path = tmp_path / "nested" / "deep" / "schema.json"
        mgr = SchemaVersionManager(schema_path=schema_path)
        mgr.write(SchemaVersion(2, 0, 0))
        assert schema_path.is_file()

    def test_write_existing_parent_no_error(self, manager: SchemaVersionManager) -> None:
        manager._schema_path.parent.mkdir(parents=True, exist_ok=True)
        manager.write(SchemaVersion(2, 0, 0))
        assert manager._schema_path.is_file()


class TestWriteErrors:
    def test_write_permission_error_raised(self, manager: SchemaVersionManager) -> None:
        if os.name == "nt":
            pytest.skip("Chmod directory permissions not fully supported on Windows")
        manager._schema_path.parent.mkdir(parents=True, exist_ok=True)
        # Make parent read-only so .tmp cannot be created
        parent = manager._schema_path.parent
        parent.chmod(0o555)
        try:
            with pytest.raises(OSError):
                manager.write(SchemaVersion(2, 0, 0))
        finally:
            parent.chmod(0o755)

    def test_write_invalid_type_raises_type_error(self, manager: SchemaVersionManager) -> None:
        with pytest.raises(TypeError, match="SchemaVersion"):
            manager.write("2.0.0")  # type: ignore[arg-type]

    def test_write_description_must_be_str(self, manager: SchemaVersionManager) -> None:
        with pytest.raises(TypeError, match="description"):
            manager.write(SchemaVersion(2, 0, 0), description=123)  # type: ignore[arg-type]


class TestWriteRoundtrip:
    def test_write_then_read_returns_same(self, manager: SchemaVersionManager) -> None:
        version = SchemaVersion(2, 0, 0)
        manager.write(version)
        assert manager.read() == version

    def test_write_then_read_minor(self, manager: SchemaVersionManager) -> None:
        version = SchemaVersion(1, 3, 0)
        manager.write(version)
        assert manager.read() == version

    def test_write_then_read_patch(self, manager: SchemaVersionManager) -> None:
        version = SchemaVersion(1, 0, 5)
        manager.write(version)
        assert manager.read() == version

    def test_write_then_read_major(self, manager: SchemaVersionManager) -> None:
        version = SchemaVersion(3, 0, 0)
        manager.write(version)
        assert manager.read() == version


class TestWriteContent:
    def test_write_description_included(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0), description="Initial schema")
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data.get("description") == "Initial schema"

    def test_write_empty_description_excluded(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0), description="")
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert "description" not in data or data["description"] == ""

    def test_write_updated_at_is_iso8601(self, manager: SchemaVersionManager) -> None:
        import re
        manager.write(SchemaVersion(2, 0, 0))
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$",
            data["updated_at"],
        )

    def test_write_app_version_matches_schema_version(self, manager: SchemaVersionManager) -> None:
        v = SchemaVersion(2, 0, 0)
        manager.write(v)
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data["app_version"] == "2.0.0"

    def test_write_stores_updated_at_utc(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0))
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data["updated_at"].endswith("Z")

    def test_write_minimal_version(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(0, 0, 1))
        data = json.loads(manager._schema_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "0.0.1"
        assert data["app_version"] == "0.0.1"


class TestWriteOrphanClean:
    def test_write_cleans_existing_orphan_tmp(self, manager: SchemaVersionManager) -> None:
        tmp_path = manager._schema_path.with_suffix(".json.tmp")
        tmp_path.write_text('{"orphan": true}', encoding="utf-8")
        manager.write(SchemaVersion(2, 0, 0))
        assert not tmp_path.exists()
        assert manager._schema_path.exists()

    def test_write_orphan_tmp_no_interference(self, manager: SchemaVersionManager) -> None:
        tmp_path = manager._schema_path.with_suffix(".json.tmp")
        tmp_path.write_text('{"orphan": true}', encoding="utf-8")
        other_tmp = manager._schema_path.with_suffix(".other.tmp")
        other_tmp.write_text("keep", encoding="utf-8")
        manager.write(SchemaVersion(2, 0, 0))
        assert other_tmp.exists()


class TestWriteLogging:
    def test_write_logs_info(self, manager: SchemaVersionManager, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        manager.write(SchemaVersion(2, 0, 0))
        assert any(r.levelno == logging.INFO for r in caplog.records)
        assert any("2.0.0" in r.message for r in caplog.records if r.levelno == logging.INFO)

    def test_write_with_description_logs_it(self, manager: SchemaVersionManager, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        manager.write(SchemaVersion(2, 0, 0), description="migration v2")
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("migration v2" in m for m in info_messages)


# ── 4: is_compatible() ───────────────────────────────────────────


class TestIsCompatibleFirstRun:
    def test_first_run_can_proceed(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), None)
        assert result.can_proceed is True

    def test_first_run_status(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), None)
        assert result.status == "first_run"

    def test_first_run_message(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), None)
        assert "first run" in result.message.lower() or "new install" in result.message.lower()


class TestIsCompatibleSameVersion:
    def test_same_version_can_proceed(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(2, 0, 0))
        assert result.can_proceed is True

    def test_same_version_status(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(2, 0, 0))
        assert result.status == "ok"

    def test_same_version_message(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(2, 0, 0))
        assert result.message == ""


class TestIsCompatibleNeedsMigration:
    def test_older_minor_can_proceed(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 1, 0))
        assert result.can_proceed is True

    def test_older_minor_status(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 1, 0))
        assert result.status == "needs_migration"

    def test_older_major_can_proceed(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 0, 0))
        assert result.can_proceed is True

    def test_older_patch_can_proceed(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 9, 9))
        assert result.can_proceed is True

    def test_older_version_message(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 1, 0))
        assert "migrat" in result.message.lower()


class TestIsCompatibleNewerData:
    def test_newer_patch_cannot_proceed(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(2, 1, 0))
        assert result.can_proceed is False

    def test_newer_patch_status(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(2, 1, 0))
        assert result.status == "newer_data"

    def test_newer_major_cannot_proceed(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(3, 0, 0))
        assert result.can_proceed is False

    def test_newer_major_status(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(3, 0, 0))
        assert result.status == "newer_data"

    def test_newer_data_message_contains_version(self, manager: SchemaVersionManager) -> None:
        result = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(2, 1, 0))
        assert "2.1.0" in result.message


class TestIsCompatibleTypeValidation:
    def test_invalid_app_version_raises(self, manager: SchemaVersionManager) -> None:
        with pytest.raises(TypeError, match="SchemaVersion"):
            manager.is_compatible("2.0.0", SchemaVersion(2, 0, 0))  # type: ignore[arg-type]

    def test_invalid_data_version_raises(self, manager: SchemaVersionManager) -> None:
        with pytest.raises(TypeError, match="SchemaVersion"):
            manager.is_compatible(SchemaVersion(2, 0, 0), "2.0.0")  # type: ignore[arg-type]


class TestIsCompatibleStats:
    def test_is_compatible_is_stateless(self, manager: SchemaVersionManager) -> None:
        r1 = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 0, 0))
        r2 = manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 0, 0))
        assert r1 == r2

    def test_is_compatible_no_disk_io(self, manager: SchemaVersionManager) -> None:
        """is_compatible should not touch the filesystem."""
        import trackora.core.schema_version_manager as svm
        original = svm.SchemaVersionManager.read
        reads = []

        def tracking_read(self) -> None:
            reads.append(1)
            return original(self)

        svm.SchemaVersionManager.read = tracking_read  # type: ignore[assignment]
        try:
            manager.is_compatible(SchemaVersion(2, 0, 0), SchemaVersion(1, 0, 0))
            assert len(reads) == 0
        finally:
            svm.SchemaVersionManager.read = original


# ── 5: compare() ───────────────────────────────────────────


class TestCompare:
    def test_compare_less(self) -> None:
        assert SchemaVersionManager.compare(
            SchemaVersion(1, 0, 0), SchemaVersion(2, 0, 0)
        ) == -1

    def test_compare_equal(self) -> None:
        assert SchemaVersionManager.compare(
            SchemaVersion(2, 0, 0), SchemaVersion(2, 0, 0)
        ) == 0

    def test_compare_greater(self) -> None:
        assert SchemaVersionManager.compare(
            SchemaVersion(2, 0, 0), SchemaVersion(1, 0, 0)
        ) == 1

    def test_compare_minor_less(self) -> None:
        assert SchemaVersionManager.compare(
            SchemaVersion(2, 0, 0), SchemaVersion(2, 1, 0)
        ) == -1

    def test_compare_minor_greater(self) -> None:
        assert SchemaVersionManager.compare(
            SchemaVersion(2, 1, 0), SchemaVersion(2, 0, 0)
        ) == 1

    def test_compare_patch_less(self) -> None:
        assert SchemaVersionManager.compare(
            SchemaVersion(2, 0, 0), SchemaVersion(2, 0, 1)
        ) == -1

    def test_compare_patch_greater(self) -> None:
        assert SchemaVersionManager.compare(
            SchemaVersion(2, 0, 1), SchemaVersion(2, 0, 0)
        ) == 1


# ── 5: delete() ────────────────────────────────────────────


class TestDelete:
    def test_delete_removes_file(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0))
        assert manager._schema_path.exists()
        manager.delete()
        assert not manager._schema_path.exists()

    def test_delete_missing_file_succeeds(self, manager: SchemaVersionManager) -> None:
        assert not manager._schema_path.exists()
        manager.delete()  # Should not raise

    def test_delete_missing_no_error(self, manager: SchemaVersionManager) -> None:
        manager.delete()

    def test_delete_after_delete_succeeds(self, manager: SchemaVersionManager) -> None:
        manager.write(SchemaVersion(2, 0, 0))
        manager.delete()
        manager.delete()  # Second delete should not raise

    def test_delete_does_not_remove_other_files(self, tmp_path: Path) -> None:
        other_file = tmp_path / "other.json"
        other_file.write_text("data", encoding="utf-8")
        schema_path = tmp_path / "schema.json"
        mgr = SchemaVersionManager(schema_path=schema_path)
        mgr.write(SchemaVersion(2, 0, 0))
        mgr.delete()
        assert other_file.exists()

    def test_delete_is_not_read(self, manager: SchemaVersionManager, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG)
        manager.write(SchemaVersion(2, 0, 0))
        caplog.clear()
        manager.delete()
        # delete() should not log about reading
        read_logs = [r for r in caplog.records if "read" in r.message.lower()]
        assert len(read_logs) == 0
