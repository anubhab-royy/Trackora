# Automatic Game Discovery — TDD Checkpoints

## Step 1 — KV Parser

### RED
Write tests for the Valve KeyValues parser:
- Parse simple `"key" "value"` pairs from VDF
- Parse nested `{ }` blocks (ACF structure)
- Parse full `libraryfolders.vdf` sample (multi-library)
- Parse full `appmanifest_730.acf` sample
- Handle empty input → empty dict
- Handle malformed input → `KVParserError`

**Test file:** `tests/tracker/discovery/test_kv_parser.py`
**New tests:** 6 tests

### GREEN
Implement `tracker/discovery/kv_parser.py` — a ~60-line tokeniser:
```
Tokenise: split on whitespace, recognise quoted strings, { } delimiters, // comments
     ↓
Parse: stack-based nesting → nested dict output
```

Return a flat `dict[str, str]` for simple files, or nested `dict` for ACF-structured files. Accept `str` content, not file paths.

### REFACTOR
Ensure error messages include line numbers for malformed input. Handle escaped quotes inside strings.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_kv_parser.py -x -v
```

---

## Step 2 — GameDetector ABC + Models

### RED
Write tests:
- `GameDetector` cannot be instantiated (raises `TypeError` via ABC)
- `CandidateGame` stores all fields correctly (frozen dataclass)
- `CandidateGame` with empty `process_name` auto-derives from `executable_path` basename
- `DiscoveryResult` aggregates candidates + errors + duration

**Test file:** `tests/tracker/discovery/test_orchestrator.py` (or dedicated `test_models.py`)
**New tests:** 4 tests

### GREEN
Implement `tracker/discovery/models.py`:
```python
@dataclass(frozen=True)
class CandidateGame:
    name: str
    executable_path: str
    platform: str
    platform_id: str
    icon_path: str = ""
    process_name: str = ""

    def __post_init__(self):
        if not self.process_name:
            object.__setattr__(self, "process_name", PureWindowsPath(self.executable_path).name)

@dataclass(frozen=True)
class DiscoveryResult:
    candidates: list[CandidateGame]
    errors: list[str]
    duration_ms: int
```

Implement `tracker/discovery/detector.py` — `GameDetector(ABC)` with `platform` property and `detect()` abstract method.

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_orchestrator.py -x -v -k "test_candidate or test_discovery or test_detector"
```

---

## Step 3 — SteamDetector

### RED
Write `test_steam_detector.py` tests:
- Detect CS2 from `appmanifest_730.acf` + `libraryfolders.vdf` → `CandidateGame(platform="steam", platform_id="730")`
- Detect multiple games from multi-library VDF (2+ manifest files)
- Steam not installed (no registry key / no default path) → empty candidates, 1 error
- Empty library (VDF with content but no manifests) → empty candidates
- Corrupt manifest (invalid ACF) → skipped with error, other manifests still parsed
- Registry path (Windows) via `monkeypatch.setattr(os, "name", "nt")` + env var

**Test file:** `tests/tracker/discovery/test_steam_detector.py`
**Test fixtures:** `fixtures/steam_libraryfolders.vdf`, `fixtures/steam_appmanifest_730.acf`
**New tests:** 6 tests

### GREEN
Implement `steam_detector.py`:
1. Find Steam root: Windows registry `HKCU\Software\Valve\Steam\SteamPath`, macOS `~/Library/Application Support/Steam`, Linux `~/.steam/steam`
2. Read `libraryfolders.vdf` via `kv_parser` → list of library paths
3. For each library, read `steamapps/` directory → collect `appmanifest_*.acf` files
4. Parse each manifest → `CandidateGame`
5. Resolve executable path: manifest `"installdir"` + scan for common executables

