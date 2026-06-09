# Changelog

## [1.0.0] — 2026-06-09

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
