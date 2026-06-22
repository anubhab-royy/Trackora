# Upgrade Foundation Architecture

**Version:** 1.0  
**Status:** Draft  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  

---

## Principles

1. **User data is sacred.** It must survive all future Trackora upgrades — reinstalls, major/minor/patch versions, and even application removal.

2. **Application code is ephemeral.** Files in `Program Files/Trackora` may be completely replaced on every upgrade. No user data may reside there.

3. **Upgrades are one-way.** The application may evolve forward. Downgrade is not supported. BackupManager exists for manual data recovery, not for version rollback.

4. **Migrations are additive.** Existing data structures must never require destructive changes. New columns, new tables, and new indexes are preferred over alterations that could lose data.

5. **Every migration must be safe, idempotent, recoverable, and tested.** If any of these properties cannot be guaranteed, the migration must not proceed.

6. **Schema version is authoritative.** The application must refuse to run on data with a newer schema version. The application must upgrade data with an older schema version.

---

## Architecture Overview

The Upgrade Foundation consists of three components, each with a single responsibility:

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Startup                       │
│                                                             │
│  1. Read schema version (SchemaVersionManager)              │
│  2. If incompatible → block with clear error                │
│  3. If upgradable → create backup (BackupManager)           │
│  4. Apply pending migrations (MigrationManager)             │
│  5. Update schema version (SchemaVersionManager)            │
│  6. Normal initialization                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Design

---

### 1. SchemaVersionManager

**File:** `trackora/core/schema_version_manager.py`

**Purpose:** Single source of truth for the current schema version of user data. Provide read, write, validation, and comparison operations.

**Storage:** `%APPDATA%/Trackora/schema.json`

```json
{
  "schema_version": "2.0.0",
  "app_version": "2.0.0",
  "updated_at": "2026-06-20T12:00:00Z",
  "description": "Schema version at time of application launch or last migration"
}
```

**API:**

```
SchemaVersionManager:
  - __init__(schema_path: Path | None = None)
  - read() -> SchemaVersion | None
  - write(version: SchemaVersion) -> None
  - validate(raw: dict) -> bool
  - is_compatible(app_version: str, data_version: str) -> bool
  - compare(a: str, b: str) -> int
```

**Key behaviors:**
- If `schema.json` does not exist on first run, create it with the application's built-in schema version.
- If `schema_version` > application's supported version, return `is_compatible = False` (application is too old for this data).
- If `schema_version` < application's supported version, return `is_compatible = True` (migration needed).
- If `schema_version` == application's supported version, return `is_compatible = True` (up to date).

**Version format:** Semantic versioning (`MAJOR.MINOR.PATCH`). Comparison follows semver rules.

**Error handling:**
- Missing file on subsequent runs → log warning, treat as v1.0.0
- Corrupt JSON → log error, back up corrupt file, create fresh
- Invalid version string → ValidationError

---

### 2. BackupManager

**File:** `trackora/core/backup_manager.py`

**Purpose:** Create full, verifiable backups of user data before any destructive or non-trivial operation. Provide restore capability for disaster recovery.

**Storage:** `%APPDATA%/Trackora/backups/`

**Backup format:** ZIP archive

```
backup_20260620_120000.zip
  ├── trackora.db           (SQLite database)
  ├── schema.json           (schema version metadata)
  └── MANIFEST.json         (backup metadata)
```

**MANIFEST.json:**

```json
{
  "backup_id": "b2f7a8c1-...",
  "created_at": "2026-06-20T12:00:00Z",
  "app_version": "1.1.0",
  "schema_version": "1.0.0",
  "files": {
    "trackora.db": {
      "size_bytes": 1048576,
      "sha256": "abcdef..."
    },
    "schema.json": {
      "size_bytes": 128,
      "sha256": "123456..."
    }
  }
}
```

**API:**

