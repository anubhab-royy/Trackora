# Milestone 8 — Upgrade Foundation

**Version:** 2.0.0-draft  
**Status:** Planning / Phase 0  
**Document Type:** Milestone Specification  
**Owner:** Architecture Team  

---

## Purpose

Establish an upgrade-safe architecture that guarantees user data survives every future Trackora upgrade. Introduce versioned schema management, safe and idempotent migration execution, and reliable backup/restore capabilities.

---

## Principle

> **User data must outlive the application that created it.**

Application files live in `Program Files/Trackora` and may be replaced on every upgrade. User data lives in `%APPDATA%/Trackora` and must never be deleted, overwritten, or corrupted by an upgrade.

---

## Scope

### In Scope

- `SchemaVersionManager` — read, write, validate schema version metadata
- `MigrationManager` — apply, track, rollback, and verify schema migrations
- `BackupManager` — create, restore, verify, and list backups
- Migration path: v1.1.x → v1.2.0 (interim schema evolution, if needed) → v2.0.0
- Architecture enforcement tests (isolation rules)
- Unit and integration tests for all three managers
- Path extensions in `trackora/core/paths.py` for backup storage

### Out of Scope

- MongoDB schema migrations (deferred to M9)
- Cloud backup destinations
- Migration of data between different database backends
- Automatic rollback on application downgrade

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | The system shall maintain a schema version identifier in a well-known location within `%APPDATA%/Trackora` | Critical |
| FR-02 | The system shall reject startup if the user data schema is newer than the application supports | Critical |
| FR-03 | The system shall apply pending migrations automatically at startup | Critical |
| FR-04 | Each migration shall be idempotent — applying it multiple times produces the same result | Critical |
| FR-05 | Each migration shall execute within a single atomic transaction | Critical |
| FR-06 | The system shall create a full backup of user data before applying any migration | Critical |
| FR-07 | The system shall verify backup integrity via checksum | High |
| FR-08 | The system shall support listing available backups | Medium |
| FR-09 | The system shall support restoring user data from a backup | High |
| FR-10 | The system shall record which migrations have been applied in a dedicated tracking table | Critical |
| FR-11 | The migration tracking mechanism must survive application reinstall (stored in APPDATA, not Program Files) | Critical |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Backup creation shall complete within 5 seconds for typical user data | <5s |
| NFR-02 | Migration application shall complete within 2 seconds per migration | <2s |
| NFR-03 | Schema version check shall add no more than 100ms to startup time | <100ms |
| NFR-04 | All upgrade operations shall be recoverable — no irreversible destructive operations | Strict |
| NFR-05 | BackupManager must not depend on MigrationManager; SchemaVersionManager must not depend on BackupManager | Strict |

---

## Architecture

### Component Diagram

```
SchemaVersionManager          MigrationManager          BackupManager
     │                             │                        │
     │  read/write schema.json     │  apply/rollback        │  create/restore
     ▼                             ▼                        ▼
%APPDATA%/Trackora/          SQLite DB                 %APPDATA%/Trackora/
    schema.json              _migrations table             backups/
```

### Dependency Rules

```
SchemaVersionManager → (standalone, no dependencies)
BackupManager → uses paths.py, SchemaVersionManager  
MigrationManager → uses SchemaVersionManager, BackupManager
Application → uses MigrationManager (which composes the others)
```

### SchemaVersionManager

**File:** `trackora/core/schema_version_manager.py`

```
SchemaVersionManager:
  - SCHEMA_VERSION_PATH: %APPDATA%/Trackora/schema.json
  - read() -> SchemaVersion | None
  - write(version: SchemaVersion) -> None
  - validate(version: SchemaVersion) -> bool
  - is_compatible(app_version: SchemaVersion, data_version: SchemaVersion) -> bool
  - compare(a: SchemaVersion, b: SchemaVersion) -> int
```

**Schema:** `schema.json`

```json
{
  "schema_version": "2.0.0",
  "app_version": "2.0.0",
  "updated_at": "2026-06-20T12:00:00Z",
  "description": "Initial v2.0.0 schema with upgrade foundation"
}
```

### MigrationManager

**File:** `trackora/core/migration_manager.py`

```
MigrationManager:
  - __init__(db_manager, schema_version_manager, backup_manager)
  - get_pending_migrations() -> list[Migration]
  - apply_all() -> MigrationResult
  - apply_one(migration_id: str) -> MigrationResult
  - get_applied_migrations() -> list[AppliedMigration]
  - has_migration_been_applied(migration_id: str) -> bool
```

**Migration interface:**

```python
class Migration(ABC):
    @property
    @abstractmethod
    def migration_id(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def upgrade(self, connection: sqlite3.Connection) -> None: ...

    @abstractmethod
    def downgrade(self, connection: sqlite3.Connection) -> None: ...
```

**Tracking table:** `_migrations`

```sql
CREATE TABLE IF NOT EXISTS _migrations (
    migration_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);
```

### BackupManager

**File:** `trackora/core/backup_manager.py`

