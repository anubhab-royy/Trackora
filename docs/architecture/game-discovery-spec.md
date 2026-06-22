# Automatic Game Discovery — Architecture Specification

## 1. Overview

Automatic Game Discovery lets users scan their installed game launchers (Steam, Epic, Battle.net, Riot, Ubisoft Connect, EA App) and configured folders to find games, then selectively import them as tracked games.

**Key constraints:**
- Discovery runs **only on user request** ("Scan For Games" button) — never on startup
- Discovered games are **candidates only** — user must confirm each import
- No schema changes needed — `platform`, `platform_id`, `is_auto_discovered` columns already exist (from `v2_0_0_add_discovery_columns` migration)
- All launcher parsing is read-only — no modification of launcher files

---

## 2. Architecture Diagram

```
USER ACTION                  UI LAYER                        DISCOVERY LAYER                 SERVICE LAYER              PERSISTENCE
───────────                  ────────                        ───────────────                 ─────────────              ───────────

Clicks "Scan For Games"  →   GamesView emits
                              scan_requested signal
                           → GamesController
                               _on_scan_requested()
                             → DiscoveryDialog (modal)
                               [progress, results]
                             ↓
                           DiscoveryDialog calls         →   DiscoveryOrchestrator
                                                              .scan_all()
                                                           → ┌──────────────────┐
                                                             │ SteamDetector    │ → libraryfolders.vdf
                                                             │ EpicDetector     │   → appmanifest_*.acf
                                                             │ RiotDetector     │ → manifest files
                                                             │ BattleNetDet.    │ → .agent.db / config
                                                             │ UbisoftDetect.   │ → settings.yaml
                                                             │ EADetector       │ → install records
                                                             │ FolderDetector   │ → *.exe / *.app
                                                             └──────────────────┘
                                                             ↓
                                                           DiscoveryResult
                                                           list[CandidateGame]
                             ↓
User sees candidates in  ←  DiscoveryDialog
DiscoveryDialog              shows table of found games
[checkbox per candidate]     [name, platform, path]
                             ↓
User clicks "Import Selected"
                           → dialog returns selected
                           → GamesController
                               _on_import_discovered()
                             → GameService
                               .import_discovered_games()
                             → GamesRepository.add()
                               for each candidate
                             → refresh games list
                                                         → GameService
                                                           .add_game() with
                                                           platform fields
                                                         → GamesRepository
                                                           .add()
                                                           INSERT into games
                                                         → "X games imported"
```

---

## 3. Discovery Models

### 3.1 CandidateGame (new — `tracker/discovery/models.py`)

```python
@dataclass(frozen=True)
class CandidateGame:
    """A game discovered by a launcher or folder scanner — not yet imported."""
    name: str
    executable_path: str
    platform: str                      # "steam", "epic", "battlenet", "riot", "ubisoft", "ea", "generic"
    platform_id: str                   # platform-specific ID (e.g. Steam appid)
    icon_path: str = ""                # optional — pre-resolved icon from launcher
    process_name: str = ""             # extracted from executable_path if empty
```

### 3.2 DiscoveryResult (new — `tracker/discovery/models.py`)

```python
@dataclass(frozen=True)
class DiscoveryResult:
    """Result of a full scan across all enabled detectors."""
    candidates: list[CandidateGame]
    errors: list[str]                  # per-detector error messages (non-fatal)
    duration_ms: int
```

### 3.3 DiscoveredGameRequest (new — `services/game_service.py`)

```python
@dataclass
class DiscoveredGameRequest:
    """DTO for importing a discovered candidate game."""
    name: str
    executable_path: str
    platform: str
    platform_id: str
    is_auto_discovered: bool = True
```

---

## 4. Detector Interface & Implementations

### 4.1 Base Interface (`tracker/discovery/detector.py`)

```python
class GameDetector(ABC):
    @property
    @abstractmethod
    def platform(self) -> str: ...

    @abstractmethod
    def detect(self) -> list[CandidateGame]: ...
```

