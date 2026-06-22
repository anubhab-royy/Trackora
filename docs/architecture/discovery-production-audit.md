# Phase D — Discovery System Production Audit

**Date:** 2026-06-21  
**Scope:** All 7 game detectors, cross-drive support, custom paths  
**Status:** Complete

---

## 1. Detector Overview

| Detector | File | Priority | Method | Cross-Drive Support |
|----------|------|----------|--------|---------------------|
| Steam | `tracker/discovery/detectors/steam_detector.py` | 0 (highest) | Registry + `libraryfolders.vdf` | ✓ Full — VDF lists all library paths |
| Epic | `tracker/discovery/detectors/epic_detector.py` | 1 | `LauncherInstalled.dat` (JSON) | ✓ Full — `InstallLocation` is absolute path |
| Battle.net | `tracker/discovery/detectors/battlenet_detector.py` | 2 | `product.db` (SQLite) | ✓ Full — `install_path` column |
| Riot | `tracker/discovery/detectors/riot_detector.py` | 3 | `RiotClientInstalls.json` | ✓ Full — `rc_install_path` is absolute |
| Ubisoft | `tracker/discovery/detectors/ubisoft_detector.py` | 4 | `games/` directory scan | ✗ Limited — uses `%LOCALAPPDATA%` only |
| EA | `tracker/discovery/detectors/ea_detector.py` | 5 | `install-record/*.json` | ✓ Full — `installPath` is absolute |
| Folder | `tracker/discovery/detectors/folder_detector.py` | 6 (lowest) | Recursive scan | ✓ User-configured paths |

---

## 2. Detector Deep-Dive

### Steam — SteamDetector

**Status:** ✅ Production ready

- **Root discovery:** Reads `HKCU\Software\Valve\Steam\SteamPath` from Windows Registry
- **Fallback:** Checks `%PROGRAMFILES(X86)%/Steam` and `%PROGRAMFILES%/Steam`
- **Libraries:** Parses `libraryfolders.vdf` using custom KV parser — supports ALL drives
- **Manifests:** Reads `appmanifest_*.acf` in each library's `steamapps/` directory
- **Executable resolution:** Scans `common/<install_dir>/` for `*.exe`
- **Edge case:** Returns `CandidateGame` with empty `executable_path` if executable not found (still shows the game to user)

**Limitation:** The KV parser (`tracker/discovery/kv_parser.py`) is custom-built. If Valve changes VDF format, parsing may break.

### Epic — EpicDetector

**Status:** ✅ Production ready

- **Manifest location:** `%PROGRAMDATA%/Epic/UnrealEngineLauncher/LauncherInstalled.dat`
- **Format:** JSON `InstallationList` array
- **Fields used:** `AppName` (platform_id), `DisplayName` (name), `InstallLocation` (path), `LaunchExecutable` (optional)
- **Cross-drive:** `InstallLocation` is an absolute path — supports any drive
- **Executable resolution:** Prefers `LaunchExecutable` field, falls back to `*.exe` glob

### Riot — RiotDetector

**Status:** ✅ Production ready

- **Config location:** `%LOCALAPPDATA%/Riot Games/RiotClientInstalls.json`
- **Format:** JSON with `associated_client` dict
- **Known games:** Hardcoded mapping of 4 game IDs (`rc_live_league_of_legends`, `rc_live_valorant`, `rc_live_teamfight_tactics`, `rc_live_legends_of_runeterra`)
- **Cross-drive:** `rc_install_path` is absolute — supports any drive
- **Limitation:** Only 4 known games — new Riot titles (e.g., 2XKO, Project L) won't be detected until the mapping is updated

### EA — EADetector

**Status:** ✅ Production ready

- **Records location:** `%LOCALAPPDATA%/Electronic Arts/EA Desktop/install-record/*.json`
- **Format:** JSON with `displayName`, `installPath`, `titleId`
- **Cross-drive:** `installPath` is absolute — supports any drive
- **Executable resolution:** `*.exe` glob in install path

### Battle.net — BattleNetDetector

**Status:** ✅ Production ready

- **Database:** `%PROGRAMDATA%/Battle.net/Agent/product.db` (SQLite)
- **Query:** `SELECT uid, product_code, install_path, name FROM products`
- **Cross-drive:** `install_path` is absolute — supports any drive
- **Executable resolution:** `*.exe` glob in install path

### Ubisoft — UbisoftDetector ⚠️

**Status:** ⚠️ Partial — needs improvement

