# Update Center — Implementation Plan

## Files to Create

| File | Purpose |
|------|---------|
| `services/update_center_service.py` | `UpdateCenterService` — GitHub API client with ETag caching, SettingsRepository integration, version comparison |
| `ui/dialogs/__init__.py` | Package init for dialog modules |
| `ui/dialogs/update_dialog.py` | `UpdateDialog` — modal dialog showing version, release notes, download/ignore/remind buttons |
| `ui/widgets/update_banner.py` | `UpdateBanner` — non-intrusive QFrame at top of MainWindow |
| `trackora/core/migrations/v2_0_0_add_update_center_settings_v2.py` | Migration for correct settings key names |
| `tests/fixtures/github_release_response.json` | Sample GitHub API response for tests |
| `tests/test_update_center_service.py` | Unit tests for `UpdateCenterService` |
| `tests/test_update_dialog.py` | Unit tests for `UpdateDialog` |
| `tests/test_update_banner.py` | Unit tests for `UpdateBanner` |
| `tests/test_update_center_integration.py` | Integration tests for full flow |
| `tests/architecture/test_update_center_isolation.py` | Layer isolation enforcement |

## Files to Modify

| File | Change |
|------|--------|
| `ui/settings/settings_view.py` | Add "Check for Updates" button, status labels to About group; add `check_updates_requested`, `view_release_notes_requested` signals; add `set_last_checked()`, `set_update_status()` methods |
| `ui/settings/settings_controller.py` | Inject `UpdateCenterService`; add `_on_check_updates()`, `_on_view_release_notes()` handlers |
| `ui/main_window.py` | Create `UpdateCenterService`; create `UpdateBanner`; wire startup update check via `QTimer.singleShot`; wire tray notification |
| `services/tray_service.py` | Add `check_updates_requested` signal; add "Check for Updates" menu action |
| `trackora/core/migrations/v2_0_0_add_update_center_settings.py` | Leave unchanged (idempotent, harmless) |

## TDD Steps

### Step 1 — Version Models & DTOs (`RED → GREEN → REFACTOR`)

**RED:** Write tests for:
- `GitHubRelease` dataclass fields: `tag_name`, `version`, `name`, `body`, `published_at`, `html_url`, `prerelease`, `download_url`
- `GitHubRelease.version` strips leading `"v"` from `tag_name`
- `UpdateCheckResult` dataclass fields: `update_available`, `current_version`, `latest_version`, `release`, `checked_at`, `error`, `source`, `previously_checked`
- `UpdateCheckResult` with no release (error state)
- `UpdateCheckResult` with cached result (source="cache")
- `UpdateCheckResult` with remote result (source="remote")

**GREEN:** Define dataclasses in `services/update_center_service.py`.

**Tests:** 6 tests

---

### Step 2 — Version Comparison (`RED → GREEN → REFACTOR`)

**RED:** Write tests for `UpdateCenterService._is_newer_version()`:
- `"2.0.0"` > `"1.1.0"` → True (major bump)
- `"1.2.0"` > `"1.1.0"` → True (minor bump)
- `"1.1.1"` > `"1.1.0"` → True (patch bump)
- `"1.1.0"` == `"1.1.0"` → False (same)
- `"1.0.0"` < `"1.1.0"` → False (older)
- `"1.1.0.0"` vs `"1.1.0"` → False (invalid latest — log warning)
- `"not_a_version"` → False (log warning)
- `""` → False (log warning)

**GREEN:** Implement `_is_newer_version(latest: str) -> bool` using strict semver tuple comparison.

**Tests:** 8 tests

---

### Step 3 — GitHub API Fetch (`RED → GREEN → REFACTOR`)

**RED:** Write tests for `_fetch_latest_release()`:
- Mock `urlopen` returning sample GitHub API JSON → parsed `GitHubRelease` with correct fields
- Sample response has assets → `download_url` picks first installer .exe
- Sample response has no assets → `download_url` is empty string
- Sample response has no installer asset → `download_url` picks first .exe fallback
- Network error (`URLError`) → raises `UpdateCheckError`
- Invalid JSON → raises `UpdateCheckError`
- HTTP error (404, 500) → raises `UpdateCheckError`

**GREEN:** Implement `_fetch_latest_release() -> GitHubRelease` using `urllib.request` with `ssl.create_default_context()`. 5s timeout. Parse JSON, extract tag/body/assets. No ETag yet (added in Step 4).

**Tests:** 6 tests

---

### Step 4 — ETag/If-None-Match Caching (`RED → GREEN → REFACTOR`)

**RED:** Write tests for ETag support:
- First fetch: no `If-None-Match` header → receives ETag → saves to cache file
- Subsequent fetch: sends saved ETag → 304 response → returns cached result
- Subsequent fetch: sends saved ETag → 200 response → updates ETag cache
- No ETag cache file exists → sends without `If-None-Match`
- Corrupt ETag cache file → sends without `If-None-Match`

**GREEN:** Store/read ETag from `CACHE_DIR / "latest_release_etag.txt"`. On fetch with `If-None-Match` + 304, return cached result from memory.

**Tests:** 5 tests

---

