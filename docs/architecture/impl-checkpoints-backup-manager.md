# BackupManager — Implementation Checklist

**Total Files:** 5 (2 source + 2 test + 1 architecture test)  
**Methodology:** Test-first (red-green-refactor for each step)  
**Estimated Steps:** 9  

---

## Step 0 — Prerequisites

- [ ] 0.1 Working Python 3.13+ environment with activated venv
- [ ] 0.2 `python -m pytest tests/test_schema_version.py tests/test_schema_version_manager.py` — all 188 tests pass
- [ ] 0.3 Read reference files:
  - `trackora/core/paths.py` (BACKUPS_DIR, DATABASE_PATH)
  - `trackora/core/schema_version_manager.py` (atomic write pattern, read API)
  - `trackora/core/schema_version.py` (SchemaVersion dataclass)
  - `tests/architecture/test_path_isolation.py` (AST pattern)
- [ ] 0.4 Verify `tests/` directory exists and writable

---

## Step 1 — Data classes + __init__

**File:** `trackora/core/backup_manager.py`  
**Dependencies:** stdlib (dataclasses, pathlib, logging, uuid, datetime) + trackora.core.paths + trackora.core.schema_version_manager  
**Test file:** `tests/test_backup_manager.py`

### 1.1 Data classes

- [ ] 1.1.1 **RED:** Write `test_backup_result_frozen` — `BackupResult` is frozen dataclass
- [ ] 1.1.2 **GREEN:** Define `BackupResult` frozen dataclass with all fields
- [ ] 1.1.3 **RED:** Write `test_restore_result_frozen` — `RestoreResult` is frozen dataclass
- [ ] 1.1.4 **GREEN:** Define `RestoreResult` frozen dataclass
- [ ] 1.1.5 **RED:** Write `test_verification_result_frozen` — `VerificationResult` is frozen dataclass
- [ ] 1.1.6 **GREEN:** Define `VerificationResult` frozen dataclass
- [ ] 1.1.7 **RED:** Write `test_backup_info_frozen` — `BackupInfo` is frozen dataclass
- [ ] 1.1.8 **GREEN:** Define `BackupInfo` frozen dataclass

**Validation:** `python -m pytest tests/test_backup_manager.py::TestBackupResult -v`

### 1.2 __init__

- [ ] 1.2.1 **RED:** Write `test_init_default_backup_dir` — default resolves to `BACKUPS_DIR`
- [ ] 1.2.2 **GREEN:** Implement `__init__()` with backup_dir defaulting to `BACKUPS_DIR`
- [ ] 1.2.3 **RED:** Write `test_init_custom_backup_dir` — custom path stored
- [ ] 1.2.4 **GREEN:** Verify custom path is stored
- [ ] 1.2.5 **RED:** Write `test_init_cleans_orphan_tmp` — `.tmp` file removed
- [ ] 1.2.6 **GREEN:** Implement `_clean_orphan_tmp()` called from `__init__()`
- [ ] 1.2.7 **RED:** Write `test_init_cleans_orphan_restore_dirs` — `.restore_*` dirs removed
- [ ] 1.2.8 **GREEN:** Implement `_clean_orphan_restore_dirs()` called from `__init__()`

**Validation:** `python -m pytest tests/test_backup_manager.py::TestInit -v`

---

## Step 2 — create_backup()

**Dependencies:** Step 1 (data classes, __init__)

### 2.1 Core backup creation

- [ ] 2.1.1 **RED:** Write `test_create_backup_file_created` — ZIP file exists after call
- [ ] 2.1.2 **GREEN:** Implement minimal `create_backup()` that creates a ZIP with MANIFEST.json
  - `_generate_backup_id()` static method
  - `_compute_sha256()` static method
  - `_build_manifest()` internal method
  - `_build_metadata()` internal method
  - `_copy_database()` internal method
  - `_get_source_paths()` internal method
