# Automatic Game Discovery — Implementation Plan

## Files to Create

| File | Purpose |
|------|---------|
| `tracker/discovery/__init__.py` | Package init, exports |
| `tracker/discovery/models.py` | `CandidateGame`, `DiscoveryResult` DTOs |
| `tracker/discovery/kv_parser.py` | Minimal Valve KeyValues parser (VDF/ACF) |
| `tracker/discovery/detector.py` | `GameDetector` ABC base class |
| `tracker/discovery/detectors/__init__.py` | Package init |
| `tracker/discovery/detectors/steam_detector.py` | Steam launcher scanner |
| `tracker/discovery/detectors/epic_detector.py` | Epic Games launcher scanner |
| `tracker/discovery/detectors/riot_detector.py` | Riot client scanner |
| `tracker/discovery/detectors/battlenet_detector.py` | Battle.net scanner |
| `tracker/discovery/detectors/ubisoft_detector.py` | Ubisoft Connect scanner |
| `tracker/discovery/detectors/ea_detector.py` | EA App scanner |
| `tracker/discovery/detectors/folder_detector.py` | Generic folder scanner |
| `tracker/discovery/orchestrator.py` | `DiscoveryOrchestrator` — runs all detectors, aggregates results |
| `ui/games/discovery_dialog.py` | Modal dialog: scanning → results → confirm |
| `tests/tracker/discovery/__init__.py` | Package init |
| `tests/tracker/discovery/test_kv_parser.py` | KV parser unit tests |
| `tests/tracker/discovery/test_steam_detector.py` | Steam detector tests |
| `tests/tracker/discovery/test_epic_detector.py` | Epic detector tests |
| `tests/tracker/discovery/test_riot_detector.py` | Riot detector tests |
| `tests/tracker/discovery/test_battlenet_detector.py` | Battle.net detector tests |
| `tests/tracker/discovery/test_ubisoft_detector.py` | Ubisoft detector tests |
| `tests/tracker/discovery/test_ea_detector.py` | EA detector tests |
| `tests/tracker/discovery/test_folder_detector.py` | Folder detector tests |
| `tests/tracker/discovery/test_orchestrator.py` | Orchestrator aggregation tests |
| `tests/tracker/discovery/test_discovery_integration.py` | End-to-end flow tests |
| `tests/architecture/test_discovery_isolation.py` | Layer isolation enforcement |
| `tests/tracker/discovery/fixtures/__init__.py` | (empty) |
| `tests/tracker/discovery/fixtures/steam_libraryfolders.vdf` | Sample Steam VDF for tests |
| `tests/tracker/discovery/fixtures/steam_appmanifest_730.acf` | Sample ACF for CS2 |
| `tests/tracker/discovery/fixtures/epic_launcher_installed.dat` | Sample Epic manifest |
| `tests/tracker/discovery/fixtures/riot_installs.json` | Sample Riot config |
| `tests/tracker/discovery/fixtures/battlenet_product.db` | Sample Battle.net DB |

## Files to Modify

| File | Change |
|------|--------|
| `database/models/game.py` | Add `platform`, `platform_id`, `is_auto_discovered` fields |
| `database/repositories/games_repository.py` | Update `_row_to_game()`, `add()`, `update()` for new fields; add `get_by_platform_id()`, `exists_by_platform_id()` |
| `services/game_service.py` | Update `AddGameRequest` with platform fields; add `import_discovered_games()`; update `add_game()` to handle platform dedup |
| `ui/games/games_view.py` | Add `scan_requested` signal; add "Scan For Games" button; add Platform column to table |
| `ui/games/games_controller.py` | Inject `DiscoveryOrchestrator`; add `_on_scan_requested()` handler; wire import flow |
| `ui/games/game_table_model.py` | Add platform column |
| `tracker/__init__.py` | Export discovery models |
| `tests/test_game_service.py` | Add tests for `import_discovered_games()` and platform-aware `add_game()` |
| `tests/conftest.py` | Add `DiscoveryOrchestrator` fixture if needed |

## TDD Steps

### Step 1 — KV Parser (`RED → GREEN → REFACTOR`)

**RED:** Write `test_kv_parser.py` tests:
- Parse simple `"key" "value"` pairs
- Parse nested `{ }` blocks
- Parse full `libraryfolders.vdf` sample
- Parse full `appmanifest_*.acf` sample
- Handle empty input → empty dict
- Handle malformed input → `KVParserError`

