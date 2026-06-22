# Milestone 11 — Automatic Game Discovery

**Version:** 2.0.0-draft  
**Status:** Planning / Phase 0  
**Document Type:** Milestone Specification  
**Owner:** Architecture Team  

---

## Purpose

Eliminate the friction of manually adding games to Trackora. Automatically detect installed games from major PC gaming platforms, Windows installed applications, and common game directories. Provide a unified discovery orchestration that merges results from all sources, deduplicates, and presents them to the user for one-click addition to their tracked library.

---

## Scope

### In Scope

- **Steam** — detection via Windows Registry (HKCU\Software\Valve\Steam) and library folders file (`steamapps/libraryfolders.vdf`)
- **Epic Games** — detection via registry (HKCU\Software\Epic Games\EOS) and manifest files (`%PROGRAMDATA%\Epic\...\Manifests\*.item`)
- **Riot Games** — detection via registry (HKLM\Software\Riot Games) and client config
- **Battle.net** — detection via registry (HKLM\Software\Battle.net) and agent product DB
- **Ubisoft Connect** — detection via registry and installation cache
- **Xbox/Game Pass** — detection via Windows Store app discovery (shell:AppsFolder) and registry
- **Windows installed applications** — detection via Registry Uninstall keys (HKLM\HKCR\Installer)
- **Common game folders** — scanning well-known directories (Steam library, Epic manifests, `%USERPROFILE%\Documents\My Games`, `%PUBLIC%\Games`)
- **Manual EXE fallback** — user can still add games by browsing to executable
- **DiscoveryOrchestrator** — coordinates all detectors, deduplicates, returns unified result set
- **UI for discovery results** — list of discovered games with checkboxes for selective addition

### Out of Scope

- GOG Galaxy detection (future)
- itch.io app detection (future)
- Amazon Games detection (future)
- Linux game detection (Steam Proton, Lutris — future)
- macOS game detection (future)
- Emulator game ROM detection (future)
- Automatic tracking enable of discovered games (user must confirm)
- Game metadata enrichment (cover art, descriptions — future)

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | The system shall detect installed Steam games via Windows Registry | Critical |
| FR-02 | The system shall detect Steam games from all configured Steam library folders | Critical |
| FR-03 | The system shall detect installed Epic Games titles via manifest files | Critical |
| FR-04 | The system shall detect installed Riot Games titles (LoL, VALORANT, etc.) | High |
| FR-05 | The system shall detect installed Battle.net games (WoW, Diablo, Overwatch, etc.) | High |
| FR-06 | The system shall detect installed Ubisoft Connect games | Medium |
| FR-07 | The system shall detect installed Xbox/Game Pass games (Windows Store) | High |
| FR-08 | The system shall detect applications installed via Windows Installer that match known game patterns | Medium |
| FR-09 | The system shall scan common game directories for executable files | Medium |
| FR-10 | The system shall allow manual EXE selection as a fallback for any missed game | Critical |
| FR-11 | The system shall orchestrate all detectors and return a unified, deduplicated list | Critical |
| FR-12 | The system shall display discovered games in the UI with checkboxes for user selection | High |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Full discovery scan shall complete within 30 seconds | <30s |
| NFR-02 | Each individual detector shall complete within 10 seconds | <10s |
| NFR-03 | Discovery shall not block application startup (background scan) | Strict |
| NFR-04 | Failed detectors shall not block other detectors | Strict |
| NFR-05 | All detectors must be testable without actual platform installations | Strict |
| NFR-06 | Detection must not modify any platform installation files or registry | Strict |
| NFR-07 | No false positive rate > 5% for Windows installed application detection | Measured |

---

## Architecture

### Detector Interface

**File:** `tracker/discovery/detector_interface.py`

```python
class GameDetector(ABC):
    @property
    @abstractmethod
    def platform_name(self) -> str: ...

    @abstractmethod
    def detect(self) -> list[DiscoveredGame]: ...
```

**Model:**

```python
@dataclass
class DiscoveredGame:
    name: str
    executable_path: Path | None
    platform: str           # "steam", "epic", "riot", "battlenet", "ubisoft", "xbox", "windows", "common_folder", "manual"
    platform_id: str | None # platform-specific identifier (Steam AppID, Epic CatalogItemId, etc.)
    icon_path: Path | None
    process_name: str | None
    source_detail: str      # e.g., "Steam library folder: D:\\SteamLibrary"
    is_tracked: bool        # True if already in user's game library
```

