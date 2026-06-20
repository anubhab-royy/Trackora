"""v2.0.0 — Add Update Center settings keys (corrected).

Seeds the correct default settings keys for the Update Center feature:

  - update_last_checked         ""         ISO-8601 timestamp of last check
  - update_ignored_version      ""         Version the user dismissed
  - update_auto_check_enabled   "1"        Whether to check on startup

Idempotent: Yes. Keys are inserted only if they do not already exist
(INSERT OR IGNORE).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from trackora.core.migration_manager import Migration

_UPDATE_CENTER_DEFAULTS: dict[str, str] = {
    "update_last_checked": "",
    "update_ignored_version": "",
    "update_auto_check_enabled": "1",
}


class V2_0_0AddUpdateCenterSettingsV2(Migration):
    migration_id = "v2_0_0_add_update_center_settings_v2"
    description = "Add Update Center settings keys (corrected)"
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