### Step 5 — SettingsRepository Integration (`RED → GREEN → REFACTOR`)

**RED:** Write tests for settings integration:
- `check_for_updates()` updates `update_last_checked` in SettingsRepository (ISO timestamp)
- `check_for_updates()` respects rate limit: if `last_checked` < 1 hour ago, returns cached result
- `ignore_version("2.0.0")` saves to `update_ignored_version` in SettingsRepository
- `clear_ignored_version()` clears `update_ignored_version`
- `is_update_available()` returns False if latest version == ignored version
- `is_update_available()` returns True if latest version > ignored version
- `get_cached_result()` returns last check result from memory
- Auto-check disabled setting prevents startup check (test in integration)

**GREEN:** Wire `SettingsRepository` into `UpdateCenterService.__init__()`. Read/write settings keys. Rate-limit guard using `update_last_checked` timestamp.

**Tests:** 8 tests

---

### Step 6 — Local Cache File Persistence (`RED → GREEN → REFACTOR`)

**RED:** Write tests for filesystem cache:
- After successful remote fetch, cache file written at `CACHE_DIR / "latest_release.json"`
- Cache file contains valid JSON with version, release notes, etc.
- After failed fetch + valid cache file → return cached result (source="cache")
- After failed fetch + missing cache file → return error result (source="error")
- `clear_cache()` removes cache file
- `get_cached_result()` reads from memory cache first (prefer in-memory)
- `get_cached_result()` with no in-memory cache but valid file → returns file cache

**GREEN:** Implement cache file read/write in `CACHE_DIR`. Atomic write (write to `.tmp`, rename).

**Tests:** 7 tests

---

### Step 7 — check_for_updates() Orchestration (`RED → GREEN → REFACTOR`)

**RED:** Write full orchestration tests:
- `check_for_updates()` happy path: remote fetch → newer version → `update_available=True`, source="remote"
- `check_for_updates()` no update: remote fetch → same version → `update_available=False`
- `check_for_updates()` rate-limited: checked 5 min ago → returns cached result, `previously_checked=True`
- `check_for_updates()` offline: network error + cache available → source="cache"
- `check_for_updates()` offline + no cache → source="error", error message populated
- `check_for_updates()` ignored version: newer available but ignored → `update_available=False`
- `check_for_updates()` prerelease ignored: prerelease detected → never newer
- Two calls in sequence: second call returns cached (rate-limit)

**GREEN:** Wire all internal methods into `check_for_updates()` with proper error handling, rate limiting, and ignored-version filtering.

**Tests:** 8 tests

---

### Step 8 — UpdateDialog (`RED → GREEN → REFACTOR`)

**RED:** Write tests for `UpdateDialog`:
- Dialog with update available → shows title "Update Available", version, release notes in QTextBrowser
- Dialog with up-to-date result → shows "Trackora X is the latest version"
- Dialog with error result → shows "Could not check for updates"
- "Download" button → calls `QDesktopServices.openUrl()` with release HTML URL
- "Ignore This Version" button → sets `dialog.ignored_version`, closes dialog
- "Remind Later" button → closes dialog, `dialog.ignored_version` is None
- Dialog without release (error/up-to-date) → no Download/Ignore/Remind buttons, only Close
- Release notes rendered via `QTextBrowser.setMarkdown()`

**GREEN:** Implement `UpdateDialog(QDialog)` — modal dialog with `QTextBrowser` for release notes, three action buttons, and state-based visibility.

**Tests:** 8 tests

---

### Step 9 — UpdateBanner (`RED → GREEN → REFACTOR`)

**RED:** Write tests for `UpdateBanner`:
- Banner hidden by default (`isVisible() == False`)
- `show(version, release)` → banner visible with version text
- `dismiss()` → banner hidden
- Dismiss emits `ignored(version)` signal
- "View Release Notes" button emits `view_notes_requested` signal
- `hide()` → banner hidden, no signal emitted
- Banner has correct object name for styling

**GREEN:** Implement `UpdateBanner(QFrame)` — colored bar with version text, "View Release Notes" button, dismiss "✕" button.

**Tests:** 7 tests

---

### Step 10 — SettingsView Integration + Controller (`RED → GREEN → REFACTOR`)

**RED:** Write tests for SettingsView updates:
- "Check for Updates" button exists in About group
- Clicking button emits `check_updates_requested` signal
- `set_last_checked("2026-06-20T12:00:00")` updates last-checked label
- `set_update_status("Up to date", False)` updates status label, hides "View Release Notes" button
- `set_update_status("Trackora 2.0.0 available", True)` updates status, shows "View Release Notes" button
- "View Release Notes" button emits `view_release_notes_requested` signal
- Status label text matches provided message

**GREEN:** Add button, labels, signals to `SettingsView._build_about_group()`. Add `set_last_checked()`, `set_update_status()` methods.

**Tests:** 7 tests

**GREEN (Controller):** Write tests for `SettingsController` additions:
- `_on_check_updates()` calls `_update_service.check_for_updates()`
- `_on_check_updates()` creates `UpdateDialog` with result
- `_on_check_updates()` on ignore → calls `_update_service.ignore_version()`
- `_on_check_updates()` no ignore → does not call ignore
- `_on_view_release_notes()` gets cached result, opens dialog
- Status labels updated after check