### Detectors

| Detector | File | Strategy |
|----------|------|----------|
| `SteamDetector` | `tracker/discovery/detectors/steam_detector.py` | Registry → libraryfolders.vdf → `appmanifest_*.acf` |
| `EpicDetector` | `tracker/discovery/detectors/epic_detector.py` | Registry → `ProgramData/Epic/.../Manifests/*.item` |
| `RiotDetector` | `tracker/discovery/detectors/riot_detector.py` | Registry → client config → installed games list |
| `BattleNetDetector` | `tracker/discovery/detectors/battlenet_detector.py` | Registry → `.agent.db` SQLite → game products |
| `UbisoftDetector` | `tracker/discovery/detectors/ubisoft_detector.py` | Registry → installation cache |
| `XboxDetector` | `tracker/discovery/detectors/xbox_detector.py` | Windows `Shell.AdvancedQuerySearch` or registry AppX manifests |
| `WindowsAppDetector` | `tracker/discovery/detectors/windows_app_detector.py` | Registry `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` + heuristics |
| `CommonFoldersDetector` | `tracker/discovery/detectors/common_folders_detector.py` | Scan predefined directories for known game EXEs |
| `ManualExeDetector` | `tracker/discovery/detectors/manual_exe_detector.py` | File dialog → validate EXE → metadata extraction |

### DiscoveryOrchestrator

**File:** `tracker/discovery/discovery_orchestrator.py`

```
DiscoveryOrchestrator:
  - __init__(games_service, detectors: list[GameDetector])
  - discover_all(progress_callback) -> DiscoveryResult
  - discover_platform(platform: str) -> list[DiscoveredGame]
  - add_to_library(games: list[DiscoveredGame]) -> LibraryAddResult
  - skip_games(games: list[DiscoveredGame]) -> None
```

**Model:**

```python
@dataclass
class DiscoveryResult:
    all_games: list[DiscoveredGame]
    new_games: list[DiscoveredGame]   # not already tracked
    tracked_games: list[DiscoveredGame]  # already in library
    platform_summary: dict[str, int]  # platform -> count
    errors: list[DiscoveryError]
    duration_ms: int
```

### UI

**File:** `ui/games/discovery_dialog.py`

- `GameDiscoveryDialog(QDialog)` — modal dialog
- Progress bar during scan
- Results table: checkbox | Game Name | Platform | Path
- "Select All" / "Deselect All" buttons
- "Add to Library" action
- "Skip" action (remembers skipped games to avoid re-prompting)

**File:** `ui/games/discovery_controller.py`

- `GameDiscoveryController` — wires detectors, orchestrator, and dialog
- Runs discovery in background thread (QThread) to keep UI responsive

### Duplicate Detection

Duplicates are resolved by:
1. Exact executable path match
2. Steam AppID / Epic CatalogItemId match
3. Name similarity (case-insensitive) with same platform
4. `is_tracked` flag set if game already exists in user's SQLite games table

---

## Deliverables

| ID | Deliverable | File |
|----|-------------|------|
| D01 | GameDetector interface | `tracker/discovery/detector_interface.py` |
| D02 | DiscoveredGame model | `tracker/discovery/discovered_game.py` |
| D03 | SteamDetector | `tracker/discovery/detectors/steam_detector.py` |
| D04 | EpicDetector | `tracker/discovery/detectors/epic_detector.py` |
| D05 | RiotDetector | `tracker/discovery/detectors/riot_detector.py` |
| D06 | BattleNetDetector | `tracker/discovery/detectors/battlenet_detector.py` |
| D07 | UbisoftDetector | `tracker/discovery/detectors/ubisoft_detector.py` |
| D08 | XboxDetector | `tracker/discovery/detectors/xbox_detector.py` |
| D09 | WindowsAppDetector | `tracker/discovery/detectors/windows_app_detector.py` |
| D10 | CommonFoldersDetector | `tracker/discovery/detectors/common_folders_detector.py` |
| D11 | ManualExeDetector | `tracker/discovery/detectors/manual_exe_detector.py` |
| D12 | DiscoveryOrchestrator | `tracker/discovery/discovery_orchestrator.py` |
| D13 | Discovery dialog | `ui/games/discovery_dialog.py` |
| D14 | Discovery controller | `ui/games/discovery_controller.py` |
| D15 | Unit tests (per detector) | `tests/test_game_discovery_*.py` |
| D16 | Unit tests (orchestrator) | `tests/test_game_discovery_orchestrator.py` |
| D17 | Integration tests | `tests/test_game_discovery_integration.py` |

