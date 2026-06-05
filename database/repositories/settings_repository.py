# Upsert key/value store

"""
SettingsRepository for GameTracker.

All SQL operations for the `settings` table live here.

The settings table is a simple key/value store.
Known keys (v1.0):
    dark_mode              "true" | "false"
    start_with_windows     "true" | "false"
    minimize_to_tray       "true" | "false"
    backup_enabled         "true" | "false"
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from database.models.setting import Setting

logger = logging.getLogger(__name__)


def _row_to_setting(row: sqlite3.Row) -> Setting:
    return Setting(
        key=row["key"],
        value=row["value"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class SettingsRepository:
    """
    CRUD operations for the `settings` table.

    Args:
        connection: An open sqlite3.Connection provided by DatabaseManager.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, key: str) -> Setting | None:
        """Return the Setting for the given key, or None if not found."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE key = ?;", (key,))
        row = cursor.fetchone()
        return _row_to_setting(row) if row else None

    def get_value(self, key: str, default: str = "") -> str:
        """
        Return the raw string value for key, or `default` if not set.

        Convenience wrapper so callers don't need to unpack the Setting.
        """
        setting = self.get(key)
        return setting.value if setting is not None else default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return a boolean value for key."""
        setting = self.get(key)
        if setting is None:
            return default
        return setting.as_bool()

    def get_all(self) -> list[Setting]:
        """Return all settings rows ordered by key."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM settings ORDER BY key ASC;")
        return [_row_to_setting(r) for r in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Write (upsert)
    # ------------------------------------------------------------------

    def set(self, key: str, value: str) -> Setting:
        """
        Insert or update a setting (upsert).

        SQLite's INSERT OR REPLACE handles the conflict on PRIMARY KEY.

        Returns:
            The persisted Setting.
        """
        now = datetime.utcnow().isoformat()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = excluded.updated_at;
            """,
            (key, value, now),
        )
        self._conn.commit()
        logger.debug("Setting saved: %r = %r", key, value)
        return Setting(key=key, value=value, updated_at=datetime.fromisoformat(now))

    def set_bool(self, key: str, value: bool) -> Setting:
        """Convenience method for boolean settings."""
        return self.set(key, "true" if value else "false")

    def set_defaults(self, defaults: dict[str, str]) -> None:
        """
        Insert default values for any keys that do not yet exist.
        Existing keys are NOT overwritten.

        Args:
            defaults: Mapping of {key: default_value}.
        """
        now = datetime.utcnow().isoformat()
        cursor = self._conn.cursor()
        for key, value in defaults.items():
            cursor.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO NOTHING;
                """,
                (key, value, now),
            )
        self._conn.commit()
        logger.debug("Default settings applied: %s keys", len(defaults))

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, key: str) -> None:
        """Remove a setting by key."""
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM settings WHERE key = ?;", (key,))
        self._conn.commit()
        logger.debug("Setting deleted: %r", key)