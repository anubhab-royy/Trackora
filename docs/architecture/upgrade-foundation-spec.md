# Upgrade Foundation Architecture Specification

**Version:** 2.0.0-draft  
**Status:** Architecture Design  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  

---

## Table of Contents

1. Design Principles
2. Component Architecture
3. SchemaVersionManager
4. BackupManager
5. MigrationManager
6. Migration Lifecycle
7. Upgrade Lifecycle
8. Failure Recovery Lifecycle
9. Migration File Structure & Naming
10. Data Formats
11. Integration Map
12. Testing Strategy
13. Future Extensibility

---

## 1. Design Principles

### P1 — Data Survival

User data in `%APPDATA%/Trackora` must survive every future Trackora upgrade — clean installs, upgrades, and even application removal. Application code in `Program Files/Trackora` is ephemeral and may be completely replaced on every install.

### P2 — Fail-Safe Upgrade

Upgrades are one-way but fail-safe. Before any migration touches user data, a full verifiable backup is created. If migration fails, the backup provides a guaranteed restore point.

### P3 — Idempotent Migrations

Every migration must produce the same result whether applied once, twice, or a hundred times. MigrationManager tracks applied migrations and never reapplies them.

### P4 — Explicit Schema Version

The schema version is stored in a well-known location (`%APPDATA%/Trackora/schema.json`). The application always reads this version on startup and refuses to run if the data schema is newer than the application supports.

### P5 — Contract Over Convention

All three managers expose explicit interfaces. Consumers (including `__main__.py` and `Migration` subclasses) depend on interfaces, never on internal implementation details.

### P6 — Isolation

| Manager | May Access | Must Not Access |
|---------|-----------|-----------------|
| SchemaVersionManager | `paths.py`, filesystem | Database, repositories, services, UI |
| BackupManager | `paths.py`, filesystem, SchemaVersionManager | Database, repositories, services, UI |
| MigrationManager | `schema_version_manager`, `backup_manager`, `sqlite3.Connection` | Repositories, services, UI |

### P7 — Future Compatibility

The architecture must support:
- v2.0.0: SQLite-only migrations
- v3.0.0: SQLite + MongoDB parallel migrations
- v4.0.0+: Multiple database backends with independent version tracking

---

