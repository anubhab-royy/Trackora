# Phase 2 Fix: Scan For Games Button — Changes Summary

## Fix 1: Defensive `_row_to_game` (`database/repositories/games_repository.py`)
Added `_safe_get()` helper that catches `IndexError`/`KeyError` when accessing
columns that may not exist in older schemas:

```python
def _safe_get(row: sqlite3.Row, key: str, default: object = None) -> object:
    try:
        return row[key]
    except (IndexError, KeyError):
        return default
```

All column accesses in `_row_to_game` now go through `_safe_get()`, providing
sensible defaults for `platform`, `platform_id`, `is_auto_discovered`,
`icon_path`, `first_played`, `last_played`, `created_at`, `updated_at`.

## Fix 2: Graceful `_exclude_existing` (`tracker/discovery/orchestrator.py`)
Wrapped each candidate-existence check in try/except so that database errors
(missing columns, connection issues) are logged as warnings and the candidate
is **included** (safe default — "not yet tracked") rather than crashing the
scan:

```python
try:
    # Check by platform_id / executable_path
    ...
except Exception as exc:
    logger.warning("Error checking existence for %r: %s", c.name, exc)
    filtered.append(c)
```

## Fix 3: `MigrationRegistry.discover()` Frozen-Mode Fallback
(`trackora/core/migrations/registry.py`)
Added a `sys.modules` fallback strategy. In frozen executables,
`pkgutil.iter_modules()` returns nothing because modules aren't on the
filesystem. The fallback scans `sys.modules` for already-loaded migration
modules (imported by `__init__.py`):

1. **Strategy 1**: `pkgutil.iter_modules()` — works in source mode
2. **Strategy 2**: `sys.modules` scan for `trackora.core.migrations.*` — works
   in frozen mode when `__init__.py` has explicit imports

## Fix 4: `__init__.py` Explicit Imports (`trackora/core/migrations/__init__.py`)
Each migration module is now explicitly imported so PyInstaller bundles it and
`sys.modules` has it at runtime:

```python
from trackora.core.migrations import (
    v1_0_0_base_schema,
    v1_1_0_initial_schema,
    v2_0_0_add_discovery_columns,
    v2_0_0_add_update_center_settings,
    v2_0_0_add_update_center_settings_v2,
)
```

## Fix 5: `_ensure_schema_columns` Startup Check (`trackora/__main__.py`)
Added a lightweight schema verification that runs on every startup when the
schema version matches. Checks if the `games` table has the expected columns
and adds them directly via `ALTER TABLE` if missing:

```python
elif compat.status == "ok":
    _ensure_schema_columns(conn)
```

This handles the case where a previous build wrote `schema.json` with version
"2.0.0" without actually running the `v2_0_0_add_discovery_columns` migration.

## Fix 6: Exception Handling in UI Layer
- **`games_controller._on_scan_requested()`**: Wrapped dialog creation and
  import in try/except blocks that show user-visible error dialogs via
  `self._view.show_error()` instead of silently failing.
- **`discovery_dialog._run_scan()`**: Wrapped `scan_all()` call in try/except
  that shows the error in the dialog's heading and status labels.
- **`discovery_dialog._populate_table()`**: Wrapped each row in try/except so
  a corrupt candidate doesn't prevent the rest of the table from rendering.

## Verification
1. **235 tests pass** (89 discovery + 26 migration_registry + 26 migration_abc
   + 54 migration_manager/phase6f + 40 game_service + 8 update_center)
2. **Full scan flow validated** against the actual production database:
   - `scan_all()` returns 3 candidates with 0 errors
   - `import_discovered_games()` imports all 3 successfully
   - Old games (v1 schema) load without errors via `_safe_get`
3. **Executable startup clean**: "Tracked games reloaded: 3 games", zero errors
4. **Missing columns added** automatically on first startup with fixed build:
   `platform`, `platform_id`, `is_auto_discovered`
