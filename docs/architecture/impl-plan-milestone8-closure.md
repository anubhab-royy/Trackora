# Milestone 8 Closure — Implementation Plan

## Files to Modify

| File | Change |
|---|---|
| `trackora/core/backup_manager.py` | Fix A: Add post-extraction validation in `restore_backup()` |
| `trackora/core/backup_manager.py` | Fix B: Rewrite `_restore_from_safety()` to use staging + atomic replace |
| `trackora/core/backup_manager.py` | Fix C: Verify safety backup before rollback in `restore_backup()` exception handler |
| `trackora/core/migrations/v2_0_0_add_discovery_columns.py` | Fix D: Harden `_column_exists()` with table name validation |
| `tests/test_startup_integration.py` | Fix E: Add `test_main_called_with_mocks` end-to-end test |
| `tests/test_startup_integration.py` | Fix F: Replace placeholder with real backup failure test |

## Files to Create

None. All changes are to existing files.

## Tests Required

### Fix A — Restore Validation (new tests in `test_backup_manager.py`)

| Test | Scenario |
|---|---|
| `test_restore_validates_staged_db_opens` | Staged trackora.db is a valid SQLite file |
| `test_restore_rejects_corrupt_staged_db` | Staged trackora.db is not valid SQLite → failure |
| `test_restore_rejects_integrity_failure` | PRAGMA integrity_check returns errors → failure |
| `test_restore_validates_checksums` | SHA-256 mismatch between manifest and staged file → failure |
| `test_restore_validates_schema_json` | Corrupt schema.json in staging → failure |
| `test_restore_does_not_touch_production_on_validation_failure` | Production files unchanged after validation failure |
| `test_restore_skips_schema_validation_when_not_in_backup` | Restore without schema.json is OK |

### Fix B — Atomic Rollback (new tests in `test_backup_manager.py`)

| Test | Scenario |
|---|---|
| `test_restore_from_safety_uses_staging_dir` | Staging directory is created and cleaned up |
| `test_restore_from_safety_validates_extracted_files` | Extracted files checksum-verified before replace |
| `test_restore_from_safety_atomic_replace` | Production files replaced via os.replace (atomic) |
| `test_restore_from_safety_partial_extract_does_not_touch_production` | Validation failure → no production write |

### Fix C — Safety Backup Verification (new tests in `test_backup_manager.py`)

| Test | Scenario |
|---|---|
| `test_restore_verifies_safety_backup_before_rollback` | Safety backup verified; corrupt safety → no rollback attempt |
| `test_restore_corrupt_safety_returns_graceful_error` | Graceful error message with safety_backup_id |

### Fix D — Column Exists Hardening (new test in `test_migration_phase6f.py`)

| Test | Scenario |
|---|---|
| `test_column_exists_validates_table_name` | Unknown table name raises ValueError |
| `test_column_exists_accepts_known_table` | Known table name works normally |

### Fix E — Startup Integration (new test in `test_startup_integration.py`)

| Test | Scenario |
|---|---|
| `test_main_first_run` | main() with no schema.json → writes version, no backup/migration |
| `test_main_normal_startup` | main() with matching version → services initialized |
| `test_main_migration_needed` | main() with old schema → backup → migration → version write |
| `test_main_newer_data_blocks` | main() with newer schema → sys.exit(2) |

### Fix F — Backup Failure (new test in `test_startup_integration.py`)

| Test | Scenario |
|---|---|
| `test_main_backup_failure_exits_with_code_3` | create_backup() fails → sys.exit(3), migration not executed |

## Acceptance Criteria

```
1.  restore_backup() validates all extracted files before replacing production files
2.  restore_backup() returns success=False without modifying production files on validation failure
3.  _restore_from_safety() uses staging directory + validation + atomic os.replace()
4.  _restore_from_safety() raises RuntimeError if safety backup verification fails
5.  restore_backup() exception handler verifies safety backup before attempting rollback
6.  _column_exists() validates table name against allowlist
7.  test_main_called_with_mocks covers first-run, normal, migration, and newer-data paths
8.  test_backup_failure_blocks actually simulates backup failure and verifies sys.exit(3)
9.  All existing tests pass (0 regressions)
10. No decrease in coverage for any component
```

## Validation Commands

```bash
# Unit + integration tests (non-CXXABI)
python -m pytest tests/test_backup_manager.py -x -v

python -m pytest tests/test_migration_phase6f.py -x -v

python -m pytest tests/test_startup_integration.py -x -v

# Full regression (excluding CXXABI-affected files)
python -m pytest tests/test_backup_manager.py tests/test_startup_integration.py tests/test_upgrade_lifecycle.py tests/test_migration_*.py tests/test_schema_version*.py tests/test_database_manager.py tests/architecture/test_migration_isolation.py -x -v

# Architecture enforcement
python -m pytest tests/architecture/test_migration_isolation.py -x -v
```