### 4.2 SteamDetector (`tracker/discovery/detectors/steam_detector.py`)

| Aspect | Detail |
|--------|--------|
| **Detection method** | Read `libraryfolders.vdf` (Valve KeyValues format) to find Steam library paths, then read `appmanifest_*.acf` files in each library's `steamapps` directory |
| **Platform string** | `"steam"` |
| **Platform ID** | Steam App ID from manifest (`"appid"` field) |
| **Game name** | `"name"` field from manifest |
| **Executable path** | Resolve from manifest's `"installdir"` + common executable patterns (.exe or known binaries) |
| **Icon path** | (Optional) path to Steam grid images |
| **Dependencies** | `steam` paths resolved via Windows registry (`HKCU\Software\Valve\Steam\SteamPath`) or macOS/Linux defaults |
| **Failure mode** | Detector returns `[]` + error message if Steam not installed or manifests unreadable |

**KeyValues parser:** A minimal tokeniser in `tracker/discovery/kv_parser.py` that handles Valve's KeyValues format (nested `{ }` blocks, quoted strings, comments `//`).

### 4.3 EpicDetector (`tracker/discovery/detectors/epic_detector.py`)

| Aspect | Detail |
|--------|--------|
| **Detection method** | Read `%PROGRAMDATA%/Epic/UnrealEngineLauncher/LauncherInstalled.dat` (JSON) |
| **Platform string** | `"epic"` |
| **Platform ID** | `"AppName"` from manifest |
| **Game name** | `"DisplayName"` from manifest |
| **Executable path** | `"InstallLocation"` + resolve `LaunchExecutable` from `.manifest` files (or scan for `.exe`) |
| **Icon path** | (Optional) |
| **Failure mode** | Returns `[]` + error if file missing |

### 4.4 RiotDetector (`tracker/discovery/detectors/riot_detector.py`)

| Aspect | Detail |
|--------|--------|
| **Detection method** | Parse `RiotClientInstalls.json` (Riot client settings) for installed games and their paths |
| **Platform string** | `"riot"` |
| **Platform ID** | Game identifier from Riot config |
| **Game name** | Friendly name mapped from known Riot game IDs |
| **Executable path** | Resolve from install path + known binary names (`LeagueClient.exe`, `VALORANT.exe`, etc.) |
| **Failure mode** | Returns `[]` + error if file missing |

### 4.5 BattleNetDetector (`tracker/discovery/detectors/battlenet_detector.py`)

| Aspect | Detail |
|--------|--------|
| **Detection method** | Parse Battle.net `product.db` (SQLite) or `config.db` (SQLite) for installed product entries |
| **Platform string** | `"battlenet"` |
| **Platform ID** | Product code (e.g. `"s2"` for StarCraft II, `"pro"` for Overwatch) |
| **Game name** | `name` field from product DB |
| **Executable path** | `install_path` from DB + resolve executable name |
| **Failure mode** | Returns `[]` + error if DB not found |

### 4.6 UbisoftDetector (`tracker/discovery/detectors/ubisoft_detector.py`)

| Aspect | Detail |
|--------|--------|
| **Detection method** | Parse Uplay/Ubisoft Connect `settings.yaml` or `config.yaml` for game entries |
| **Platform string** | `"ubisoft"` |
| **Platform ID** | Game UUID from config |
| **Game name** | `name` field |
| **Executable path** | `install_path` from config |
| **Failure mode** | Returns `[]` + error if config not found |

### 4.7 EADetector (`tracker/discovery/detectors/ea_detector.py`)

| Aspect | Detail |
|--------|--------|
| **Detection method** | Parse EA App's `install-record` directories or `EADesktop/install.db` for installed titles |
| **Platform string** | `"ea"` |
| **Platform ID** | EA title ID |
| **Game name** | `displayName` from install record |
| **Executable path** | `installPath` + executable name |
| **Failure mode** | Returns `[]` + error if not found |

### 4.8 FolderDetector (`tracker/discovery/detectors/folder_detector.py`)