**Tests:** 6 tests

---

### Step 11 — MainWindow Integration (`RED → GREEN → REFACTOR`)

**RED:** Write integration tests:
- `MainWindow.__init__()` creates `UpdateCenterService` with SettingsRepository
- `MainWindow.__init__()` creates `UpdateBanner` (hidden)
- `QTimer.singleShot(5000, ...)` is called for startup check
- `_perform_startup_update_check()` when auto-check disabled → no check
- `_perform_startup_update_check()` when update available → banner shown
- `_perform_startup_update_check()` when update available → tray notification shown
- `_perform_startup_update_check()` when update ignored → no banner, no notification
- `_perform_startup_update_check()` when network error → no crash (logged)
- `UpdateDialog` downloads → `QDesktopServices.openUrl` called
- Tray "Check for Updates" action connected to controller or main window

**GREEN:** Wire in `MainWindow.__init__()` and `_build_views()`:
- Create `UpdateCenterService`
- Create `UpdateBanner` and position at top of content area
- `QTimer.singleShot(5000, _perform_startup_update_check)`
- `_perform_startup_update_check` implementation
- Wire `UpdateBanner` signals to show `UpdateDialog`
- Wire `TrayService` update action

**Tests:** 10 tests

---

### Step 12 — Migration + Architecture Isolation + Validation (`RED → GREEN → REFACTOR`)

**RED (Migration):** Write tests for `v2_0_0_add_update_center_settings_v2`:
- `upgrade()` inserts `update_last_checked`, `update_ignored_version`, `update_auto_check_enabled`
- Idempotent — second run does not error (INSERT OR IGNORE)
- `verify()` returns empty list when all keys present
- `verify()` reports missing keys
- `downgrade()` removes keys
- App version is "2.0.0"

**GREEN:** Implement migration with `INSERT OR IGNORE` pattern matching `Migration` ABC.

**Tests:** 6 tests

**RED (Architecture):** Write `test_update_center_isolation.py`:
- `services/update_center_service.py` does not import `ui.*`, `PyQt6`, `PyQt5`
- `services/update_center_service.py` only imports from stdlib, `database.repositories`, `trackora`
- `ui/dialogs/update_dialog.py` does not import `database.*` or `tracker.*`
- `ui/widgets/update_banner.py` does not import `database.*` or `tracker.*`
- `ui/settings/settings_view.py` does not import `database.*` or `tracker.*`
- Allowed imports verified via AST analysis

**GREEN:** Verify import chains follow architecture rules.

**Tests:** 6 tests

**RED (Integration):** Write `test_update_center_integration.py`:
- Full flow: mock GitHub API → `UpdateCenterService.check_for_updates()` → cache file written → `UpdateCheckResult` has source="remote"
- Second call within 1 min → returns cached (previously_checked=True)
- Cache file survives between instances (read cache on fresh service)
- SettingsRepository persists `update_ignored_version` across service instances
- `ignore_version()` → subsequent `check_for_updates()` returns `update_available=False`
- `clear_ignored_version()` → subsequent check returns `update_available=True`
- `clear_cache()` → cache file removed

**GREEN:** Integration wiring.

**Tests:** 7 tests

---

## Acceptance Criteria

```
1. "Check for Updates" button visible in Settings > About section
2. Clicking "Check for Updates" shows UpdateDialog (update available / up to date / error)
3. UpdateDialog shows release notes when update available
4. "Download" button opens GitHub Releases page in browser
5. "Ignore This Version" suppresses notifications for that version
6. "Remind Later" closes dialog, banner stays visible (if any)
7. Startup check runs 5 seconds after launch (non-blocking)
8. UpdateBanner appears when update detected on startup
9. UpdateBanner dismiss hides it for the ignored version
10. Tray notification shown on startup when update available
11. Tray menu has "Check for Updates" action
12. "Last checked" timestamp shown in Settings after any check
13. All tests pass (architecture + unit + integration)
14. Zero new dependencies
15. No UI imports in service layer
```

## Validation Commands

```bash
# Step 1-7: Service unit tests
python -m pytest tests/test_update_center_service.py -x -v

# Step 8: UpdateDialog
python -m pytest tests/test_update_dialog.py -x -v

# Step 9: UpdateBanner
python -m pytest tests/test_update_banner.py -x -v

# Step 10: Settings UI
python -m pytest tests/test_settings_view_ext.py -x -v  (if created separately)
# OR test in context of existing settings tests:
python -m pytest tests/test_settings_controller.py -x -v

# Step 11: Integration
python -m pytest tests/test_update_center_integration.py -x -v

# Step 12: Migration
python -m pytest tests/test_migrations.py -x -v

# Step 12: Architecture
python -m pytest tests/architecture/test_update_center_isolation.py -x -v

# Full Update Center suite
python -m pytest tests/test_update_center_service.py tests/test_update_dialog.py tests/test_update_banner.py tests/test_update_center_integration.py tests/architecture/test_update_center_isolation.py -x -v

# Full regression
python -m pytest --tb=short
```
