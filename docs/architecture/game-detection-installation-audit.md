# Game Detection — Installation Audit

## Date
2026-06-21

## Installer
`installer/Trackora.iss` → `installer/Output/Trackora-Setup-2.0.0.exe`

## Installation Target
`{autopf}\Trackora` → `C:\Program Files\Trackora\Trackora.exe`

## Bundled Assets

### Executable (`Trackora.exe`)
- Built via `pyinstaller Trackora.spec`
- Console=False (windowed GUI application)
- UPX-compressed
- Version info from `version_info.txt`
- Icon from `ui/icons/app_icon.ico`

### Embedded Resources (inside .exe via datas)
| Source | Dest in bundle |
|--------|---------------|
| `ui/themes/` | `ui/themes/` |
| `ui/icons/` | `ui/icons/` |

### Hidden Imports (PyInstaller finds these)
All first-party packages explicitly listed in `hiddenimports`:
- `database`, `database.models`, `database.repositories`
- `services`, `services.crash`, `services.support`, `services.update_service`
- `trackora`, `trackora.core`, `trackora.core.migrations`
- `trackora_stats`
- `tracker`, `tracker.discovery`, `tracker.discovery.detectors`
- `ui`, `ui.dashboard`, `ui.dialogs`, `ui.games`, `ui.history`, `ui.settings`, `ui.themes`, `ui.widgets`

Third-party hidden imports:
- `PyQt6.QtSvg`, `pyqtgraph`, `psutil`, `pymongo`, `dns`, `bson`

### Excluded (not bundled)
- `tkinter`, `PyQt5`, `PySide2`, `PySide6` — other GUI frameworks
- `matplotlib`, `mpl_toolkits` — large, unused
- `test`, `unittest`, `pytest`, `_pytest`, `tests` — test infrastructure
- `scipy`, `cupy`, `h5py`, `numba`, `bottleneck`, `colorcet` — unused pyqtgraph deps
- `tornado`, `jinja2` — unused web frameworks

## Inno Setup Script Validation

### `[Setup]` Section
| Property | Value | Status |
|----------|-------|--------|
| AppId | `{{8E3B5C1A-2D4F-4E6A-9B7C-1D2E3F4A5B6C}}` | ✅ Unique, used for upgrade detection |
| DefaultDirName | `{autopf}\Trackora` | ✅ Program Files — standard |
| UsePreviousAppDir | `no` | ✅ Forces clean install to new dir |
| DisableProgramGroupPage | `yes` | ✅ Start menu managed automatically |
| PrivilegesRequired | `admin` | ✅ Required for Program Files write |
| OutputBaseFilename | `Trackora-Setup-{#MyAppVersion}` | ✅ Versioned |
| Compression | `lzma2/max` | ✅ Smallest installer size |
| UninstallDisplayName | `Trackora {#MyAppVersion}` | ✅ Identifiable in Add/Remove |

### `[Files]` Section
Only one file listed:
```
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
```
This is correct — the PyInstaller executable contains all resources internally.

### `[Registry]` Section
Minimal registry usage:
- **Startup entry** (optional task): `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Trackora`
- **Old cleanup**: Deletes `HKCU\...\Run\GameTracker` if it exists
- No other registry keys created

### `[Code]` Section — Upgrade Logic
| Function | Purpose | Status |
|----------|---------|--------|
| `KillProcessByName` | Kills running app instances before install/upgrade | ✅ |
| `KillAppProcesses` | Kills both `Trackora.exe` and `GameTracker.exe` | ✅ |
| `GetOldInstallPath` | Finds old GameTracker install from uninstall key | ✅ |
| `MigrateAppData` | Renames `%APPDATA%\GameTracker` → `%APPDATA%\Trackora` | ✅ |
| `RemoveOldProgramDir` | Deletes old `Program Files\GameTracker` | ✅ |
| `RemoveOldShortcuts` | Cleans old Start Menu group | ✅ |
| `RemoveOldDesktopShortcut` | Removes old desktop shortcut | ✅ |

### Uninstall Behavior
- Kills running app before uninstall
- Removes only `{app}` directory
- **AppData is never deleted** — user data preserved

## Runtime Data Locations

All runtime data lives in `%APPDATA%\Trackora\`, independent of installation directory:

| Path | Purpose |
|------|---------|
| `%APPDATA%\Trackora\trackora.db` | Main database (games, sessions, settings) |
| `%APPDATA%\Trackora\logs\` | Daily rotating log files |
| `%APPDATA%\Trackora\backups\` | Pre-migration database backups |
| `%APPDATA%\Trackora\reports\` | Crash and support reports |
| `%APPDATA%\Trackora\cache\` | Application cache |
| `%APPDATA%\Trackora\config\` | User configuration |
| `%APPDATA%\Trackora\exports\` | Exported data |
| `%APPDATA%\Trackora\imports\` | Imported data |
| `%APPDATA%\Trackora\screenshots\` | Screenshots |
| `%APPDATA%\Trackora\crash_reports\` | Crash diagnostics |

## Environment Detection

`trackora/core/environment.py` determines the environment:

```python
def _resolve_environment() -> Environment:
    if explicit env var APP_ENV set → use it
    elif sys.frozen == True → PRODUCTION
    else → DEVELOPMENT
```

When running from the installed .exe (PyInstaller frozen), `sys.frozen` is `True`, so environment is `PRODUCTION` and `BASE_DIR` resolves to `%APPDATA%\Trackora`.

During development (`python -m trackora`), environment is `DEVELOPMENT` and `BASE_DIR` resolves to `%APPDATA%\Trackora-Dev`.

## First Launch Sequence

```
1. Single-instance lock  →  %APPDATA%\Trackora\instance.lock
2. ensure_dirs()         →  Creates all AppData directories
3. DatabaseManager()     →  Opens %APPDATA%\Trackora\trackora.db
4. SchemaVersionManager  →  Reads current schema version
5. Compatibility check   →  new_data? → block; first_run? → write version
6. Migration check       →  needs_migration? → backup → apply → update version
7. _ensure_schema_columns →  Adds missing discovery columns
8. Crash check           →  Detect and report previous crash
9. Repositories          →  Games, Sessions, ActiveSessions, Settings
10. Services              →  GameService, SessionHistory, Statistics, etc.
11. Recovery              →  Recover orphaned active sessions
12. Process Monitor       →  Start tracking
13. UI                    →  MainWindow.show()
```

## Registry Access (First Launch)

No registry writes during operation (only reads for launcher detection). The single optional registry write is the startup task (`HKCU\...\Run\Trackora`) which is controlled by the installer task checkbox, not by application code.

## Edge Cases

| Scenario | Expected Behavior | Verified |
|----------|------------------|----------|
| Fresh install, no prior data | DB created, schema initialized, first_run version written | ✅ Code audit |
| Upgrade from v1.1.x (GameTracker) | AppData migrated, schema upgraded, columns added | ✅ Code audit |
| Reinstall over existing install | Inno Setup handles; DB preserved in AppData | ✅ Code audit |
| Install to non-default directory | Allowed via `DisableDirPage=auto` | ✅ |
| Uninstall + reinstall | AppData preserved across uninstall | ✅ |
| Multiple instances | Blocked by single-instance lock | ✅ |
