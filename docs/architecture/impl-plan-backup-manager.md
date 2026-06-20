# BackupManager Implementation Plan

**Version:** 2.0.0-draft
**Status:** Implementation Plan
**Document Type:** Technical Design
**Owner:** Architecture Team

---

## Table of Contents

1. File Structure
2. Components
3. Public Methods
4. Internal Methods
5. Data Classes
6. Dependencies
7. Error Handling
8. Acceptance Criteria
9. Testing Strategy
10. Implementation Order

---

## 1. File Structure

### 1.1 Source Files

```
trackora/core/
├── __init__.py                  (existing)
├── paths.py                     (existing — BACKUPS_DIR, DATABASE_PATH already defined)
├── schema_version.py            (existing — SchemaVersion, SchemaVersionError, CompatibilityStatus)
├── schema_version_manager.py    (existing — SchemaVersionManager)
└── backup_manager.py            (NEW — BackupManager class)
```

### 1.2 Test Files

```
tests/
├── test_backup_manager.py        (NEW — ~65 tests)
├── test_upgrade_lifecycle.py     (MODIFIED — add backup integration tests)
└── architecture/
    └── test_backup_isolation.py  (NEW — architecture enforcement)
```

### 1.3 Documentation Files (already created in Phase 2)

```
docs/architecture/backup-foundation-spec.md
```

---

## 2. Components

### 2.1 BackupManager Class

Single class in `trackora/core/backup_manager.py`. No subclasses, no mixins. The entire backup subsystem is encapsulated in one class for simplicity and testability.

```python
class BackupManager:
    def __init__(
        self,
        schema_version_manager: SchemaVersionManager,
        backup_dir: Path | None = None,
    ) -> None

    def create_backup(self, backup_type: str = "manual") -> BackupResult
    def restore_backup(self, backup_id: str) -> RestoreResult
    def verify_backup(self, backup_id: str) -> VerificationResult
    def list_backups(self, sort_by: str = "created_at", limit: int | None = None) -> list[BackupInfo]
    def get_latest_backup(self) -> BackupInfo | None
    def delete_backup(self, backup_id: str) -> bool
    def clean_old_backups(self, keep_last: int = 5) -> int
```

### 2.2 Data Classes (in `backup_manager.py`)

- `BackupResult` — frozen dataclass
- `RestoreResult` — frozen dataclass
- `VerificationResult` — frozen dataclass
- `BackupInfo` — frozen dataclass

### 2.3 Internal Components

- `backup_id` format: `backup_<YYYYMMDD>_<HHMMSS>_<uuid4_short>`
- Staging directory for restore: `.restore_<uuid>` under `BACKUPS_DIR`
- Temporary files: `<backup_id>.zip.tmp`
- Corrupt files: `<backup_id>.corrupt.<timestamp>.zip`

### 2.4 Helper Functions

- `_generate_backup_id()` — static method
- `_build_manifest()` — internal
- `_build_metadata()` — internal
- `_copy_database()` — internal (sqlite3 online backup)
- `_compute_sha256(data: bytes) -> str` — static method
- `_clean_orphan_tmp()` — internal
- `_resolve_backup_path(backup_id) -> Path` — internal
- `_get_source_paths() -> dict[str, Path]` — internal

---

## 3. Public Methods

### 3.1 `__init__(schema_version_manager, backup_dir=None)`

**Purpose:** Initialize the BackupManager with dependencies.

**Parameters:**
- `schema_version_manager`: An initialized `SchemaVersionManager` instance. Required for reading schema version for manifest metadata.
- `backup_dir`: Optional explicit path to the backup directory. Defaults to `BACKUPS_DIR` from `trackora.core.paths`.

**Behavior:**
- Store reference to `schema_version_manager`
- Resolve `backup_dir` (default: `BACKUPS_DIR` from paths.py)
- Call `_clean_orphan_tmp()` to clean any leftover `.tmp` files
- Call `_clean_orphan_restore_dirs()` to clean leftover staging directories

**Raises:**
- None (failures in cleanup are logged, not propagated)

### 3.2 `create_backup(backup_type="manual")`

**Purpose:** Create a new backup ZIP archive.

**Parameters:**
- `backup_type`: The reason for the backup. One of `"manual"`, `"pre_migration"`, `"pre_restore"`, `"scheduled"`.