| Aspect | Detail |
|--------|--------|
| **Detection method** | Scan user-configured directories for executables (`.exe` on Windows, `.app` bundles on macOS, various binaries on Linux) |
| **Platform string** | `"generic"` |
| **Platform ID** | SHA-256 hash of executable path (uniqueness without collision) |
| **Game name** | Stem of filename (cleaned: `_`/`-` → space, title-cased) |
| **Executable path** | Full canonical path |
| **Configuration** | List of directories stored in `SettingsRepository` key `discovery_scan_folders` |
| **Exclusions** | System folders, Windows directory, Program Files (configurable) |
| **Filter** | Minimum file size (1 MB default), common executable types only |
| **Failure mode** | Empty list + error for each unreadable directory |

---

## 5. Discovery Orchestrator (`tracker/discovery/orchestrator.py`)

```python
class DiscoveryOrchestrator:
    """
    Orchestrates all enabled detectors and aggregates results.

    Responsibilities:
    - Discover and run all GameDetector implementations
    - Collect CandidateGame lists with deduplication
    - Sort results (platform groups, alphabetically)
    - Exclude games already in the database
    - Return DiscoveryResult with timing and errors
    """
```

### Deduplication within a single scan

If the same game is discovered by multiple detectors (e.g. Steam game also found by folder scan), keep the launcher-detected entry and discard the generic one. If two launchers report the same game (e.g. same executable path), keep the first one encountered (priority order: Steam > Epic > BattleNet > Riot > Ubisoft > EA > generic).

**In-scan dedup key:** `(executable_path)` — normalized via `os.path.normpath()`.

### Exclusion of already-tracked games

After collecting all candidates, filter out any whose `executable_path` already exists in the database via `GamesRepository.exists_by_executable_path()`. Also filter by `(platform, platform_id)` if both present — if a game was previously imported from Steam App ID 730, it should not appear again.

---

## 6. Integration with Existing Services

### 6.1 GameService changes

`GameService.add_game()` gets updated to accept `platform`, `platform_id`, `is_auto_discovered` fields:

```python
# Updated AddGameRequest
@dataclass
class AddGameRequest:
    name: str
    executable_path: str
    platform: str = ""
    platform_id: str = ""
    is_auto_discovered: bool = False
```

**New method:**

```python
def import_discovered_games(
    self, candidates: list[CandidateGame]
) -> GameServiceResult:
    """
    Bulk-import discovered game candidates.

    For each candidate:
    1. Check duplicate by (platform, platform_id) — skip if exists
    2. Check duplicate by executable_path — skip if exists
    3. Build AddGameRequest with platform fields
    4. Call add_game() for each
    5. Return count of successfully imported games
    """
```

### 6.2 GamesRepository changes

- `add()` updated to write `platform`, `platform_id`, `is_auto_discovered` columns
- `_row_to_game()` updated to read these columns
- `get_by_platform_id(platform, platform_id)` added for duplicate checking
- `exists_by_platform_id(platform, platform_id)` added

### 6.3 Game model changes

```python
@dataclass
class Game:
    name: str
    process_name: str
    executable_path: str
    icon_path: str = ""
    is_enabled: bool = True
    platform: str = ""
    platform_id: str = ""
    is_auto_discovered: bool = False
    first_played: datetime | None = None
    last_played: datetime | None = None
    created_at: datetime = ...
    updated_at: datetime = ...
    id: int | None = None
```

All fields added with sensible defaults — no breaking changes to existing code that constructs `Game(...)` without these fields.

---

## 7. UI Integration

### 7.1 New discovery dialog (`ui/games/discovery_dialog.py`)

