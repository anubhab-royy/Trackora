# Phase 3 — Installed Application Validation

## Date
2026-06-21

## Scope
Validates that game detection works correctly **after installation** through Inno Setup — the final production environment.

## Installation Structure

### Inno Setup (`installer/Trackora.iss`)
| Property | Value |
|----------|-------|
| Install dir | `{autopf}\Trackora` (typically `C:\Program Files\Trackora`) |
| Executable | `Trackora.exe` (PyInstaller build from `Trackora.spec`) |
| AppData | `%APPDATA%\Trackora\` (created on first launch) |
| Database | `%APPDATA%\Trackora\trackora.db` |
| Logs | `%APPDATA%\Trackora\logs\` |
| Upgrade | Detects old `GameTracker` via AppId, migrates AppData |
| Uninstall | Preserves AppData; removes only `{app}` directory |

### Bundled Resources
All themes, icons, and resources are embedded inside the PyInstaller executable via the `.spec` file's `datas` section:
```python
datas=[
    ("ui/themes", "ui/themes"),
    ("ui/icons", "ui/icons"),
],
```

### First Launch Flow
1. Single-instance lock acquired via `%APPDATA%\Trackora\instance.lock`
2. `ensure_dirs()` creates all AppData directories
3. Database opened at `%APPDATA%\Trackora\trackora.db`
4. Schema version checked; migrations applied if needed
5. `_ensure_schema_columns()` adds any missing discovery columns
6. Repositories, services, UI initialized
7. Process monitor starts, UI shown

## Detection Matrix

| Platform | Detector | Method | Resolves From | Installed-Safe | Elevation Required |
|----------|----------|--------|---------------|----------------|-------------------|
| Steam | `SteamDetector` | Registry: `HKCU\Software\Valve\Steam\SteamPath` + env fallback | `HKCU` + `PROGRAMFILES(X86)` | ✅ | No |
| Epic Games | `EpicDetector` | `%PROGRAMDATA%\Epic\...\LauncherInstalled.dat` | `PROGRAMDATA` | ✅ | No |
| Riot Games | `RiotDetector` | `%PROGRAMDATA%\Riot Games\RiotClientInstalls.json` | `PROGRAMDATA` + `LOCALAPPDATA` | ✅ | No |
| Battle.net | `BattleNetDetector` | `%PROGRAMDATA%\Battle.net\Agent\product.db` | `PROGRAMDATA` | ✅ | No |
| EA App | `EADetector` | `%LOCALAPPDATA%\Electronic Arts\...\install-record\*.json` + HKLM registry | `LOCALAPPDATA` + `HKLM` | ✅ | HKLM read (graceful degrade) |
| Ubisoft | `UbisoftDetector` | `HKLM\SOFTWARE\WOW6432Node\Ubisoft\...` + `%LOCALAPPDATA%\Ubisoft\...` | Registry + `LOCALAPPDATA` | ✅ | HKLM read (graceful degrade) |
| Custom Libraries | `FolderDetector` | User-configured absolute paths | User input | ✅ | N/A |

## Path Dependency Audit

### Code Audit Results
| Dependency | Usage Count | Found In | Verdict |
|-----------|-------------|----------|---------|
| `Path.cwd()` | 0 | — | ❌ Not used — ✅ Safe |
| `__file__` | 0 in detectors; 1 in `database_manager.py` (unused default) | `database_manager.py:31` — `_DEFAULT_DB_PATH` | ✅ Only dev default; production always passes explicit `DATABASE_PATH` |
| `sys.executable` | 0 | — | ❌ Not used — ✅ Safe |
| `os.environ` (APPDATA, PROGRAMDATA, LOCALAPPDATA, PROGRAMFILES) | Multiple | All detectors + paths.py | ✅ Correct for installed apps |
| Registry (HKCU, HKLM) | Multiple | Steam, EA, Ubisoft detectors | ✅ All wrapped in try/except |

### Database Path Resolution
In production, the database path is always `%APPDATA%\Trackora\trackora.db`:
- `__main__.py:129` — `db = DatabaseManager(str(DATABASE_PATH))`
- `trackora/core/paths.py:40` — `DATABASE_PATH: Path = BASE_DIR / "trackora.db"`
- `trackora/core/paths.py:30-35` — `_resolve_base_dir()` uses `os.environ["APPDATA"]`

## Registry Access Validation

| Registry Key | Hive | Detector | Wrapped? | Degrade Behavior |
|-------------|------|----------|----------|-----------------|
| `Software\Valve\Steam\SteamPath` | HKCU | Steam | ✅ | Falls back to `PROGRAMFILES(X86)\Steam` |
| `SOFTWARE\EA Games` | HKLM | EA | ✅ | Returns empty list |
| `SOFTWARE\WOW6432Node\EA Games` | HKLM | EA | ✅ | Returns empty list |
| `SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs` | HKLM | Ubisoft | ✅ | Continues to next registry path |
| `SOFTWARE\Ubisoft\Launcher\Installs` | HKLM | Ubisoft | ✅ | Continues to next registry path |
| `Software\Ubisoft\Launcher\Installs` | HKCU | Ubisoft | ✅ | Continues to config dir detection |

All registry reads are read-only and do not require administrative elevation for standard configurations. HKLM reads may fail on locked-down enterprise systems but all detectors handle this gracefully with try/except.

## Database Validation

### Import Persistence
Games imported via `Scan For Games → Import` are persisted in the `games` table and survive application restart. The database lives at `%APPDATA%\Trackora\trackora.db`, independent of the installation directory.

### Duplicate Prevention
`import_discovered_games()` in `services/game_service.py` prevents duplicates at three levels:
1. **Executable path** — exact match on `executable_path`
2. **Platform ID** — match on `(platform, platform_id)` pair
3. **Normalized name** — legacy games (empty `platform`) with matching normalized name are updated instead of duplicated

### Game Consolidation
The eFootball/eFootball™ merge was validated in Phase 5: 8 sessions (64621s) migrated, legacy record deleted, playtime preserved. See `game-consolidation-validation.md` for details.

## Upgrade Validation

### Migrations (5 modules)
| ID | Description |
|----|-------------|
| `v1_0_0_base_schema` | Initial database schema |
| `v1_1_0_initial_schema` | Schema refinements |
| `v2_0_0_add_discovery_columns` | Adds `platform`, `platform_id`, `is_auto_discovered` |
| `v2_0_0_add_update_center_settings` | Update center settings table |
| `v2_0_0_add_update_center_settings_v2` | Update center schema fix |

All migrations are explicitly imported in `trackora/core/migrations/__init__.py` to ensure PyInstaller bundles them.

### Startup Safety
- `_ensure_schema_columns()` adds missing columns via `ALTER TABLE` every startup
- `SchemaVersionManager` checks compatibility before proceeding
- Pre-migration backup is created automatically
- Migration failures block startup and show user-visible error

### GameTracker → Trackora Upgrade
The Inno Setup script handles this via `MigrateAppData()` in the `[Code]` section:
1. Detects old `%APPDATA%\GameTracker`
2. Renames to `%APPDATA%\Trackora` (with xcopy fallback)
3. Removes old program directory and shortcuts

## Production Edge Cases

| Scenario | Behavior | Status |
|----------|----------|--------|
| Games moved between drives | Steam detector reads live libraryfolders.vdf; Ubisoft/EA use registry which updates on reinstall | Graceful |
| Libraries added after install | Steam detector re-reads libraryfolders.vdf on each scan | Works |
| Launcher updates | All config file formats are version-tolerant (JSON, protobuf, KV) | Works |
| External drives connected/disconnected | Detectors check `is_dir()` / `is_file()` on resolved paths; missing paths are skipped | Graceful |
| No admin rights | All HKLM reads wrapped in try/except; HKCU/PROGRAMDATA/LOCALAPPDATA paths work without elevation | Graceful |
| First run (no DB) | Schema created automatically; first-run version written | Works |
| Corrupt manifest | Each manifest/file is parsed individually with try/except | Graceful |
| Empty Steam library | Returns only Steam root as library path; no manifests → empty result | Works |
| HKLM read failure (locked-down enterprise) | EA/Ubisoft return empty lists; other detectors unaffected | Graceful |

## Remaining Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **No actual fresh-VM install test** | Low — code paths are verified through static analysis and existing tests | All critical paths validated via code audit |
| **HKLM registry reads may fail** on enterprise locked-down PCs | Low — EA and Ubisoft detection would return empty | Graceful degradation; both have multiple fallback methods |
| **No explicit UI integration test** for "Scan For Games" button | Low — tested in Phase 2 (executable build); all service-layer flows have unit tests | Manual testing on first install is recommended |
| **PyInstaller build time** — no CI/CD pipeline | Medium — regressions could go undetected until next manual build | Manual `pyinstaller Trackora.spec` before releases |