**Returns:** `BackupResult`

**Steps:**
1. Generate `backup_id` from current timestamp + UUID
2. Build `MANIFEST.json` content (without checksums initially)
3. Build `metadata.json` content
4. Checkpoint WAL on source database
5. Create temporary staging directory or use in-memory staging
6. Copy `trackora.db` to staging
7. Copy `schema.json` to staging
8. Stage `MANIFEST.json` and `metadata.json`
9. Compute SHA-256 checksums for all staged files
10. Write final `MANIFEST.json` with checksums
11. Create ZIP archive at `.tmp` path
12. Add all files to ZIP with correct compression
13. Verify the ZIP archive
14. Rename `.tmp` to final name via `os.replace`
15. Return `BackupResult`

**Error Handling:**
- If database does not exist → return error result
- If schema.json does not exist → log warning, continue (first-run state)
- If disk full → remove `.tmp`, return error result
- If rename fails → return error result

### 3.3 `restore_backup(backup_id)`

**Purpose:** Restore user data from a backup ZIP.

**Parameters:**
- `backup_id`: The backup identifier (format: `backup_<YYYYMMDD>_<HHMMSS>_<uuid>`)

**Returns:** `RestoreResult`

**Steps:**
1. Verify the backup first — if verification fails, return error
2. Create safety backup (`backup_type="pre_restore"`)
3. Create staging directory: `.restore_<uuid>` under `BACKUPS_DIR`
4. Extract ZIP contents to staging
5. Re-verify extracted file checksums
6. Validate extracted `schema.json` via `SchemaVersionManager`
7. Atomic replace production files: `os.replace(staging/x → production/x)`
8. Remove staging directory
9. Return `RestoreResult` with safety_backup_id

### 3.4 `verify_backup(backup_id)`

**Purpose:** Verify the integrity of a backup ZIP.

**Parameters:**
- `backup_id`: The backup identifier.

**Returns:** `VerificationResult`

**Steps:**
1. Resolve backup path from `backup_id`
2. Open ZIP, verify CRC via `testzip()`
3. Extract and parse `MANIFEST.json`
4. Validate required manifest fields
5. Verify `file_count` matches actual file count in ZIP
6. For each entry in `files` array: read file, compute SHA-256, compare
7. Return result

### 3.5 `list_backups(sort_by="created_at", limit=None)`

**Purpose:** List available backups.

**Parameters:**
- `sort_by`: Sort field (`"created_at"` or `"name"`). Defaults to `"created_at"`.
- `limit`: Maximum number of backups to return. `None` = all.

**Returns:** `list[BackupInfo]`

**Steps:**
1. Glob `backup_*.zip` in `BACKUPS_DIR`
2. For each ZIP, extract `MANIFEST.json` from within and parse `BackupInfo`
3. Sort by specified field
4. Apply limit if specified
5. Return list

### 3.6 `get_latest_backup()`

**Purpose:** Get the most recent backup by creation time.

**Returns:** `BackupInfo | None`

**Steps:**
1. Call `list_backups(limit=1)`
2. Return first element or None

### 3.7 `delete_backup(backup_id)`

**Purpose:** Delete a backup.

**Parameters:**
- `backup_id`: The backup identifier.

**Returns:** `bool` — True if deleted, False if not found.

**Steps:**
1. Resolve path from `backup_id`
2. Call `path.unlink(missing_ok=False)`
3. Return True on success, False on FileNotFoundError

### 3.8 `clean_old_backups(keep_last=5)`

**Purpose:** Remove old backups beyond the retention limit.

**Parameters:**
- `keep_last`: Number of most recent backups to keep. Defaults to 5.

**Returns:** `int` — number of backups deleted.

**Steps:**
1. List all backups sorted by creation time (newest first)
2. Filter out `backup_type="pre_restore"` (these are excluded from cleanup)
3. Keep the first `keep_last` backups
4. Delete the rest
5. Return count of deleted backups

---

## 4. Internal Methods

### 4.1 `_generate_backup_id() -> str`

Static method. Generates a unique backup identifier.

```python
@staticmethod
def _generate_backup_id() -> str:
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"backup_{ts}_{uid}"
```

