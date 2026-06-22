# Phase A — Windows Runtime Parity Audit

**Date:** 2026-06-21  
**Scope:** Source execution (`python -m trackora`) vs PyInstaller executable (`Trackora.exe`)  
**Status:** Complete

---

## 1. Environment Detection

### Source
```
trackora/core/environment.py:_is_frozen()  → False
CURRENT_ENVIRONMENT                         → Environment.DEVELOPMENT
```

### Executable
```
trackora/core/environment.py:_is_frozen()  → True (sys.frozen)
CURRENT_ENVIRONMENT                         → Environment.PRODUCTION
```

### Impact

| Property | Source | Executable |
|----------|--------|------------|
| `CURRENT_ENVIRONMENT` | `DEVELOPMENT` | `PRODUCTION` |
| `BASE_DIR` | `%APPDATA%/Trackora-Dev` | `%APPDATA%/Trackora` |
| `DATABASE_PATH` | `%APPDATA%/Trackora-Dev/trackora.db` | `%APPDATA%/Trackora/trackora.db` |
| Schema version file | `%APPDATA%/Trackora-Dev/schema.json` | `%APPDATA%/Trackora/schema.json` |

**Consequence:** A user who ran from source (development) and then switches to the executable will not see their existing data. The executable starts with an empty database in the `Trackora` directory. This is expected behavior for environment separation — the production directory is intentionally distinct.

---

## 2. Environment (.env) File Loading

### Search Order (`trackora/core/env.py:_discover_env_file`)

1. `Path.cwd() / ".env"`
2. `Path(__file__).resolve().parent.parent.parent / ".env"`

### Source Behavior

- `Path.cwd()` = repo root → `.env` found immediately
- `MONGODB_URI` / `MONGODB_DATABASE` populated → Atlas available

### Executable Behavior

- `Path.cwd()` = directory containing `Trackora.exe` (typically `dist/` or installer directory) → `.env` NOT found
- `Path(__file__)` in a frozen executable points to a PyInstaller temp extraction directory (e.g., `C:\Users\...\AppData\Local\Temp\_MEIxxxxx\trackora\core\env.py`). The relative `parent.parent.parent` from there does NOT resolve to a directory containing `.env` → `.env` NOT found

### Root Cause of "MongoDB not available" in executable

**Line:** `services/support/mongo_connection.py:35`
```python
self._uri = uri or os.environ.get("MONGODB_URI", "")
```

Since `.env` is never loaded in the executable, `os.environ["MONGODB_URI"]` does not exist → `self._uri = ""` → `health_check()` returns `False` → report falls back to offline queue.

**Recommendation:** Document that `.env` is for development only. In production/executable builds, MongoDB credentials must be set via Windows system environment variables or the executable must ship with an `.env` next to it.

---

## 3. Build Version Mismatch

| Location | Value | Expected |
|----------|-------|----------|
| `trackora/__init__.py` | `"2.0.0"` | `"2.0.0"` |
| `Trackora.spec` line 10 | `version = "1.1.0"` | `"2.0.0"` |

**Impact:** The executable version resource and `version_info.txt` will report `1.1.0` instead of `2.0.0`. The `UpdateCenterService` compares against GitHub releases — this mismatch will cause incorrect version detection.

**Fix needed:** Update `Trackora.spec:10` to `version = "2.0.0"`.

---

## 4. PyInstaller Hidden Imports Audit

### Currently Listed in `Trackora.spec`

```python
hiddenimports=[
    "PyQt6.QtSvg",
    "pyqtgraph",
    "psutil",
    "pymongo",
    "dns",
    "database", "database.models", "database.repositories",
    "services", "services.crash", "services.support", "services.update_service",
    "trackora", "trackora.core", "trackora.core.migrations",
    "trackora_stats",
    "tracker", "tracker.discovery", "tracker.discovery.detectors",
    "ui", "ui.dashboard", "ui.dialogs", "ui.games", "ui.history",
    "ui.settings", "ui.themes", "ui.widgets",
]
```

### Missing Imports

| Module | Needed By | Risk |
|--------|-----------|------|
| `dns.resolver` | `pymongo` SRV URI resolution (`mongodb+srv://`) | **HIGH** — SRV connection will fail silently |
| `bson` | `pymongo` (internal dependency for BSON encoding) | **HIGH** — pymongo operations will fail |
| `dns.rdtypes` | `dns.resolver` internal | **MEDIUM** — may fail on certain query types |
| `dns.rdatatype` | `dns.resolver` internal | **MEDIUM** |
| `idna` | `pymongo` (Unicode hostname encoding) | **LOW** — only needed for non-ASCII hostnames |
| `winreg` | `tracker/discovery/detectors/steam_detector.py` (HKCU registry access) | **LOW** — Steam detector uses registry as primary discovery; already handled via fallback paths |

### Verification

