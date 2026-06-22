# Backup Foundation Architecture Specification

**Version:** 2.0.0-draft
**Status:** Architecture Design
**Document Type:** Architecture Specification
**Owner:** Architecture Team

---

## Table of Contents

1. Purpose
2. Responsibilities
3. Design Principles
4. Public API
5. Backup Lifecycle
6. Restore Lifecycle
7. Validation Lifecycle
8. Failure Recovery Lifecycle
9. Backup Format Specification
10. Manifest Specification
11. Metadata Specification
12. Integrity Verification
13. Database Copy Strategy
14. File Naming Convention
15. Retention Policy
16. Error Handling Matrix
17. Dependencies
18. Testing Strategy
19. Future MongoDB Compatibility
20. Integration Map

---

## 1. Purpose

BackupManager provides production-grade backup and recovery for Trackora user data. It is the safety net that guarantees data survival across upgrades, migrations, and disaster recovery scenarios. Every backup is a self-verifying, atomic ZIP archive that can be restored independently.

BackupManager operates at the infrastructure layer, distinct from ExportService which provides user-facing data portability. BackupManager backs up raw database files with integrity verification; ExportService exports application data in human-readable formats.

---

## 2. Responsibilities

| Responsibility | Description |
|---|---|
| Create backups | Atomic ZIP creation of `trackora.db` + `schema.json` + manifest + metadata |
| Validate backups | Verify archive integrity, manifest structure, checksums, and required file presence |
| Restore backups | Atomic restore with pre-restore safety backup and rollback on failure |
| List backups | Enumerate available backups in `BACKUPS_DIR` |
| Delete backups | Remove individual backups or clean old backups per retention policy |
| Integrity verification | SHA-256 checksums for every file in the archive |
| Error handling | Corrupt ZIP detection, missing files, invalid manifest, checksum mismatch, restore interruption |

### Non-Responsibilities

- User-facing data export (handled by `ExportService`)
- Database migration logic (handled by `MigrationManager`)
- Startup integration (handled by `StartupService`)
- Application-level data transformation

---

## 3. Design Principles

### B1 — Backup Before Mutation

Every destructive operation on user data must be preceded by a verified backup. MigrationManager must call `BackupManager.create_backup()` before any migration step.

### B2 — Atomic Operations

Backups are written atomically (`.tmp` + rename). Restores create a safety backup of the current state before proceeding. Every operation either completes fully or leaves the system in a known good state.

### B3 — Self-Verifying Archives

Every backup ZIP contains its own integrity manifest with SHA-256 checksums. No external metadata is required to verify a backup. A backup can be verified on any machine at any time.

### B4 — Crash-Only Recovery

BackupManager handles every failure mode described in the error matrix. Corrupt files are detected and reported. Interrupted restores are rolled back. The system never enters an unrecoverable state.

### B5 — Layer Isolation

BackupManager lives in `trackora/core/` and depends only on stdlib and `trackora.core` modules. It must never import from `services`, `database`, `ui`, `tracker`, or `trackora_stats`.

### B6 — No Data Loss Guarantee

Data loss is unacceptable. Every code path in BackupManager is tested with integration tests that simulate failures. The testing strategy covers corrupt ZIPs, corrupt manifests, missing files, checksum mismatches, permission errors, disk-full scenarios, and rollback correctness.

---

## 4. Public API

```python
class BackupManager:
    def __init__(
        self,
        schema_version_manager: SchemaVersionManager,
        backup_dir: Path | None = None,
    ) -> None

    def create_backup(
        self,
        backup_type: str = "manual",
    ) -> BackupResult

    def restore_backup(
        self,
        backup_id: str,
    ) -> RestoreResult

    def verify_backup(
        self,
        backup_id: str,
    ) -> VerificationResult

    def list_backups(
        self,
        sort_by: str = "created_at",
        limit: int | None = None,
    ) -> list[BackupInfo]

    def get_latest_backup(self) -> BackupInfo | None

    def delete_backup(self, backup_id: str) -> bool

    def clean_old_backups(
        self,
        keep_last: int = 5,
    ) -> int
```

### Data Classes

```python
@dataclass(frozen=True)
class BackupResult:
    success: bool
    backup_id: str
    backup_path: Path
    size_bytes: int
    file_count: int
    created_at: datetime
    error: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    backup_id: str
    safety_backup_id: str | None
    error: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    backup_id: str
    checksum_errors: list[str]
    missing_files: list[str]
    error: str | None = None


@dataclass(frozen=True)
class BackupInfo:
    backup_id: str
    backup_path: Path
    size_bytes: int
    created_at: datetime
    schema_version: str
    trackora_version: str
    backup_type: str
    file_count: int
```