```
BackupManager:
  - __init__(backup_dir: Path, source_dir: Path)
  - create_backup() -> BackupResult
  - restore_backup(backup_id: str) -> RestoreResult
  - verify_backup(backup_id: str) -> bool
  - list_backups() -> list[BackupInfo]
  - delete_backup(backup_id: str) -> None
  - get_latest_backup() -> BackupInfo | None
```

**Backup lifecycle:**
1. `create_backup()` generates UUID-based backup ID
2. Copies `trackora.db` to temp location (ensuring no write lock issues via `VACUUM INTO` or file copy)
3. Copies `schema.json`
4. Creates MANIFEST.json with SHA-256 checksums
5. Packages into ZIP archive with atomic rename (`.tmp` → `.zip`)
6. Verifies ZIP integrity by re-reading and checking checksums
7. Returns `BackupResult` with success/failure, backup_id, path, error

**Restore lifecycle:**
1. `restore_backup(backup_id)` reads MANIFEST.json
2. Verifies checksums of all files in ZIP
3. Creates temporary restore directory
4. Extracts files to temporary directory
5. Verifies extracted files against MANIFEST checksums
6. Stops the application database connection
7. Replaces `trackora.db` and `schema.json` with restored versions
8. Reopens database connection
9. Returns `RestoreResult`

**Backup retention:**
- Keep last 5 backups by default
- Delete oldest backup when creating new one if limit exceeded
- Configurable via SettingsRepository: `backup_retention_count`

---

### 3. MigrationManager

**File:** `trackora/core/migration_manager.py`

**Purpose:** Discover, apply, and track database schema migrations. Guarantee idempotency and atomicity.

**Storage:** `_migrations` table in SQLite database

```sql
CREATE TABLE IF NOT EXISTS _migrations (
    migration_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);
```

**Migration interface:**

```python
class Migration(ABC):
    @property
    @abstractmethod
    def migration_id(self) -> str:
        """Unique identifier, e.g., 'v2.0.0_add_discovery_flags'"""
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description, e.g., 'Add game discovery metadata columns'"""
    
    @abstractmethod
    def upgrade(self, connection: sqlite3.Connection) -> None:
        """Apply the migration. Must be idempotent."""
    
    @abstractmethod
    def downgrade(self, connection: sqlite3.Connection) -> None:
        """Revert the migration. Must be idempotent."""
    
    @property
    def requires_backup(self) -> bool:
        """Whether a backup should be created before this migration. Default: True"""
        return True
```

**API:**

```
MigrationManager:
  - __init__(connection, schema_version_manager, backup_manager)
  - get_pending_migrations() -> list[Migration]
  - get_applied_migrations() -> list[AppliedMigration]
  - apply_all() -> MigrationResult
  - apply_one(migration_id: str) -> MigrationResult
  - has_been_applied(migration_id: str) -> bool
  - get_migration_checksum(migration_id: str) -> str | None
```

**Migration flow:**

```
1. MigrationManager.get_pending_migrations()
   → Query _migrations table
   → Compare against registered migrations list
   → Return unapplied migrations sorted by version

2. MigrationManager.apply_all()
   For each pending migration (in order):
     ├── a. If requires_backup → BackupManager.create_backup()
     ├── b. Begin transaction (SAVEPOINT)
     ├── c. migration.upgrade(connection)
     ├── d. Record in _migrations table (INSERT)
     ├── e. Commit transaction (RELEASE SAVEPOINT)
     └── f. On error → ROLLBACK TO SAVEPOINT → log error → continue? abort?

3. SchemaVersionManager.write(new_version)
```