### REFACTOR
Extract executable resolution into `_resolve_steam_executable(installdir)` helper for testability.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_steam_detector.py -x -v
```

---

## Step 4 — EpicDetector

### RED
Write `test_epic_detector.py` tests:
- Parse `LauncherInstalled.dat` → 2+ candidates with `platform="epic"`, correct `platform_id`
- File missing → empty candidates, 1 error
- Empty install list (`"InstallationList": []`) → empty candidates
- Malformed JSON → empty candidates, 1 error

**Test file:** `tests/tracker/discovery/test_epic_detector.py`
**Test fixtures:** `fixtures/epic_launcher_installed.dat`
**New tests:** 4 tests

### GREEN
Implement `epic_detector.py`:
1. Read `LauncherInstalled.dat` from `%PROGRAMDATA%/Epic/UnrealEngineLauncher/` (Windows) or equivalent paths
2. Parse JSON, iterate `InstallationList`
3. Extract `AppName` (platform_id), `DisplayName` (name), `InstallLocation` (path)
4. Resolve executable from `InstallLocation` + scan for `.exe` files

### REFACTOR
Handle cross-platform path resolution for Epic's data directory.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_epic_detector.py -x -v
```

---

## Step 5 — RiotDetector

### RED
Write `test_riot_detector.py` tests:
- Parse `RiotClientInstalls.json` → League of Legends + VALORANT candidates
- File missing → empty candidates, 1 error
- Empty config → empty candidates

**Test file:** `tests/tracker/discovery/test_riot_detector.py`
**Test fixtures:** `fixtures/riot_installs.json`
**New tests:** 3 tests

### GREEN
Implement `riot_detector.py`:
1. Read `RiotClientInstalls.json` from Riot client data dir
2. Parse known game IDs → friendly names via lookup dict
3. Resolve executable path from install location

### REFACTOR
Extract game ID → name mapping into a class constant.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_riot_detector.py -x -v
```

---

## Step 6 — BattleNetDetector

### RED
Write `test_battlenet_detector.py` tests:
- Parse sample `product.db` (SQLite) → 2+ candidates with `platform="battlenet"`
- DB not found → empty candidates, 1 error
- Corrupt DB → empty candidates, 1 error

**Test file:** `tests/tracker/discovery/test_battlenet_detector.py`
**Test fixtures:** `fixtures/battlenet_product.db` (generate via test setup script)
**New tests:** 3 tests

### GREEN
Implement `battlenet_detector.py`:
1. Locate Battle.net data directory (`%PROGRAMDATA%/Battle.net/Agent/`)
2. Open `product.db` via `sqlite3.connect()`
3. Query `products` table for installed titles
4. Extract product code (platform_id), name, install_path

### REFACTOR
Wrap SQLite access in try/except for `OperationalError`.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_battlenet_detector.py -x -v
```

---

## Step 7 — UbisoftDetector

### RED
Write `test_ubisoft_detector.py` tests:
- Parse sample settings file → candidates with `platform="ubisoft"`
- File missing → empty candidates, 1 error

**Test file:** `tests/tracker/discovery/test_ubisoft_detector.py`
**New tests:** 2 tests

### GREEN
Implement `ubisoft_detector.py`:
1. Locate Ubisoft Connect config directory
2. Parse `settings.yaml` or game entries
3. Extract game entries with name, install path, UUID

### REFACTOR
Handle both Uplay (old) and Ubisoft Connect (new) paths.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_ubisoft_detector.py -x -v
```

---

## Step 8 — EADetector

### RED
Write `test_ea_detector.py` tests:
- Parse sample install records → candidates with `platform="ea"`
- EA App not installed → empty candidates, 1 error

**Test file:** `tests/tracker/discovery/test_ea_detector.py`
**New tests:** 2 tests

### GREEN
Implement `ea_detector.py`:
1. Locate EA App data directory
2. Read install records from known file paths
3. Extract game entries with name, install path, title ID

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_ea_detector.py -x -v
```

---

## Step 9 — FolderDetector

### RED
Write `test_folder_detector.py` tests:
- Scan `tmp_path` with 3 `.exe` files → 3 candidates with `platform="generic"`
- Empty directory → empty candidates
- Minimum file size filter (1 MB) → files under 1 MB excluded
- System directory exclusion → `/usr/bin`, `C:\Windows` ignored
- Custom directory list from config parameter
- No configured directories → empty candidates, 1 error

**Test file:** `tests/tracker/discovery/test_folder_detector.py`
**New tests:** 6 tests