- [ ] 2.1.3 **RED:** Write `test_create_backup_naming` — name matches `backup_<ts>_<uuid>.zip`
- [ ] 2.1.4 **GREEN:** Verify backup_id format
- [ ] 2.1.5 **RED:** Write `test_create_backup_atomic` — no `.tmp` residue after success
- [ ] 2.1.6 **GREEN:** Use `.tmp` + `os.replace` atomic pattern
- [ ] 2.1.7 **RED:** Write `test_create_backup_zip_contents` — ZIP contains MANIFEST.json, trackora.db, schema.json, metadata.json
- [ ] 2.1.8 **GREEN:** Add all source files to ZIP
- [ ] 2.1.9 **RED:** Write `test_create_backup_manifest_present` — MANIFEST.json inside ZIP, parseable
- [ ] 2.1.10 **GREEN:** Write MANIFEST.json with correct structure

**Validation:** `python -m pytest tests/test_backup_manager.py::TestCreateBackup -v` (10 tests)

### 2.2 Manifest + checksums

- [ ] 2.2.1 **RED:** Write `test_create_backup_manifest_stored` — MANIFEST.json uses ZIP_STORED
- [ ] 2.2.2 **GREEN:** Set compression type for MANIFEST.json to ZIP_STORED
- [ ] 2.2.3 **RED:** Write `test_create_backup_manifest_checksums` — every file has SHA-256 in manifest
- [ ] 2.2.4 **GREEN:** Compute SHA-256 for each file, include in manifest
- [ ] 2.2.5 **RED:** Write `test_create_backup_checksums_valid` — SHA-256 matches actual file content
- [ ] 2.2.6 **GREEN:** Verify checksums via `_compute_sha256()` during manifest build
- [ ] 2.2.7 **RED:** Write `test_create_backup_metadata` — metadata.json has required fields
- [ ] 2.2.8 **GREEN:** Write metadata.json with all required fields
- [ ] 2.2.9 **RED:** Write `test_create_backup_backup_result` — returns BackupResult with correct fields
- [ ] 2.2.10 **GREEN:** Return BackupResult from create_backup()

**Validation:** `python -m pytest tests/test_backup_manager.py -v` (passes all Step 2 tests)

### 2.3 Error handling + edge cases

- [ ] 2.3.1 **RED:** Write `test_create_backup_missing_db` — returns error when trackora.db missing
- [ ] 2.3.2 **GREEN:** Check DATABASE_PATH.exists() before backup, return error if missing
- [ ] 2.3.3 **RED:** Write `test_create_backup_missing_schema` — logs warning, continues without it
- [ ] 2.3.4 **GREEN:** Handle missing schema.json gracefully
- [ ] 2.3.5 **RED:** Write `test_create_backup_unicode_paths` — database/schema with Unicode works
- [ ] 2.3.6 **GREEN:** Ensure ensure_ascii=False in JSON, UTF-8 encoding in ZIP
- [ ] 2.3.7 **RED:** Write `test_create_backup_concurrent` — no collision with concurrent calls
- [ ] 2.3.8 **GREEN:** UUID-based backup_id ensures uniqueness

**Validation:** `python -m pytest tests/test_backup_manager.py::TestCreateBackup -v`

---

## Step 3 — verify_backup()

**Dependencies:** Step 2 (needs a valid backup to test against)

