# Startup Integration — Architecture Specification

## 1. Startup Lifecycle Diagram

```
Application Start
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 1. LoggingService.setup()                           │
│    • Configure daily rotating file handler          │
│    • Configure console handler (dev only)           │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 2. Single-instance check                            │
│    • acquire_lock() → exit(1) if another instance   │
│    • atexit register release_lock                   │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 3. QApplication(sys.argv)                           │
│    • Required early for QMessageBox in error paths  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 4. ensure_dirs()                                    │
│    • Creates BASE_DIR, logs, backups, reports, ...  │
│    • Must succeed or startup is aborted             │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 5. DatabaseManager.initialize()                     │
│    • Open / create SQLite database                  │
│    • Apply PRAGMAs (WAL, foreign_keys, busy_timeout)│
│    • Create all tables + indexes (idempotent)       │
│    • Includes _migrations table                     │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 6. SchemaVersionManager.read()                      │
│    • Reads BASE_DIR/schema.json                     │
│    • Returns SchemaVersion or None (first run)      │
│    • Renames corrupt files → raises                 │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 7. is_compatible(app_version, data_version)         │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────┴───────┐  │
│  │ first_run│  │    ok    │  │needs_mig │  │  newer_data   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬───────┘  │
│       │             │            │             │              │
│       ▼             ▼            ▼             ▼              │
│   Write ver     Continue    Enter          Block +           │
│   + continue               Upgrade        exit(2)            │
│                             Lifecycle                        │
└───────────────────────────────────────────────────────────────┘
    │
    ▼  (needs_migration path only)
┌─────────────────────────────────────────────────────┐
│ 8. Upgrade Lifecycle                                │
│    • See Section 2 below                            │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 9. Repository Layer                                 │
│    • GamesRepository, SessionsRepository,           │
│      ActiveSessionsRepository, SettingsRepository   │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│10. Service Layer                                    │
│    • GameService, StatisticsService,                │
│      ExportService, PlaytimeCalculator              │
│    • Reporting: SupabaseReportService,              │
│      ReportQueueService, SupportService             │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│11. Tracking Infrastructure                          │
│    • TrackingState, SessionManager,                 │
│      RecoveryManager, ProcessMonitor                │
│    • RecoveryManager.recover() — orphaned sessions  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│12. ThemeManager + MainWindow creation               │
│    • Apply theme                                    │
│    • Create MainWindow with all services injected   │
│    • Show window                                    │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│13. ProcessMonitor.start()                           │
│    • Begin background game tracking                 │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│14. app.exec() — Enter Qt event loop                 │
│    • On exit: atexit handlers fire                  │
└─────────────────────────────────────────────────────┘
```

## 2. Upgrade Lifecycle Diagram

```
Enter Upgrade Lifecycle (status == "needs_migration")
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 2a. SchemaVersionManager.write()  (optional)        │
│     Write current-app version to schema.json        │
│     BEFORE migration (mark as "migration in flight")│
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 2b. BackupManager.create_backup(pre_migration)      │
│     • Creates self-verifying ZIP                    │
│     • Includes db, schema.json, manifest            │
│     │                                               │
│     ├── Success → continue                          │
│     └── Failure → QMessageBox.critical + exit(3)    │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 2c. MigrationManager.apply_all()                    │
│     • Discover pending migrations (sorted by ID)    │
│     • For each migration:                           │
│       │                                             │
│       ├── SAVEPOINT → upgrade() → verify()          │
│       ├── Success → record in _migrations, RELEASE  │
│       └── Failure → ROLLBACK, continue to next      │
│     • Write final schema version (if all OK)        │
│     │                                               │
│     ├── All succeed → continue normally             │
│     ├── Partial fail → QMessageBox.warning + cont.  │
│     └── Schema write skipped on partial failure     │
└─────────────────────────────────────────────────────┘
    │
    ▼
    Continue to Repository Layer
```

## 3. First-Run Behaviour

| Aspect | Behaviour |
|---|---|
| **Detection** | `SchemaVersionManager.read()` returns `None` (no `schema.json`) |
| **Decision** | `is_compatible(None)` → `CompatibilityStatus(status="first_run")` |
| **Schema write** | Write current `app_version` to `schema.json` immediately |
| **Migration** | Skipped entirely — no backup, no `MigrationManager.apply_all()` |
| **Repositories** | Created normally — `DatabaseManager._create_schema()` creates all tables |
| **User experience** | No prompts, no dialogs — silent first-launch normalization |
| **Logging** | `"First run — schema version set to X.X.X"` |

### Rationale

On first run there is no user data to protect and no schema to upgrade. The base schema is created by `DatabaseManager._create_schema()` (which runs before the upgrade lifecycle). Recording the schema version creates the anchor for future migrations.