| Aspect | Detail |
|--------|--------|
| **Type** | `QDialog` (modal) |
| **Stages** | Scanning → Results → Confirm |
| **Scanning phase** | "Scanning for games..." with platform-by-platform progress labels (no progress bar — scan is < 3s total); each detector result logged as it completes |
| **Results phase** | `QTableWidget` with columns: checkbox, Game Name, Platform, Executable Path. Grouped by platform. |
| **Empty state** | "No new games found." message if scan yields zero new candidates |
| **Actions** | "Import Selected" + "Cancel". Select All / Deselect All toggle. |
| **Error display** | Per-detector errors shown in a collapsible "Scan Warnings" section |
| **Sizing** | Default 700×500, resizable |

### 7.2 GamesView changes

- Add `"Scan For Games"` button next to the existing `"+ Add Game"` button in the header bar
- New signal: `scan_requested = pyqtSignal()`

### 7.3 GamesController changes

- Connect `scan_requested` → `_on_scan_requested()`
- `_on_scan_requested()`: open `DiscoveryDialog`, pass `DiscoveryOrchestrator` instance, handle results
- Wire `DiscoveryDialog.import_selected(candidates)` → `GameService.import_discovered_games()`

### 7.4 DiscoveryDialog wiring

```python
class GamesController:
    def __init__(self, view, game_service, discovery_orchestrator):
        ...

    def _on_scan_requested(self):
        dialog = DiscoveryDialog(
            parent=self._view,
            orchestrator=self._discovery_orchestrator,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        candidates = dialog.get_selected_candidates()
        if not candidates:
            return

        result = self._service.import_discovered_games(candidates)
        self.load_games()
        self._view.show_info("Scan Complete", result.message)
```

---

## 8. Duplicate Detection Strategy

| Scenario | Detection | Action |
|----------|-----------|--------|
| Same executable path | `GamesRepository.get_by_executable_path()` | Skip candidate |
| Same (platform, platform_id) | `GamesRepository.exists_by_platform_id()` | Skip candidate |
| Same game re-scanned (second scan) | `exists_by_platform_id()` or `get_by_executable_path()` | Not shown again |
| User-added game (manual) rescan | `exists_by_platform_id()` only if platform_id stored; otherwise `get_by_executable_path()` | Vice-versa: skip if executable_path exists |
| Same game detected by two launchers | In-memory dedup by `(executable_path)` in orchestrator | Keep first by launcher priority |
| User modifies executable_path after import | No duplicate guard needed — it's their game now | N/A |

Priority order for in-scan dedup: `steam > epic > battlenet > riot > ubisoft > ea > generic`

---

## 9. Platform Data Flow

```
AddGameRequest / Game (updated model)
  │
  ├── platform: str           ──► games.platform TEXT DEFAULT NULL
  ├── platform_id: str        ──► games.platform_id TEXT DEFAULT NULL
  └── is_auto_discovered: bool──► games.is_auto_discovered INTEGER DEFAULT 0

Duplicate check:
  ┌─ By (platform, platform_id) ──► GamesRepository.exists_by_platform_id()
  └─ By executable_path          ──► GamesRepository.get_by_executable_path()
                                      (falls back to existing check)

Display:
  GameTableModel shows platform column (new column, inserted after Name)
  "Auto-Discovered" badge or tag in UI for is_auto_discovered games
```

---

## 10. Testing Strategy

### 10.1 Unit tests per detector

Each detector tested in isolation with real (sample) manifest files:

| Test file | Tests |
|-----------|-------|
| `tests/tracker/discovery/test_steam_detector.py` | Parse `libraryfolders.vdf` + `appmanifest_*.acf` samples; handle missing Steam; empty library |
| `tests/tracker/discovery/test_epic_detector.py` | Parse `LauncherInstalled.dat` sample; missing file |
| `tests/tracker/discovery/test_riot_detector.py` | Parse `RiotClientInstalls.json`; missing Riot |
| `tests/tracker/discovery/test_battlenet_detector.py` | Parse `product.db` sample; missing Battle.net |
| `tests/tracker/discovery/test_ubisoft_detector.py` | Parse settings sample; missing Ubisoft |
| `tests/tracker/discovery/test_ea_detector.py` | Parse EA install records; missing EA App |
| `tests/tracker/discovery/test_folder_detector.py` | Scan `tmp_path` with sample executables; empty dir; exclusions |

