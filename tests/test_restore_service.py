"""
test_restore_service.py — unit and integration tests for T-206 Database Restore Manager service layer.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.backup.backup_manager import BackupManager
from services.backup.restore_result import RestoreResult
from services.backup.restore_manager import RestoreManager
from services.backup.restore_service import RestoreService
from trackora.core.schema_version import SchemaVersion, SchemaVersionError
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
    schema_file.write_text(
        '{"schema_version": "2.0.0", "app_version": "2.0.0", "updated_at": "2026-07-07T11:00:00Z"}',
        encoding="utf-8"
    )
    return SchemaVersionManager(schema_path=schema_file)


@pytest.fixture
def fake_db_path(tmp_path: Path) -> Path:
    """Fake database file path."""
    db_file = tmp_path / "trackora.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT);")
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def fake_repo(fake_db_path: Path) -> MagicMock:
    """Fake repository wrapper holding a sqlite connection."""
    conn = sqlite3.connect(str(fake_db_path))
    repo = MagicMock()
    repo._conn = conn
    
    # Mock games query representation
    repo.get_all_games.return_value = []
    return repo


# ------------------------------------------------------------------
# Restore Tests
# ------------------------------------------------------------------

def test_restore_successful_workflow(
    temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager, fake_db_path: Path, fake_repo: MagicMock
) -> None:
    with patch("trackora.core.paths.DATABASE_PATH", fake_db_path):
        backup_manager = BackupManager(fake_schema_manager, temp_backup_dir)
        
        # 1. Create a valid backup to restore from
        res_backup = backup_manager.create_backup("manual")
        assert res_backup.success is True

        # Mock collaborators
        mock_monitor = MagicMock()
        mock_monitor.is_running = True
        mock_health = MagicMock()
        mock_scheduler = MagicMock()
        mock_window = MagicMock()

        restore_manager = RestoreManager(
            backup_manager=backup_manager,
            db_path=fake_db_path,
            repositories=[fake_repo],
            schema_version_manager=fake_schema_manager,
            process_monitor=mock_monitor,
            health_monitor=mock_health,
            backup_scheduler=mock_scheduler,
            main_window=mock_window,
        )
        service = RestoreService(restore_manager)

        # 2. Run restore
        res_restore = service.restore_backup(res_backup.backup_id)
        
        assert res_restore.success is True
        assert res_restore.safety_backup_id is not None

        # Verify services were stopped and restarted
        mock_monitor.stop.assert_called_once()
        mock_monitor.start.assert_called_once()
        mock_health.stop.assert_called_once()
        mock_health.start.assert_called_once_with(30000)
        mock_scheduler.stop.assert_called_once()
        mock_scheduler.start.assert_called_once_with(60000)

        # Check repository reinitialization
        assert fake_repo._conn is not None


def test_restore_aborted_on_incompatible_schema(
    temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager, fake_db_path: Path, fake_repo: MagicMock
) -> None:
    with patch("trackora.core.paths.DATABASE_PATH", fake_db_path):
        backup_manager = BackupManager(fake_schema_manager, temp_backup_dir)
        res_backup = backup_manager.create_backup("manual")
        assert res_backup.success is True

        # Mock schema manager to return an older supported version
        mock_schema_manager = MagicMock()
        mock_schema_manager.read.return_value = SchemaVersion(1, 0, 0) # Current capability is 1.0.0

        restore_manager = RestoreManager(
            backup_manager=backup_manager,
            db_path=fake_db_path,
            repositories=[fake_repo],
            schema_version_manager=mock_schema_manager,
        )
        
        # Manifest has 2.0.0, current is 1.0.0 -> Incompatible (newer backup schema than app can parse)
        res_restore = restore_manager.restore(res_backup.backup_id)
        assert res_restore.success is False
        assert "Incompatible" in res_restore.error


def test_restore_automatic_rollback_on_integrity_check_failure(
    temp_backup_dir: Path, fake_schema_manager: SchemaVersionManager, fake_db_path: Path, fake_repo: MagicMock
) -> None:
    with patch("trackora.core.paths.DATABASE_PATH", fake_db_path):
        backup_manager = BackupManager(fake_schema_manager, temp_backup_dir)
        res_backup = backup_manager.create_backup("manual")
        assert res_backup.success is True

        # Mock sqlite3.connect to return a mock connection whose integrity check returns corrupt
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("database is corrupt",)
        mock_conn.cursor.return_value = mock_cursor

        # Store calls
        mock_monitor = MagicMock()

        restore_manager = RestoreManager(
            backup_manager=backup_manager,
            db_path=fake_db_path,
            repositories=[fake_repo],
            schema_version_manager=fake_schema_manager,
            process_monitor=mock_monitor,
        )

        with patch("sqlite3.connect", return_value=mock_conn):
            res_restore = restore_manager.restore(res_backup.backup_id)
            assert res_restore.success is False
            assert "integrity" in res_restore.error or "corrupt" in res_restore.error

        # Ensure process monitor resumed state
        mock_monitor.start.assert_not_called()  # was not active at start in this test case