**GREEN:** Implement `tracker/discovery/kv_parser.py` — minimal tokeniser that handles quoted strings, `{ }` nesting, `//` comments.

**Tests:** 6 tests

### Step 2 — GameDetector ABC + Models (`RED → GREEN → REFACTOR`)

**RED:** Write tests verifying:
- `GameDetector` cannot be instantiated (abstract)
- `CandidateGame` fields match spec (frozen, optional process_name computed)
- `DiscoveryResult` aggregates candidates + errors + duration

**GREEN:** Implement `tracker/discovery/models.py` + `tracker/discovery/detector.py`.

**Tests:** 4 tests

### Step 3 — SteamDetector (`RED → GREEN → REFACTOR`)

**RED:** Write `test_steam_detector.py` tests:
- Detect CS2 from sample `appmanifest_730.acf` + `libraryfolders.vdf` → single candidate with platform="steam", platform_id="730"
- Detect multiple games from multi-library VDF
- Steam not installed → empty list + error
- Empty library → empty list
- Corrupt manifest → graceful error per manifest
- Registry path (Windows) mocked via `monkeypatch`

**GREEN:** Implement `steam_detector.py` — read `libraryfolders.vdf` via `kv_parser`, iterate `appmanifest_*.acf` files, resolve executables.

**Tests:** 6 tests

### Step 4 — EpicDetector (`RED → GREEN → REFACTOR`)

**RED:** Write `test_epic_detector.py` tests:
- Parse `LauncherInstalled.dat` sample → candidates with platform="epic"
- File missing → empty list + error
- Empty install list → empty list
- Malformed JSON → graceful error

**GREEN:** Implement `epic_detector.py` — read JSON from `LauncherInstalled.dat`, extract `DisplayName`, `AppName`, `InstallLocation`.

**Tests:** 4 tests

### Step 5 — RiotDetector (`RED → GREEN → REFACTOR`)

**RED:** Write `test_riot_detector.py` tests:
- Parse `RiotClientInstalls.json` → League of Legends, VALORANT candidates
- File missing → empty list + error
- Empty config → empty list

**GREEN:** Implement `riot_detector.py` — known game ID → name mapping, resolve executables from install paths.

**Tests:** 3 tests

### Step 6 — BattleNetDetector (`RED → GREEN → REFACTOR`)

**RED:** Write `test_battlenet_detector.py` tests:
- Parse sample `product.db` (SQLite) → candidates with platform="battlenet"
- DB not found → empty list + error
- Corrupt DB → graceful error

**GREEN:** Implement `battlenet_detector.py` — open Battle.net SQLite DB, query `products` table.

**Tests:** 3 tests

### Step 7 — UbisoftDetector (`RED → GREEN → REFACTOR`)

**RED:** Write `test_ubisoft_detector.py` tests:
- Parse sample settings file → candidates
- File missing → empty list + error

**GREEN:** Implement `ubisoft_detector.py`.

**Tests:** 2 tests

### Step 8 — EADetector (`RED → GREEN → REFACTOR`)

**RED:** Write `test_ea_detector.py` tests:
- Parse sample install records → candidates
- EA App not installed → empty list + error

**GREEN:** Implement `ea_detector.py`.

**Tests:** 2 tests

### Step 9 — FolderDetector (`RED → GREEN → REFACTOR`)

**RED:** Write `test_folder_detector.py` tests:
- Scan `tmp_path` with `.exe` files → candidates with platform="generic"
- Empty directory → empty list
- System directory exclusion → no false positives
- Minimum file size filter
- Custom directory list from settings
- No configured folders → empty list + error

**GREEN:** Implement `folder_detector.py`.

**Tests:** 6 tests

### Step 10 — DiscoveryOrchestrator (`RED → GREEN → REFACTOR`)

**RED:** Write `test_orchestrator.py` tests:
- Run all mock detectors → aggregated `DiscoveryResult`
- Dedup by executable_path (same game from two detectors) → single candidate
- Dedup launcher priority (steam > generic) → steam kept
- Exclude already-tracked games (mock `exists_by_executable_path`)
- Collect per-detector errors → errors list populated
- Run no detectors → empty result
- Timing captured → duration_ms > 0

**GREEN:** Implement `orchestrator.py`.

**Tests:** 7 tests

### Step 11 — Game Model + Repository Updates (`RED → GREEN → REFACTOR`)