---

## 5. Backup Lifecycle

```
create_backup(backup_type="manual")
    │
    ├── 1. Resolve paths
    │     - BACKUPS_DIR from paths.py (or injected backup_dir)
    │     - DATABASE_PATH from paths.py
    │     - SCHEMA_PATH from schema_version_manager._schema_path
    │
    ├── 2. Checkpoint the database
    │     - Obtain db.lock (if provided via injection)
    │     - Execute PRAGMA wal_checkpoint(TRUNCATE)
    │     - Execute PRAGMA schema_version
    │     - (Future: sqlite3.Connection.backup() for live copy)
    │
    ├── 3. Generate backup_id
    │     - Format: backup_<YYYYMMDD_HHMMSS>_<UUID4 first 8 chars>
    │
    ├── 4. Build metadata
    │     - Read schema_version from SchemaVersionManager
    │     - Read trackora_version from trackora.__version__
    │     - Collect platform, environment, backup_reason
    │
    ├── 5. Stage files
    │     - Copy trackora.db to staging area
    │     - Copy schema.json to staging area
    │     - Write MANIFEST.json (see section 10)
    │     - Write metadata.json (see section 11)
    │
    ├── 6. Create ZIP archive atomically
    │     - Build ZIP in memory or at .tmp path
    │     - Add: MANIFEST.json, trackora.db, schema.json, metadata.json
    │     - Each file compressed with ZIP_DEFLATED
    │     - MANIFEST.json stored uncompressed (for fast verification)
    │
    ├── 7. Verify the backup
    │     - Read back the ZIP
    │     - Verify all files present
    │     - Verify checksums match
    │     - Verify manifest parses correctly
    │
    ├── 8. Finalize
    │     - Rename .tmp to final name (atomic)
    │     - Log success with path, size, file count
    │     - Return BackupResult
```

### Atomicity

The backup ZIP is first written to `<backup_id>.zip.tmp` in `BACKUPS_DIR`. Only after successful verification is it renamed to `<backup_id>.zip` via `os.replace`. If the process crashes during steps 5-7, only the `.tmp` file remains — it is cleaned on next `__init__()`.

---

## 6. Restore Lifecycle

```
restore_backup(backup_id)
    │
    ├── 1. Verify the backup first
    │     - If verification fails: return RestoreResult(success=False, error=...)
    │
    ├── 2. Create safety backup of current state
    │     - Call create_backup(backup_type="pre_restore")
    │     - If safety backup fails: abort, return error
    │
    ├── 3. Extract to staging directory
    │     - Create random staging dir under BACKUPS_DIR / .restore_<uuid>
    │     - Extract ZIP contents to staging
    │
    ├── 4. Validate extracted files
    │     - Verify checksums of extracted files
    │     - Validate schema.json via SchemaVersionManager
    │     - Verify trackora.db is a valid SQLite database
    │
    ├── 5. Atomic replace of production files
    │     - os.replace staging/trackora.db → DATABASE_PATH
    │     - os.replace staging/schema.json → SCHEMA_PATH
    │     - (Future: os.replace staging/other files → corresponding paths)
    │
    ├── 6. Clean up staging
    │     - Remove staging directory
    │     - Remove .tmp file if it exists
    │
    ├── 7. Return RestoreResult
    │     - On failure at any step: rollback
```

### Rollback on Restore Failure

If any step in the restore lifecycle fails after the safety backup is created:

1. Log the failure with full details
2. Copy production files back from safety backup ZIP
3. Mark the safety backup as "post_restore" so it is not auto-deleted
4. Return RestoreResult with error description

---

## 7. Validation Lifecycle

```
verify_backup(backup_id)
    │
    ├── 1. Locate backup ZIP
    │     - Resolve backup_id to Path in BACKUPS_DIR
    │     - If not found: return VerificationResult(valid=False, error="not found")
    │
    ├── 2. Verify ZIP integrity
    │     - Open ZIP with ZipFile
    │     - Call zipfile.testzip() to verify CRC
    │     - If corrupt: return verification result
    │
    ├── 3. Extract MANIFEST.json to memory
    │     - Parse JSON
    │     - Validate required fields (see section 10)
    │     - If invalid: return verification result
    │
    ├── 4. Verify all required files present in ZIP
    │     - Required: MANIFEST.json, trackora.db, schema.json, metadata.json
    │     - Record any missing files
    │
    ├── 5. Verify checksums
    │     - For each file listed in MANIFEST.file_checksums:
    │       - Read file from ZIP
    │       - Compute SHA-256
    │       - Compare with stored checksum
    │     - Record any mismatches
    │
    ├── 6. Return VerificationResult
    │     - valid = True iff no errors, no missing files, no checksum mismatches
```