## 4. Existing-User Behaviour (Normal Startup — same version)

| Aspect | Behaviour |
|---|---|
| **Detection** | `data_version == app_version` |
| **Decision** | `CompatibilityStatus(status="ok", can_proceed=True)` |
| **Schema write** | No change |
| **Migration** | Skipped |
| **Backup** | Skipped |
| **User experience** | No prompts — startup proceeds exactly as before |
| **Logging** | No upgrade-related logs |

## 5. Migration-Needed Behaviour

| Aspect | Behaviour |
|---|---|
| **Detection** | `data_version < app_version` |
| **Decision** | `CompatibilityStatus(status="needs_migration")` |
| **Backup** | `BackupManager.create_backup(backup_type="pre_migration")` — mandatory |
| **Migration** | `MigrationManager.apply_all()` — discovers + applies pending migrations |
| **Schema write** | After all migrations succeed → write `final_version` to `schema.json` |
| **On partial failure** | Show warning dialog — do NOT update schema version |
| **User experience** | Warning dialog only if migration fails; progress bar optional |
| **Logging** | Full lifecycle logged — see Section 11 |

## 6. Newer-Schema Behaviour (Block)

| Aspect | Behaviour |
|---|---|
| **Detection** | `data_version > app_version` |
| **Decision** | `CompatibilityStatus(status="newer_data", can_proceed=False)` |
| **User message** | `QMessageBox.critical("This database requires Trackora X.X.X or newer...")` |
| **Exit code** | `sys.exit(2)` |
| **Recovery** | User must update Trackora to the required version |
| **Logging** | `CRITICAL: "Startup blocked: ..."` |

## 7. Failure Handling

| Failure | Detection | User-Facing | Exit Code | Recovery |
|---|---|---|---|---|
| Single instance | `acquire_lock()` returns False | Warning dialog | 1 | Close other instance |
| Newer schema | `is_compatible().status == "newer_data"` | Critical dialog | 2 | Update Trackora |
| Backup failure | `BackupManager.create_backup()` returns `!success` | Critical dialog | 3 | Free disk space, check permissions |
| Migration upgrade() fail | Exception in `upgrade()` | Warning dialog | 0 | Restore from backup |
| Migration verify() fail | `verify()` returns errors | Warning dialog | 0 | Restore from backup |
| Corrupt schema.json | `read()` raises `SchemaVersionError` | Renamed to `.corrupt`; treated as first-run | 0 | (automatic) |
| DB init failure | `DatabaseManager.initialize()` raises | (bubbles up) | 1 | Check DB file |
| ensure_dirs failure | `OSError` from `mkdir()` | (bubbles up) | 1 | Check permissions |

### Exit Code Reference

| Code | Meaning |
|---|---|
| 0 | Normal startup (including first-run, same-version, partial migration) |
| 1 | Single-instance conflict / fatal OS error |
| 2 | Newer schema data — update required |
| 3 | Pre-migration backup failed |

## 8. Recovery Handling

### Corrupt Schema Recovery

If `schema.json` is corrupt:
1. `SchemaVersionManager.read()` detects corrupt JSON or missing fields
2. File is renamed to `schema.json.corrupt.<timestamp>` (preserved for forensics)
3. `SchemaVersionError` is raised
4. In `__main__.py`, the exception is caught → file renamed → retry as first-run

### Crash Recovery

If the application crashes:
1. On next startup, `StartupStateManager.detect_crash()` sees `"running"` (never set to `"closed_cleanly"`)
2. `CrashService.check_for_crash()` generates a crash report
3. `RecoveryManager.recover()` handles orphaned database sessions

### Migration Failure Recovery

If a migration fails:
1. Individual migration is rolled back via SAVEPOINT
2. Schema version is NOT updated (remains at pre-migration version)
3. User is shown a warning dialog
4. Pre-migration backup (created by `BackupManager`) is available for full restore
5. User can restore manually via `BackupManager.restore(backup_id)`

## 9. Rollback Handling

### Per-Migration Rollback

```python
SAVEPOINT mig_<migration_id>
  upgrade(connection)
  verify(connection)  → if errors, ROLLBACK TO SAVEPOINT
RELEASE SAVEPOINT     → on success
```

- Each migration's changes are atomic
- If `upgrade()` or `verify()` fails, only that migration's changes are undone
- Previously applied migrations remain applied
- `_migrations` table is NOT updated for the failed migration

### Full Restore

```python
BackupManager.restore(backup_id)
  → safety_backup created before overwrite
  → original files restored from backup ZIP
  → VerificationResult returned
```

- Full backup is available for manual restore
- Safety backup is created automatically during restore (protects current state)