### GREEN
Implement `folder_detector.py`:
1. Accept list of directory paths
2. Recursively scan for executables (`.exe`, `.app` bundles, ELF binaries)
3. Filter: min 1 MB, exclude system directories
4. Generate candidate with platform="generic", platform_id=SHA256(executable_path)

### REFACTOR
Extract exclusion filter into `_is_excluded(path)` method. Accept `min_size_bytes` as constructor parameter for testability.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_folder_detector.py -x -v
```

---

## Step 10 — DiscoveryOrchestrator

### RED
Write `test_orchestrator.py` tests:
- 3 mock detectors each returning 1 candidate → `DiscoveryResult` with 3 candidates
- 2 detectors return same game (same executable_path) → 1 candidate (dedup)
- 2 detectors find same path, launcher priority: steam kept, generic dropped
- 1 candidate matches existing game in DB → excluded from results
- 1 detector raises exception → error collected, other detectors still run
- No detectors registered → empty result with no errors
- `DiscoveryResult.duration_ms` > 0

**Test file:** `tests/tracker/discovery/test_orchestrator.py`
**New tests:** 7 tests

### GREEN
Implement `orchestrator.py`:
```python
class DiscoveryOrchestrator:
    def __init__(self, games_repository: GamesRepository):
        self._detectors: list[GameDetector] = [
            SteamDetector(),
            EpicDetector(),
            RiotDetector(),
            BattleNetDetector(),
            UbisoftDetector(),
            EADetector(),
            FolderDetector(),
        ]
        self._games_repo = games_repository

    def scan_all(self, folder_paths: list[str] | None = None) -> DiscoveryResult:
        ...
```

Scan logic:
1. Start timer
2. For each detector: call `detect()`, collect candidates + errors
3. Dedup by `(executable_path)` with launcher priority
4. Filter out already-tracked games via `exists_by_executable_path()` and `exists_by_platform_id()`
5. Return `DiscoveryResult`

### REFACTOR
Extract dedup logic into `_deduplicate(candidates)` and filter into `_exclude_existing(candidates)`.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_orchestrator.py -x -v
```

---

## Step 11 — Game Model + Repository Updates

### RED
Write tests:
- `Game(name="T", process_name="t.exe", executable_path="/t/t.exe", platform="steam", platform_id="730", is_auto_discovered=True)` — model accepts fields
- `Game` with defaults: `platform == ""`, `platform_id == ""`, `is_auto_discovered == False`
- `_row_to_game()` reads `platform`, `platform_id`, `is_auto_discovered` from sqlite3.Row
- `GamesRepository.add()` writes platform columns in INSERT
- `GamesRepository.update()` writes platform columns in UPDATE
- `GamesRepository.get_by_platform_id("steam", "730")` returns matching `Game`
- `GamesRepository.exists_by_platform_id("steam", "999")` returns `False`
- `GamesRepository.exists_by_platform_id("steam", "730")` returns `True` (after inserting)

**Test file:** `tests/test_game_service.py` (new class `TestGameModel` + `TestGamesRepositoryExtensions`)
**New tests:** 8 tests

### GREEN
1. Update `Game` dataclass with 3 new fields (defaults `""`, `""`, `False`)
2. Update `_row_to_game()` to read new columns
3. Update `GamesRepository.add()` INSERT to include new columns
4. Update `GamesRepository.update()` UPDATE to include new columns
5. Add `get_by_platform_id(platform, platform_id) -> Game | None`
6. Add `exists_by_platform_id(platform, platform_id) -> bool`

### REFACTOR
Ensure existing code that constructs `Game(...)` without these fields still works (keyword defaults).

### Validation
```bash
python -m pytest tests/test_game_service.py -x -v -k "TestGameModel or TestGamesRepository"
```

---

## Step 12 — GameService Discovery Integration