## 2. Component Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     trackora/core/                               │
│                                                                  │
│  ┌─────────────────────┐    ┌─────────────────────────┐        │
│  │  paths.py           │    │  environment.py         │        │
│  │  - BACKUPS_DIR      │    │  - CURRENT_ENVIRONMENT  │        │
│  │  - DATABASE_PATH    │    │  - Environment enum     │        │
│  │  - CACHE_DIR        │    └────────────┬────────────┘        │
│  │  - BASE_DIR         │                 │                      │
│  └─────────┬───────────┘                 │                      │
│            │                             │                      │
│            ▼                             ▼                      │
│  ┌──────────────────────────────────────────────────┐          │
│  │            SchemaVersionManager                  │          │
│  │  - read() → SchemaVersion                        │          │
│  │  - write(SchemaVersion) → None                   │          │
│  │  - is_compatible(app, data) → bool               │          │
│  │  Storage: %APPDATA%/Trackora/schema.json         │          │
│  └────────────────────┬─────────────────────────────┘          │
│                       │ depends on                              │
│                       ▼                                         │
│  ┌──────────────────────────────────────────────────┐          │
│  │               BackupManager                      │          │
│  │  - create_backup() → BackupResult                │          │
│  │  - restore_backup(id) → RestoreResult            │          │
│  │  - verify_backup(id) → bool                      │          │
│  │  - list_backups() → list[BackupInfo]             │          │
│  │  Storage: %APPDATA%/Trackora/backups/*.zip       │          │
│  └────────────────────┬─────────────────────────────┘          │
│                       │ depends on                              │
│                       ▼                                         │
│  ┌──────────────────────────────────────────────────┐          │
│  │             MigrationManager                     │          │
│  │  - apply_all() → MigrationResult                 │          │
│  │  - get_pending() → list[Migration]               │          │
│  │  - get_applied() → list[AppliedMigration]        │          │
│  │  Discovers migrations in:                        │          │
│  │  trackora/core/migrations/*.py                   │          │
│  └──────────────────────────────────────────────────┘          │
│                       │                                          │
│                       ▼                                          │
│  ┌──────────────────────────────────────────────────┐          │
│  │        trackora/core/migrations/                 │          │
│  │  - registry.py     (MigrationRegistry)           │          │
│  │  - base_schema.py  (Migration subclass)          │          │
│  │  - v2_0_0_*.py     (v2.0.0 migrations)          │          │
│  │  - v3_0_0_*.py     (future)                     │          │
│  └──────────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                     trackora/__main__.py                         │
│  Upgrade lifecycle orchestrator                                  │
│  1. ensure_dirs()                                                │
│  2. db.initialize()  (creates base schema + _migrations table)   │
│  3. SchemaVersionManager.read()                                  │
│  4. SchemaVersionManager.is_compatible()  → guard or proceed     │
│  5. BackupManager.create_backup()                                │
│  6. MigrationManager.apply_all()                                 │
│  7. SchemaVersionManager.write(new_version)                      │
│  8. Repository creation → normal startup                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. SchemaVersionManager

### 3.1 Purpose

Single source of truth for the current schema version of user data. Provides read, write, validation, and compatibility-check operations. This is the gatekeeper that prevents the application from running on incompatible data.

### 3.2 Responsibilities

- Read schema version from `%APPDATA%/Trackora/schema.json`
- Write schema version after successful migration
- Validate schema.json format and content
- Compare two schema versions using semantic versioning
- Determine compatibility between application version and data version
- Handle missing or corrupt schema.json gracefully

### 3.3 SchemaVersion Dataclass

```python
@dataclass(frozen=True)
class SchemaVersion:
    """Immutable value object representing a schema version."""
    major: int
    minor: int
    patch: int

    # Factory
    @classmethod
    def from_string(cls, version: str) -> SchemaVersion: ...

    @classmethod
    def current_app_version(cls) -> SchemaVersion: ...

    # Comparison
    def __lt__(self, other: SchemaVersion) -> bool: ...
    def __eq__(self, other: SchemaVersion) -> bool: ...
    def __gt__(self, other: SchemaVersion) -> bool: ...
    def __str__(self) -> str: ...
```

### 3.4 schema.json Format

```json
{
  "schema_version": "2.0.0",
  "app_version": "2.0.0",
  "updated_at": "2026-06-20T12:00:00Z",
  "description": "Schema version after application of v2.0.0 migrations"
}
```

Fields:
- `schema_version` — version of the database schema (what the user data is at)
- `app_version` — the Trackora version that last wrote this file (informational)
- `updated_at` — ISO-8601 UTC timestamp of last write
- `description` — human-readable description of what this version means

### 3.5 Public API

```
class SchemaVersionManager:
    def __init__(self, schema_path: Path | None = None) -> None
        Default: BASE_DIR / "schema.json"

    def read(self) -> SchemaVersion | None
        Returns SchemaVersion from schema.json.
        Returns None if file does not exist (first run).

    def write(self, version: SchemaVersion) -> None
        Atomically writes schema.json.
        Uses .tmp + rename pattern for crash safety.
        Raises OSError on write failure.

    def is_compatible(
        self,
        app_version: SchemaVersion,
        data_version: SchemaVersion | None,
    ) -> tuple[bool, CompatibilityStatus]

    def compare(
        self, a: SchemaVersion, b: SchemaVersion
    ) -> int
        Returns -1 (a < b), 0 (a == b), or 1 (a > b).

    def delete(self) -> None
        Removes schema.json. Used only for testing.
```

```python
@dataclass(frozen=True)
class CompatibilityStatus:
    """Result of a compatibility check."""
    can_proceed: bool
    status: str  # "ok" | "newer_data" | "needs_migration" | "first_run" | "unknown"
    message: str
```

### 3.6 Compatibility Matrix

| Data Version | App Version | `is_compatible()` | Action |
|---|---|---|---|
| None (first run) | any | `(True, "first_run")` | Create schema.json at app version, skip migration |
| == 1.1.0 | == 2.0.0 | `(True, "needs_migration")` | Backup + migrate |
| == 1.1.0 | == 1.1.0 | `(True, "ok")` | Normal startup |
| == 2.0.0 | == 2.0.0 | `(True, "ok")` | Normal startup |
| == 2.0.0 | == 1.1.0 | `(False, "newer_data")` | Block startup — app too old |
| == 2.5.0 | == 2.0.0 | `(False, "newer_data")` | Block startup — app too old |

### 3.7 Error Handling

| Condition | Behavior |
|---|---|
| schema.json missing | Return `None` (first run assumption) |
| schema.json corrupt JSON | Rename to `schema.json.corrupt.<timestamp>`, log warning, return `None` |
| schema.json invalid version string | Rename to `schema.json.invalid.<timestamp>`, log error, block startup |
| Write failure (disk full, permissions) | Log error, raise `OSError` — caller (MigrationManager) must abort |
| File locked by another process | Retry once after 100ms, then fail |

### 3.8 Dependencies

- `trackora/core/paths.py` — for `BASE_DIR`
- `json` (stdlib)
- `os`, `pathlib` (stdlib)

No database dependency. No application model dependency.

### 3.9 Testing Requirements

| Test Category | Scenarios |
|---|---|
| Read | File exists, file missing, file corrupt JSON, file invalid version string, file with extra unknown keys |
| Write | Fresh write, overwrite, atomicity (.tmp + rename), disk full (mock), permissions error (mock) |
| Compare | Equal, less than, greater than, major/minor/patch edge cases |
| Compatibility | First run, same version, needs migration, newer data, older app, prerelease versions |
| Concurrency | Two instances reading/writing simultaneously (with single-instance lock, this is prevented, but defense-in-depth) |

---

## 4. BackupManager

### 4.1 Purpose

Create full, verifiable, atomic backups of user data before any destructive or non-trivial operation. Provide reliable restore capability for disaster recovery.

### 4.2 Responsibilities

- Create atomic ZIP backup of `trackora.db` + `schema.json` + manifest
- Verify backup integrity via SHA-256 checksums
- Restore user data from a backup ZIP
- List available backups with metadata
- Enforce backup retention policy (keep last N, delete oldest)
- Provide backup info (size, date, version) for UI display

### 4.3 Public API

```
class BackupManager:
    def __init__(
        self,
        backup_dir: Path | None = None,
        source_db: Path | None = None,
        schema_manager: SchemaVersionManager | None = None,
        retention_count: int = 5,
    ) -> None
        Default backup_dir: BACKUPS_DIR from paths.py
        Default source_db: DATABASE_PATH from paths.py

    def create_backup(self) -> BackupResult
        Creates an atomic backup of the current database + schema.

    def restore_backup(self, backup_id: str) -> RestoreResult
        Restores user data from a specific backup.
        The caller is responsible for closing the database connection first.

    def verify_backup(self, backup_id: str) -> VerificationResult
        Reads the ZIP, verifies MANIFEST checksums.
        Does NOT require closing the database.

    def list_backups(self) -> list[BackupInfo]
        Returns sorted list (newest first).

    def get_latest_backup(self) -> BackupInfo | None

    def delete_backup(self, backup_id: str) -> None

    def clean_old_backups(self) -> int
        Deletes oldest backups beyond retention_count.
        Returns number of deletions.
```

### 3.4 Result Types

```python
@dataclass
class BackupResult:
    success: bool
    backup_id: str | None
    path: Path | None
    size_bytes: int | None
    checksum: str | None
    error_message: str | None

@dataclass
class RestoreResult:
    success: bool
    backup_id: str
    restored_files: list[str]
    error_message: str | None

@dataclass
class VerificationResult:
    valid: bool
    backup_id: str
    errors: list[str]

@dataclass
class BackupInfo:
    backup_id: str
    created_at: str          # ISO-8601
    app_version: str
    schema_version: str
    size_bytes: int
    checksum: str
    path: Path
```

### 4.4 Backup Format

```
backups/
├── backup_20260620_120000_<uuid8>.zip
├── backup_20260619_080000_<uuid8>.zip
└── ...
```

ZIP contents:

```
backup_20260620_120000_a1b2c3d4.zip
├── trackora.db               (SQLite database file — copied via VACUUM INTO or file copy)
├── schema.json               (current schema version file)
└── MANIFEST.json             (backup metadata, see below)
```

MANIFEST.json:

```json
{
  "backup_id": "a1b2c3d4",
  "manifest_version": 1,
  "created_at": "2026-06-20T12:00:00Z",
  "app_version": "1.1.0",
  "schema_version": "1.0.0",
  "files": {
    "trackora.db": {
      "size_bytes": 1048576,
      "sha256": "abcdef1234567890..."
    },
    "schema.json": {
      "size_bytes": 128,
      "sha256": "1234567890abcdef..."
    }
  }
}
```

### 4.5 Internal Workflow — create_backup()

```
1. Generate backup_id = first 8 chars of UUID4 hex
2. Compose filename: backup_<timestamp>_<backup_id>.zip
3. Create temp path: BACKUPS_DIR / <filename>.tmp
4. Open ZipFile (ZIP_DEFLATED) writing to temp path
5.   Write trackora.db:
       a. Read current db file into memory (or use temp copy)
       b. Compute SHA-256 of raw bytes
       c. Write bytes to ZIP
       d. Record size + checksum in manifest
6.   Write schema.json:
       a. Read from BASE_DIR
       b. Compute SHA-256
       c. Write to ZIP
       d. Record size + checksum in manifest
7.   Build MANIFEST dict with backup metadata + file checksums
8.   Write MANIFEST.json to ZIP (serialize after file checksums are known)
9.   Close ZIP
10.  Rename .tmp → .zip (atomic)
11.  Verify backup by re-reading ZIP and recomputing checksums
12.  clean_old_backups() — delete beyond retention_count
13.  Return BackupResult
```

### 4.6 Database Copy Strategy

For copying `trackora.db` into the backup ZIP, use one of:

**Preferred:** `sqlite3.Connection.backup()` API — creates an online backup of an open database without locking the main connection for long.

**Fallback:** Close database → copy file → reopen. This requires the BackupManager to be called early in startup before the database is heavily used, or called at shutdown.

**Never use:** `shutil.copy2()` on a live WAL database — WAL and SHM files must be accounted for.

### 4.7 Restore Workflow

```
1. Caller closes database connection

2. Verify backup ZIP integrity (checksums in MANIFEST)

3. Create temp restore directory: BACKUPS_DIR / .restore_<backup_id>/

4. Extract ZIP to temp directory

5. Recompute SHA-256 of extracted files, compare to MANIFEST

6. Copy extracted files over originals:
     trackora.db → DATABASE_PATH
     schema.json → BASE_DIR / schema.json

7. Clean up temp restore directory

8. Return RestoreResult
```

### 4.8 Error Handling

| Condition | Behavior |
|---|---|
| Backup creation fails mid-ZIP | .tmp file is abandoned; no partial ZIP appears at final path |
| Backup verification fails | Delete the just-created backup, log error, raise BackupError |
| Disk full during backup | Catch OSError, log, raise BackupError with specific message |
| Restore target file locked | Log error, raise RestoreError — caller must close DB first |
| Backup retention deletion fails | Log warning, continue — non-fatal |
| source_db does not exist | Log error (first-run scenario), skip backup, return success |

### 4.9 Dependencies

- `trackora/core/paths.py` — for `BACKUPS_DIR`, `DATABASE_PATH`, `BASE_DIR`
- `SchemaVersionManager` — for reading/writing `schema.json` during backup/restore
- `zipfile` (stdlib), `hashlib` (stdlib), `json` (stdlib), `shutil` (stdlib), `uuid` (stdlib)

No database driver dependency. No application model dependency.

### 4.10 Testing Requirements

| Test Category | Scenarios |
|---|---|
| Create backup | Fresh database, existing backups, empty database, large database |
| Backup atomicity | Crash during write → .tmp orphan, never .zip; verify on next startup |
| Backup verification | Valid ZIP, corrupt ZIP, missing file in ZIP, wrong checksum, tampered MANIFEST |
| Backup listing | No backups, 1 backup, 5+ backups, mixed old/new format |
| Backup retention | Keep last 5, delete beyond 5, retention_count=0 (keep all) |
| Restore | Full restore, verify data integrity, restore from corrupted backup |
| Database copy | Live database (WAL mode), large database, database with active readers |
| Edge cases | Disk full, permissions error, backup dir does not exist, backup dir is file |

---

## 5. MigrationManager

### 5.1 Purpose

Discover, order, apply, and track database schema migrations. Guarantee that every migration is applied exactly once, atomically, and with a verifiable backup taken beforehand.

### 5.2 Responsibilities

- Discover all `Migration` subclasses in `trackora/core/migrations/`
- Sort migrations by version (ascending)
- Query `_migrations` table to determine which have been applied
- Compute pending migrations (discovered − applied)
- For each pending migration (in order):
  1. Create backup (if migration requires it)
  2. Begin transaction
  3. Apply migration `upgrade()`
  4. Verify migration result (`verify()`)
  5. Record migration in `_migrations` table
  6. Commit transaction
  7. Handle failure: rollback, log, report
- Update schema version after all migrations succeed
- Provide rollback capability (development only, not for production)

### 5.3 Public API

```
class MigrationManager:
    def __init__(
        self,
        connection: sqlite3.Connection,
        schema_version_manager: SchemaVersionManager,
        backup_manager: BackupManager | None = None,
        registry: MigrationRegistry | None = None,
    ) -> None
        Default registry: MigrationRegistry.discover()

    def get_pending_migrations(self) -> list[Migration]
    def get_applied_migrations(self) -> list[AppliedMigration]
    def get_all_migrations(self) -> list[Migration]

    def apply_all(self) -> MigrationResult
        Applies all pending migrations in order.
        Returns summary of what was applied, what failed, etc.

    def apply_one(self, migration_id: str) -> MigrationResult
        Applies a single migration by ID.
        Used for development/testing.

    def has_been_applied(self, migration_id: str) -> bool

    def get_migration_checksum(self, migration_id: str) -> str | None
```

### 4.3 Result Types

```python
@dataclass
class MigrationResult:
    success: bool
    applied_count: int
    failed_count: int
    results: list[MigrationAttempt]
    backup_id: str | None   # from pre-migration backup
    final_version: str | None

@dataclass
class MigrationAttempt:
    migration_id: str
    description: str
    success: bool
    duration_ms: int
    error: str | None
    backup_id: str | None
```

### 5.4 Migration ABC

```python
class Migration(ABC):
    """Base class for all schema migrations."""

    @property
    @abstractmethod
    def migration_id(self) -> str:
        """Unique identifier. Must match regex: ^v\d+_\d+_\d+_[a-z0-9_]+$"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for logging and the _migrations table."""
        ...

    @property
    @abstractmethod
    def app_version(self) -> str:
        """Target application version after this migration, e.g. '2.0.0'."""
        ...

    @abstractmethod
    def upgrade(self, connection: sqlite3.Connection) -> None:
        """Apply the migration.
        Must be idempotent — use IF NOT EXISTS, check columns, etc."""
        ...

    @abstractmethod
    def downgrade(self, connection: sqlite3.Connection) -> None:
        """Revert the migration.
        Called during rollback. Must be idempotent."""
        ...

    def verify(self, connection: sqlite3.Connection) -> list[str]:
        """Optional: verify migration succeeded.
        Return empty list on success, list of error messages on failure.
        Default: return [] (no verification)."""
        return []

    @property
    def requires_backup(self) -> bool:
        """Whether a full backup should be created before this migration.
        Default: True — all schema changes should be backed up first."""
        return True

    @property
    def requires_downtime(self) -> bool:
        """Whether the application must not be running during this migration.
        Default: False — most migrations run at startup before repos are created."""
        return False
```

### 5.5 MigrationRegistry

```python
class MigrationRegistry:
    @staticmethod
    def discover() -> list[type[Migration]]:
        """Scan trackora/core/migrations/ for Migration subclasses.
        Returns sorted by migration_id (ascending)."""

    @staticmethod
    def get_by_id(migration_id: str) -> type[Migration] | None:
        """Lookup a specific migration class."""
```

### 5.6 `_migrations` Table

```sql
CREATE TABLE IF NOT EXISTS _migrations (
    migration_id TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    app_version  TEXT NOT NULL,
    checksum     TEXT NOT NULL,
    applied_at   TEXT NOT NULL,   -- ISO-8601 UTC
    duration_ms  INTEGER NOT NULL DEFAULT 0
);
```

- `migration_id` — unique identifier (PK), e.g., `v2_0_0_add_discovery_columns`
- `description` — human-readable, from `Migration.description`
- `app_version` — target app version, from `Migration.app_version`
- `checksum` — SHA-256 of the migration class source code (to detect tampering)
- `applied_at` — when the migration was applied
- `duration_ms` — how long the upgrade() took

### 5.7 Internal Workflow — apply_all()

```
MigrationManager.apply_all():
1. Read current schema version via SchemaVersionManager.read()
   ├── None (first run) → SchemaVersionManager.write(current_app_version) → return (no migrations needed)
   └── Version found → continue

2. Query _migrations table → get list of applied migration_ids

3. Discover all migrations via MigrationRegistry.discover()
   Sort by migration_id ascending (ensures consistent order)

4. Compute pending = [m for m in discovered if m.migration_id not in applied]

5. If pending is empty → return MigrationResult(success=True, applied_count=0)

6. For each migration in pending (in order):
   a. If migration.requires_backup:
        result = BackupManager.create_backup()
        if not result.success:
            → ABORT: return MigrationResult with failure (migration blocked, backup failed)
   b. Begin transaction (connection.execute("SAVEPOINT migration_<id>"))
   c. Try:
        migration.upgrade(connection)
        errors = migration.verify(connection)
        if errors:
            raise MigrationVerificationError(errors)
        checksum = compute_source_checksum(migration)
        connection.execute(
            "INSERT INTO _migrations (...) VALUES (...) ",
            (migration.migration_id, migration.description,
             migration.app_version, checksum, utcnow(), duration_ms)
        )
        connection.execute("RELEASE SAVEPOINT migration_<id>")
   d. Except:
        connection.execute("ROLLBACK TO SAVEPOINT migration_<id>")
        → Record failure, continue to next migration OR abort (configurable)
        → Log error with full traceback

7. If all migrations succeeded:
     SchemaVersionManager.write(SchemaVersion.from_string(app_version))
     where app_version is the last migration's app_version
     Log success summary
     Return MigrationResult(success=True, applied_count=N)

8. If any migration failed:
     Schema version is NOT updated (data remains at previous version)
     Log error summary
     Suggest user restore from latest backup
     Return MigrationResult(success=False, ...)
```

### 5.8 First-Run Scenario

On a completely fresh install (no `%APPDATA%/Trackora/` directory):

1. `ensure_dirs()` creates all directories
2. `DatabaseManager.initialize()` creates base schema
3. `SchemaVersionManager.read()` → returns `None` (no `schema.json`)
4. `MigrationManager.apply_all()`:
   - `read()` returned `None` → this is first run
   - All discovered migrations are inserted into `_migrations` table as "applied" (skipped)
   - `SchemaVersionManager.write(current_app_version)` locks the schema
5. Normal startup proceeds

This means the `_create_schema()` in `DatabaseManager` creates the full v1.1.0 base schema, and all subsequent migrations are marked as "already applied" without executing them. The base schema is always the v1.1.0 schema — everything after that is a migration.

### 5.9 Error Handling

| Condition | Behavior |
|---|---|
| Migration upgrade() raises | Rollback SAVEPOINT, log error, record failure, continue to next |
| Migration verify() fails | Rollback SAVEPOINT, log error, record failure, continue to next |
| Backup before migration fails | ABORT — do not proceed with migration |
| _migrations table does not exist | Create it first (should be created by DatabaseManager._create_schema()) |
| Duplicate migration_id in registry | Raise ConfigurationError at startup |
| Migration checksum changed (reapplying) | Log warning, skip with checksum mismatch error, do NOT reapply |
| Multiple migrations fail | Report all failures, suggest restore from backup |
| Disk full during migration | Rollback, log, fail — data is safe |

### 5.10 Dependencies

- `sqlite3.Connection` — from `DatabaseManager`
- `SchemaVersionManager` — read before, write after
- `BackupManager` — create backup before each migration
- `trackora.core.migrations.registry.MigrationRegistry` — discover migrations

### 5.11 Testing Requirements

| Test Category | Scenarios |
|---|---|
| Discovery | Discover migrations in package, empty package, package with non-Migration classes |
| Sorting | Migrations ordered by migration_id ascending |
| Applied detection | Query _migrations table, empty table, partial set, all applied |
| Pending computation | Full set, empty, partial overlaps |
| Single migration apply | Success, failure, verify failure, checksum computation |
| Multiple migrations | Chain of 3, failure in middle, failure at end |
| Idempotency | Apply same migration twice — second is skipped |
| Rollback | SAVEPOINT rollback on failure, verify no partial changes |
| Backup integration | Backup created before migration, backup skipped when requires_backup=False |
| First run | No schema.json → migrations skipped → version written |
| Transaction safety | Crash during migration → no partial apply, retry completes successfully |

---

## 5. Migration Lifecycle

### 5.1 States

```
                                   ┌──────────┐
                                   │ DISCOVERED│
                                   └─────┬────┘
                                         │
                                         ▼
                                   ┌──────────┐
                                   │  PENDING  │
                                   └─────┬────┘
                                         │
                              ┌──────────┼──────────┐
                              │          │          │
                              ▼          ▼          ▼
                      ┌──────────┐ ┌──────────┐ ┌──────────┐
                      │ BACKING  │ │ SKIPPED  │ │ FAILED   │
                      │   UP     │ │(first run)│ │(recover) │
                      └────┬─────┘ └──────────┘ └──────────┘
                           │
                           ▼
                     ┌──────────┐
                     │APPLYING  │
                     └────┬─────┘
                          │
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
              ┌──────────┐ ┌──────────┐
              │ VERIFIED │ │  ROLLED  │
              │          │ │  BACK    │
              └────┬─────┘ └──────────┘
                   │
                   ▼
             ┌──────────┐
             │ RECORDED │
             └──────────┘
```

### 5.2 State Transitions

| From | To | Trigger |
|---|---|---|
| DISCOVERED | PENDING | MigrationManager.get_pending_migrations() — discovered but not in _migrations table |
| PENDING | BACKING_UP | MigrationManager.apply_all() starts processing this migration |
| PENDING | SKIPPED | First run — all migrations are skipped and recorded as applied without execution |
| BACKING_UP | APPLYING | BackupManager.create_backup() succeeds |
| BACKING_UP | FAILED | BackupManager.create_backup() fails |
| APPLYING | VERIFIED | migration.upgrade() succeeds AND migration.verify() returns no errors |
| APPLYING | ROLLED_BACK | migration.upgrade() raises OR migration.verify() returns errors |
| VERIFIED | RECORDED | Migration recorded in _migrations table, SAVEPOINT released |
| ROLLED_BACK | FAILED | Error logged, next migration processed (or abort depending on policy) |

---

## 6. Upgrade Lifecycle

### 6.1 Full Sequence

```
LAUNCH
  │
  ▼
[1] Single-instance lock
  │
  ▼
[2] QApplication creation
  │
  ▼
[3] ensure_dirs()
    ├── Creates BASE_DIR, LOGS_DIR, BACKUPS_DIR, CACHE_DIR, etc.
    └── (schema.json does NOT exist yet on first run)
  │
  ▼
[4] DatabaseManager.initialize()
    ├── Opens SQLite connection
    ├── Applies PRAGMAs (WAL, foreign_keys, busy_timeout)
    ├── Creates base schema: games, sessions, active_sessions, settings
    ├── Creates _migrations table  ★ NEW
    └── Commits transaction
  │
  ▼
[5] SchemaVersionManager.read()
    ├── File exists → parse version
    ├── File missing → return None (first run or manual wipe)
    └── File corrupt → rename, log, return None
  │
  ▼
[6] SchemaVersionManager.is_compatible(app_version, data_version)
    ├── data_version == None (first run) → PROCEED (step 7 skipped)
    ├── data_version > app_version → BLOCK:
    │     Show error dialog: "Database requires Trackora X.Y.Z or newer"
    │     Exit application
    ├── data_version == app_version → PROCEED (skip to step 10)
    └── data_version < app_version → PROCEED (continue to step 7)
  │
  ▼
[7] BackupManager.create_backup()
    ├── Creates ZIP of trackora.db + schema.json + MANIFEST
    ├── Verifies backup immediately
    ├── On failure → BLOCK:
    │     Log error, show warning, abort upgrade
    │     User must resolve disk/permission issue
    └── On success → store backup_id
  │
  ▼
[8] MigrationManager.apply_all()
    ├── Discover pending migrations (if any)
    ├── For each:
    │   ├── Backup (if required)
    │   ├── Apply upgrade()
    │   ├── Verify
    │   ├── Record in _migrations
    │   └── Commit
    ├── All succeed → continue
    └── Any fail → log, show warning, suggest backup restore
  │
  ▼
[9] SchemaVersionManager.write(new_version)
    ├── Atomic write to schema.json
    └── new_version = last applied migration's app_version
  │
  ▼
[10] Repository creation (GamesRepository, etc.)
[11] Service creation (GameService, etc.)
[12] RecoveryManager.recover()
[13] ProcessMonitor.start()
[14] MainWindow.show()
[15] Normal operation
```

### 6.2 Normal Startup (no upgrade needed)

Steps 5-9 compress to:

```
[5] SchemaVersionManager.read()
[6] is_compatible() == (True, "ok")
    → Skip directly to [10]
```

Steps 7-9 are completely bypassed. The entire upgrade lifecycle adds **< 100ms** to startup when no migration is needed.

### 6.3 Version Increment Rules

| Scenario | After Event | schema_version in schema.json |
|---|---|---|
| First run (no schema.json) | SchemaVersionManager.write() | Set to current app version (e.g., `2.0.0`) |
| Upgrade: v1.1.0 → v2.0.0 | All v2.0.0 migrations applied | Set to `2.0.0` |
| Same version startup | Nothing | Unchanged |
| Patch version migration (v2.0.0 → v2.0.1) | Single migration applied | Set to `2.0.1` |
| Minor version migration (v2.0.0 → v2.1.0) | Multiple migrations applied | Set to `2.1.0` |

---

## 7. Failure Recovery Lifecycle

### 7.1 Migration Failure During upgrade()

```
Applied: v2_0_0_add_discovery_columns
         v2_0_0_add_update_center_settings   ← last successful
Pending: v2_0_0_add_some_new_feature         ← FAILS HERE

Recovery:
1. SAVEPOINT rolled back by MigrationManager
2. _migrations table does NOT have v2_0_0_add_some_new_feature
3. Schema version is NOT updated (still at previous version)
4. Application starts with partially migrated schema (migrations before failure are applied)
5. Error is logged with full detail
6. User is shown warning at startup

On next launch:
1. SchemaVersionManager reads previous version (e.g., 2.0.0)
2. Compatiblity check → needs_applying (pending migrations exist)
3. Backup is created
4. MigrationManager.apply_all() runs again
5. Already-applied migrations (v2_0_0_add_discovery_columns, v2_0_0_add_update_center_settings)
   are skipped because they exist in _migrations
6. Failed migration (v2_0_0_add_some_new_feature) is retried
7. If it fails again → user is offered backup restore
```

### 7.2 Application Crash During Migration

```
Crash occurs AFTER upgrade() succeeds but BEFORE _migrations INSERT commits:
  → SAVEPOINT is automatically rolled back by SQLite
  → No partial data
  → On next launch, migration is retried

Crash occurs AFTER _migrations INSERT commits:
  → Migration is recorded as applied
  → On next launch, migration is skipped (found in _migrations)
  → If the upgrade() had side effects that were committed, they persist
  → This is correct because upgrade() is idempotent

Crash occurs during backup creation:
  → .tmp backup file is orphaned
  → On next launch, backup is retried
  → Old backups are unaffected
```

### 7.3 Backup Restore Flow

```
User trigger (or automatic suggestion after failed migration):

1. Application shows: "Migration failed. Restore from backup?"
2. User confirms
3. Application:
   a. Close database connection
   b. BackupManager.restore_backup(latest_backup_id)
   c. Reopen database
   d. SchemaVersionManager.read() → previous version restored
   e. Normal startup (no migration applied)
4. User can retry after resolving the underlying issue
```

### 7.4 Application Crash During Restore

```
Crash during step (b) — restore_backup():
  → Temp restore directory may contain partial files
  → Original database is NOT touched until verified extraction is complete
  → On next launch, the original (pre-restore) database is intact
  → BackupManager cleans orphaned .restore_* directories on init
```

### 7.5 Fatal Error: Schema Too New

```
SchemaVersionManager.read() returns version 2.5.0
Application only supports up to 2.0.0

Behavior:
1. Log error: "Database schema version 2.5.0 is newer than app supports (max 2.0.0)"
2. Show blocking error dialog:
     "This Trackora database was created by a newer version.
      Please update Trackora to the latest version."
3. Application exits with code 2
4. Data is untouched

Recovery:
  User must install a newer Trackora that supports schema version 2.5.0+
```

---

## 8. Migration File Structure & Naming

### 8.1 Directory Layout

```
trackora/core/migrations/
├── __init__.py                      # Package init
├── registry.py                      # MigrationRegistry class
├── base_schema.py                   # Base schema marker migration (v1.0.0)
│
├── v2_0_0_add_discovery_columns.py
├── v2_0_0_add_update_center_settings.py
│
├── v2_1_0_add_game_tags.py          # Future
│
├── v3_0_0_add_mongodb_collections.py # Future
│
└── v4_0_0_add_cloud_sync.py         # Future
```

### 8.2 Naming Convention

Format:
```
v<major>_<minor>_<patch>_<short_description>.py
```

Rules:
- All lowercase
- Words separated by single underscores
- Version prefix matches the target app version (e.g., `v2_0_0_*` for migrations that must be applied before v2.0.0 can run)
- Description is a brief snake_case summary (max 6 words)
- Must be valid Python module name (no hyphens, no leading digits after version)

Examples:
```
v2_0_0_add_discovery_columns.py
v2_0_0_add_update_center_settings.py
v2_0_0_add_schema_version_tracking.py
v2_1_0_add_game_tags.py
v3_0_0_add_mongodb_schema.py
```

### 8.3 Migration File Template

```python
"""Migration: <description>"""
from __future__ import annotations

import sqlite3

from trackora.core.migration_manager import Migration


class AddDiscoveryColumns(Migration):
    migration_id = "v2_0_0_add_discovery_columns"
    description = "Add platform, platform_id, is_auto_discovered to games table"
    app_version = "2.0.0"

    def upgrade(self, connection: sqlite3.Connection) -> None:
        cursor = connection.execute("PRAGMA table_info(games)")
        columns = {row[1] for row in cursor.fetchall()}

        if "platform" not in columns:
            connection.execute(
                "ALTER TABLE games ADD COLUMN platform TEXT DEFAULT NULL"
            )
        if "platform_id" not in columns:
            connection.execute(
                "ALTER TABLE games ADD COLUMN platform_id TEXT DEFAULT NULL"
            )
        if "is_auto_discovered" not in columns:
            connection.execute(
                "ALTER TABLE games ADD COLUMN is_auto_discovered INTEGER DEFAULT 0"
            )

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_platform ON games(platform)"
        )

    def downgrade(self, connection: sqlite3.Connection) -> None:
        # SQLite 3.35+ supports DROP COLUMN; for older versions, recreate table.
        cursor = connection.execute("PRAGMA table_info(games)")
        columns = {row[1] for row in cursor.fetchall()}

        if "platform" not in columns:
            return  # Nothing to downgrade

        # Recreate games table without the discovery columns
        connection.executescript("""
            PRAGMA foreign_keys=OFF;

            CREATE TABLE games_new (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL,
                process_name     TEXT    NOT NULL,
                executable_path  TEXT    NOT NULL,
                icon_path        TEXT    NOT NULL DEFAULT '',
                is_enabled       INTEGER NOT NULL DEFAULT 1,
                first_played     DATETIME,
                last_played      DATETIME,
                created_at       DATETIME NOT NULL,
                updated_at       DATETIME NOT NULL
            );

            INSERT INTO games_new
                (id, name, process_name, executable_path, icon_path,
                 is_enabled, first_played, last_played, created_at, updated_at)
            SELECT
                id, name, process_name, executable_path, icon_path,
                is_enabled, first_played, last_played, created_at, updated_at
            FROM games;

            DROP TABLE games;
            ALTER TABLE games_new RENAME TO games;
            PRAGMA foreign_keys=ON;
        """)
```

### 8.4 registry.py

```python
"""MigrationRegistry — auto-discovers Migration subclasses."""

from __future__ import annotations

import inspect
import logging
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import Type

from trackora.core.migration_manager import Migration

logger = logging.getLogger(__name__)

_MIGRATIONS_PACKAGE = "trackora.core.migrations"


class MigrationRegistry:
    """Discovers and orders Migration subclasses."""

    @classmethod
    def discover(cls) -> list[Type[Migration]]:
        """Scan the migrations package and return sorted Migration classes."""
        import importlib

        migrations: list[Type[Migration]] = []
        package = importlib.import_module(_MIGRATIONS_PACKAGE)
        package_path = Path(package.__file__).parent if package.__file__ else None

        if package_path is None:
            return []

        for importer, modname, is_pkg in pkgutil.iter_modules(
            [str(package_path)]
        ):
            if modname == "__init__" or modname == "registry":
                continue
            module = importlib.import_module(f"{_MIGRATIONS_PACKAGE}.{modname}")
            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    obj is not Migration
                    and issubclass(obj, Migration)
                    and not inspect.isabstract(obj)
                ):
                    migrations.append(obj)

        migrations.sort(key=lambda m: m.migration_id)
        logger.debug("Discovered %d migrations", len(migrations))
        return migrations

    @classmethod
    def get_by_id(cls, migration_id: str) -> Type[Migration] | None:
        for m in cls.discover():
            if m.migration_id == migration_id:
                return m
        return None
```

---

## 9. Data Formats

### 9.1 schema.json

**Location:** `%APPDATA%/Trackora/schema.json`

```json
{
  "schema_version": "2.0.0",
  "app_version": "2.0.0",
  "updated_at": "2026-06-20T12:00:00Z",
  "description": "Schema version after application of v2.0.0 migrations"
}
```

### 9.2 _migrations Table Row

```sql
INSERT INTO _migrations VALUES (
    'v2_0_0_add_discovery_columns',
    'Add platform, platform_id, is_auto_discovered to games table',
    '2.0.0',
    'sha256:a1b2c3d4e5f6...',
    '2026-06-20T12:00:00Z',
    1500
);
```

### 9.3 Backup MANIFEST.json

```json
{
  "backup_id": "a1b2c3d4",
  "manifest_version": 1,
  "created_at": "2026-06-20T12:00:00Z",
  "app_version": "1.1.0",
  "schema_version": "1.0.0",
  "files": {
    "trackora.db": {
      "size_bytes": 1048576,
      "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    },
    "schema.json": {
      "size_bytes": 128,
      "sha256": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    }
  }
}
```

---

## 10. Integration Map

### 10.1 __main__.py — Modified Startup

```python
# Current flow (v1.1.0):
ensure_dirs()
db = DatabaseManager(str(DATABASE_PATH))
db.initialize()
conn = db.connection
# ... repos, services, etc.

# New flow (v2.0.0):
ensure_dirs()
db = DatabaseManager(str(DATABASE_PATH))
db.initialize()  # now also creates _migrations table
conn = db.connection

# ── NEW: Upgrade Lifecycle ──────────────────────────────────────
schema_version_manager = SchemaVersionManager()
backup_manager = BackupManager()
migration_manager = MigrationManager(
    connection=conn,
    schema_version_manager=schema_version_manager,
    backup_manager=backup_manager,
)

data_version = schema_version_manager.read()
compatible, status = schema_version_manager.is_compatible(
    SchemaVersion.current_app_version(), data_version
)

if not compatible:
    # Block startup — show error dialog, exit
    _show_incompatible_schema_error(status.message)
    sys.exit(2)

if status.status == "first_run":
    # First launch — mark schema version, skip migration
    schema_version_manager.write(SchemaVersion.current_app_version())
    logger.info("First run — schema initialized at %s", SchemaVersion.current_app_version())

elif status.status == "needs_migration":
    # Backup first
    backup_result = backup_manager.create_backup()
    if not backup_result.success:
        _show_backup_failed_error(backup_result.error_message)
        sys.exit(3)

    # Apply migrations
    migration_result = migration_manager.apply_all()
    if not migration_result.success:
        logger.error("Migration failed: %s", migration_result)
        _show_migration_failed_warning(migration_result)
        # Application continues with partial migration; user warned

    # Write new schema version
    if migration_result.final_version:
        schema_version_manager.write(
            SchemaVersion.from_string(migration_result.final_version)
        )
# ── END NEW ─────────────────────────────────────────────────────

# Repository creation (unchanged)
games_repo = GamesRepository(conn)
# ...
```

### 10.2 DatabaseManager._create_schema() — Modified

```python
def _create_schema(self) -> None:
    # Existing tables (unchanged)
    cursor.execute("CREATE TABLE IF NOT EXISTS games (...)")
    cursor.execute("CREATE TABLE IF NOT EXISTS sessions (...)")
    cursor.execute("CREATE TABLE IF NOT EXISTS active_sessions (...)")
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (...)")

    # ── NEW: _migrations table ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            migration_id TEXT PRIMARY KEY,
            description  TEXT NOT NULL,
            app_version  TEXT NOT NULL,
            checksum     TEXT NOT NULL,
            applied_at   TEXT NOT NULL,
            duration_ms  INTEGER NOT NULL DEFAULT 0
        );
    """)

    # Existing indexes (unchanged)
    # ...
```

### 10.3 Architecture Enforcement — New Tests

```python
# tests/architecture/test_schema_version_isolation.py
# Only SchemaVersionManager may read/write schema.json

# tests/architecture/test_migration_isolation.py
# Only MigrationManager and Migration subclasses may apply DDL

# tests/architecture/test_backup_isolation.py
# Only BackupManager may create/restore full-database backups
```

### 10.4 Integration Test — Full Upgrade Lifecycle

```python
# tests/test_upgrade_lifecycle.py
# Tests:
# 1. v1.1.0 database → upgrade → v2.0.0 schema
# 2. Backup created → verified → migration applied → version written
# 3. Crash during migration → recoverable on next launch
# 4. First run → schema written → no migration attempted
# 5. Incompatible data → blocked with error
```

---

## 11. Testing Strategy

### 11.1 Test Pyramid

```
         ┌─────┐
         │ E2E │  Full upgrade lifecycle with real SQLite
         │  3  │  (tmp_path, sample v1.1.0 database)
         ├─────┤
         │ INT │  MigrationManager + BackupManager + SchemaVersionManager
         │  7  │  wired together; backup then migrate
         ├─────┤
         │ UNIT│  Each component in isolation (mock dependencies)
         │ 25+ │  SchemaVersionManager: read/write/compare/validate
         │     │  BackupManager: create/verify/restore/list/retention
         │     │  MigrationManager: discover/pending/apply/skip/rollback
         ├─────┤
         │ ARC │  Architecture enforcement (AST-based isolation rules)
         │  3  │  schema_version, migration, backup isolation
         └─────┘
```

### 11.2 Unit Tests

| Component | Tests | File |
|---|---|---|
| SchemaVersion | 6 | `tests/test_schema_version.py` |
| SchemaVersionManager | 10 | `tests/test_schema_version_manager.py` |
| BackupManager | 12 | `tests/test_backup_manager.py` |
| MigrationManager | 14 | `tests/test_migration_manager.py` |
| MigrationRegistry | 4 | `tests/test_migration_registry.py` |

### 11.3 Integration Tests

| Scenario | File |
|---|---|
| Full upgrade lifecycle (backup → migrate → verify → version write) | `tests/test_upgrade_lifecycle.py` |
| First run (no schema.json) | `tests/test_upgrade_lifecycle.py` |
| Crash during migration (recovery on next launch) | `tests/test_upgrade_lifecycle.py` |
| Incompatible schema (block startup) | `tests/test_upgrade_lifecycle.py` |
| Backup restore after failed migration | `tests/test_upgrade_lifecycle.py` |

### 11.4 Architecture Enforcement Tests

| Test | Rule | File |
|---|---|---|
| Schema version isolation | Only `schema_version_manager.py` may touch `schema.json` | `tests/architecture/test_schema_version_isolation.py` |
| Migration isolation | Only `Migration` subclasses may apply DDL | `tests/architecture/test_migration_isolation.py` |
| Backup isolation | Only `backup_manager.py` may create/restore ZIP backups | `tests/architecture/test_backup_isolation.py` |

### 11.5 Test Fixtures

```python
# conftest.py additions

@pytest.fixture
def schema_version_manager(tmp_path):
    """SchemaVersionManager with isolated temp directory."""
    return SchemaVersionManager(schema_path=tmp_path / "schema.json")

@pytest.fixture
def backup_manager(tmp_path, schema_version_manager):
    """BackupManager with isolated backup directory."""
    db_path = tmp_path / "trackora.db"
    # Create an empty SQLite database
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    conn.close()
    return BackupManager(
        backup_dir=tmp_path / "backups",
        source_db=db_path,
        schema_manager=schema_version_manager,
    )

@pytest.fixture
def migration_manager(backup_manager, schema_version_manager):
    """MigrationManager with in-memory database."""
    conn = sqlite3.connect(":memory:")
    return MigrationManager(
        connection=conn,
        schema_version_manager=schema_version_manager,
        backup_manager=backup_manager,
    )

@pytest.fixture
def sample_v1_database(tmp_path):
    """Create a SQLite database that mimics a real v1.1.0 user database."""
    db_path = tmp_path / "trackora.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            process_name     TEXT    NOT NULL,
            executable_path  TEXT    NOT NULL,
            icon_path        TEXT    NOT NULL DEFAULT '',
            is_enabled       INTEGER NOT NULL DEFAULT 1,
            first_played     DATETIME,
            last_played      DATETIME,
            created_at       DATETIME NOT NULL,
            updated_at       DATETIME NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id          INTEGER  NOT NULL,
            start_time       DATETIME NOT NULL,
            end_time         DATETIME NOT NULL,
            duration_seconds INTEGER  NOT NULL,
            created_at       DATETIME NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games (id)
        );
        CREATE TABLE IF NOT EXISTS active_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id    INTEGER  NOT NULL,
            process_id INTEGER  NOT NULL,
            start_time DATETIME NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games (id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT     PRIMARY KEY,
            value      TEXT     NOT NULL DEFAULT '',
            updated_at DATETIME NOT NULL
        );
        INSERT INTO games (name, process_name, executable_path, created_at, updated_at)
        VALUES ('Test Game', 'test.exe', 'C:\\test.exe',
                '2026-01-01T00:00:00', '2026-01-01T00:00:00');
        INSERT INTO settings (key, value, updated_at)
        VALUES ('theme', 'dark', '2026-01-01T00:00:00');
    """)
    conn.close()
    return db_path
```

---

## 12. Future Extensibility

### 12.1 v3.0.0 — MongoDB Parallel Migrations

```
trackora/core/migrations/
├── v3_0_0_add_mongodb_reports_collection.py     # SQLite migration (adds config)
├── v3_0_0_mongodb_reports_schema_v1.py          # MongoDB migration (creates collections)
└── v3_0_0_add_cloud_sync_settings.py            # SQLite migration (adds settings)
```

MigrationManager must be extended to support:
- `Migration.upgrade_mongodb(mongo_client, db_name)` (new abstract method)
- Backends list: managers discover migrations for each backend type
- `_migrations` table gains a `backend` column (`sqlite` | `mongodb`)

### 12.2 v4.0.0 — Multi-Backend Version Tracking

SchemaVersionManager extended:
- Support per-backend schema version in `schema.json`
- `schema_version` becomes an object keyed by backend:

```json
{
  "schema_versions": {
    "sqlite": "4.0.0",
    "mongodb": "2.0.0"
  },
  "app_version": "4.0.0",
  "updated_at": "..."
}
```

### 12.3 v4.0.0+ — Continuous Evolution

| Feature | Mechanism |
|---|---|
| New backends | Add backend key to `schema.json`; add `backend` column to `_migrations`; extend `Migration` ABC |
| New SQLite-only migrations | Continue adding to `trackora/core/migrations/` — no architecture change |
| Migration pre-conditions | Add `Migration.check_prerequisites(connection) -> list[str]` for conditional migration gating |
| Data-only migrations | Add `Migration.migrate_data(connection)` alongside `upgrade()` for data transformation in addition to schema changes |

---

## 13. Implementation Order

### Phase 1 — Core Infrastructure

| Step | Component | Depends On |
|------|-----------|------------|
| 1.1 | `SchemaVersion` dataclass | Nothing |
| 1.2 | `SchemaVersionManager` | `SchemaVersion`, `paths.py` |
| 1.3 | Add `_migrations` table to `DatabaseManager._create_schema()` | Nothing (solo DB change) |
| 1.4 | `Migration` ABC + `MigrationRegistry` | Nothing |
| 1.5 | `BackupManager` | `SchemaVersionManager`, `paths.py` |
| 1.6 | `MigrationManager` | `SchemaVersionManager`, `BackupManager`, `Migration` ABC |

### Phase 2 — Startup Integration

| Step | Component | Depends On |
|------|-----------|------------|
| 2.1 | Restructure `__main__.py` startup sequence | All Phase 1 |
| 2.2 | Incompatible schema error dialog | Phase 1 |
| 2.3 | Migration failure warning dialog | Phase 1 |

### Phase 3 — v2.0.0 Migrations

| Step | Migration | Adds |
|------|-----------|------|
| 3.1 | `base_schema.py` (v1.0.0 marker) | — |
| 3.2 | `v2_0_0_add_discovery_columns.py` | platform, platform_id, is_auto_discovered columns |
| 3.3 | `v2_0_0_add_update_center_settings.py` | Settings keys for update center |

### Phase 4 — Testing

| Step | Tests | Depends On |
|------|-------|------------|
| 4.1 | Unit tests: SchemaVersionManager | Phase 1.2 |
| 4.2 | Unit tests: BackupManager | Phase 1.5 |
| 4.3 | Unit tests: MigrationManager | Phase 1.6 |
| 4.4 | Integration tests: upgrade lifecycle | Phase 2 |
| 4.5 | Architecture enforcement tests | Phase 1 |
| 4.6 | Regression: all 824 existing tests | All |

---

## References

- `docs/architecture/upgrade-foundation-assessment.md` — Audit findings and integration point analysis
- `docs/releases/v2.0.0/milestone-8-upgrade-foundation.md` — M8 milestone requirements
- `docs/releases/v2.0.0/v2.0.0-overview.md` — Release overview, risk register, implementation order
- `database/database_manager.py` — Current database initialization (target for `_migrations` table addition)
- `trackora/__main__.py` — Current startup sequence (target for upgrade lifecycle insertion)
- `trackora/core/paths.py` — Path resolution (BACKUPS_DIR already defined)
- `trackora/core/environment.py` — Environment isolation (schema path inherits Dev/Prod separation)