---

## 8. Failure Recovery Lifecycle

### 8.1 Corrupt Backup Detection

Detected during `verify_backup()` or during extraction for restore. On detection:
1. Log warning with backup_id and error details
2. Rename corrupt ZIP to `<backup_id>.corrupt.<timestamp>.zip` (forensic preservation)
3. Return error to caller

### 8.2 Missing Files in Backup

Detected during `verify_backup()`. On detection:
1. Record missing file paths in `missing_files` list
2. Return `VerificationResult(valid=False, missing_files=[...])`
3. No automatic deletion — caller decides

### 8.3 Invalid Manifest

Detected during `verify_backup()` or `restore_backup()`. Automatically treated as corrupt backup. Same flow as corrupt ZIP.

### 8.4 Checksum Mismatch

Detected during `verify_backup()`. On detection:
1. Record mismatched file paths in `checksum_errors` list
2. Return `VerificationResult(valid=False, checksum_errors=[...])`
3. Backup is not deleted — allows forensic analysis

### 8.5 Restore Interruption

If the process crashes during `restore_backup()`:
1. On next startup, `BackupManager.__init__()` checks for orphan `.restore_*` staging dirs
2. If found: log warning, remove staging dir
3. Production files are safe because replace is the last atomic step
4. The pre-restore safety backup is still available in BACKUPS_DIR

### 8.6 Orphan .tmp File Cleanup

Handled during `__init__()`:
1. Scan `BACKUPS_DIR` for `*.zip.tmp` files
2. If found: log warning, remove each
3. Same pattern as `SchemaVersionManager._clean_orphan_tmp()`

---

## 9. Backup Format Specification

### 9.1 File Structure

```
backup_20260620_120000_a1b2c3d4.zip
├── MANIFEST.json          (uncompressed — fast header read)
├── trackora.db            (deflated — large, compressible)
├── schema.json            (deflated — small)
└── metadata.json          (deflated — small)
```

### 9.2 Compression Strategy

| File | Compression | Rationale |
|---|---|---|
| `MANIFEST.json` | `ZIP_STORED` (uncompressed) | Must be readable without decompression for fast verification |
| `trackora.db` | `ZIP_DEFLATED` | SQLite databases compress well (often 5:1 with text content) |
| `schema.json` | `ZIP_DEFLATED` | Small file, negligible cost |
| `metadata.json` | `ZIP_DEFLATED` | Small file, negligible cost |

### 9.3 Encoding

All JSON files within the ZIP use `utf-8` encoding, `indent=2`, `ensure_ascii=False`.

---

## 10. Manifest Specification

### 10.1 File: `MANIFEST.json`

```json
{
    "manifest_version": "1.0",
    "backup_version": 1,
    "created_at": "2026-06-20T12:00:00.000000Z",
    "schema_version": "2.0.0",
    "trackora_version": "2.0.0",
    "backup_type": "manual",
    "backup_id": "backup_20260620_120000_a1b2c3d4",
    "file_count": 4,
    "files": [
        {
            "path": "MANIFEST.json",
            "size": 512,
            "sha256": "abc123..."
        },
        {
            "path": "trackora.db",
            "size": 262144,
            "sha256": "def456..."
        },
        {
            "path": "schema.json",
            "size": 128,
            "sha256": "ghi789..."
        },
        {
            "path": "metadata.json",
            "size": 256,
            "sha256": "jkl012..."
        }
    ]
}
```

### 10.2 Required Fields

| Field | Type | Description |
|---|---|---|
| `manifest_version` | string | Version of the manifest schema (currently `"1.0"`) |
| `backup_version` | integer | Monotonic backup format version (currently `1`) |
| `created_at` | string | ISO-8601 UTC with microsecond precision |
| `schema_version` | string | Schema version at time of backup (from `schema.json`) |
| `trackora_version` | string | Application version at time of backup (from `trackora.__version__`) |
| `backup_type` | string | `"manual"`, `"pre_migration"`, `"pre_restore"`, `"scheduled"` |
| `backup_id` | string | Unique backup identifier |
| `file_count` | integer | Number of files in the archive |
| `files` | array | Array of file entries (see below) |