### 4.2 `_compute_sha256(data: bytes) -> str`

Static method. Compute SHA-256 hex digest.

```python
@staticmethod
def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
```

### 4.3 `_build_manifest(files: list[ManifestEntry], backup_id: str, backup_type: str) -> dict`

Internal method. Build the MANIFEST.json payload.

Parameters:
- `files`: List of file entries with path, size, sha256.
- `backup_id`: The backup identifier.
- `backup_type`: The backup type.

Returns a dict ready for JSON serialization.

### 4.4 `_build_metadata(backup_type: str) -> dict`

Internal method. Build the metadata.json payload.

Reads:
- Environment from `trackora.core.environment`
- Platform from `sys.platform`
- Python version from `sys.version`
- Application version from `trackora.__version__`
- Schema version from `SchemaVersionManager`

### 4.5 `_copy_database(dest_path: Path) -> bool`

Internal method. Copy the production database to a destination path.

```python
def _copy_database(self, dest_path: Path) -> bool:
    source_path = self._database_path
    if not source_path.is_file():
        return False
    # Checkpoint WAL
    with sqlite3.connect(str(source_path)) as src:
        src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # Copy via sqlite3 backup API
    with sqlite3.connect(str(source_path)) as src:
        with sqlite3.connect(str(dest_path)) as dest:
            src.backup(dest, pages=-1)
    return True
```

### 4.6 `_clean_orphan_tmp() -> None`

Internal method. Clean orphaned `.tmp` backup files.

Scans `backup_dir` for `*.zip.tmp` files and removes them.

### 4.7 `_clean_orphan_restore_dirs() -> None`

Internal method. Clean orphaned `.restore_*` staging directories.

Scans `backup_dir` for `.restore_*` directories and removes them.

### 4.8 `_resolve_backup_path(backup_id: str) -> Path`

Internal method. Resolve a backup_id to a full Path.

```python
def _resolve_backup_path(self, backup_id: str) -> Path:
    return self._backup_dir / f"{backup_id}.zip"
```

### 4.9 `_get_source_paths() -> dict[str, Path]`

Internal method. Get map of archive path → source path for files to back up.

```python
def _get_source_paths(self) -> dict[str, Path]:
    return {
        "schema.json": self._schema_path,
        "trackora.db": self._database_path,
    }
```

### 4.10 `_check_dataclass_types() -> None`

Internal (debug/validation). Verify that dataclass instances have correct field types.

---

## 5. Data Classes

All data classes are frozen dataclasses defined in `backup_manager.py`.

