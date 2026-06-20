"""v1.1.0 — Drop statistics_cache table.

Changes from v1.0.0 → v1.1.0:
  - DROP TABLE statistics_cache (dead code removal)
  - The _migrations table is created by DatabaseManager._create_schema()
    and does NOT need to be created here.

Idempotent: Yes. DROP TABLE IF EXISTS is safe to run multiple times.
"""

from __future__ import annotations

import sqlite3

from trackora.core.migration_manager import Migration


class V1_1_0InitialSchema(Migration):
    migration_id = "v1_1_0_initial_schema"
    description = "Drop statistics_cache table (dead code removal)"
    app_version = "1.1.0"
    requires_backup = False

    def upgrade(self, connection: sqlite3.Connection) -> None:
        cursor = connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS statistics_cache;")

    def verify(self, connection: sqlite3.Connection) -> list[str]:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='statistics_cache';"
        )
        if cursor.fetchone() is not None:
            return ["statistics_cache table still exists after migration"]
        return []

    def downgrade(self, connection: sqlite3.Connection) -> None:
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistics_cache (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id       INTEGER NOT NULL,
                period_type   TEXT    NOT NULL,
                period_key    TEXT    NOT NULL,
                value_seconds INTEGER NOT NULL DEFAULT 0
            );
        """)
