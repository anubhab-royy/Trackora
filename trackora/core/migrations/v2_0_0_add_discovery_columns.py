"""v2.0.0 — Add game discovery columns to the games table.

Adds three optional columns to support automatic game discovery:
  - platform         TEXT DEFAULT NULL  — e.g. "steam", "epic", "gog"
  - platform_id      TEXT DEFAULT NULL  — platform-specific game ID
  - is_auto_discovered INTEGER DEFAULT 0 — flag for auto-detected games

Also adds an index on platform for efficient filtering.

Idempotent: Yes. ALTER TABLE ADD COLUMN raises an error if the column
already exists, so we check before adding.
"""

from __future__ import annotations

import sqlite3

from trackora.core.migration_manager import Migration


_VALID_TABLES: frozenset[str] = frozenset({"games"})


def _column_exists(
    connection: sqlite3.Connection, table: str, column: str
) -> bool:
    if table not in _VALID_TABLES:
        raise ValueError(f"Unknown table: {table}")
    cursor = connection.cursor()
    cursor.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cursor.fetchall())


class V2_0_0AddDiscoveryColumns(Migration):
    migration_id = "v2_0_0_add_discovery_columns"
    description = "Add platform, platform_id, is_auto_discovered to games table"
    app_version = "2.0.0"
    requires_backup = True
    requires_downtime = False

    def upgrade(self, connection: sqlite3.Connection) -> None:
        cursor = connection.cursor()

        if not _column_exists(connection, "games", "platform"):
            cursor.execute(
                "ALTER TABLE games ADD COLUMN platform TEXT DEFAULT NULL;"
            )

        if not _column_exists(connection, "games", "platform_id"):
            cursor.execute(
                "ALTER TABLE games ADD COLUMN platform_id TEXT DEFAULT NULL;"
            )

        if not _column_exists(connection, "games", "is_auto_discovered"):
            cursor.execute(
                "ALTER TABLE games ADD COLUMN is_auto_discovered INTEGER DEFAULT 0;"
            )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_platform ON games (platform);"
        )

    def verify(self, connection: sqlite3.Connection) -> list[str]:
        errors: list[str] = []
        for col in ("platform", "platform_id", "is_auto_discovered"):
            if not _column_exists(connection, "games", col):
                errors.append(f"Column 'games.{col}' was not created")
        return errors

    def downgrade(self, connection: sqlite3.Connection) -> None:
        cursor = connection.cursor()
        cursor.execute("DROP INDEX IF EXISTS idx_games_platform;")