### RED
Write tests:
- `AddGameRequest` accepts optional `platform="steam"`, `platform_id="730"`, `is_auto_discovered=True`
- `add_game()` checks duplicate by `(platform, platform_id)` — if match exists, reject
- `add_game()` with `platform=""` falls back to executable_path dedup (existing behaviour)
- `import_discovered_games([candidate1, candidate2])` → both imported, success message "2 games imported"
- `import_discovered_games([candidate1, duplicate])` → 1 imported, 1 skipped
- `import_discovered_games([])` → success=False, "No games to import"
- `import_discovered_games()` with repo error → graceful failure message

**Test file:** `tests/test_game_service.py` (new class `TestImportDiscoveredGames`)
**New tests:** 7 tests

### GREEN
1. Update `AddGameRequest` with `platform: str = ""`, `platform_id: str = ""`, `is_auto_discovered: bool = False`
2. Update `GameService.add_game()` to check `(platform, platform_id)` duplication before executable_path
3. Add `import_discovered_games(self, candidates: list[CandidateGame]) -> GameServiceResult`

### REFACTOR
Extract duplicate-check logic into `_is_duplicate(request)` private method.

### Validation
```bash
python -m pytest tests/test_game_service.py -x -v -k "TestImportDiscoveredGames or TestAddGame"
```

---

## Step 13 — UI Integration

### RED
Write tests:
- `DiscoveryDialog` shows scanning state labels during construction
- `DiscoveryDialog` populates table with candidates on completion
- `DiscoveryDialog.get_selected_candidates()` returns checked items
- `DiscoveryDialog` returns empty list if nothing checked
- `GamesView` has "Scan For Games" button that emits `scan_requested`
- `GamesController._on_scan_requested()` opens dialog, imports selected, refreshes list
- `GameTableModel` has Platform column at index 1

**Test file:** `tests/tracker/discovery/test_discovery_integration.py`
**New tests:** 7 tests

### GREEN
1. Create `ui/games/discovery_dialog.py` — `QDialog` with `QStackedWidget` (scanning → results), `QTableWidget` with checkboxes, "Import Selected" + "Cancel"
2. Update `ui/games/games_view.py` — add `scan_requested` signal, add "Scan For Games" button next to "+ Add Game"
3. Update `game_table_model.py` — add Platform column (column index 1)
4. Update `games_controller.py` — inject `DiscoveryOrchestrator`, connect `scan_requested`, implement `_on_scan_requested()`

### REFACTOR
Ensure `DiscoveryDialog` does not directly call detectors — it receives `DiscoveryOrchestrator` instance.

### Validation
```bash
python -m pytest tests/tracker/discovery/test_discovery_integration.py -x -v
```

---

## Step 14 — Architecture Isolation Tests

### RED
Write `test_discovery_isolation.py`:
- Verify `tracker.discovery.detectors.*` modules do not import `ui`, `services`, `PyQt6`
- Verify `tracker.discovery.orchestrator` does not import `ui`, `PyQt6`
- Verify `ui.games.discovery_dialog` does not import detector internals directly
- Verify `tracker.discovery` package structure: `models`, `detector`, `kv_parser`, `orchestrator`, `detectors.*` all importable

**Test file:** `tests/architecture/test_discovery_isolation.py`
**New tests:** 4 tests

### GREEN
Implement AST-based import checks. Ensure all imports follow the layer isolation rules.

### REFACTOR
None — architecture tests are read-only verification.

### Validation
```bash
python -m pytest tests/architecture/test_discovery_isolation.py -x -v
```

---

## Step 15 — Final Validation

### RED
Full discovery regression suite — all tests must pass.

### GREEN
```bash
# KV Parser + Detectors + Orchestrator
python -m pytest tests/tracker/discovery/ -x -v

# Architecture isolation
python -m pytest tests/architecture/test_discovery_isolation.py -x -v

# Service + Repository
python -m pytest tests/test_game_service.py -x -v

# Full integration
python -m pytest tests/tracker/discovery/test_discovery_integration.py -x -v

# Full suite (excluding CXXABI-affected files)
python -m pytest tests/tracker/discovery/ tests/architecture/test_discovery_isolation.py tests/test_game_service.py -x -v
```

### REFACTOR
Address any test failures, flakiness, or import issues.

### Validation
All tests pass. Architecture enforcement intact.