```
BackupManager:
  - BACKUP_DIR: %APPDATA%/Trackora/backups/
  - create_backup() -> BackupResult
  - restore_backup(backup_id: str) -> RestoreResult
  - verify_backup(backup_id: str) -> bool
  - list_backups() -> list[BackupInfo]
  - delete_backup(backup_id: str) -> None
```

**Backup format:** ZIP archive containing:

- `trackora.db` (SQLite database file)
- `schema.json` (schema version metadata)
- `MANIFEST.json` (backup metadata + SHA-256 checksums)

---

## Deliverables

| ID | Deliverable | File |
|----|-------------|------|
| D01 | SchemaVersionManager | `trackora/core/schema_version_manager.py` |
| D02 | MigrationManager | `trackora/core/migration_manager.py` |
| D03 | BackupManager | `trackora/core/backup_manager.py` |
| D04 | Migration classes | `trackora/core/migrations/` directory |
| D05 | Path extensions | Update `trackora/core/paths.py` with backup paths |
| D06 | Schema version model | `trackora/core/schema_version.py` |
| D07 | Unit tests | `tests/test_schema_version_manager.py` |
| D08 | Unit tests | `tests/test_migration_manager.py` |
| D09 | Unit tests | `tests/test_backup_manager.py` |
| D10 | Architecture tests | `tests/architecture/test_schema_version_isolation.py` |
| D11 | Architecture tests | `tests/architecture/test_migration_isolation.py` |
| D12 | Architecture tests | `tests/architecture/test_backup_isolation.py` |
| D13 | Integration tests | `tests/test_upgrade_lifecycle.py` |

---

## Risks

See also AR-01, AR-07, AR-08, MR-01 through MR-06 in `v2.0.0-overview.md`.

| Risk | Impact | Mitigation |
|------|--------|------------|
| Migration runs on corrupted database | Data loss | BackupManager takes backup before any migration; backup verified by checksum |
| Migration fails mid-transaction | Inconsistent state | Each migration is a single atomic SQLite transaction; rollback on error |
| User modifies APPDATA manually | Invalid schema version | SchemaVersionManager validates format on read; rejects invalid values |
| Multiple app instances trigger simultaneous migration | Race condition | Single-instance enforcement already exists (`single_instance.py`); migration runs at startup before any other operation |
| Backup disk full | Migration blocked | BackupManager checks available space before backup; logs warning; migration proceeds without backup (degraded mode) |

---

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-01 | SchemaVersionManager can read, write, and validate schema version JSON | Pytest |
| AC-02 | SchemaVersionManager correctly rejects incompatible schema versions | Pytest |
| AC-03 | MigrationManager identifies pending migrations correctly | Pytest |
| AC-04 | MigrationManager applies migrations atomically | Pytest + SQLite journal inspection |
| AC-05 | MigrationManager detects and skips already-applied migrations (idempotent) | Pytest |
| AC-06 | MigrationManager rolls back on migration failure | Pytest |
| AC-07 | BackupManager creates a valid ZIP backup with checksum | Pytest + manual extraction |
| AC-08 | BackupManager restores data from backup correctly | Pytest + data verification |
| AC-09 | Full upgrade lifecycle (backup → migrate → verify) completes successfully | Integration test |
| AC-10 | All 824 existing tests pass after M8 implementation | pytest |
| AC-11 | Architecture enforcement tests pass (isolation rules) | pytest |
| AC-12 | Startup time penalty from schema version check < 100ms | Benchmark test |

---

## Dependencies

### Internal Dependencies

| Dependency | Notes |
|------------|-------|
| `trackora/core/paths.py` | Must extend with backup directory path |
| `trackora/core/environment.py` | Schema version path must respect environment isolation |
| `database/database_manager.py` | MigrationManager wraps DatabaseManager for schema changes |
| `tests/architecture/` | New isolation tests added; existing tests must pass |

### No External Dependencies

All upgrade foundation code uses only Python standard library. No new third-party packages are required.

---

## Integration Points

| Point | Details |
|-------|---------|
| `trackora/__main__.py` | Application startup flow: check schema version → backup → apply migrations → initialize → normal startup |
| `trackora/core/paths.py` | Extend `ensure_dirs()` to create backup directory; add `BACKUPS_DIR` if not already present |
| `database/database_manager.py` | Add `_migrations` table to schema creation; provide transaction helper for migrations |

---

## Future Compatibility

### v2.1+

- MigrationManager may support parallel SQLite and MongoDB migrations
- BackupManager may add cloud backup targets (S3, B2)

### v3.0+

- MigrationManager must support multi-step chaining through multiple app versions
- SchemaVersionManager must support multiple database backends

### v4.0+

- SchemaVersionManager may support per-collection schema versions for MongoDB
- BackupManager may support incremental and differential backups

---

## References

- `v2.0.0-overview.md` — Release overview, risk register, testing requirements
- `docs/architecture/upgrade-foundation.md` — Architecture deep-dive for upgrade foundation
- `docs/architecture/runtime-environments.md` — Path and environment architecture
- `docs/database_schema.md` — SQLite schema design (v1.x baseline)
