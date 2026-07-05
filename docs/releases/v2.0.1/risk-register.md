# Trackora v2.0.1 Risk Register

Detailed tracking of risks, mitigations, and safety profiles for the v2.0.1 release cycle.

## 1. GitHub API Rate Limiting (Resolved / Controlled)
* **Risk**: Public GitHub API checks are unauthenticated and rate-limited to 60 queries/hour per IP. Frequent update queries can lead to temporary HTTP 403 blocks.
* **Impact**: Moderate. Update check returns "Rate limited" errors instead of checking the network.
* **Mitigation**: 
  - Retained automatic startup update check restriction to a 1-hour local cooldown.
  - Manual triggers bypass the rate limit cooldown but gracefully catch rate-limit failures to fall back onto the offline local JSON cache file (`latest_release.json`).
  - Caching is managed using standard HTTP `If-None-Match` (ETag) headers, reducing network payload sizes and rate-limiting counters.

## 2. Hardcoded Repository Configurations (Resolved)
* **Risk**: Stale placeholder configurations pointing to `"anomalyco/trackora"` caused HTTP 404 responses during testing.
* **Impact**: High. Prevented update check functionality entirely.
* **Mitigation**: Unified and redirected all repository references to `"anubhab-royy/Trackora"` across the application core and main window. Added specific test coverage `test_api_url_format` to prevent regressions.

## 3. Build/Packaging Out-of-Sync version info (Resolved)
* **Risk**: Rebuilding installers/binaries without manually updating resource headers in `version_info.txt` and Inno Setup files causes mismatching metadata (e.g. executable version properties mismatching installer properties).
* **Impact**: Low/Moderate. Leads to installer and application version property drift.
* **Mitigation**: 
  - Introduced `scripts/bump_version.py` which automatically regenerates version resource parameters dynamically from the source of truth (`trackora/__init__.py`).
  - Modified PyInstaller and Inno Setup spec files to dynamically parse or `#include` the synchronized version files.
  - Added test suite `test_version_consistency.py` validating file structure matches on build.

## 4. PyQt6 OpenUrl Argument Crash (Resolved)
* **Risk**: `QDesktopServices.openUrl` expects a `QUrl` object, but was passed a plain string, causing a TypeError crash inside Qt's event loop.
* **Impact**: Moderate. Blocked update dialogue button execution.
* **Mitigation**: Wrapped all targets in `QUrl` before dispatch. Updated unit tests to inspect the wrapped parameters.
