# Milestone 8 Closure — TDD Checkpoints

## Step 1 — Restore Validation

### RED
Write tests that verify `restore_backup()` validates extracted files before replacing production files. Tests must demonstrate that corrupt or invalid staged files cause failure without modifying production files.

**Test file:** `tests/test_backup_manager.py`
**New tests:** `TestRestoreValidation` class (6+ tests)

### GREEN
Add post-extraction validation block in `restore_backup()` between extraction (line 502) and atomic replace (line 508):
- Verify required files exist
- Verify SHA-256 checksums match manifest
- Verify manifest file_count consistency
- Verify SQLite database opens
- Run `PRAGMA integrity_check`
- Validate schema.json via `SchemaVersionManager`

### REFACTOR
Extract validation logic into `_validate_staging(staging_dir, zip_path)` private method. Ensure error messages are specific and include "production files not modified" suffix.

### Validation
```bash
python -m pytest tests/test_backup_manager.py::TestRestoreValidation -x -v
```

---

## Step 2 — Atomic Rollback

### RED
Write tests that verify `_restore_from_safety()` uses a staging directory, validates extracted files, and performs atomic `os.replace()`. Verify no direct `write_bytes()` to production paths.

**Test file:** `tests/test_backup_manager.py`
**New tests:** `TestAtomicRollback` class (4+ tests)

### GREEN
Rewrite `_restore_from_safety()`:
1. Verify safety backup existence (existing check)
2. Verify safety backup via `verify_backup()` (new)
3. Create staging directory in backup dir
4. Extract files to staging
5. Validate extracted files (reuse validation from Step 1)
6. `os.replace()` for atomic cutover
7. Clean up staging

### REFACTOR
Ensure `_restore_from_safety()` shares the staging validation logic with `restore_backup()` to avoid duplication.

### Validation
```bash
python -m pytest tests/test_backup_manager.py::TestAtomicRollback -x -v
```

---

## Step 3 — Safety Backup Verification

### RED
Write tests that verify `restore_backup()` exception handler calls `verify_backup()` on the safety backup before attempting rollback. If safety backup is corrupt, return graceful error without attempting rollback.

**Test file:** `tests/test_backup_manager.py`
**New tests:** `TestSafetyBackupVerification` class (2+ tests)

### GREEN
Modify the exception handler in `restore_backup()` (lines 526-561):
```python
except Exception as exc:
    verify_result = self.verify_backup(safety_backup_id)
    if not verify_result.valid:
        # Return error without rollback
        ...
    self._restore_from_safety(safety_backup_id)
```

### REFACTOR
Ensure the error message includes `safety_backup_id` for manual recovery.

### Validation
```bash
python -m pytest tests/test_backup_manager.py::TestSafetyBackupVerification -x -v
```

---

## Step 4 — SQL Injection Hardening

### RED
Write a test that calls `_column_exists()` with an unknown table name and expects `ValueError`. Verify known table names still work.

**Test file:** `tests/test_migration_phase6f.py`
**New tests:** `TestColumnExistsHardening` class (2 tests)

### GREEN
Add table name validation to `_column_exists()` in `v2_0_0_add_discovery_columns.py`:
```python
_VALID_TABLES = frozenset({"games"})
def _column_exists(connection, table, column):
    if table not in _VALID_TABLES:
        raise ValueError(f"Unknown table: {table}")
    ...
```

### REFACTOR
None needed — the change is minimal and focused.

### Validation
```bash
python -m pytest tests/test_migration_phase6f.py::TestColumnExistsHardening -x -v
```

---

## Step 5 — Startup Integration Test

### RED
Write tests that call `trackora.__main__.main()` with all external dependencies mocked.

**Test file:** `tests/test_startup_integration.py`
**New tests:** `TestMainIntegration` class (4 tests: first-run, normal, migration, newer-data)

### GREEN
Implement mock fixtures covering: `QApplication`, `QMessageBox`, `QTimer`, `DatabaseManager`, `CrashService`, all repos, all services, `MainWindow`, `ProcessMonitor`, `ThemeManager`, `_acquire_lock`.

Use `monkeypatch.setattr` for all PyQt6 classes and `unittest.mock.MagicMock` for services.

### REFACTOR
Create a `_mock_all_deps(tmp_path, monkeypatch)` helper fixture that returns a dict of mocks and a `sqlite3.Connection` for the database.

### Validation
```bash
python -m pytest tests/test_startup_integration.py::TestMainIntegration -x -v
```

---

## Step 6 — Backup Failure Test

### RED
Write a test that patches `BackupManager.create_backup()` to return failure and verifies `sys.exit(3)` is called.

**Test file:** `tests/test_startup_integration.py`
**Changes:** Replace `TestStartupBackupFailure.test_backup_failure_blocks` placeholder with real test

### GREEN
Use `monkeypatch.setattr` to replace `BackupManager.create_backup` with a function that returns `BackupResult(success=False, error="Simulated failure")`. Call main via the test infrastructure from Step 5. Expect `SystemExit(3)`.

### REFACTOR
Ensure the test reuses the mock infrastructure from Step 5's helper fixture.

### Validation
```bash
python -m pytest tests/test_startup_integration.py::TestStartupBackupFailure -x -v
```

---

## Step 7 — Architecture Validation

### RED
Ensure all architecture enforcement tests still pass after changes.

Tests:
- `tests/architecture/test_migration_isolation.py` — import restrictions
- No new forbidden imports introduced

### GREEN
Run architecture tests. If any fail, fix the import issues.

### REFACTOR
None needed — architecture rules are already enforced.

### Validation
```bash
python -m pytest tests/architecture/test_migration_isolation.py -x -v
```

---

## Step 8 — Final Validation

### RED
Full regression test suite — all tests must pass.

### GREEN

```bash
# All migration/startup/backup tests
python -m pytest tests/test_backup_manager.py tests/test_startup_integration.py tests/test_upgrade_lifecycle.py tests/test_migration_*.py tests/test_schema_version*.py tests/test_database_manager.py tests/architecture/test_migration_isolation.py -v

# Architecture enforcement
python -m pytest tests/architecture/test_migration_isolation.py -v
```

### REFACTOR
Address any test fragility (e.g., hardcoded `applied_count == 4`).

### Validation
All tests pass. Coverage report shows no decrease.
