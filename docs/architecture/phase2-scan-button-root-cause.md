# Phase 2 Root Cause: Scan For Games Button — "Nothing Happens"

## Symptom
Clicking the **Scan For Games** button in `Trackora.exe` produces no visible
response — no dialog, no error message, no games imported.

## Root Cause — Three-Layer Failure

### Layer 1: Missing Database Columns (Proximate Cause)
The production database at `%APPDATA%\Trackora\trackora.db` was created with a
v1 schema that has **10 columns** on the `games` table:

```
id, name, process_name, executable_path, icon_path,
is_enabled, first_played, last_played, created_at, updated_at
```

The v2 code expects **13 columns**, adding:

```
platform         TEXT DEFAULT NULL
platform_id      TEXT DEFAULT NULL
is_auto_discovered INTEGER DEFAULT 0
```

When `_row_to_game()` accessed `row["platform"]` on old rows, `sqlite3.Row`
raised `IndexError: No item with that key`. This caused a cascade of failures:

1. `game_service.get_all_games()` → error → returns `[]` (games list always empty)
2. `orchestrator._exclude_existing()` → calls `exists_by_platform_id()` →
   `OperationalError: no such column: platform` → exception propagates through
   `scan_all()` → **no summary log** → dialog never displays

### Layer 2: Migration Never Ran in Frozen Executable
The `v2_0_0_add_discovery_columns` migration adds the missing columns.
`MigrationRegistry.discover()` uses `pkgutil.iter_modules()` which scans the
filesystem for migration modules. **This does not work inside a PyInstaller
bundle** because modules live in an archive, not on the filesystem.

Result: `get_pending_migrations()` returned `[]` → `apply_all()` returned
immediately with `success=True, applied_count=0` → schema.json was written as
"2.0.0" without any columns actually being added. Subsequent startups saw
`schema_version = 2.0.0 == app_version 2.0.0` → "ok" → no migration path
triggered.

### Layer 3: Silently Swallowed Exceptions
Even when the database error occurred, no user-visible feedback was produced:

- `games_controller._on_scan_requested()` had no try/except
- `discovery_dialog._run_scan()` had no try/except around `scan_all()`
- PyQt catches exceptions in slots and writes them to stderr (which goes to
  `/dev/null` in a `console=False` GUI app)
- The dialog constructor raised → `dialog` variable never assigned →
  `dialog.exec()` raises `NameError` → PyQt catches it → user sees nothing

## Files Affected
- `database/repositories/games_repository.py:26-45` — `_row_to_game`
- `tracker/discovery/orchestrator.py:147-163` — `_exclude_existing`
- `trackora/core/migrations/registry.py:41-112` — `MigrationRegistry.discover()`
- `trackora/core/migrations/__init__.py` — explicit migration imports
- `ui/games/games_controller.py:93-119` — `_on_scan_requested`
- `ui/games/discovery_dialog.py:133-169` — `_run_scan`
- `trackora/__main__.py` — `_ensure_schema_columns` startup check