- [ ] 3.1.1 **RED:** Write `test_verify_valid_backup` — valid backup returns `valid=True`
- [ ] 3.1.2 **GREEN:** Implement `verify_backup()` — open ZIP, parse manifest, check files
- [ ] 3.1.3 **RED:** Write `test_verify_missing_backup` — non-existent backup_id returns error
- [ ] 3.1.4 **GREEN:** Handle FileNotFoundError, return verification result with error
- [ ] 3.1.5 **RED:** Write `test_verify_corrupt_zip` — corrupt ZIP returns valid=False
- [ ] 3.1.6 **GREEN:** Catch zipfile.BadZipFile, return verification result
- [ ] 3.1.7 **RED:** Write `test_verify_missing_manifest` — ZIP without MANIFEST returns error
- [ ] 3.1.8 **GREEN:** Check MANIFEST.json exists in ZIP, return missing_files list
- [ ] 3.1.9 **RED:** Write `test_verify_invalid_manifest_json` — bad JSON manifest returns error
- [ ] 3.1.10 **GREEN:** Catch json.JSONDecodeError, return error
- [ ] 3.1.11 **RED:** Write `test_verify_missing_file` — file listed in manifest but missing from ZIP
- [ ] 3.1.12 **GREEN:** Check each file from manifest exists in ZIP, record missing
- [ ] 3.1.13 **RED:** Write `test_verify_checksum_mismatch` — tampered file detected
- [ ] 3.1.14 **GREEN:** Compute SHA-256 for each file, compare with manifest
- [ ] 3.1.15 **RED:** Write `test_verify_wrong_file_count` — file_count mismatch detected
- [ ] 3.1.16 **GREEN:** Compare manifest file_count with actual zipfile.namelist() count
- [ ] 3.1.17 **RED:** Write `test_verify_empty_backup` — empty ZIP returns valid=False
- [ ] 3.1.18 **GREEN:** Handle empty ZIP gracefully
- [ ] 3.1.19 **RED:** Write `test_verify_extra_file_ok` — extra files not in manifest are ignored
- [ ] 3.1.20 **GREEN:** Ignore files in ZIP not listed in manifest

**Validation:** `python -m pytest tests/test_backup_manager.py::TestVerifyBackup -v`

---

## Step 4 — restore_backup()

**Dependencies:** Steps 2-3 (needs verify + create)

- [ ] 4.1.1 **RED:** Write `test_restore_valid_backup` — files restored correctly
- [ ] 4.1.2 **GREEN:** Implement `restore_backup()` — verify, safety backup, extract, replace
- [ ] 4.1.3 **RED:** Write `test_restore_creates_safety_backup` — safety backup exists after restore
- [ ] 4.1.4 **GREEN:** Call `create_backup(backup_type="pre_restore")` before restore
- [ ] 4.1.5 **RED:** Write `test_restore_safety_backup_has_type` — safety backup has correct type
- [ ] 4.1.6 **GREEN:** Verify backup_type is "pre_restore"
- [ ] 4.1.7 **RED:** Write `test_restore_fails_corrupt_backup` — returns error, no files changed
- [ ] 4.1.8 **GREEN:** Call verify_backup() first, abort on failure
- [ ] 4.1.9 **RED:** Write `test_restore_fails_missing_backup` — error for non-existent backup
- [ ] 4.1.10 **GREEN:** Handle missing backup gracefully
- [ ] 4.1.11 **RED:** Write `test_restore_verifies_first` — verify_backup() called before restore
- [ ] 4.1.12 **GREEN:** Ensure verify_backup() is the first step
- [ ] 4.1.13 **RED:** Write `test_restore_staging_cleanup` — staging dir removed after success
- [ ] 4.1.14 **GREEN:** Remove staging directory after successful restore
- [ ] 4.1.15 **RED:** Write `test_restore_replace_failure_rollback` — safety backup restored on failure
- [ ] 4.1.16 **GREEN:** Implement rollback: catch OSError on replace, restore safety backup
- [ ] 4.1.17 **RED:** Write `test_restore_schema_json_replaced` — schema.json replaced correctly
- [ ] 4.1.18 **GREEN:** os.replace staging/schema.json → production/schema.json
- [ ] 4.1.19 **RED:** Write `test_restore_trackora_db_replaced` — trackora.db replaced correctly
- [ ] 4.1.20 **GREEN:** os.replace staging/trackora.db → production/trackora.db

**Validation:** `python -m pytest tests/test_backup_manager.py::TestRestoreBackup -v`

---

## Step 5 — list_backups() + get_latest_backup()