**Idempotency guarantee:**
- Migration `upgrade()` must use `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (or check for column existence first), `CREATE INDEX IF NOT EXISTS`
- MigrationManager checks `_migrations` table before applying: if `migration_id` exists, skip entirely
- The `checksum` of the migration code itself is stored to detect modified migrations

**Downgrade support:**
- Each migration must implement `downgrade()`
- `downgrade()` is only used for development/testing — production does not downgrade
- In production, the only "rollback" is BackupManager.restore_backup()

---

## Directory Layout

```
%APPDATA%/Trackora/
├── trackora.db              ← SQLite database (user data)
├── schema.json              ← Schema version metadata
├── backups/                 ← Backup archives
│   ├── backup_20260620_120000.zip
│   ├── backup_20260619_080000.zip
│   └── ...
├── logs/                    ← Application logs
├── crash_reports/           ← Crash diagnostics
├── cache/                   ← Application cache files
├── config/                  ← Configuration files
├── reports/                 ← Report exports
├── screenshots/             ← Screenshots
├── exports/                 ← Data exports
└── imports/                 ← Data imports
```

---

## Migration Examples

### Migration: Add game discovery metadata columns

```python
class AddGameDiscoveryColumns(Migration):
    migration_id = "v2.0.0_add_discovery_columns"
    description = "Add platform, platform_id, and is_auto_discovered columns to games table"

    def upgrade(self, connection):
        # Check column existence first for idempotency
        cursor = connection.execute("PRAGMA table_info(games)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if "platform" not in columns:
            connection.execute("ALTER TABLE games ADD COLUMN platform TEXT DEFAULT NULL")
        if "platform_id" not in columns:
            connection.execute("ALTER TABLE games ADD COLUMN platform_id TEXT DEFAULT NULL")
        if "is_auto_discovered" not in columns:
            connection.execute("ALTER TABLE games ADD COLUMN is_auto_discovered INTEGER DEFAULT 0")
        
        # Add index
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_platform
            ON games(platform)
        """)

    def downgrade(self, connection):
        # SQLite does not support DROP COLUMN in older versions
        # Strategy: recreate table without these columns
        connection.executescript("""
            PRAGMA foreign_keys=OFF;
            CREATE TABLE games_new (...);
            INSERT INTO games_new SELECT ... FROM games;
            DROP TABLE games;
            ALTER TABLE games_new RENAME TO games;
            PRAGMA foreign_keys=ON;
        """)
```

### Migration: Add settings keys

```python
class AddUpdateCenterSettings(Migration):
    migration_id = "v2.0.0_add_update_center_settings"
    description = "Add update center configuration settings"

    def upgrade(self, connection):
        settings = [
            ("update_check_enabled", "true"),
            ("update_check_interval_hours", "24"),
            ("last_update_check", ""),
            ("last_dismissed_version", ""),
        ]
        for key, default_value in settings:
            connection.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, default_value),
            )

    def downgrade(self, connection):
        keys = ["update_check_enabled", "update_check_interval_hours",
                "last_update_check", "last_dismissed_version"]
        for key in keys:
            connection.execute("DELETE FROM settings WHERE key = ?", (key,))
```

---

## Migration Discovery

Migrations are automatically discovered by scanning the `trackora/core/migrations/` directory:

```
trackora/core/migrations/
├── __init__.py
├── registry.py              ← MigrationRegistry (discovers and sorts migrations)
├── v2_0_0_add_discovery_columns.py
├── v2_0_0_add_update_center_settings.py
└── ...
```

**MigrationRegistry:**

```python
class MigrationRegistry:
    @staticmethod
    def discover() -> list[type[Migration]]:
        """Discover all Migration subclasses in the migrations package.
        
        Returns migrations sorted by migration_id to ensure consistent ordering.
        """
    
    @staticmethod
    def get_by_id(migration_id: str) -> type[Migration] | None:
        """Look up a specific migration by ID."""
```

---

## Upgrade Flow (Detailed)

```
Application Start
        │
        ▼
SchemaVersionManager.read()
        │
        ├── File missing (first run):
        │     └── SchemaVersionManager.write(current_app_version)
        │         → Normal startup
        │
        ├── schema_version > app_supported_version:
        │     └── Show error: "This database requires Trackora X.Y.Z or newer"
        │         → Block startup
        │
        ├── schema_version == app_supported_version:
        │     └── Normal startup
        │
        └── schema_version < app_supported_version:
              │
              ▼
        BackupManager.create_backup()
              │
              ├── Backup failed:
              │     └── Log error → Block migration → Show error to user
              │
              └── Backup succeeded:
                    │
                    ▼
              MigrationManager.apply_all()
                    │
                    ├── All succeeded:
                    │     SchemaVersionManager.write(new_version)
                    │     → Normal startup
                    │
                    └── Some failed:
                          └── Log error (migration state is already recorded atomically)
                              → Application may start with partially migrated state
                              → Show warning to user
                              → Recommend restore from backup
```

---

## Architecture Enforcement Rules

### Rule 1 — Schema Version Isolation

Fail if any file except `trackora/core/schema_version_manager.py` reads or writes schema version metadata (`schema.json`-like files).

### Rule 2 — Migration Isolation

Fail if any file outside `trackora.core.migrations` or `trackora/core/migration_manager.py` applies database schema changes that are not idempotent.

### Rule 3 — Backup Isolation

Fail if any file except `trackora/core/backup_manager.py` creates or restores full-database backups.

### Rule 4 — Migration Idempotency

Fail if any registered migration's `upgrade()` method would fail when applied twice to the same schema (verified via automated test).

---

## Testing Strategy

### Unit Tests

| Component | Tests |
|-----------|-------|
| SchemaVersionManager | Read, write, validate, compare, missing file, corrupt file, incompatible version |
| BackupManager | Create backup, verify backup, restore backup, list backups, delete backup, retention limit, disk full |
| MigrationManager | Discover pending, apply one, apply all, detect applied, skip applied, rollback on error, checksum verification |

### Integration Tests

| Scenario | Coverage |
|----------|----------|
| Full upgrade lifecycle | Backup → migrate → verify → restart (schema check passes) |
| First run | No schema.json → create → normal startup |
| Incompatible data | Newer schema → block with error |
| Partial migration | Migration fails → state check → log → user notification |
| Backup restore | Full restore cycle with data integrity verification |

### Architecture Enforcement Tests

| Test | Rule |
|------|------|
| test_schema_version_isolation.py | Only schema_version_manager.py touches schema version |
| test_migration_isolation.py | Only migration system applies schema changes |
| test_backup_isolation.py | Only backup_manager.py creates/restores backups |

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| `schema.json` missing | Create with current app version (first run assumption) |
| `schema.json` corrupt | Rename to `schema.json.corrupt`, create fresh, log warning |
| Schema version incompatible | Show error dialog; application will not start |
| Backup creation fails | Log error; migration is blocked; user is warned |
| Backup verification fails | Re-create backup; if it fails again, block migration |
| Migration fails during upgrade | Transaction rolled back; migration not recorded in `_migrations` table; error logged; user is warned and offered restore |
| Restore fails | Original data untouched; log error; user is warned |

---

## Future Extensibility

### v2.1+
- MigrationManager may support parallel SQLite and MongoDB migrations
- BackupManager may support incremental backups
- Schema version stored in both SQLite `_migrations` table and `schema.json` for redundancy

### v3.0+
- Multi-backend schema management (SQLite + MongoDB)
- Cloud backup targets (S3, B2, GCS)
- Migration chaining through multiple app versions (v1.x → v2.x → v3.x)

### v4.0+
- Cross-version migration testing framework
- Automated migration dry-run in staging environment
- Rollback to last-known-good schema version (with data loss acknowledgment)

---

## References

- `v2.0.0-overview.md` — Release overview, risk register, dependency graph
- `milestone-8-upgrade-foundation.md` — M8 milestone specification
- `docs/architecture/runtime-environments.md` — Existing path and environment architecture
- `docs/architecture.md` — Current architecture v1.1
- `trackora/core/paths.py` — Path resolution (must be extended)
- `trackora/core/environment.py` — Environment detection (schema version path must respect environment)
