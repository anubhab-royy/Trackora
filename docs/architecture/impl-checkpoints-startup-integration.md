# Startup Integration — Implementation Checkpoints

## Step 1 — Startup Integration Tests

Create the test file that will drive implementation.

### RED
Write tests for all startup integration scenarios:
- First-run logging
- Normal startup (same-version) logging
- Migration-needed logging  
- Newer-data logging + exit code
- Backup failure logging + exit code
- Partial migration logging
- CrashService.mark_running() called
- Clean shutdown registered

**Files Created:**
- `tests/test_startup_integration.py`

**Validation:**
```bash
python -m pytest tests/test_startup_integration.py --tb=short
# Expected: all RED (fail) — `__main__.py` not yet updated
```

### GREEN
No code changes. Tests may pass if existing behaviour already correct.

If all pass: mark GREEN and move to Step 2.
If some fail: those define the scope for Step 2+.

### REFACTOR
None.

---

## Step 2 — SchemaVersionManager Integration

Ensure schema version is read, logged, and acted upon correctly.

### RED
Tests already written in Step 1. Verify first-run, normal, newer-data tests fail if logging is missing.

### GREEN
Update `__main__.py` to add structured logging at version-check stage.

**Files Modified:**
- `trackora/__main__.py`

**Changes:**
```python
# After line 83 (is_compatible):
logger.info(
    "App version: %s, Data version: %s | status: %s",
    app_version, data_version, compat.status,
)
```

**Validation:**
```bash
python -m pytest tests/test_startup_integration.py --tb=short -v
python -m pytest tests/test_upgrade_lifecycle.py --tb=short -v
```

### REFACTOR
Review log message format for consistency. Ensure `CURRENT_ENVIRONMENT` is logged at startup start.

---

## Step 3 — MigrationManager Integration

Ensure migration lifecycle produces correct log messages.

### RED
Tests for migration-needed, backup-failure, partial-migration scenarios should fail.

### GREEN
Update `__main__.py` to add structured logging at each migration stage.

**Files Modified:**
- `trackora/__main__.py`

**Validation:**
```bash
python -m pytest tests/test_startup_integration.py --tb=short -v
```

### REFACTOR
Ensure log messages match the format specified in the architecture spec (Section 11).

---

## Step 4 — Startup Error Handling

Wire CrashService and add atexit clean-shutdown.

### RED
Tests for `CrashService.mark_running()` and `mark_clean_shutdown()` fail.

### GREEN
Update `__main__.py` to:
1. Import and create `CrashService` + `DiagnosticService`
2. Call `crash_service.mark_startup()` after compat check passes
3. Register `atexit.register(crash_service.mark_clean_shutdown)` before `app.exec()`

**Files Modified:**
- `trackora/__main__.py`

**Validation:**
```bash
python -m pytest tests/test_startup_integration.py --tb=short -v
```

### REFACTOR
- Move `CrashService` creation to a helper function if it grows too complex
- Verify graceful degradation if `CrashService` init fails

---

## Step 5 — Integration Tests

Verify the full startup lifecycle end-to-end.

### RED
Write end-to-end tests that simulate:
1. Full first-run: `ensure_dirs` → DB init → SV read= None → SV write → repos → services
2. Full same-version: DB init → SV read=1.0.0 → compat ok → repos → services
3. Full migration: DB init → SV read=1.0.0 → compat needs_migration → backup → migrate → SV write=2.0.0 → repos → services
4. Newer data block: DB init → SV read=99.0.0 → compat newer_data → exit(2)
5. Backup failure block: DB init → SV read=1.0.0 → compat needs_migration → backup fails → exit(3)

### GREEN
These tests should pass after Steps 2-4 are complete.

**Validation:**
```bash
python -m pytest tests/test_startup_integration.py -v --tb=short 2>&1 | tail -30
```

### REFACTOR
- Extract repeated test setup into fixtures
- Verify test isolation (no cross-test state leaks)

---

## Step 6 — Architecture Tests

Verify startup integration follows architecture rules.

### RED
Write architecture tests that enforce:
- `__main__.py` does not import from `database` directly (already satisfied — uses `DatabaseManager`)
- Upgrade lifecycle runs before service/UI imports are resolved
- No circular imports introduced

**Files Created/Modified:**
- `tests/architecture/test_startup_integration_isolation.py`

### GREEN
These tests should pass if Step 2-4 maintain clean architecture.

**Validation:**
```bash
python -m pytest tests/architecture/test_startup_integration_isolation.py -v
```

### REFACTOR
None.

---

## Step 7 — Final Validation

Full regression suite.

### RED
N/A — final validation.

### GREEN
```bash
# All startup integration tests
python -m pytest tests/test_startup_integration.py -v --tb=short

# All migration/upgrade tests
python -m pytest tests/test_migration_abc.py tests/test_migration_registry.py tests/test_migration_manager.py tests/test_upgrade_lifecycle.py tests/test_migration_phase6f.py -v --tb=short

# All architecture tests
python -m pytest tests/architecture/test_migration_isolation.py tests/architecture/test_startup_integration_isolation.py -v --tb=short

# Full regression (excluding known CXXABI failures)
python -m pytest --tb=short -q --ignore=tests/test_crash_dialog.py --ignore=tests/test_dashboard_controller.py --ignore=tests/test_history_controller.py --ignore=tests/test_reporting_interface.py --ignore=tests/test_support_center_controller.py --ignore=tests/test_crash_service.py --ignore=tests/test_diagnostic_service.py --ignore=tests/test_export_service.py --ignore=tests/test_game_service.py --ignore=tests/test_github_issue_service.py --ignore=tests/test_logging_service.py --ignore=tests/test_report_queue_service.py --ignore=tests/test_startup_service.py --ignore=tests/test_supabase_report_service.py --ignore=tests/test_support_service.py --ignore=tests/test_tray_service.py --ignore=tests/test_update_announcements_service.py

# Coverage
python -m pytest tests/test_startup_integration.py tests/test_migration_abc.py tests/test_migration_registry.py tests/test_migration_manager.py tests/test_upgrade_lifecycle.py tests/test_migration_phase6f.py tests/architecture/test_migration_isolation.py tests/architecture/test_startup_integration_isolation.py --cov=trackora.core --cov=trackora.core.migrations --cov-report=term-missing --tb=short
```

### REFACTOR
- Address any warnings
- Verify no dead code introduced
- Update `AGENTS.md` if new conventions emerged
