# Changelog

## [2.0.1] — 2026-07-09

### Added
- **Silent Startup (T-201)**: Implemented `--silent` / `-s` argument parsing to start Trackora minimized to the system tray without displaying the GUI window.
- **Background Update Checker (T-210)**: Offloaded update verification to background worker QThread to prevent main UI thread locks.
- **JSON Queue Validation (T-232)**: Added an automatic JSON schema validator (`QueueValidator`) for offline reports, quarantining corrupt payloads to prevent startup parser loops.
- **Cascading Game Deletion UI (T-224)**: Added deletion confirmation dialog displaying session counts and warning notices before permanent removal.

### Changed
- **Direct Installer Download (T-215)**: Re-routed update dialog download logic to directly prompt browser download of `.exe` setup assets from GitHub releases.
- **Repository Mappings (T-211)**: Mapped references to the active project repository `anubhab-royy/Trackora` across update services.

### Improved
- **Manual Check Cooldown Bypass**: Configured manual update checks to bypass ETag cache check constraints, forcing live API validation checks immediately.
- **Contextual Logging Traces (T-233)**: Extended logging detail with system states, connection validations, and API HTTP codes.

### Fixed
- **PyQt6 openUrl String Crash**: Resolved openUrl crash by wrapping string targets inside type-safe `QUrl` objects.
- **Autostart Path Register (T-202)**: Corrected Windows autostart directory configuration to sync matching executable paths.
- **Queue Worker Lock Contention (T-231)**: Resolved startup queue resubmission bottlenecks by integrating file-based locks.
- **Crash Recovery Open Sessions (T-203)**: Fixed session duration recovery computations during unclean termination checks.

### Performance
- Satisfied all Non-Functional Requirements (NFRs).
- Composite dashboard load times verified at 5.25 ms (Target: ≤ 5000 ms).
- Idle memory footprint stabilized at 32 MB with zero leaks across repeated navigation.
- Average active CPU scanning overhead restricted to 0.15%.

### Testing
- Expanded test suite to **2,560 total tests** spanning regression checks, upgrade migration paths, installer registry records, queue schema compliance, and performance NFR benchmarks.

### Release Engineering
- Automated setup compiler version mappings using compile-time `#include "version.iss"` definitions.
- Configured dynamic PyInstaller version info parsing directly from `trackora/__init__.py`.

## [2.0.0] — 2026-06-22

### Highlights

- **MongoDB Integration** — Optional cloud reporting with configurable connection and database target
- **Automatic Game Discovery** — Scans for installed games from Steam, Epic, Battle.net, EA, Ubisoft, and Riot
- **Analytics & Charts** — Full statistics dashboard with daily activity, monthly trends, and game distribution charts
- **Backup & Recovery** — Database backup/restore with crash recovery and startup state detection
- **Upgrade Framework** — Schema migration system supporting v1.0.0 → v2.0.0 upgrades with old GameTracker data migration
- **Support Center** — In-app bug reports, feature requests, and feedback submission via GitHub Issues
- **Runtime Validation** — 46 performance benchmarks across 8 domains, all NFR targets met

### Added

- MongoDB reporting service (`services/support/mongo_report_service.py`)
- Game discovery system (`tracker/discovery/`) with 6 platform detectors
- Statistics service (`trackora_stats/`) with playtime calculation and trend analysis
- Charts: daily activity, monthly trends, game distribution
- Dashboard composite widget with game cards and stat cards
- Support center UI with bug report, feature request, and feedback forms
- GitHub issue service for automated report submission
- Offline report queue with crash-safe atomic storage
- Update service with announcement banners
- Backup manager with full database backup and restore
- Schema migration framework with version tracking
- Environment detection and runtime path resolution
- Single-instance lock prevention
- Update center with dialog-based update notifications
- Theme manager with dark and light modes
- Code signing helper script
- CI/CD pipeline with test, build, and release automation

### Changed

- Version bumped to 2.0.0
- Database schema updated to v2.0.0 (added discovery columns, update center settings)
- All internal migration infrastructure refactored for forward compatibility

### Fixed

- Crash recovery now reliably detects unclean shutdowns
- Startup state management with atomic file writes
- Process monitor handles edge cases with disappearing processes

### Performance

- Dashboard composite load: 4.08ms (NFR: ≤5000ms)
- History default page: 0.43ms (NFR: ≤300ms)
- Charts 30d activity: 0.28ms (NFR: ≤300ms)
- Migration v1→v2 total: 9.90ms (NFR: ≤10000ms)
- Report submission: 2.04ms (NFR: ≤15000ms)

### Packaging

- PyInstaller spec updated for complete hidden import coverage
- Inno Setup installer with automatic GameTracker upgrade path
- AppData migration from old GameTracker paths
- Windows VERSIONINFO resource metadata

## [1.0.0] — 2026-06-11

### Changed

- **Project renamed from GameTracker to Trackora**
- All source code, imports, and module paths updated to Trackora
- Application executable renamed to `Trackora.exe`
- Window title, tray tooltip, and about dialog updated to Trackora
- Database path changed to `%APPDATA%\Trackora\trackora.db`
- Log file path changed to `%APPDATA%\Trackora\logs\trackora.log`
- Windows registry and autostart entries use Trackora naming
- GitHub repository references updated to `anomalyco/trackora`
- All documentation and build instructions updated

### Added

- Initial production release
- Automatic game detection via process monitoring (psutil)
- Session tracking with start/end times and crash recovery
- Session history browser with search, filter, and sort
- Statistics dashboard with lifetime, daily, weekly, monthly playtime
- Interactive charts: daily activity, monthly trends, game distribution
- System tray with minimize-to-tray and background tracking
- Windows startup registration (optional)
- CSV and JSON export with full backup support
- Dark and light themes
- SQLite local storage (no cloud, no accounts)
- 319 automated tests

### Packaging

- PyInstaller standalone executable (`--onefile --windowed`)
- Inno Setup Windows installer
- APPDATA-safe runtime paths for database and logs
- Application icons in PNG and multi-resolution ICO
- Windows VERSIONINFO resource metadata

## [0.9.0] — 2026-05-01

### Added

- Beta release under original GameTracker name
- Core tracking engine and statistics layer
- All UI views: dashboard, games, history, charts, settings
- System tray integration and startup service
- Export and backup functionality
- Theme management with dark/light mode
