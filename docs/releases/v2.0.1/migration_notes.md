# Trackora v2.0.1 Migration Notes

This document provides instructions and technical details regarding upgrades and database migrations to Trackora v2.0.1.

---

## 1. Supported Upgrade Paths

Trackora v2.0.1 fully validates and supports upgrades from all previous public versions:

| Source Version | Target Version | Action Taken | Data Integrity |
|----------------|----------------|--------------|----------------|
| **v1.0.0** | v2.0.1 | 5 sequential migrations applied, database backups created | 100% Preserved |
| **v1.1.0** | v2.0.1 | 4 sequential migrations applied, database backups created | 100% Preserved |
| **v2.0.0** | v2.0.1 | Transaction schema check, backup verification, version stamp update | 100% Preserved |
| **Fresh Install** | v2.0.1 | Skip migrations, write schema version `2.0.1` and create base schema | 100% Initialized |

---

## 2. Migration Execution Flow

Database migrations are managed automatically by the `SchemaVersionManager` at application startup.

1. **Version Detection**: The system queries the `schema_version` or checks for the legacy `GameTracker` sqlite files.
2. **Pre-Upgrade Backup**: Before executing database migrations, `BackupManager` compresses the current database file into `%APPDATA%\Trackora\backups/pre_migration_<timestamp>.zip`.
3. **Transactional Migrations**: Migrations are executed within transactional boundaries. If a migration step fails, the transaction is rolled back, the backup is restored, and the application halts safely.
4. **Validation Check**: A post-migration script (`_ensure_schema_columns`) validates the presence and types of all required columns across the `games`, `sessions`, `active_sessions`, and `settings` tables.
5. **Version Stamp**: The `schema_version` is updated to `2.0.1`.

---

## 3. Data & State Preservation

### Settings Preservation
All user settings (such as theme choice, autostart toggle, tracking interval, and GitHub API credentials) are stored in the SQLite `settings` table and are fully preserved across all upgrade paths. No settings are overwritten during the upgrade.

### Queue Preservation
Pending support reports stored in `%APPDATA%\Trackora\pending_reports/` are completely decoupled from the database migrations. The queue files survive upgrades and are processed by the queue runner on the next startup.

### Statistics Preservation
Because all statistics are compiled dynamically from raw session data, no calculated values are hardcoded. Historical data in the `sessions` table is preserved, and the Statistics engine regenerates the dashboard metrics immediately on the first launch of v2.0.1.

---

## 4. Compatibility Guidelines

### Backward Compatibility
Database files upgraded to v2.0.1 are backward-compatible with v2.0.0, but NOT with v1.0.0 or v1.1.0 due to structural changes in the schema (the introduction of game launchers, update settings, and active session recovery tables).

### Forward Compatibility & Downgrade Safety
If a newer database version (e.g. v2.1.0 or higher) is detected by Trackora v2.0.1, the application will:
1. Block execution to prevent data loss.
2. Present a critical alert dialog informing the user that a newer version of Trackora has modified the database.
3. Exit safely with code `2`.
This ensures that downgrades do not corrupt newer database structures.
