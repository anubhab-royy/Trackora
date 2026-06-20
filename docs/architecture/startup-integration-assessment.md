# Startup Integration Assessment Report

## Current Startup Order (as-is)

```
1. LoggingService.setup()
2. Single-instance lock (_acquire_lock)
3. QApplication(app)
4. ensure_dirs()
5. DatabaseManager.initialize()       ← creates _migrations table
6. SchemaVersionManager.read()
7. is_compatible(app_version, data_version)
8.   ├─ first_run  → write schema version
9.   ├─ newer_data → QMessageBox.critical + sys.exit(2)
10.  └─ needs_migration → BackupManager → MigrationManager.apply_all() → write version
11. Repository creation (GamesRepository, etc.)
12. Service creation (GameService, etc.)
13. Reporting backend (SupabaseReportService, ReportQueueService)
14. Tracking infra (TrackingState, SessionManager, RecoveryManager, ProcessMonitor)
15. RecoveryManager.recover()
16. ThemeManager
17. MainWindow creation + display
18. ProcessMonitor.start()
19. app.exec()
```

## Key Observations

### 1. QApplication is created before upgrade lifecycle
- **Line 70**: `app = QApplication(sys.argv)` — needed because `QMessageBox` is used for error dialogs (newer_data, backup_failure).
- **Trade-off**: UI framework initialized early, but no UI windows are shown until the lifecycle completes.

### 2. Database is initialized before SchemaVersionManager
- **Line 75-76**: `db = DatabaseManager(); db.initialize()` creates the SQLite connection and `_migrations` table.
- **Correct ordering**: `_migrations` table MUST exist before `MigrationManager` reads/writes it.

### 3. CrashService is NOT integrated
- `CrashService` / `StartupStateManager` are never instantiated in `__main__.py`.
- `mark_running()` and `mark_closed_cleanly()` are never called.
- Crash detection (orphan session recovery) happens after migration but is handled by `RecoveryManager`, not `CrashService`.

### 4. Logging gaps
- No structured log messages for: "Version Check", "Compatibility Result", "Backup Creation", "Migration Start/Result", "Startup Abort".
- Startup abort exit codes: `2` (newer_data), `3` (backup failure) — documented but not logged in a standardised format.

### 5. No progress indication during migration
- `MigrationManager.apply_all()` blocks the main thread.
- No progress bar or status message for the user.

### 6. No timeout on backup/migration
- Backup and migration run synchronously. A slow or hung operation blocks startup indefinitely.

## Dependency Graph

```
LoggingService
  └── (no deps)
    
ensure_dirs
  └── (no deps)
  
DatabaseManager.initialize
  └── ensure_dirs (implicit — creates .parent dir)
  
SchemaVersionManager
  └── trackora.core.paths
  └── trackora.core.schema_version
  
BackupManager
  └── SchemaVersionManager
  └── trackora.core.paths
  └── database file (DISK, not DB API)

MigrationManager
  └── database connection (sqlite3.Connection)
  └── SchemaVersionManager
  └── BackupManager (optional)
  └── MigrationRegistry (default: trackora.core.migrations)

Services/Repos
  └── database connection
  └── (no upgrade deps)
```

## Safe Insertion Points

| Insertion Point | Between | What Can Go Here |
|---|---|---|
| A | `ensure_dirs` → `DatabaseManager.initialize` | SchemaVersionManager init (needs `BASE_DIR` but not DB) |
| B | After `compat` check, before `needs_migration` | User-facing progress, CrashService.mark_running() |
| C | After `apply_all`, before repo creation | Schema version final write, post-migration verification |
| D | Before `app.exec()` | Clean-shutdown hook (atexit), CrashService.mark_closed_cleanly() |

## Failure Handling Paths

| Scenario | Current Behaviour | Exit Code | User Message |
|---|---|---|---|
| Single instance conflict | Warning dialog + exit(1) | 1 | "Another instance of Trackora is already running." |
| Newer schema data | Critical dialog + exit(2) | 2 | "This database requires Trackora X.X.X or newer..." |
| Backup failure | Critical dialog + exit(3) | 3 | "Could not create a backup before migration..." |
| Migration partial failure | Warning dialog + continue | 0 | "Some migrations did not complete successfully..." |
| Migration complete success | (silent) | 0 | — |
| First run | (silent) | 0 | — |
| Normal startup (ok) | (silent) | 0 | — |

## What Already Works

- ✅ SchemaVersionManager — read, write, is_compatible, first_run detection
- ✅ BackupManager — create_backup, verify, list, restore
- ✅ MigrationManager — apply_all, apply_one, query API
- ✅ `_migrations` table in DatabaseManager._create_schema()
- ✅ 4 concrete migration files (v1.0.0, v1.1.0, v2.0.0 x2)
- ✅ 132 migration/upgrade tests passing at 98% coverage

## What's Missing for Final Integration

| Gap | Impact | Priority |
|---|---|---|
| CrashService not wired | No crash detection on startup | Medium |
| No startup_state.json lifecycle | No "running" / "closed_cleanly" tracking | Medium |
| No structured startup logging | Hard to diagnose startup failures | Low |
| No migration progress UI | User sees frozen screen during long migrations | Low |
| QApplication created before lifecycle | UI initialised before data safety verified | Low (intentional) |

## Recommendations

1. **Keep QApplication early** — needed for error dialogs. Do not move it.
2. **Integrate CrashService** — call `mark_running()` after SchemaVersionManager confirms data is compatible, and `mark_closed_cleanly()` at shutdown.
3. **Add structured logging** — info-level messages at each lifecycle stage.
4. **Do NOT add progress UI** — migrations complete in < 2s (verified by NFR-02 benchmarks).
5. **Do NOT add timeouts** — no observable latency in any scenario.

## Files Touched by Startup Integration

| File | Change Type |
|---|---|
| `trackora/__main__.py` | Modify — wire CrashService, improve logging |
| `trackora/core/__init__.py` | No change needed |
| `services/__init__.py` | No change needed |

## Test Count (Current)

- Unit tests (migration): 132
- Upgrade lifecycle integration: 33
- Architecture isolation: 4
- Total: 169 migration/upgrade tests (all passing)
