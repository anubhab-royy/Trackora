"""Tests for DatabaseManager — connection, PRAGMAs, schema creation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from database.database_manager import DatabaseManager


class TestMigrationsTable:
    """_migrations table is created during schema init."""

    def test_migrations_table_exists_after_initialize(self) -> None:
        db = DatabaseManager(":memory:")
        db.initialize()
        conn = db.connection
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='_migrations'"
        )
        assert cursor.fetchone() is not None

    def test_migrations_table_has_expected_columns(self) -> None:
        db = DatabaseManager(":memory:")
        db.initialize()
        conn = db.connection
        cursor = conn.execute("PRAGMA table_info(_migrations)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "migration_id",
            "description",
            "app_version",
            "checksum",
            "applied_at",
            "duration_ms",
        }
        assert expected.issubset(columns)

    def test_migrations_table_is_empty_on_first_init(self) -> None:
        db = DatabaseManager(":memory:")
        db.initialize()
        conn = db.connection
        cursor = conn.execute("SELECT COUNT(*) FROM _migrations")
        assert cursor.fetchone()[0] == 0

    def test_existing_tables_still_created(self) -> None:
        db = DatabaseManager(":memory:")
        db.initialize()
        conn = db.connection
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "games" in tables
        assert "sessions" in tables
        assert "active_sessions" in tables
        assert "settings" in tables
        assert "_migrations" in tables

    def test_migrations_table_idempotent_init(self) -> None:
        """Calling initialize twice does not error."""
        db = DatabaseManager(":memory:")
        db.initialize()
        db.initialize()  # second call should be safe
        conn = db.connection
        cursor = conn.execute("SELECT COUNT(*) FROM _migrations")
        assert cursor.fetchone()[0] == 0