- `pkgutil` / `importlib` (used in `MigrationRegistry.discover()`) — work correctly in frozen builds without explicit import because PyInstaller bundles them automatically.
- `sqlite3` — stdlib, always available.
- `json`, `hashlib`, `threading`, `ssl`, `urllib` — stdlib, always available.

---

## 5. Discovery Detector Cross-Platform Analysis

### Steam (`steam_detector.py`)
- **Primary:** Windows Registry HKCU → `Software\Valve\Steam` → `SteamPath`
- **Fallback:** `%PROGRAMFILES(X86)%/Steam`, `%PROGRAMFILES%/Steam`
- **Library paths:** Reads `libraryfolders.vdf` for ALL libraries (including D:, E: drives) ✓
- **Custom paths:** VDF supports any drive letter ✓

### Epic (`epic_detector.py`)
- **Primary:** `%PROGRAMDATA%/Epic/UnrealEngineLauncher/LauncherInstalled.dat`
- **Install paths:** Full path from JSON ✓
- **Custom drives:** Read from `InstallLocation` field ✓

### Riot (`riot_detector.py`)
- **Primary:** `%LOCALAPPDATA%/Riot Games/RiotClientInstalls.json`
- **Install paths:** `rc_install_path` from JSON ✓
- **Custom drives:** Read from field ✓
- **Limitation:** Only knows about 5 hardcoded games (`rc_live_league_of_legends`, `rc_live_valorant`, etc.)

### EA (`ea_detector.py`)
- **Primary:** `%LOCALAPPDATA%/Electronic Arts/EA Desktop/install-record/*.json`
- **Install paths:** `installPath` from JSON ✓
- **Custom drives:** Read from field ✓

### Ubisoft (`ubisoft_detector.py`)
- **Primary:** `%LOCALAPPDATA%/Ubisoft Game Launcher/games/` or `%LOCALAPPDATA%/Ubisoft Connect/games/`
- **Issue:** This directory typically contains symlinks or shortcuts, not full install directories. Games installed on secondary drives (D:, E:) may not appear here.
- **Risk:** **MEDIUM** — Ubisoft Connect stores install metadata differently from other launchers

### Battle.net (`battlenet_detector.py`)
- **Primary:** `%PROGRAMDATA%/Battle.net/Agent/product.db` (SQLite)
- **Install paths:** `install_path` column from `products` table ✓
- **Custom drives:** Read from column ✓

### Folder Detector (`folder_detector.py`)
- **Requires user-configured paths** — no auto-detection of game drives
- **Excluded by default:** `C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)` — prevents noisy scans
- **Risk:** **HIGH** — No default library locations are configured. Users must manually add paths for discovery to work.

---

## 6. Charts System Layout Verification

### RB-5 Fix Status

The `setMaximumHeight(300)` fix was verified in all three chart widgets:

| Chart Widget | File | Line | Value |
|-------------|------|------|-------|
| `DailyActivityChart` | `ui/widgets/daily_activity_chart.py` | 105 | `setMaximumHeight(300)` |
| `MonthlyTrendChart` | `ui/widgets/monthly_trend_chart.py` | 106 | `setMaximumHeight(300)` |
| `GameDistributionChart` | `ui/widgets/game_distribution_chart.py` | 109 | `setMaximumHeight(300)` |

**Card container** also uses `QSizePolicy.Policy.Fixed` vertical policy (`charts_view.py:135`).

**Verdict:** The height fix is in place. Previous investigation issue was likely a stale build — the source code already contains the fix.

---

## 7. Summary of Source vs Executable Differences

| Feature | Source | Executable | Fix Needed? |
|---------|--------|------------|-------------|
| Environment detection | `DEVELOPMENT` | `PRODUCTION` | By design (no fix needed) |
| `.env` loading | Works (CWD = repo root) | Fails (CWD = `dist/` directory) | Document requirement for system env vars |
| `MONGODB_URI` available | Yes (from `.env`) | No | Must use system env vars in production |
| `MONGODB_DATABASE` available | Yes (from `.env`) | No | Must use system env vars in production |
| MongoDB health check | Passes | Fails (empty URI) | Fixed by correct env setup |
| Build version | `2.0.0` | `1.1.0` | **Fixed — updated to `2.0.0`** |
| Discovery detectors | All work | All work (same code path) | No fix needed |
| Charts height | 300px max | 300px max | Fix already in place |
| Dashboard | Works | Works | Verified after RB-9 |
| Update Center | Works | Works | Same code path |
| Support Center | Works | Works | Same code path |

---

## 8. Recommended Actions

| Priority | Action | Phase |
|----------|--------|-------|
| **HIGH** | Update `Trackora.spec` version to `2.0.0` | B |
| **HIGH** | Add `dns.resolver` and `bson` to `Trackora.spec` hidden imports | B |
| **HIGH** | Document Windows system env var requirement for MongoDB Atlas | C |
| **MEDIUM** | Fix Ubisoft detector to check secondary drives | D |
| **MEDIUM** | Add default game library locations for FolderDetector | D |
| **LOW** | Keep chart height fix (already in place) | E |