### 10.3 File Entry Fields

| Field | Type | Description |
|---|---|---|
| `path` | string | Relative path within the ZIP archive |
| `size` | integer | Uncompressed file size in bytes |
| `sha256` | string | Lowercase hex SHA-256 hash of the uncompressed file content |

### 10.4 Validation Rules

- `manifest_version` must be a non-empty string
- `backup_version` must be a positive integer
- `created_at` must match ISO-8601 regex
- `schema_version` must match `SchemaVersion.is_valid_format()`
- `trackora_version` must be a non-empty string
- `file_count` must match the actual number of files in the archive
- `files` array must contain exactly `file_count` entries
- Every file entry must have `path`, `size`, and `sha256`
- No duplicate paths in `files`
- The manifest itself (`MANIFEST.json`) must be listed first in the `files` array
- The manifest's own checksum is computed and verified last (circular — verified by reading back from the completed ZIP)

---

## 11. Metadata Specification

### 11.1 File: `metadata.json`

```json
{
    "environment": "production",
    "platform": "linux",
    "python_version": "3.13.2",
    "application_version": "2.0.0",
    "backup_reason": "manual",
    "notes": ""
}
```

### 11.2 Required Fields

| Field | Type | Description |
|---|---|---|
| `environment` | string | `"production"` or `"development"` (from `trackora.core.environment`) |
| `platform` | string | `sys.platform` value |
| `python_version` | string | `sys.version` (first component) |
| `application_version` | string | From `trackora.__version__` |
| `backup_reason` | string | Same as `backup_type` in manifest |
| `notes` | string | Optional human-readable notes |

### 11.3 Purpose

`metadata.json` exists for human readability and forensic analysis. It is NOT used for integrity verification — that is the role of `MANIFEST.json`. It is included in the checksum manifest so any tampering is detected.

---

## 12. Integrity Verification

### 12.1 Verification Levels

| Level | What Is Checked | Method |
|---|---|---|
| Zipfile CRC | File-level CRC-32 embedded in ZIP | `zipfile.ZipFile.testzip()` |
| SHA-256 checksum | Each file's content hash | `hashlib.sha256()` over raw bytes |
| Manifest validation | JSON parse + field validation | `json.loads()` + field type checks |
| Required files | Presence of mandatory files | Check `files` array in manifest |
| Archive completeness | `file_count` matches actual count | `len(zipfile.namelist())` |

### 12.2 SHA-256 Computation

1. Read file content from the ZIP archive as raw bytes (uncompressed)
2. Compute `hashlib.sha256(data).hexdigest()` — lowercase hex
3. Compare with the stored `sha256` value in MANIFEST
4. Must match exactly

### 12.3 Self-Verification Sequence

1. Open ZIP, verify ZIP CRC via `testzip()`
2. Extract and parse `MANIFEST.json`
3. Validate manifest structure and fields
4. Compute `expected_file_count` from `zipfile.namelist()` — compare with `file_count`
5. For each entry in `files`: read file, compute SHA-256, compare
6. Return result with all checksum mismatches and missing files

---

## 13. Database Copy Strategy

### 13.1 Primary Approach: Online Backup via sqlite3

The recommended approach for copying the database during backup:

```python
import sqlite3

def _copy_database(source_path: Path, dest_path: Path) -> None:
    """Copy a live SQLite database using the backup API.

    This is safe for databases with active writers when used
    with WAL mode and a checkpoint.
    """
    with sqlite3.connect(str(source_path)) as src:
        src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        src.execute("PRAGMA schema_version")
        with sqlite3.connect(str(dest_path)) as dest:
            src.backup(dest, pages=-1)  # Copy all pages
```

This approach:
- Does not require a lock on the production database
- Works while the database is in use (WAL mode allows concurrent reads)
- Produces a consistent snapshot
- Is the official sqlite3 online backup API

### 13.2 Fallback: VACUUM INTO

If the backup API is unavailable or the database is small:

```python
def _copy_database_vacuum(source_path: Path, dest_path: Path) -> None:
    """Copy database using VACUUM INTO (SQLite 3.27+)."""
    with sqlite3.connect(str(source_path)) as src:
        src.execute(f"VACUUM INTO '{dest_path}'")
```

