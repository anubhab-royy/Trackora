"""Tests for v2.0.0 Update Center settings migration."""

from __future__ import annotations

import sqlite3

from trackora.core.migrations.v2_0_0_add_update_center_settings_v2 import (
    V2_0_0AddUpdateCenterSettingsV2,
)


class TestUpdateCenterMigrationV2:
    def _make_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
        )
        return conn

    def test_upgrade_inserts_keys(self) -> None:
        conn = self._make_conn()
        migration = V2_0_0AddUpdateCenterSettingsV2()
        migration.upgrade(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT key FROM settings ORDER BY key")
        keys = [row["key"] for row in cursor.fetchall()]
        assert "update_last_checked" in keys
        assert "update_ignored_version" in keys
        assert "update_auto_check_enabled" in keys

    def test_upgrade_sets_default_values(self) -> None:
        conn = self._make_conn()
        migration = V2_0_0AddUpdateCenterSettingsV2()
        migration.upgrade(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", ("update_auto_check_enabled",))
        row = cursor.fetchone()
        assert row is not None
        assert row["value"] == "1"

    def test_idempotent(self) -> None:
        conn = self._make_conn()
        migration = V2_0_0AddUpdateCenterSettingsV2()
        migration.upgrade(conn)
        migration.upgrade(conn)  # second run should not raise

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM settings")
        row = cursor.fetchone()
        assert row is not None
        assert row["cnt"] == 3

    def test_verify_returns_empty_when_all_present(self) -> None:
        conn = self._make_conn()
        migration = V2_0_0AddUpdateCenterSettingsV2()
        migration.upgrade(conn)
        errors = migration.verify(conn)
        assert errors == []

    def test_verify_returns_missing_keys(self) -> None:
        conn = self._make_conn()
        migration = V2_0_0AddUpdateCenterSettingsV2()
        errors = migration.verify(conn)
        assert len(errors) == 1
        assert "update_last_checked" in errors[0]

    def test_downgrade_removes_keys(self) -> None:
        conn = self._make_conn()
        migration = V2_0_0AddUpdateCenterSettingsV2()
        migration.upgrade(conn)
        migration.downgrade(conn)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM settings")
        row = cursor.fetchone()
        assert row is not None
        assert row["cnt"] == 0

    def test_app_version(self) -> None:
        migration = V2_0_0AddUpdateCenterSettingsV2()
        assert migration.app_version == "2.0.0"

    def test_migration_id(self) -> None:
        migration = V2_0_0AddUpdateCenterSettingsV2()
        assert migration.migration_id == "v2_0_0_add_update_center_settings_v2"
