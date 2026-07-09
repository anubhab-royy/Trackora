# Trackora v2.0.1 Working Changelog

Working log of changes introduced in this release cycle.

## [2.0.1] - 2026-07-06

### Added
- **Silent Startup (T-201)**: Implemented `--silent` argument parsing to start Trackora minimized to system tray without displaying the main GUI window.
- **Background Update Checker (T-210)**: Offloaded update verification to a dedicated background worker (`QThread`) subclass `UpdateCheckerThread` to guarantee responsive startup and prevent main UI blocking.
- **Latest Version Display**: Integrated "Latest Version" and "Auto-Check Updates" controls under SettingsView.
- **Automatic Version Consistency Verification**: Added a pre-build script `scripts/bump_version.py` that parses `trackora/__init__.py` and updates `version_info.txt` and `installer/version.iss` automatically. Added validation checks in `tests/test_version_consistency.py`.

### Improved
- **Manual Update Bypass**: Modified update verification flow to bypass the 1-hour rate limit caching cooldown when triggered manually by the user clicking the "Check for Updates" button.
- **Direct Installer Download (T-215)**: Re-routed the "Download" button in the update dialog to directly prompt browser download of the `.exe` installer asset when available, falling back to the release HTML page if absent.
- **Installer Integration**: Modified Inno Setup configurations to dynamically resolve compile variables from the auto-generated `#include "version.iss"`.

### Fixed
- **PyQt6 QDesktopServices String Crash**: Resolved the application `TypeError` crash by converting plain string URLs to `QUrl` objects when calling `QDesktopServices.openUrl()`.
- **Repository Path Alignment**: Corrected the hardcoded repository configuration from `anomalyco/trackora` to the actual active project repo `anubhab-royy/Trackora` across all update service implementations, fixing update checks failing with HTTP 404.
- **Startup Validation Errors**: Resolved startup service failures related to environment detection and database lock mechanisms.

### Internal
- Added test suites for the background thread, version consistency, manual check bypass, and update dialog link routing.
- Excluded dynamic build include `installer/version.iss` from Git tracking.