### 10.2 KV parser tests

`tests/tracker/discovery/test_kv_parser.py` — test with real Steam VDF/ACF samples; edge cases (empty, malformed, escaped strings).

### 10.3 Orchestrator tests

`tests/tracker/discovery/test_orchestrator.py` — mock detectors, verify aggregation, dedup logic, error collection.

### 10.4 Integration tests

`tests/test_discovery_integration.py` — end-to-end tests using in-memory SQLite + mock detectors; verify full flow from scan to persistence.

### 10.5 Architecture tests

`tests/architecture/test_discovery_isolation.py` — verify discovery layer does not import UI or service code.

### 10.6 Test data files

Sample launcher manifests stored in `tests/tracker/discovery/fixtures/`:
- `steam/libraryfolders.vdf`
- `steam/appmanifest_730.acf`
- `epic/LauncherInstalled.dat`
- `riot/RiotClientInstalls.json`
- `battlenet/product.db` (SQLite dump script for test setup)

---

## 11. Architecture Rules

```
Do NOT import:
  ├── ui/*                   in any discovery detector
  ├── services/*             in any discovery detector
  ├── PyQt6                  in tracker/discovery/ (pure Python)
  └── database/models/*      in detector classes (use CandidateGame DTO instead)

Do NOT:
  ├── Write to launcher files or directories
  ├── Modify launcher configuration
  ├── Run discovery at application startup
  ├── Import games without user confirmation
  └── Block the Qt event loop during scanning (run synchronously only; scan is < 3s)

Do NOT add dependencies:
  ├── Requests/httpx          (no network calls in discovery)
  ├── third-party VDF parser  (write minimal KV parser in-house)
  ├── aiofiles / asyncio      (synchronous only; scan is fast)
  └── Any launcher SDK

Allowed imports in tracker/discovery/:
  ├── os, pathlib, re, json, struct
  ├── dataclasses, logging, abc
  └── sqlite3 (only in BattleNetDetector for reading product.db)

Layer isolation:
  tracker/discovery/  →  services/  →  ui/
  (detectors)            (game_service)  (discovery_dialog, controller)
```

---

## 12. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| Discovery runs synchronously, not async | All platform scans complete in < 3s — async overhead unwarranted; UI uses `QDialog.exec()` modal pattern | 2026-06-20 |
| In-house KV parser, not `vdf` PyPI | Zero new dependencies; Steam VDF format is simple enough for a ~60-line tokeniser | 2026-06-20 |
| Detectors live in `tracker/discovery/`, not `services/` | Architecture tests enforce that tracker layer has no UI/service imports. Detectors are pure filesystem scanners — they belong in the tracker layer alongside `game_detector.py` (process detection) | 2026-06-20 |
| `CandidateGame` is a separate DTO from `Game` | `CandidateGame` is unvalidated, unpersisted, and contains only discovery-relevant fields. Converting to `Game`/`AddGameRequest` happens in the service layer | 2026-06-20 |
| Folders are the last/default scanner | Generic folder scanning has highest false-positive rate (system binaries); launcher scanners are authoritative | 2026-06-20 |
| No bulk-insert in repository | Each import calls `add()` individually — preserves per-row error handling and logging. Import of 50+ games is still < 200ms | 2026-06-20 |
| Duplicate prevention uses (platform, platform_id) as primary key, executable_path as fallback | `platform_id` is the authoritative identity from the launcher; executable_path can change (Steam reinstall, library migration) | 2026-06-20 |
| Discovery dialog shows full results before import | User must confirm each game; no implicit "import all" without review | 2026-06-20 |
| No startup scanning | Performance requirement — app must launch instantly. "Scan For Games" is a user-initiated action only | 2026-06-20 |
| Existing migration `v2_0_0_add_discovery_columns` already adds schema columns | No schema changes needed in this phase — the columns are already in the `games` table. Only the Python model needs updating | 2026-06-20 |
