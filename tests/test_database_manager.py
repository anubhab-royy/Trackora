# 15 tests: schema, WAL, FK, indexes

"""
Tests for DatabaseManager.

Covers:
    - In-memory and file-based initialization
    - WAL journal mode
    - Foreign key enforcement
    - All tables created
    - All indexes created
    - Context manager usage
    - Error on uninitialized access
"""

from __future__ import annotations

import pytest

from database.database_manager import DatabaseManager


class TestDatabaseManagerInitialization:
    def test_initializes_without_error(self, db_manager):
        """DatabaseManager.initialize() should complete without raising."""
        assert db_manager.connection is not None

    def test_connection_available_after_initialize(self, db_manager):
        """connection property returns a live connection after initialize()."""
        conn = db_manager.connection
        # A simple query should work
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        assert cursor.fetchone()[0] == 1

    def test_raises_if_not_initialized(self):
        """Accessing .connection before initialize() raises RuntimeError."""
        manager = DatabaseManager(db_path=":memory:")
        with pytest.raises(RuntimeError, match="initialize"):
            _ = manager.connection

    def test_context_manager_opens_and_closes(self):
        """Using DatabaseManager as a context manager initializes and closes."""
        with DatabaseManager(db_path=":memory:") as db:
            conn = db.connection
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            assert cursor.fetchone()[0] == 1
        # After __exit__, connection should be None
        assert db._connection is None

    def test_close_is_idempotent(self, db_manager):
        """Calling close() twice should not raise."""
        db_manager.close()
        db_manager.close()  # Must not raise


class TestPragmas:
    def test_wal_mode_enabled_on_file_db(self, tmp_path):
        """
        journal_mode must be WAL on a real file database (tech_spec.md).

        Note: SQLite in-memory databases (:memory:) always report 'memory'
        as their journal_mode — WAL requires a real file on disk.
        This test uses a temporary file to verify the PRAGMA is applied
        correctly by DatabaseManager on actual production-style databases.
        """
        db_file = tmp_path / "test_wal.db"
        with DatabaseManager(db_path=db_file) as db:
            cursor = db.connection.cursor()
            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"

    def test_foreign_keys_enabled(self, connection):
        """Foreign key support must be ON."""
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        fk = cursor.fetchone()[0]
        assert fk == 1


class TestSchemaCreation:
    """Verify every table from database_schema.md exists."""

    EXPECTED_TABLES = {
        "games",
        "sessions",
        "active_sessions",
        "settings",
        "statistics_cache",
    }

    def _get_tables(self, connection) -> set[str]:
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return {row[0] for row in cursor.fetchall()}

    def test_all_tables_exist(self, connection):
        tables = self._get_tables(connection)
        for table in self.EXPECTED_TABLES:
            assert table in tables, f"Table '{table}' not found in schema."

    def test_games_table_columns(self, connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(games);")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {
            "id", "name", "process_name", "executable_path", "icon_path",
            "is_enabled", "first_played", "last_played", "created_at", "updated_at",
        }
        assert expected == columns

    def test_sessions_table_columns(self, connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(sessions);")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {
            "id", "game_id", "start_time", "end_time", "duration_seconds", "created_at",
        }
        assert expected == columns

    def test_active_sessions_table_columns(self, connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(active_sessions);")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {"id", "game_id", "process_id", "start_time", "created_at"}
        assert expected == columns

    def test_settings_table_columns(self, connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(settings);")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {"key", "value", "updated_at"}
        assert expected == columns

    def test_statistics_cache_table_columns(self, connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(statistics_cache);")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {"id", "game_id", "period_type", "period_key", "value_seconds"}
        assert expected == columns

    def test_initialize_is_idempotent(self):
        """Calling initialize() twice should not raise (IF NOT EXISTS guards)."""
        with DatabaseManager(db_path=":memory:") as db:
            db.initialize()  # second call
            cursor = db.connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            assert "games" in tables


class TestIndexCreation:
    EXPECTED_INDEXES = {
        "idx_games_process_name",
        "idx_sessions_game_id",
        "idx_sessions_start_time",
        "idx_sessions_end_time",
        "idx_active_sessions_game_id",
    }

    def test_all_indexes_exist(self, connection):
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = {row[0] for row in cursor.fetchall()}
        for idx in self.EXPECTED_INDEXES:
            assert idx in indexes, f"Index '{idx}' not found."