## 10. User Experience Requirements

| Scenario | UX |
|---|---|
| First run | Silent — no prompts |
| Normal startup | Silent — no prompts |
| Migration needed | Silent if all succeed — warning dialog only on failure |
| Newer schema | Critical error dialog — cannot dismiss |
| Backup failure | Critical error dialog — cannot dismiss |
| Partial migration failure | Warning dialog — startup continues with degraded state |

All dialogs:
- Are modal (block startup until dismissed)
- Use platform-native Qt widgets (`QMessageBox`)
- Show actionable messages (not stack traces)
- Suggest next steps where applicable

## 11. Logging Requirements

Every startup must produce a clear audit trail. The following log messages shall be emitted at `INFO` level or above:

```
# Startup Begin
INFO   __main__ | Trackora starting — version X.X.X, environment {dev|prod}

# Version Check
INFO   schema_version_manager | Schema version read: X.X.X
INFO   __main__ | App version: X.X.X, Data version: X.X.X | compat status: {first_run|ok|needs_migration|newer_data}

# First Run
INFO   __main__ | First run — schema version set to X.X.X

# Upgrade Lifecycle
INFO   __main__ | Pre-migration backup started
INFO   backup_manager | Backup created: {backup_id} ({size} bytes, {n} files)
INFO   __main__ | Pre-migration backup completed: {backup_id}
INFO   __main__ | Migration started — {n} pending
INFO   __main__ | Migration applied: {migration_id} ({duration_ms}ms)
WARNING __main__ | Migration failed: {migration_id} ({duration_ms}ms) — {error}
INFO   __main__ | Migration completed — applied: {n}, failed: {n}
INFO   __main__ | Schema version updated to X.X.X

# Normal Continuation
INFO   __main__ | Database version matches app version — no migration needed

# Startup Complete
INFO   __main__ | Trackora started — database: {path}

# Startup Abort
CRITICAL __main__ | Startup blocked: {reason}
CRITICAL __main__ | Pre-migration backup failed: {error}
```

## 12. Future Extensibility

### Adding a new startup phase

To add a new phase to the startup lifecycle:
1. Insert the phase at the correct position in `__main__.py` `main()`
2. Add corresponding logging
3. Handle failure with appropriate exit code and user dialog
4. Wire error recovery if needed

### Runtime environment flags

The environment (`DEVELOPMENT` / `PRODUCTION`) is resolved by `trackora.core.environment.CURRENT_ENVIRONMENT` at module load time. Startup behaviour may diverge based on environment:

- **DEVELOPMENT**: Verbose console logging, relaxed file-permission checks
- **PRODUCTION**: Minimal console logging, strict validation

### Adding a new compatible-compatibility status

To add a new `is_compatible()` status:
1. Add the branch to `SchemaVersionManager.is_compatible()`
2. Handle the new status in `__main__.py` main() switch
3. Map to `CompatibilityStatus` with `can_proceed`, `status`, `message`
4. Add tests for the new path

### Extending the upgrade lifecycle

The upgrade lifecycle is a linear sequence of:
```
backup → [per-migration: upgrade + verify] → version write
```

To insert additional steps (e.g., pre-migration hooks, post-migration validation):
1. Add the step between the current positions in the sequence
2. Use `SAVEPOINT` for atomicity if the step modifies the database
3. Log the step with standardised format

## 13. Architecture Rules

```
Do NOT import:
  ├── database/*          in any startup-phase code (already satisfied)
  ├── services/*          before migration completion (already satisfied)
  ├── ui/*                before migration completion (already satisfied)
  └── trackora_stats/*    before migration completion (already satisfied)

Do NOT add dependencies:
  ├── MongoDB, Redis, or any external store
  ├── Update Center logic
  └── Game Discovery logic

Do NOT modify:
  ├── MigrationManager architecture
  ├── BackupManager architecture
  └── SchemaVersionManager architecture
```

## 14. Decision Log

| Decision | Rationale | Date |
|---|---|---|
| QApplication created before upgrade lifecycle | Needed for QMessageBox in error dialogs | 2026-06-20 |
| DB initialized before SchemaVersionManager | _migrations table must exist before MigrationManager runs | 2026-06-20 |
| CrashService wired after compatibility check | No point tracking crash state if startup is blocked | 2026-06-20 |
| Pre-migration backup failure = abort | Data safety is non-negotiable | 2026-06-20 |
| Partial migration failure = continue with warning | Better to start with degraded state than deny access | 2026-06-20 |
| Schema version NOT written on partial failure | Prevents silent future-schema gaps | 2026-06-20 |
| No progress bar for migration | All migrations benchmarked < 2s — UI overhead unwarranted | 2026-06-20 |
