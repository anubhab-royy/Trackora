"""v2.0.0 — Add Update Center settings keys.

Adds default settings keys for the Upcoming Updates / Update Center
feature:
  - update_check_enabled     "true" | "false"  — enable periodic checks
  - update_channel           "stable" | "beta" | "nightly"
  - last_update_check        ISO-8601 datetime or empty

Idempotent: Yes. Keys are inserted only if they do not already exist
(INSERT OR IGNORE).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from trackora.core.migration_manager import Migration

_UPDATE_CENTER_DEFAULTS: dict[str, str] = {
    "update_check_enabled": "true",
    "update_channel": "stable",
    "last_update_check": "",
}


class V2_0_0AddUpdateCenterSettings(Migration):
    migration_id = "v2_0_0_add_update_center_settings"
    description = "Add Update Center default settings keys"
    app_version = "2.0.0"
    requires_backup = False
    requires_downtime = False

    def upgrade(self, connection: sqlite3.Connection) -> None:
        cursor = connection.cursor()
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        for key, value in _UPDATE_CENTER_DEFAULTS.items():
            cursor.execute(
                """
                INSERT OR IGNORE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?);
                """,
                (key, value, now),
            )

    def verify(self, connection: sqlite3.Connection) -> list[str]:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT key FROM settings WHERE key IN ("
            + ",".join("?" for _ in _UPDATE_CENTER_DEFAULTS)
            + ");",
            list(_UPDATE_CENTER_DEFAULTS),
        )
        existing = {row[0] for row in cursor.fetchall()}
        missing = set(_UPDATE_CENTER_DEFAULTS) - existing
        if missing:
            return [f"Settings keys not found: {', '.join(sorted(missing))}"]
        return []

    def downgrade(self, connection: sqlite3.Connection) -> None:
        cursor = connection.cursor()
        for key in _UPDATE_CENTER_DEFAULTS:
            cursor.execute("DELETE FROM settings WHERE key = ?;", (key,))