- **Config location:** `%LOCALAPPDATA%/Ubisoft Game Launcher/games/` or `%LOCALAPPDATA%/Ubisoft Connect/games/`
- **Format:** Per-game subdirectories with `info.txt` metadata files
- **Cross-drive:** ❌ Only checks `%LOCALAPPDATA%` — games installed on D:, E: drives are MISSED
- **Issue:** Ubisoft Connect uses symlinks/shortcuts in the `games/` directory. Actual install locations are stored elsewhere (registry or Uplay DB). The current scan of subdirectories may miss games installed on non-C: drives.
- **Recommendation:** Read `HKCU\Software\Ubisoft\Launcher\Installs` or `HKLM\Software\Wow6432Node\Ubisoft\Launcher\Installs` for absolute install paths.

### Folder — FolderDetector ⚠️

**Status:** ⚠️ Needs user configuration

- **Current behavior:** Only scans user-provided `folder_paths` list — no defaults
- **System exclusions:** Correctly excludes `C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)` to avoid noise
- **Minimum file size:** 1 MB — filters out small utilities
- **Cross-drive:** Scans any directory the user provides, including D:\, E:\
- **Issue:** **No default scan locations.** Users must manually add game library paths. The orchestrator passes `None` for folder_paths by default, resulting in zero results.

---

## 3. Orchestrator — DiscoveryOrchestrator

**File:** `tracker/discovery/orchestrator.py`  
**Status:** ✅ Production ready

- **Detector order:** Steam → Epic → Riot → BattleNet → Ubisoft → EA → Folder (by priority)
- **Dedup strategy:** Higher-priority detector wins when same executable path is found
- **Exclusion:** Checks against existing tracked games by `platform_id` and `executable_path`
- **Error isolation:** Each detector runs independently — one failure does not block others
- **Timing:** Reports total scan duration in milliseconds

---

## 4. Cross-Drive Support Matrix

| Drive | Steam | Epic | Riot | EA | Battle.net | Ubisoft | Folder |
|-------|-------|------|------|----|-----------|---------|--------|
| C: | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| D: | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| E: | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| F: | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| G: | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |

---

## 5. Issues Found

### Issue D-1: Ubisoft detector limited to %LOCALAPPDATA%
- **Severity:** MEDIUM
- **Impact:** Up to 50% of Ubisoft games may be missed (those on D:, E: drives)
- **Fix:** Read Ubisoft install paths from Windows Registry (same approach as Steam)

### Issue D-2: FolderDetector has no default paths
- **Severity:** MEDIUM
- **Impact:** Zero results unless user configures paths. New users won't know to add folders.
- **Fix:** Add well-known game directories as defaults (Steam default lib, Epic default lib) or auto-suggest after launcher scan

### Issue D-3: Riot detector hardcodes game IDs
- **Severity:** LOW
- **Impact:** New Riot games not auto-detected until mapping updated
- **Fix:** Use dynamic name lookup from the Riot config data rather than hardcoded mapping

### Issue D-4: EA detector no error handling for corrupted JSON files
- **Severity:** LOW
- **Impact:** One corrupt `install-record/*.json` silently skips all EA games
- **Fix:** Continue to next file on parse error (already partially handled)

---

## 6. Library Locations — Architecture Proposal

### Settings UI Design

```
Settings → Library Locations
├── Automatically detected libraries
│   ├── Steam (C:\Program Files (x86)\Steam)
│   ├── Epic (D:\Epic Games)
│   └── Battle.net (E:\Blizzard)
├── Custom folders
│   ├── [✓] D:\Games
│   ├── [✓] E:\SteamLibrary
│   └── [+] Add folder
└── [Scan Now] [Clear All]
```

**Implementation approach (future):**

1. Add `library_folders` table to the `settings` table (key-value with JSON-serialized paths)
2. Add `LibraryLocationsPage` to `ui/settings/`
3. Add `FolderDetector.folder_paths` to be persisted in settings
4. Update `DiscoveryOrchestrator` to read folder paths from settings on scan
5. Add "Scan" button to discovery dialog

**Database schema addition** (settings table already supports arbitrary keys):
```
key="library_folders"
value='["D:\\Games", "E:\\SteamLibrary"]'
```

---

## 7. Summary

| Detector | Status | Cross-Drive | Issues |
|----------|--------|-------------|--------|
| Steam | ✅ Ready | ✓ All drives | None |
| Epic | ✅ Ready | ✓ All drives | None |
| Riot | ✅ Ready | ✓ All drives | D-3 (LOW) |
| EA | ✅ Ready | ✓ All drives | D-4 (LOW) |
| Battle.net | ✅ Ready | ✓ All drives | None |
| Ubisoft | ⚠️ Partial | ✗ C: only | D-1 (MEDIUM) |
| Folder | ⚠️ Needs config | ✓ Any path | D-2 (MEDIUM) |

**Critical path for v2.0.0:** Fix Ubisoft detector (D-1) and add default folder paths (D-2) for a complete discovery experience.
