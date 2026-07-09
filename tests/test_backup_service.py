"""
test_backup_service.py — unit and integration tests for T-205 Database Backup Manager service layer.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, UTC, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.backup.backup_result import BackupResult, BackupInfo
from services.backup.backup_metadata import BackupMetadata
from services.backup.backup_validator import BackupValidator
from services.backup.backup_manager import BackupManager
from services.backup.backup_service import BackupService
from services.backup.backup_scheduler import BackupScheduler
from trackora.core.schema_version_manager import SchemaVersionManager


@pytest.fixture
def temp_backup_dir(tmp_path: Path) -> Path:
    """Isolated directory for backups."""
    d = tmp_path / "Backups"
    d.mkdir()
    return d


@pytest.fixture
def fake_schema_manager(tmp_path: Path) -> SchemaVersionManager:
    """Fake SchemaVersionManager pointing to a temp file."""
    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"schema_version": "2.0.0", "app_version": "2.0.0"}', encoding="utf-8")
    return SchemaVersionManager(schema_path=schema_file)


@pytest.fixture
def fake_db_path(tmp_path: Path) -> Path:
    """Fake database file path."""
    db_file = tmp_path / "trackora.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY);")
    conn.commit()
    conn.close()
    return db_file


# ------------------------------------------------------------------
# BackupMetadata Tests
# ------------------------------------------------------------------

def test_metadata_generation() -> None:
    meta = BackupMetadata.generate("manual")
    assert "environment" in meta
    assert "platform" in meta
    assert meta["backup_reason"] == "manual"
    assert "application_version" in meta


# ------------------------------------------------------------------
# BackupValidator Tests
# ------------------------------------------------------------------

def test_validator_missing_file() -> None:
    is_valid, err = BackupValidator.validate(Path("non_existent_file.zip"))
    assert is_valid is False
    assert "exist" in err.lower()


def test_validator_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.zip"
    empty_file.write_bytes(b"")
    is_valid, err = BackupValidator.validate(empty_file)
    assert is_valid is False
    assert "size" in err.lower()


# ------------------------------------------------------------------
# BackupManager & BackupService Tests
# ------------------------------------------------------------------

def test_manual_backup_creation_and_validation(
    temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager, fake_db_path: Path
) -> None:
    # Patch the global DATABASE_PATH in paths module
    with patch("trackora.core.paths.DATABASE_PATH", fake_db_path):
        manager = BackupManager(fake_schema_manager, temp_backup_dir)
        service = BackupService(manager)

        res = service.perform_manual_backup()
        assert res.success is True
        assert res.backup_path is not None
        assert res.backup_path.is_file()

        # Validate
        is_valid, err = BackupValidator.validate(res.backup_path)
        assert is_valid is True
        assert err is None

        # Check history
        history = service.get_backup_history()
        assert len(history) == 1
        assert history[0].backup_id == res.backup_id


def test_concurrent_backup_protection(
    temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager, fake_db_path: Path
) -> None:
    with patch("trackora.core.paths.DATABASE_PATH", fake_db_path):
        manager = BackupManager(fake_schema_manager, temp_backup_dir)

        # Acquire lock manually to simulate concurrent backup
        manager._lock.acquire()
        try:
            res = manager.create_backup("manual")
            assert res.success is False
            assert "progress" in res.error
        finally:
            manager._lock.release()


def test_retention_policy_enforcement(
    temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager, fake_db_path: Path
) -> None:
    with patch("trackora.core.paths.DATABASE_PATH", fake_db_path):
        manager = BackupManager(fake_schema_manager, temp_backup_dir)

        # Create 12 scheduled backups
        for i in range(12):
            # Patch time or IDs to ensure they are created with distinct names
            res = manager.create_backup("scheduled")
            assert res.success is True

        # Retention should cap at 10
        backups = manager._core.list_backups()
        scheduled = [b for b in backups if b.backup_type == "scheduled"]
        assert len(scheduled) == 10

        # Create a manual backup
        res_manual = manager.create_backup("manual")
        assert res_manual.success is True

        # Total backups should be 10 scheduled + 1 manual = 11
        backups = manager._core.list_backups()
        assert len(backups) == 11


# ------------------------------------------------------------------
# BackupScheduler Tests
# ------------------------------------------------------------------

def test_scheduler_disabled(temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager) -> None:
    mock_settings = MagicMock()
    mock_settings.get_value.return_value = "disabled"

    manager = MagicMock()
    scheduler = BackupScheduler(manager, mock_settings)
    scheduler.check_and_trigger()

    manager.create_backup.assert_not_called()


def test_scheduler_daily_trigger(temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager) -> None:
    mock_settings = MagicMock()
    mock_settings.get_value.return_value = "daily"

    manager = MagicMock()
    
    # 1. No previous backup exists -> should trigger immediately
    manager._core.list_backups.return_value = []
    scheduler = BackupScheduler(manager, mock_settings)
    scheduler.check_and_trigger()
    manager.create_backup.assert_called_once_with("scheduled")
    manager.create_backup.reset_mock()

    # 2. Previous scheduled backup exists but is < 24h old -> should NOT trigger
    mock_backup = MagicMock()
    mock_backup.backup_type = "scheduled"
    mock_backup.created_at = datetime.now(UTC) - timedelta(hours=12)
    manager._core.list_backups.return_value = [mock_backup]
    scheduler.check_and_trigger()
    manager.create_backup.assert_not_called()

    # 3. Previous scheduled backup exists and is > 24h old -> should trigger
    mock_backup.created_at = datetime.now(UTC) - timedelta(hours=25)
    scheduler.check_and_trigger()
    manager.create_backup.assert_called_once_with("scheduled")