---

## Risks

See also AR-03, AR-04 in `v2.0.0-overview.md`.

| Risk | Impact | Mitigation |
|------|--------|------------|
| Steam libraryfolders.vdf format changes (VDF v2) | Medium | Parse as generic key-value; add format version detection; test with sample VDF files |
| Epic manifest format changes | Medium | Parse JSON manifest; schema-version-aware; test with sample manifests |
| Xbox AppX package discovery requires elevation | Medium | Use non-elevated Windows APIs (Shell COM); document elevation requirements |
| Registry key permissions deny read access | Low | Catch permission errors gracefully; skip detector; log warning |
| False positives from WindowsAppDetector (non-game executables) | Medium | Maintain curated game name filter list; publish filter for community contributions |
| Discovery scan takes too long | Medium | Timebox each detector (10s max); run in background thread; progress reporting |
| Games installed on network/removable drives | Low | Detect and list; log warning if drive is unavailable |

---

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-01 | SteamDetector detects games from registry and all library folders | Unit test with mock registry/VDF |
| AC-02 | EpicDetector detects games from manifest directory | Unit test with mock manifests |
| AC-03 | RiotDetector detects installed Riot games | Unit test with mock registry/config |
| AC-04 | BattleNetDetector detects installed Battle.net games | Unit test with mock agent DB |
| AC-05 | UbisoftDetector detects installed Ubisoft games | Unit test with mock registry/cache |
| AC-06 | XboxDetector detects installed Xbox/Game Pass apps | Unit test with mock AppX enumeration |
| AC-07 | WindowsAppDetector detects known game applications | Unit test with mock registry keys |
| AC-08 | CommonFoldersDetector finds game EXEs in scanned directories | Unit test with tmp_path fixtures |
| AC-09 | ManualExeDetector validates and accepts any valid EXE path | Unit test |
| AC-10 | DiscoveryOrchestrator runs all detectors and merges results | Unit test with mock detectors |
| AC-11 | DiscoveryOrchestrator deduplicates games across platforms | Unit test |
| AC-12 | DiscoveryOrchestrator correctly marks already-tracked games | Integration test with GameService |
| AC-13 | Discovery dialog shows results and supports batch add | UI integration test |
| AC-14 | Discovery runs in background thread without blocking UI | Measured |
| AC-15 | All existing tests pass | Regression |
| AC-16 | Full discovery completes within 30 seconds (with mocked data) | Benchmark test |

---

## Dependencies

### Internal Dependencies

| Dependency | Notes |
|------------|-------|
| `services/game_service.py` | DiscoveryOrchestrator uses GameService to check if game is already tracked and to add new games |
| `ui/games/` | Discovery dialog integrated into games section |
| `ui/games/games_controller.py` | Extended with "Discover Games" action |
| `tracker/game_detector.py` | Existing `detect_changes()` for running processes; new discovery is separate (installed games, not running) |

### External Dependencies

| Dependency | Justification | Approval Status |
|------------|---------------|-----------------|
| None required | All platform detection uses stdlib (os, pathlib, winreg on Windows, configparser for VDF) | Not required |

---

## Integration Points

| Point | Details |
|-------|---------|
| `ui/games/games_controller.py` | Add "Discover Games" button/menu action; launch `GameDiscoveryController` |
| `ui/games/games_view.py` | Add discovery dialog integration point |
| `services/game_service.py` | `add_game()` used by orchestrator to persist discovered games |
| `tracker/` | New `tracker/discovery/` sub-package for all discovery logic |
| `trackora/__main__.py` | Instantiate discovery components (if needed at startup) |

---

## Detector Implementation Notes

### Steam Detection Strategy

1. Read `HKCU\Software\Valve\Steam\SteamPath` for Steam root
2. Read `SteamRoot\steamapps\libraryfolders.vdf` for all library paths
3. For each library path, read `library_path\steamapps\appmanifest_<appid>.acf`
4. Extract: `name`, `appid`, `installdir`, `LastPlayed`
5. Determine executable path: `library_path\steamapps\common\<installdir>\*.exe`
6. Filter out Steam tools (Steamworks Common Redistributables, etc.) by known AppID list

