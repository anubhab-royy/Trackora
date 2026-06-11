# Changelog

## [1.0.0] — 2026-06-11

### Changed
- **Project renamed from GameTracker to Trackora**
- All source code, imports, and module paths updated to Trackora
- Application executable renamed to `Trackora.exe`
- Window title, tray tooltip, and about dialog updated to Trackora
- Database path changed to `%APPDATA%\Trackora\trackora.db`
- Log file path changed to `%APPDATA%\Trackora\logs\trackora.log`
- Windows registry and autostart entries use Trackora naming
- GitHub repository references updated to `yourusername/trackora`
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
