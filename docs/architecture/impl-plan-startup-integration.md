# Startup Integration — Implementation Plan

## Summary

The existing `__main__.py` already has a working upgrade lifecycle (SchemaVersionManager → BackupManager → MigrationManager). This plan covers the remaining gaps identified in the Startup Audit:

1. Wire `CrashService` / `StartupStateManager` for crash detection lifecycle
2. Add structured logging at each lifecycle stage
3. Add proper `atexit` clean-shutdown marking

## Files to Modify

| File | Change |
|---|---|
| `trackora/__main__.py` | Wire CrashService, add structured logging, add atexit clean-shutdown |

## Files to Create

| File | Change |
|---|---|
| `tests/test_startup_integration.py` | Integration tests for the full startup lifecycle (new) |

## No Files to Change (already correct)

- `trackora/core/schema_version_manager.py` — no changes needed
- `trackora/core/backup_manager.py` — no changes needed
- `trackora/core/migration_manager.py` — no changes needed
- `trackora/core/paths.py` — no changes needed
- `database/database_manager.py` — no changes needed

## Integration Points

### Point A — After compatibility check, before upgrade lifecycle

Insert `CrashService.mark_running()`:
```python
# After compat decision, before entering upgrade lifecycle
crash_service = CrashService(
    diagnostic_service=DiagnosticService(),
)
crash_service.mark_startup()
```

### Point B — Structured logging

Add `INFO`-level log calls at each lifecycle stage:
```python
logger.info("Trackora starting — version %s, environment %s", app_version, CURRENT_ENVIRONMENT)
logger.info("App version: %s, Data version: %s | status: %s", app_version, data_version, compat.status)
logger.info("Pre-migration backup completed: %s", bk.backup_id)
# etc.
```

### Point C — Clean shutdown

Replace bare `sys.exit(app.exec())` with a shutdown sequence that marks clean state:
```python
import atexit
atexit.register(crash_service.mark_clean_shutdown)
sys.exit(app.exec())
```

## Error Handling

| Scenario | Handling |
|---|---|
| `DiagnosticService` init failure | Catch, log warning, continue without crash service |
| `CrashService.mark_running()` disk error | Log warning, continue — not critical |
| `CrashService.mark_clean_shutdown()` error | Log warning (atexit → can't propagate) |

## Acceptance Criteria

```
✅ First-run creates schema.json, no backup, no migration
✅ First-run log messages correct
✅ Normal startup (same version) → no backup, no migration
✅ Correct "compat ok" log messages
✅ Migration startup → backup created → migrations applied → version written
✅ Correct "migration needed" log messages
✅ Newer-data → blocked → exit(2) → correct log messages
✅ Backup failure → blocked → exit(3) → correct log messages
✅ Partial migration → warning dialog → continue → correct log messages
✅ CrashService.mark_running() called after compat check
✅ CrashService.mark_clean_shutdown() called via atexit
✅ Structured logging at every lifecycle stage
✅ Full regression passes (132 existing migration tests + new)
✅ Architecture isolation intact (no forbidden imports)
```

## Testing Strategy

### New Test File: `tests/test_startup_integration.py`

| Test | Type | Description |
|---|---|---|
| `test_startup_logging_first_run` | Unit | Verify log messages for first-run path |
| `test_startup_logging_normal` | Unit | Verify log messages for same-version path |
| `test_startup_logging_migration` | Unit | Verify log messages for migration path |
| `test_startup_logging_newer_data` | Unit | Verify log messages + exit for newer_data |
| `test_startup_logging_backup_failure` | Unit | Verify log messages + exit for backup failure |
| `test_crash_service_wired` | Integration | Verify CrashService.mark_running() is called |
| `test_clean_shutdown_registered` | Integration | Verify atexit handler for mark_clean_shutdown |
| `test_startup_full_lifecycle` | Integration | End-to-end: dirs → DB → SV → backup → migrate → repos → services |

### Existing Tests (must still pass)

All 132 migration/upgrade tests + 33 lifecycle tests + 4 architecture tests.

## Dependency Graph (post-integration)

```
LoggingService.setup()
  └── no deps

ensure_dirs()
  └── no deps

DatabaseManager.initialize()
  └── ensure_dirs (implied)

SchemaVersionManager.read()
  └── BASE_DIR exists (from ensure_dirs)

CrashService.mark_startup()
  └── BASE_DIR exists (from ensure_dirs)
  └── NOT called if startup is blocked (exit 2 or 3)

BackupManager.create_backup()
  └── SchemaVersionManager
  └── BACKUPS_DIR exists (from ensure_dirs)

MigrationManager.apply_all()
  └── DB connection (from DatabaseManager)
  └── SchemaVersionManager
  └── BackupManager (optional)

Repositories
  └── DB connection

Services
  └── Repositories

CrashService.mark_clean_shutdown() (atexit)
  └── no deps (always safe to call)
```
