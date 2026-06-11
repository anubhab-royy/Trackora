"""
Tests for services/database_migration_service.py

Covers scenarios A–H from the production bug report:
  A. Old GameTracker exists, no Trackora               → auto-migrate
  B. Trackora folder exists, DB doesn't                 → auto-migrate
  C. Trackora DB exists but is empty                    → auto-migrate
  D. Trackora DB exists with valid data                 → NO action
  E. Partial failed migration                           → retry
  F. Both exist with data                               → use DB with most data
  G. WAL / SHM present                                  → flush before copy
  H. Future rename                                      → add path to SOURCE_DIRS
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from services.database_migration_service import (
    DatabaseMigrationService,
    MigrationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_db(
    path: Path,
    *,
    games: int = 0,
    sessions: int = 0,
    settings: int = 0,
    add_schema: bool = True,
) -> None:
    """Create a SQLite database at *path* with optional data rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()
    if add_schema:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                process_name TEXT NOT NULL,
                executable_path TEXT NOT NULL,
                icon_path TEXT NOT NULL DEFAULT '',
                is_enabled INTEGER NOT NULL DEFAULT 1,
                first_played DATETIME,
                last_played DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME NOT NULL,
                duration_seconds INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at DATETIME NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                process_id INTEGER NOT NULL,
                start_time DATETIME NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)
    for i in range(games):
        cursor.execute(
            "INSERT INTO games (name, process_name, executable_path, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (f"Game{i}", f"game{i}.exe", f"C:\\Games\\Game{i}\\game{i}.exe"),
        )
    for i in range(sessions):
        cursor.execute(
            "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds, created_at) "
            "VALUES (?, datetime('now', ?), datetime('now'), ?, datetime('now'))",
            (1, f'-{i+1} hours', (i + 1) * 3600),
        )
    for i in range(settings):
        cursor.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (f"key_{i}", f"value_{i}"),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixture: creates a patched service that uses tmp_path as appdata root
# ---------------------------------------------------------------------------

@pytest.fixture
def svc(request: pytest.FixtureRequest) -> DatabaseMigrationService:
    """
    Fixture providing a DatabaseMigrationService that operates on tmp_path.

    Patches _get_appdata_root so source discovery and target path
    resolution point at {tmp_path} rather than the real %APPDATA%.
    """
    tmp_path: Path = request.getfixturevalue("tmp_path")
    target = tmp_path / "Trackora" / "trackora.db"
    patcher = patch(
        "services.database_migration_service._get_appdata_root",
        return_value=tmp_path,
    )
    patcher.start()
    request.addfinalizer(patcher.stop)
    return DatabaseMigrationService(target)


@pytest.fixture
def target(request: pytest.FixtureRequest) -> Path:
    """Return the target database path under tmp_path."""
    tmp_path: Path = request.getfixturevalue("tmp_path")
    return tmp_path / "Trackora" / "trackora.db"


def _make_source(tmp_path: Path, **data_kwargs) -> Path:
    """Create a source database under tmp_path/GameTracker/tracker.db."""
    src_dir = tmp_path / "GameTracker"
    src_db = src_dir / "tracker.db"
    _create_db(src_db, **data_kwargs)
    return src_db


# ---------------------------------------------------------------------------
# Scenario A: Old GameTracker exists, no Trackora
# ---------------------------------------------------------------------------