**Dependencies:** Step 2 (needs backups to list)

- [ ] 5.1.1 **RED:** Write `test_list_empty_dir` — empty list for empty dir
- [ ] 5.1.2 **GREEN:** Implement `list_backups()` — glob `backup_*.zip`, parse MANIFEST, return BackupInfo list
- [ ] 5.1.3 **RED:** Write `test_list_mixed_files` — ignores non-backup files
- [ ] 5.1.4 **GREEN:** Filter by `backup_*.zip` glob pattern
- [ ] 5.1.5 **RED:** Write `test_list_sorted_by_date` — newest first (default sort)
- [ ] 5.1.6 **GREEN:** Sort BackupInfo by created_at descending
- [ ] 5.1.7 **RED:** Write `test_list_sorted_by_name` — alphabetical sort
- [ ] 5.1.8 **GREEN:** Support sort_by="name" parameter
- [ ] 5.1.9 **RED:** Write `test_list_limit` — respects limit parameter
- [ ] 5.1.10 **GREEN:** Apply limit to returned list
- [ ] 5.1.11 **RED:** Write `test_list_filters_backup_id` — correct backup_id in results
- [ ] 5.1.12 **GREEN:** Extract backup_id from filename, verify match
- [ ] 5.1.13 **RED:** Write `test_get_latest_empty` — returns None
- [ ] 5.1.14 **GREEN:** Implement `get_latest_backup()` — call list_backups(limit=1)
- [ ] 5.1.15 **RED:** Write `test_get_latest_single` — returns only backup
- [ ] 5.1.16 **GREEN:** Verify returns correct single backup
- [ ] 5.1.17 **RED:** Write `test_get_latest_multiple` — returns newest
- [ ] 5.1.18 **GREEN:** Verify returns most recent backup
- [ ] 5.1.19 **RED:** Write `test_get_latest_ignores_other_files` — ignores non-backup .zip files
- [ ] 5.1.20 **GREEN:** Verify only backup_*.zip files are considered

**Validation:** `python -m pytest tests/test_backup_manager.py::TestListBackups::TestGetLatestBackup -v`

---

## Step 6 — delete_backup() + clean_old_backups()

**Dependencies:** Step 2 (needs backups to delete)

- [ ] 6.1.1 **RED:** Write `test_delete_existing` — returns True, file gone
- [ ] 6.1.2 **GREEN:** Implement `delete_backup()` — unlink with missing_ok=True
- [ ] 6.1.3 **RED:** Write `test_delete_missing` — returns False
- [ ] 6.1.4 **GREEN:** Handle FileNotFoundError, return False
- [ ] 6.1.5 **RED:** Write `test_delete_only_target_file` — does not delete other backups
- [ ] 6.1.6 **GREEN:** Only delete exact path match
- [ ] 6.1.7 **RED:** Write `test_delete_twice` — first True, second False
- [ ] 6.1.8 **GREEN:** Verify idempotent behavior
- [ ] 6.1.9 **RED:** Write `test_clean_keeps_last_5` — default retention
- [ ] 6.1.10 **GREEN:** Implement `clean_old_backups()` — get sorted list, delete beyond keep_last
- [ ] 6.1.11 **RED:** Write `test_clean_custom_keep` — custom keep_last respected
- [ ] 6.1.12 **GREEN:** Pass keep_last to retention logic
- [ ] 6.1.13 **RED:** Write `test_clean_preserves_pre_restore` — pre_restore backups not deleted
- [ ] 6.1.14 **GREEN:** Filter out backup_type="pre_restore" from deletion candidates
- [ ] 6.1.15 **RED:** Write `test_clean_empty_dir` — no-op on empty dir
- [ ] 6.1.16 **GREEN:** Handle empty backup_dir gracefully
- [ ] 6.1.17 **RED:** Write `test_clean_fewer_than_keep` — no-op when fewer than limit
- [ ] 6.1.18 **GREEN:** Check count before deletion
- [ ] 6.1.19 **RED:** Write `test_clean_returns_count` — correct deletion count
- [ ] 6.1.20 **GREEN:** Return integer count of deleted backups