### 13.3 WAL Mode Handling

Before backup:
1. Execute `PRAGMA wal_checkpoint(TRUNCATE)` to flush WAL into the main database
2. This ensures all data is in `trackora.db`, not in `trackora.db-wal` or `trackora.db-shm`

---

## 14. File Naming Convention

### 14.1 Backup Files

```
backup_<YYYYMMDD>_<HHMMSS>_<UUID4 first 8 chars>.zip
```

Example: `backup_20260620_120000_a1b2c3d4.zip`

### 14.2 Temporary Files

```
backup_<YYYYMMDD>_<HHMMSS>_<UUID4 first 8 chars>.zip.tmp
```

### 14.3 Corrupt Backup Files

```
backup_<YYYYMMDD>_<HHMMSS>_<UUID4 first 8 chars>.corrupt.<YYYYMMDD_HHMMSS>.zip
```

### 14.4 Staging Directories

```
.restore_<UUID>
```

Hidden directories under `BACKUPS_DIR` during restore operations.

---

## 15. Retention Policy

### 15.1 Default Policy

Keep the last 5 backups by creation time. This is the default for `clean_old_backups()`.

### 15.2 Exclusions

Backups with `backup_type="pre_restore"` are excluded from automatic cleanup. Safety backups created before a restore are explicitly preserved.

### 15.3 Manual Deletion

Users and callers can always call `delete_backup(backup_id)` to remove specific backups.

---

## 16. Error Handling Matrix

| Condition | Detection | Action | User Impact |
|---|---|---|---|
| Source DB does not exist | `create_backup()` checks `DATABASE_PATH.is_file()` | Return `BackupResult(success=False, error="...")` | Cannot create backup until database exists |
| Source schema.json does not exist | `SchemaVersionManager.read()` returns None | Create backup without schema.json (first-run state), log warning | Backup created, no schema version recorded |
| Disk full during backup | `OSError` during ZIP write | Remove `.tmp`, return error | No backup created |
| Permission denied on BACKUPS_DIR | `OSError` during directory creation | Return error | Cannot create backup |
| Corrupt ZIP on verify | `zipfile.BadZipFile` | Rename to `.corrupt.` suffix, return verification result | Backup marked as corrupt |
| Checksum mismatch | SHA-256 comparison | Return mismatched files in result | Backup cannot be restored |
| Missing manifest | File not in ZIP | Return error | Cannot verify or restore |
| Invalid manifest JSON | `json.JSONDecodeError` | Treat as corrupt, rename | Backup marked as corrupt |
| Restore source not found | `verify_backup()` fails | Abort restore, return error | No restore performed |
| Safety backup fails | `create_backup()` fails | Abort restore | No restore performed |
| atomic replace fails (restore) | `os.replace` OSError | Rollback production files from safety backup | Data remains in original state |
| WAL checkpoint fails | `PRAGMA` error | Log warning, continue with current WAL state | Potential for incomplete backup if WAL not flushed |
| Concurrent backup | Race condition in backup dir | Unique `backup_id` prevents collision | Both backups coexist |

---

## 17. Dependencies

### 17.1 Runtime Dependencies

| Module | Usage |
|---|---|
| `zipfile` | ZIP archive creation and extraction |
| `hashlib` | SHA-256 checksum computation |
| `json` | MANIFEST.json and metadata.json serialization |
| `os` | `os.replace()` for atomic file operations |
| `shutil` | `shutil.rmtree()` for staging directory cleanup |
| `uuid` | `uuid.uuid4()` for unique backup IDs |
| `sqlite3` | `sqlite3.connect()` for online database backup |
| `pathlib` | Cross-platform path handling |
| `logging` | Structured logging for all operations |
| `datetime` | Timestamp generation |
| `sys` | Platform detection for metadata |
| `trackora.core.paths` | `BACKUPS_DIR`, `DATABASE_PATH`, `BASE_DIR` |
| `trackora.core.schema_version` | `SchemaVersion`, `SchemaVersionError` |
| `trackora.core.schema_version_manager` | `SchemaVersionManager` for reading schema version |

### 17.2 Test Dependencies

| Module | Usage |
|---|---|
| `pytest` | Test framework |
| `pytest.fixture` | Test fixtures (tmp_path, monkeypatch) |
| `zipfile` | Test ZIP creation/corruption |
| `hashlib` | Test checksum generation |
| `sqlite3` | In-memory database for test fixtures |
| `json` | Test manifest generation |

