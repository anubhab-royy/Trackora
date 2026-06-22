"""v1.0.0 Base Schema — no-op marker migration.

Records that the v1.0.0 base schema (games, sessions, active_sessions,
settings tables and their indexes) is in place. This migration does not
modify the database — the schema is created by DatabaseManager on startup.

Idempotent: Yes.
"""

from __future__ import annotations

import sqlite3

from trackora.core.migration_manager import Migration


class V1_0_0BaseSchema(Migration):
    migration_id = "v1_0_0_base_schema"
    description = "v1.0.0 base schema (games, sessions, active_sessions, settings)"
    app_version = "1.0.0"
    requires_backup = False

    def upgrade(self, connection: sqlite3.Connection) -> None:
        pass

    def downgrade(self, connection: sqlite3.Connection) -> None:
        pass