**Validation:** `python -m pytest tests/test_backup_manager.py::TestDeleteBackup::TestCleanOldBackups -v`

---

## Step 7 — Integration tests

**File:** `tests/test_upgrade_lifecycle.py` (append)

- [ ] 7.1.1 **RED:** Write `test_backup_restore_roundtrip`:
  1. Create in-memory test database
  2. Create backup
  3. Verify backup passes
  4. Restore from backup
  5. Verify data fidelity
- [ ] 7.1.2 **GREEN:** Implement roundtrip integration test
- [ ] 7.1.3 **RED:** Write `test_backup_verify_lifecycle`:
  1. Create backup
  2. Verify → valid=True
  3. Delete backup
  4. Verify → backup not found
- [ ] 7.1.4 **GREEN:** Implement verify lifecycle test
- [ ] 7.1.5 **RED:** Write `test_corrupt_backup_detection_in_restore`:
  1. Corrupt a backup ZIP
  2. Try restore → fails
  3. Verify no files changed
- [ ] 7.1.6 **GREEN:** Implement corrupt detection integration test
- [ ] 7.1.7 **RED:** Write `test_backup_with_real_schema_manager`:
  1. Create SchemaVersionManager with real tmp_path
  2. Write schema version
  3. Create BackupManager with this SchemaVersionManager
  4. Create backup
  5. Verify manifest contains correct schema_version
- [ ] 7.1.8 **GREEN:** Implement schema version integration test

**Validation:** `python -m pytest tests/test_upgrade_lifecycle.py -v` (passes all backup tests)

---

## Step 8 — Architecture tests

**File:** `tests/architecture/test_backup_isolation.py`

- [ ] 8.1.1 **RED:** Write `test_backup_manager_import_restrictions`:
  - AST-parse `backup_manager.py`
  - Fail if imports from `database`, `services`, `ui`, `tracker`, `trackora_stats`
- [ ] 8.1.2 **GREEN:** Verify no forbidden imports exist

- [ ] 8.2.1 **RED:** Write `test_no_backup_zip_outside_manager`:
  - Scan source `.py` files for backup ZIP operations (`backup_*.zip`, `ZipFile`, `zipfile`)
  - Fail if found outside `backup_manager.py` or test files
- [ ] 8.2.2 **GREEN:** Ensure no violations exist

- [ ] 8.3.1 **RED:** Write `test_backup_manager_no_database_import`:
  - Specific check for `database/` import chain
- [ ] 8.3.2 **GREEN:** Ensure no database imports

- [ ] 8.4.1 **RED:** Write `test_backup_manager_no_services_import`:
  - Specific check for `services/` import chain
- [ ] 8.4.2 **GREEN:** Ensure no services imports

**Validation:** `python -m pytest tests/architecture/test_backup_isolation.py -v`

---

## Step 9 — Final validation

- [ ] 9.1 Run all unit tests:
  ```bash
  python -m pytest tests/test_backup_manager.py -v
  ```
  Expected: 65-70 tests, all PASS

- [ ] 9.2 Run all integration tests:
  ```bash
  python -m pytest tests/test_upgrade_lifecycle.py -v
  ```
  Expected: 28-32 tests (existing lifecycle + new backup tests), all PASS

- [ ] 9.3 Run architecture tests:
  ```bash
  python -m pytest tests/architecture/test_backup_isolation.py -v
  ```
  Expected: 4 tests, all PASS

- [ ] 9.4 Coverage report:
  ```bash
  python -m pytest --tb=short -q --cov=trackora.core.backup_manager
  ```
  Expected: 99%+ coverage

- [ ] 9.5 Full regression:
  ```bash
  python -m pytest --tb=short -q
  ```
  Expected: 900+ tests, all PASS (excluding pre-existing CXXABI issues)