```python
@dataclass(frozen=True)
class BackupResult:
    success: bool
    backup_id: str
    backup_path: Path | None
    size_bytes: int
    file_count: int
    created_at: datetime
    error: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    backup_id: str
    safety_backup_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    backup_id: str
    checksum_errors: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
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

## 6. Dependencies

### 6.1 Standard Library

| Module | Version | Usage |
|---|---|---|
| `zipfile` | stdlib | ZIP creation, extraction, integrity check |
| `hashlib` | stdlib | SHA-256 checksums |
| `json` | stdlib | Manifest and metadata serialization |
| `os` | stdlib | `os.replace()` for atomic file operations |
| `shutil` | stdlib | `shutil.rmtree()` for staging cleanup |
| `uuid` | stdlib | `uuid.uuid4()` for unique IDs |
| `sqlite3` | stdlib | Online database backup via backup API |
| `pathlib` | stdlib | Cross-platform path operations |
| `logging` | stdlib | Structured logging |
| `datetime` | stdlib | Timestamps and formatting |
| `sys` | stdlib | Platform detection for metadata |
| `dataclasses` | stdlib | Frozen dataclasses for result types |
| `typing` | stdlib | Type hints |
| `__future__` | stdlib | `from __future__ import annotations` |
| `functools` | stdlib | `@functools.singledispatch` if needed |

### 6.2 Application Modules

| Module | Usage |
|---|---|
| `trackora.__version__` | Application version for manifest/metadata |
| `trackora.core.paths` | `BACKUPS_DIR`, `DATABASE_PATH` |
| `trackora.core.schema_version` | `SchemaVersion`, `SchemaVersionError` |
| `trackora.core.schema_version_manager` | `SchemaVersionManager` for reading schema version |
| `trackora.core.environment` | `CURRENT_ENVIRONMENT` for metadata |

### 6.3 Forbidden Imports

Must NOT import from:
- `database` (database_manager, models, repositories)
- `services` (any module)
- `ui` (any module)
- `tracker` (any module)
- `trackora_stats` (any module)

---

## 7. Error Handling

### 7.1 Exception Policy

- **Do not define custom exceptions** for BackupManager. Use appropriate standard exceptions:
  - `FileNotFoundError` — backup file not found
  - `OSError` — disk full, permission denied, replace failed
  - `zipfile.BadZipFile` — corrupt ZIP
  - `json.JSONDecodeError` — invalid manifest JSON
- All errors are caught, logged, and returned via result objects.
- `BackupResult.error`, `RestoreResult.error`, `VerificationResult.error` always contain a human-readable string.

### 7.2 Error Propagation

- Errors in `__init__()` cleanup: logged, not propagated.
- Errors in public methods: always returned via result object, never raised to caller.
- Errors in internal methods: may raise, caller (public method) catches and wraps.

### 7.3 Error Logging

All errors are logged at `ERROR` level with:
- Backup ID (if available)
- Error message
- Path (if applicable)
- Full traceback at `DEBUG` level

---

## 8. Acceptance Criteria

### 8.1 Functional Requirements

| ID | Requirement | Verification |
|---|---|---|
| AC-BM-01 | `create_backup()` creates a valid ZIP at `BACKUPS_DIR` | File exists, is ZIP, contains expected files |
| AC-BM-02 | `create_backup()` creates backup with correct naming | Name matches `backup_<ts>_<uuid>.zip` |
| AC-BM-03 | `create_backup()` backup is atomic | `.tmp` file does not remain after success |
| AC-BM-04 | `create_backup()` includes MANIFEST.json with correct structure | JSON parseable, all fields present |
| AC-BM-05 | `create_backup()` includes SHA-256 checksums in manifest | Every file in archive has valid SHA-256 |
| AC-BM-06 | `create_backup()` MANIFEST.json is stored uncompressed | `ZipInfo.compress_type == ZIP_STORED` |
| AC-BM-07 | `create_backup()` includes metadata.json | Present, valid JSON, required fields present |
| AC-BM-08 | `create_backup()` includes trackora.db | Present, is valid SQLite database |
| AC-BM-09 | `create_backup()` includes schema.json | Present, valid schema version |
| AC-BM-10 | `create_backup()` returns BackupResult on success | `success=True`, backup_id non-empty |
| AC-BM-11 | `create_backup()` returns BackupResult on failure | `success=False`, error non-null |
| AC-BM-12 | `create_backup()` with missing DB returns error | Result has error describing missing DB |
| AC-BM-13 | `verify_backup()` passes on valid backup | `valid=True`, no errors |
| AC-BM-14 | `verify_backup()` fails on corrupt ZIP | `valid=False`, error describes corruption |
| AC-BM-15 | `verify_backup()` fails on missing manifest | `valid=False`, missing_files contains MANIFEST |
| AC-BM-16 | `verify_backup()` fails on checksum mismatch | `valid=False`, checksum_errors lists file |
| AC-BM-17 | `verify_backup()` fails on missing file in ZIP | `valid=False`, missing_files lists file |
| AC-BM-18 | `restore_backup()` succeeds on valid backup | `success=True`, files replaced |
| AC-BM-19 | `restore_backup()` creates safety backup first | Safety backup exists in BACKUPS_DIR |
| AC-BM-20 | `restore_backup()` fails on corrupt backup | `success=False`, error describes failure |
| AC-BM-21 | `restore_backup()` rollback on replace failure | Safety backup restored, original files intact |
| AC-BM-22 | `list_backups()` returns empty list for empty dir | `[]` |
| AC-BM-23 | `list_backups()` returns sorted by date | Newest first |
| AC-BM-24 | `list_backups()` respects limit | Returns at most `limit` items |
| AC-BM-25 | `get_latest_backup()` returns None for empty dir | `None` |
| AC-BM-26 | `get_latest_backup()` returns most recent | Correct backup |
| AC-BM-27 | `delete_backup()` removes backup file | File gone, returns True |
| AC-BM-28 | `delete_backup()` returns False for missing | No error, returns False |
| AC-BM-29 | `clean_old_backups()` keeps last N | Older backups deleted, newer remain |
| AC-BM-30 | `clean_old_backups()` preserves pre_restore | pre_restore backups not deleted |
| AC-BM-31 | Orphan `.tmp` files cleaned on __init__ | `.tmp` file removed |
| AC-BM-32 | `BackupResult`, `RestoreResult`, `VerificationResult`, `BackupInfo` are frozen | `FrozenInstanceError` on mutation attempt |

### 8.2 Non-Functional Requirements

| ID | Requirement | Acceptance |
|---|---|---|
| AC-BM-33 | No imports from `database`, `services`, `ui`, `tracker`, `trackora_stats` | Architecture test passes |
| AC-BM-34 | No file outside `backup_manager.py` creates or reads backup ZIPs | Architecture test passes |
| AC-BM-35 | All backup identifiers are URL-safe | Match regex `^backup_\d{8}_\d{6}_[a-f0-9]{8}$` |
| AC-BM-36 | Unicode paths in database/schema are supported | Backup created and verified successfully |

---

## 9. Testing Strategy

### 9.1 Test File: `tests/test_backup_manager.py`

Total estimated tests: **65-70**

#### 9.1.1 __init__ Tests (4)

| Test | Description |
|---|---|
| `test_init_default_backup_dir` | Default uses `BACKUPS_DIR` from paths.py |
| `test_init_custom_backup_dir` | Custom path is stored |
| `test_init_cleans_orphan_tmp` | `.tmp` file in backup dir is removed |
| `test_init_cleans_orphan_restore_dirs` | `.restore_*` dir is removed |

#### 9.1.2 create_backup Tests (14)

| Test | Description |
|---|---|
| `test_create_backup_file_created` | ZIP file created in backup dir |
| `test_create_backup_naming` | Name matches expected format |
| `test_create_backup_atomic` | No `.tmp` residue after success |
| `test_create_backup_zip_contents` | Contains expected files |
| `test_create_backup_manifest_present` | MANIFEST.json inside ZIP |
| `test_create_backup_manifest_stored` | MANIFEST.json is ZIP_STORED |
| `test_create_backup_manifest_checksums` | Every file has SHA-256 in manifest |
| `test_create_backup_checksums_valid` | SHA-256 checksums match actual files |
| `test_create_backup_metadata` | metadata.json has required fields |
| `test_create_backup_backup_result` | Returns BackupResult with correct fields |
| `test_create_backup_missing_db` | Returns error if database missing |
| `test_create_backup_missing_schema` | Returns success with warning if schema missing |
| `test_create_backup_unicode_paths` | Database/schema with Unicode paths |
| `test_create_backup_concurrent` | Two backups in same dir — no collision |

#### 9.1.3 verify_backup Tests (10)

| Test | Description |
|---|---|
| `test_verify_valid_backup` | Valid backup returns valid=True |
| `test_verify_missing_backup` | Non-existent backup returns error |
| `test_verify_corrupt_zip` | Corrupt ZIP returns valid=False |
| `test_verify_missing_manifest` | ZIP without MANIFEST returns error |
| `test_verify_invalid_manifest_json` | Bad JSON in manifest returns error |
| `test_verify_missing_file` | ZIP missing file from manifest |
| `test_verify_checksum_mismatch` | Tampered file detected |
| `test_verify_wrong_file_count` | file_count mismatch detected |
| `test_verify_empty_backup` | ZIP with no files |
| `test_verify_extra_file_ok` | Extra files beyond manifest are ignored |

#### 9.1.4 restore_backup Tests (10)

| Test | Description |
|---|---|
| `test_restore_valid_backup` | Files restored correctly |
| `test_restore_creates_safety_backup` | Safety backup ZIP exists after restore |
| `test_restore_safety_backup_has_type` | Safety backup has `backup_type="pre_restore"` |
| `test_restore_fails_corrupt_backup` | Returns error, no files changed |
| `test_restore_fails_missing_backup` | Returns error for non-existent backup |
| `test_restore_verifies_first` | Does not restore unverified backup |
| `test_restore_staging_cleanup` | Staging dir removed after success |
| `test_restore_replace_failure_rollback` | Safety backup restored on replace failure |
| `test_restore_schema_json_replaced` | schema.json is replaced correctly |
| `test_restore_trackora_db_replaced` | trackora.db is replaced correctly |

#### 9.1.5 list_backups Tests (6)

| Test | Description |
|---|---|
| `test_list_empty_dir` | Empty list for empty dir |
| `test_list_mixed_files` | Ignores non-backup files |
| `test_list_sorted_by_date` | Newest first |
| `test_list_sorted_by_name` | Alphabetical |
| `test_list_limit` | Respects limit parameter |
| `test_list_filters_backup_id` | Correct backup_id in results |

#### 9.1.6 get_latest_backup Tests (4)

| Test | Description |
|---|---|
| `test_get_latest_empty` | Returns None |
| `test_get_latest_single` | Returns only backup |
| `test_get_latest_multiple` | Returns newest |
| `test_get_latest_ignores_other_files` | Ignores non-backup .zip files |

#### 9.1.7 delete_backup Tests (4)

| Test | Description |
|---|---|
| `test_delete_existing` | Returns True, file gone |
| `test_delete_missing` | Returns False |
| `test_delete_only_target_file` | Does not delete other backups |
| `test_delete_twice` | First True, second False |

#### 9.1.8 clean_old_backups Tests (6)

| Test | Description |
|---|---|
| `test_clean_keeps_last_5` | Default retention |
| `test_clean_custom_keep` | Custom keep_last respected |
| `test_clean_preserves_pre_restore` | pre_restore backups not deleted |
| `test_clean_empty_dir` | No-op on empty dir |
| `test_clean_fewer_than_keep` | No-op when fewer than limit |
| `test_clean_returns_count` | Correct deletion count |

#### 9.1.9 Data Class Tests (4)

| Test | Description |
|---|---|
| `test_backup_result_frozen` | FrozenInstanceError on mutation |
| `test_restore_result_frozen` | FrozenInstanceError on mutation |
| `test_verification_result_frozen` | FrozenInstanceError on mutation |
| `test_backup_info_frozen` | FrozenInstanceError on mutation |

### 9.2 Test File: `tests/test_upgrade_lifecycle.py`

Add to existing file:

| Test | Description |
|---|---|
| `test_backup_restore_roundtrip` | Create backup of test DB → restore → verify data |
| `test_backup_verify_lifecycle` | Create → verify → delete → exsts |


### 9.3 Test File: `tests/architecture/test_backup_isolation.py`

| Test | Description |
|---|---|
| `test_backup_manager_import_restrictions` | Only stdlib + trackora.core allowed |
| `test_no_backup_zip_outside_manager` | No `backup_*.zip` or backup ZIP ops outside manager |
| `test_backup_manager_no_database_import` | No `database/` imports |
| `test_backup_manager_no_services_import` | No `services/` imports |

---

## 10. Implementation Order

### 10.1 Step Order

| Step | Component | Tests | Est. Files |
|---|---|---|---|
| 1 | Data classes + `__init__` | 8 | `backup_manager.py` |
| 2 | `create_backup()` — core | 14 | `backup_manager.py` |
| 3 | `verify_backup()` | 10 | `backup_manager.py` |
| 4 | `restore_backup()` | 10 | `backup_manager.py` |
| 5 | `list_backups()` + `get_latest_backup()` | 10 | `backup_manager.py` |
| 6 | `delete_backup()` + `clean_old_backups()` | 10 | `backup_manager.py` |
| 7 | Integration tests | 5 | `test_upgrade_lifecycle.py` |
| 8 | Architecture tests | 4 | `test_backup_isolation.py` |
| 9 | Full validation | — | coverage + regression |

### 10.2 Step Dependencies

- Step 1 has no dependencies
- Step 2 depends on Step 1
- Step 3 depends on Step 2 (needs valid backup to verify)
- Step 4 depends on Steps 2 and 3 (verifies before restore)
- Step 5 depends on Step 2 (needs backups to list)
- Step 6 depends on Steps 2 and 5 (lists and deletes)
- Step 7 depends on Steps 2-4 (integration scenario)
- Step 8 has no dependencies (static analysis)
- Step 9 depends on all previous steps