### 17.3 Forbidden Dependencies

BackupManager must NOT import from:
- `database` (including `database_manager`, `models`, `repositories`)
- `services` (including `export_service`, `crash_service`, `tray_service`)
- `ui` (any module)
- `tracker` (any module)
- `trackora_stats` (any module)

---

## 18. Testing Strategy

### 18.1 Unit Tests

| Category | Test Count | Scope |
|---|---|---|
| `__init__` | 4 | Default path, custom path, orphan .tmp cleanup, path type |
| `create_backup` | 12 | File created, ZIP structure, manifest content, checksums, compression, empty backup dir, existing backups, Unicode paths, long paths, backup ID format, atomicity, cleanup |
| `verify_backup` | 12 | Valid backup, missing MANIFEST, invalid JSON, missing files, checksum mismatch, corrupt ZIP, empty ZIP, wrong file_count, duplicate paths in manifest |
| `restore_backup` | 10 | Success, verifies before restore, creates safety backup, replaces files, fails on corrupt backup, fails on missing backup, rollback on replace failure, staging cleanup, WAL handling |
| `list_backups` | 6 | Empty dir, mixed files, sorted by date, limited count, backup_id filtering, ignores non-backup files |
| `delete_backup` | 4 | Existing, missing, failure logged, does not delete other files |
| `clean_old_backups` | 5 | Default keep=5, keeps pre_restore, removes oldest, empty dir, no-op |
| `database_copy` | 3 | Online backup via sqlite3, WAL checkpoint, VACUUM INTO |
| `BackupResult` / `RestoreResult` | 2 | Dataclass frozen, field access |

### 18.2 Integration Tests

| Test | Scenario |
|---|---|
| `test_backup_restore_roundtrip` | Create backup of real database → restore → verify data fidelity |
| `test_backup_then_verify` | Create backup → verify passes |
| `test_corrupt_backup_detection` | Corrupt ZIP bytes → verify fails |
| `test_restore_failure_rollback` | Mock replace failure → verify safety backup restored |
| `test_wal_checkpoint_before_backup` | Database with uncheckpointed WAL → backup succeeds |
| `test_concurrent_backup_safety` | Create multiple backups concurrently → no data loss |

### 18.3 Architecture Tests

| Test | Rule |
|---|---|
| `test_backup_manager_import_restrictions` | Only stdlib + trackora.core allowed |
| `test_no_backup_outside_backup_manager` | No other source file references backup ZIP operations |

---

## 19. Future MongoDB Compatibility

### 19.1 Design Considerations

BackupManager is designed to support future MongoDB backups without architectural changes:

| Current (SQLite) | Future (MongoDB) | Design Accommodation |
|---|---|---|
| `sqlite3.Connection.backup()` | `mongodump` / driver dump | Database copy is an injected strategy |
| `trackora.db` file path | MongoDB connection string | Source path is abstracted via `_get_source_paths()` |
| Single-file database | Multi-document database | ZIP archive can hold multiple files |
| `PRAGMA wal_checkpoint` | `db.fsyncLock()` / `db.fsyncUnlock()` | Pre-backup preparation is a hook |
| `DATABASE_PATH` constant | `MONGODB_URI` constant | Path resolution is centralized in `paths.py` |

### 19.2 Extensibility Points

- **Database copy strategy**: The `_copy_database()` method is a single replacement point for MongoDB backup
- **File list in manifest**: The `files` array in MANIFEST.json is extensible — MongoDB can add `collections/` entries
- **Source path resolution**: `_get_source_paths()` returns a `list[Path]` that can be extended for additional sources
- **Pre-backup hook**: `_prepare_for_backup()` executes before file collection — can be extended for MongoDB locking

---

## 20. Integration Map

```
BackupManager
  │
  ├── trackora.core.paths
  │     ├── BACKUPS_DIR        → backup storage location
  │     ├── DATABASE_PATH       → source database file
  │     └── BASE_DIR           → schema.json location
  │
  ├── trackora.core.schema_version.SchemaVersion
  │     └── from_string()       → parse schema version for manifest
  │
  ├── trackora.core.schema_version_manager.SchemaVersionManager
  │     └── read()             → get current schema version
  │
  ├── trackora.__version__
  │     └── (imported directly) → application version for manifest
  │
  ├── stdlib: zipfile, hashlib, json, os, shutil, uuid, sqlite3
  │
  └── [future] MigrationManager
        └── calls create_backup() before each migration step
```