### Epic Detection Strategy

1. Read `HKCU\Software\Epic Games\EOS\ModSdkMetadataDir` or `ProgramData\Epic\EpicGamesLauncher\Data\Manifests`
2. Parse `*.item` JSON manifest files
3. Extract: `DisplayName`, `CatalogItemId`, `InstallLocation`, `MainGameAppName` (AppExecutable)

### Riot Detection Strategy

1. Read `HKLM\SOFTWARE\Riot Games\Riot Client\InstallPath`
2. Read client config for installed game list
3. Known games: VALORANT, League of Legends, Teamfight Tactics, Legends of Runeterra, Wild Rift

### Battle.net Detection Strategy

1. Read `HKLM\SOFTWARE\Battle.net\InstallPath` (or `Wow64` node)
2. Locate `.agent.db` (SQLite) in Battle.net installation
3. Query `product_installs` table for installed games
4. Known product codes: `wow`, `wowt`, `d3`, `s2`, `hs`, `hero`, `pro`, `odp`, `viper`

### Ubisoft Detection Strategy

1. Read `HKLM\SOFTWARE\Ubisoft\Launcher\InstallPath`
2. Read `HKLM\SOFTWARE\Ubisoft\Launcher\Installs` for game GUIDs
3. For each GUID, read install path from `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{GUID}`
4. Or scan `%PROGRAMFILES(X86)%\Ubisoft\Ubisoft Game Launcher\cache\installation\`

### Xbox / Game Pass Detection Strategy

1. Use Windows `Windows.ApplicationModel.Store` API or registry `AppxManifest.xml` enumeration
2. Filter by known Xbox Game Pass publishers
3. Extract: `DisplayName`, `InstalledLocation`, `Logo`
4. Note: This is the most complex detector due to Windows AppX package model

### Windows App Detection Strategy

1. Enumerate `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` and `HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall`
2. Filter by `DisplayName` matching known game publishers / patterns
3. Exclude system components, drivers, SDKs, and development tools via blocklist
4. Extract: `DisplayName`, `InstallLocation`, `DisplayIcon`

### Common Folders Detection Strategy

1. Scan: `%USERPROFILE%\Documents\My Games`, `%PUBLIC%\Games`, `%SYSTEMDRIVE%\Games`, `%SYSTEMDRIVE%\Program Files`, `%SYSTEMDRIVE%\Program Files (x86)`
2. Match against known game executable names
3. Exclude non-game executables via curated filter

---

## Testing Strategy

### Mock-Based Testing

Every detector must be testable without the actual platform installed. Use:
- Fake registry values via `unittest.mock.patch('winreg.OpenKey')`
- Fake file system via `tmp_path` fixtures and `.vdf`/`.item`/`.db` sample files
- Sample manifests and configs committed as test fixtures

### Test Fixtures

- `tests/fixtures/discovery/steam/libraryfolders.vdf`
- `tests/fixtures/discovery/steam/appmanifest_*.acf`
- `tests/fixtures/discovery/epic/manifests/*.item`
- `tests/fixtures/discovery/riot/config.yaml`
- `tests/fixtures/discovery/battlenet/agent.db`
- `tests/fixtures/discovery/ubisoft/cache/*.json`
- `tests/fixtures/discovery/xbox/appx_manifests/*.xml`

---

## Future Compatibility

### v2.1+

- GOG Galaxy detection
- Amazon Games detection
- itch.io app detection
- Community-contributed game name filters

### v3.0+

- Linux platform support (Steam Proton, Lutris, Heroic Games Launcher)
- macOS platform support
- Game metadata enrichment (cover art, genre, store page links)
- Automatic import of tracked games from detected platforms

### v4.0+

- Cloud-synced game library across devices
- Game discovery from external drives and network shares
- Emulator game ROM scanning

---

## References

- `tracker/game_detector.py` — Existing game detection for running processes (reference)
- `services/game_service.py` — Game management service (integration target)
- `ui/games/games_controller.py` — Existing games controller (extension target)
- `v2.0.0-overview.md` — Release overview, risk register, testing requirements