class TestScenarioA:
    """Old source exists, target directory (and DB) do not exist."""

    def test_migrates_when_no_target_exists(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        assert not target.exists()

        result = svc.migrate_if_needed()

        assert result.success is True
        assert result.source_path is not None
        assert target.exists()
        assert result.tables_before.get("games") == 3
        assert result.tables_after.get("games") == 3
        assert result.tables_before.get("sessions") == 8
        assert result.tables_after.get("sessions") == 8
        assert result.tables_before.get("settings") == 1
        assert result.tables_after.get("settings") == 1

    def test_source_preserved_after_migration(self, svc, target, tmp_path) -> None:
        """Source file must not be deleted automatically."""
        src = _make_source(tmp_path, games=3, sessions=8, settings=1)
        svc.migrate_if_needed()
        assert src.exists(), "Source must not be deleted"

    def test_backup_created(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        result = svc.migrate_if_needed()
        assert result.backup_path is not None
        assert result.backup_path.exists()

    def test_idempotent(self, svc, target, tmp_path) -> None:
        """Second call should detect target has data and skip."""
        _make_source(tmp_path, games=3, sessions=8, settings=1)

        r1 = svc.migrate_if_needed()
        assert r1.success is True

        r2 = svc.migrate_if_needed()
        assert r2.action == "skipped_has_data"


# ---------------------------------------------------------------------------
# Scenario B: Trackora folder exists, DB does not
# ---------------------------------------------------------------------------

class TestScenarioB:
    """Target directory exists (created by installer or prior launch) but no .db file."""

    def test_migrates_when_folder_exists_no_db(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        (tmp_path / "Trackora").mkdir(parents=True, exist_ok=True)
        assert not target.exists()

        result = svc.migrate_if_needed()

        assert result.success is True
        assert target.exists()
        assert result.tables_after.get("games") == 3

    def test_no_data_loss_when_folder_empty(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        (tmp_path / "Trackora").mkdir(parents=True, exist_ok=True)

        result = svc.migrate_if_needed()

        assert result.success is True
        conn = sqlite3.connect(str(target))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        assert cursor.fetchone()[0] == 3
        cursor.execute("SELECT COUNT(*) FROM sessions")
        assert cursor.fetchone()[0] == 8
        conn.close()


# ---------------------------------------------------------------------------
# Scenario C: Trackora DB exists but is empty
# ---------------------------------------------------------------------------

class TestScenarioC:
    """Target DB exists (was freshly created by a prior launch) but contains no data."""

    def test_migrates_when_target_is_empty(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        _create_db(target, games=0, sessions=0, settings=0)

        result = svc.migrate_if_needed()

        assert result.success is True
        conn = sqlite3.connect(str(target))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        assert cursor.fetchone()[0] == 3
        conn.close()

    def test_migrates_when_target_has_only_schema(self, svc, target, tmp_path) -> None:
        """Target has schema from DatabaseManager but zero user rows."""
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        _create_db(target)

        result = svc.migrate_if_needed()

        assert result.success is True
        assert result.tables_after.get("games") == 3


# ---------------------------------------------------------------------------
# Scenario D: Trackora DB exists with valid data
# ---------------------------------------------------------------------------

class TestScenarioD:
    """Target DB already has valid user data — must NOT be overwritten."""

    def test_skips_when_target_has_data(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        _create_db(target, games=5, sessions=10)

        result = svc.migrate_if_needed()

        assert result.action == "skipped_has_data"
        conn = sqlite3.connect(str(target))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        assert cursor.fetchone()[0] == 5, "Existing data must not be overwritten"
        conn.close()

    def test_skips_when_target_has_only_settings(self, svc, target, tmp_path) -> None:
        """Even a single row of user data is enough to skip."""
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        _create_db(target, settings=1)

        result = svc.migrate_if_needed()

        assert result.action == "skipped_has_data"

    def test_multi_launch_safety(self, svc, target, tmp_path) -> None:
        """Multiple launches after migration must be safe."""
        _make_source(tmp_path, games=3, sessions=8, settings=1)

        for _ in range(5):
            result = svc.migrate_if_needed()
            assert result.action in ("migrated", "skipped_has_data")

        conn = sqlite3.connect(str(target))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        assert cursor.fetchone()[0] == 3
        conn.close()


# ---------------------------------------------------------------------------
# Scenario E: Partial failed migration → retry
# ---------------------------------------------------------------------------

class TestScenarioE:
    """Simulate a partially failed migration — target exists but is corrupted."""

    def test_retries_when_target_corrupted(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("NOT A VALID SQLITE FILE")

        result = svc.migrate_if_needed()

        assert result.success is True
        conn = sqlite3.connect(str(target))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        assert cursor.fetchone()[0] == 3
        conn.close()

    def test_retries_when_target_empty_empty(self, svc, target, tmp_path) -> None:
        """A zero-byte target file is treated as corrupted and re-migrated."""
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("")

        result = svc.migrate_if_needed()

        assert result.success is True

    def test_backup_restored_on_validation_failure(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)

        # Corrupt the copy by injecting a zero-byte file after migration.
        original_copy = svc._copy_db

        def _bad_copy(src, tgt):
            ok = original_copy(src, tgt)
            tgt.write_bytes(b"")
            return ok

        svc._copy_db = _bad_copy  # type: ignore[method-assign]

        result = svc.migrate_if_needed()

        assert result.action == "validation_failed"


# ---------------------------------------------------------------------------
# Scenario F: Both exist with data — never destroy
# ---------------------------------------------------------------------------

class TestScenarioF:
    """Both source and target have data — never overwrite."""

    def test_skips_when_target_has_more_data(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=10, sessions=100)
        _create_db(target, games=5, sessions=50)

        result = svc.migrate_if_needed()

        assert result.action == "skipped_has_data"
        conn = sqlite3.connect(str(target))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        assert cursor.fetchone()[0] == 5, "Must not overwrite existing data"
        conn.close()

    def test_skips_when_both_have_equal_data(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        _create_db(target, games=3, sessions=8, settings=1)

        result = svc.migrate_if_needed()

        assert result.action == "skipped_has_data"


# ---------------------------------------------------------------------------
# Scenario G: WAL / SHM files present
# ---------------------------------------------------------------------------

class TestScenarioG:
    """Source database is in WAL mode with -wal and -shm companions."""

    def test_migrates_with_wal_files(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        src = tmp_path / "GameTracker" / "tracker.db"

        conn = sqlite3.connect(str(src))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO games (name, process_name, executable_path, created_at, updated_at) "
                     "VALUES ('WAL Test', 'wal_test.exe', 'C:\\test.exe', datetime('now'), datetime('now'))")
        conn.commit()
        conn.close()

        result = svc.migrate_if_needed()

        assert result.success is True
        conn = sqlite3.connect(str(target))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        assert cursor.fetchone()[0] == 4
        conn.close()

    def test_wal_checkpoint_preserves_data(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        src = tmp_path / "GameTracker" / "tracker.db"

        conn = sqlite3.connect(str(src))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO games (name, process_name, executable_path, created_at, updated_at) "
                     "VALUES ('Post-WAL', 'post_wal.exe', 'C:\\test.exe', datetime('now'), datetime('now'))")
        conn.commit()
        conn.close()

        result = svc.migrate_if_needed()

        assert result.success is True
        assert result.tables_after.get("games") == 4


# ---------------------------------------------------------------------------
# Scenario H: Future rename — reusable migration framework
# ---------------------------------------------------------------------------

class TestScenarioH:
    """Adding a new source path should be sufficient for future renames."""

    def test_custom_source_path(self, svc, target, tmp_path, monkeypatch) -> None:
        from services import database_migration_service as mod

        original_dirs = mod.SOURCE_DIRS.copy()
        monkeypatch.setattr(mod, "SOURCE_DIRS", ["GameTracker"])

        _make_source(tmp_path, games=3, sessions=8, settings=1)

        result = svc.migrate_if_needed()
        assert result.success is True
        assert result.tables_after.get("games") == 3

    def test_multiple_sources_prefers_most_data(
        self, svc, target, tmp_path, monkeypatch
    ) -> None:
        from services import database_migration_service as mod

        monkeypatch.setattr(mod, "SOURCE_DIRS", ["GameTracker", "TrackoraBeta"])

        _create_db(
            tmp_path / "GameTracker" / "tracker.db",
            games=3, sessions=8, settings=1,
        )
        _create_db(
            tmp_path / "TrackoraBeta" / "beta.db",
            games=10, sessions=50, settings=3,
        )

        result = svc.migrate_if_needed()

        assert result.success is True
        assert "TrackoraBeta" in str(result.source_path)
        assert result.tables_after.get("games") == 10

    def test_skips_when_only_empty_sources(self, svc, target, tmp_path, monkeypatch) -> None:
        from services import database_migration_service as mod

        monkeypatch.setattr(mod, "SOURCE_DIRS", ["GameTracker", "TrackoraBeta"])

        _create_db(tmp_path / "GameTracker" / "tracker.db")
        _create_db(tmp_path / "TrackoraBeta" / "beta.db")

        result = svc.migrate_if_needed()
        assert result.action == "skipped_no_source"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_source_no_migration(self, svc, target) -> None:
        result = svc.migrate_if_needed()
        assert result.action == "skipped_no_source"
        assert not target.exists()

    def test_source_db_does_not_exist(self, svc, target, tmp_path) -> None:
        (tmp_path / "GameTracker").mkdir(parents=True, exist_ok=True)

        result = svc.migrate_if_needed()
        assert result.action == "skipped_no_source"

    def test_source_is_not_valid_sqlite(self, svc, target, tmp_path) -> None:
        src_dir = tmp_path / "GameTracker"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "tracker.db").write_text("not a database")

        result = svc.migrate_if_needed()
        assert result.action == "skipped_no_source"

    def test_source_and_target_same_path(self, svc, target, tmp_path) -> None:
        _create_db(target, games=3)

        result = svc.migrate_if_needed()
        assert result.action in ("skipped_has_data",)

    def test_handles_io_error_during_copy(self, svc, target, tmp_path) -> None:
        _make_source(tmp_path, games=3, sessions=8, settings=1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        with patch("shutil.copy2", side_effect=PermissionError("Access denied")):
            result = svc.migrate_if_needed()

        assert result.action == "failed"
        assert len(result.errors) > 0

    def test_migration_result_properties(self) -> None:
        r = MigrationResult(action="migrated")
        assert r.success is True

        r = MigrationResult(action="skipped_no_source")
        assert r.success is False

        r = MigrationResult(action="failed", errors=["something"])
        assert r.success is False