**RED:** Write tests in `test_game_service.py`:
- `Game` model accepts `platform`, `platform_id`, `is_auto_discovered` with defaults
- `_row_to_game()` reads platform columns from row
- `add()` writes platform columns to INSERT
- `update()` writes platform columns to UPDATE
- `get_by_platform_id()` returns matching game
- `exists_by_platform_id()` returns True/False
- `get_by_platform_id()` returns None when not found

**GREEN:** Update `Game` dataclass, `GamesRepository._row_to_game()`, `add()`, `update()`, `get_by_platform_id()`, `exists_by_platform_id()`.

**Tests:** 7 tests

### Step 12 — GameService Discovery Integration (`RED → GREEN → REFACTOR`)

**RED:** Write tests:
- `AddGameRequest` accepts optional `platform`, `platform_id`, `is_auto_discovered`
- `add_game()` checks duplicate by (platform, platform_id) in addition to executable_path
- `import_discovered_games()` with valid candidates → all imported
- `import_discovered_games()` with duplicate candidates → skips duplicates, imports rest
- `import_discovered_games()` with no candidates → zero imported
- `import_discovered_games()` with repository error → graceful failure message
- `import_discovered_games()` returns correct count in message

**GREEN:** Update `GameService.add_game()`, add `import_discovered_games()`.

**Tests:** 7 tests

### Step 13 — UI Integration (`RED → GREEN → REFACTOR`)

**RED:** Write tests for:
- `DiscoveryDialog` shows scanning state, then results, then confirm
- `DiscoveryDialog` returns selected candidates on accept
- `DiscoveryDialog` returns empty list on cancel
- `GamesView` has "Scan For Games" button, emits `scan_requested`
- `GamesController._on_scan_requested()` opens dialog, calls `import_discovered_games`, refreshes
- `GameTableModel` has Platform column

**GREEN:** Implement `discovery_dialog.py`, update `games_view.py`, `games_controller.py`, `game_table_model.py`.

**Tests:** 6 tests

### Architecture Isolation Tests

**RED:** Write `test_discovery_isolation.py`:
- Detectors do not import `ui`, `services`, `PyQt6`
- `DiscoveryOrchestrator` does not import `ui`, `PyQt6`
- `DiscoveryDialog` does not import detector internals directly
- `tracker.discovery` package structure matches spec

**GREEN:** Verify imports follow architecture rules.

**Tests:** 4 tests

## Acceptance Criteria

```
1. "Scan For Games" button visible in Games View header (next to "+ Add Game")
2. Clicking "Scan For Games" opens modal discovery dialog
3. Scanning phase shows platform-by-platform progress labels
4. Results phase shows table of discovered games (checkbox, name, platform, path)
5. Already-tracked games do not appear in results
6. User can select/deselect individual games or use Select All
7. "Import Selected" imports checked games and shows success count
8. Imported games appear in main games list with platform column populated
9. Duplicate protection: same game cannot be imported twice
10. All 7 detectors run and aggregate results (even if some fail)
11. No startup scanning — discovery runs only on user request
12. All tests pass (architecture + unit + integration)
13. Zero new dependencies
```

## Validation Commands

```bash
# KV Parser
python -m pytest tests/tracker/discovery/test_kv_parser.py -x -v

# Detectors
python -m pytest tests/tracker/discovery/test_steam_detector.py -x -v
python -m pytest tests/tracker/discovery/test_epic_detector.py -x -v
python -m pytest tests/tracker/discovery/test_riot_detector.py -x -v
python -m pytest tests/tracker/discovery/test_battlenet_detector.py -x -v
python -m pytest tests/tracker/discovery/test_ubisoft_detector.py -x -v
python -m pytest tests/tracker/discovery/test_ea_detector.py -x -v
python -m pytest tests/tracker/discovery/test_folder_detector.py -x -v

# Orchestrator
python -m pytest tests/tracker/discovery/test_orchestrator.py -x -v

# Service + Repository
python -m pytest tests/test_game_service.py -x -v

# UI
python -m pytest tests/tracker/discovery/test_discovery_integration.py -x -v

# Architecture
python -m pytest tests/architecture/test_discovery_isolation.py -x -v

# Full discovery suite
python -m pytest tests/tracker/discovery/ tests/architecture/test_discovery_isolation.py tests/test_game_service.py -x -v

# Full regression (excluding CXXABI-affected files)
python -m pytest tests/tracker/discovery/ tests/architecture/ tests/test_game_service.py tests/tracker/ -x -v
```
