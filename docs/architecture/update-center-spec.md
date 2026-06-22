# Update Center — Architecture Specification

## 1. Overview

Update Center lets users check for new Trackora releases on GitHub, see release notes, and open the download page — without leaving the app.

**Key constraints:**
- **Notification-only for v2.0.0** — no automatic download or installation
- Startup update check runs **non-blocking** via `QTimer.singleShot` — never blocks UI or tracking
- All GitHub API calls use `urllib.request` (stdlib) — no new dependencies
- Network failures are silent to the user — log warning, continue normally
- UI never calls GitHub API directly — always through service layer
- Rate-limit safe — anonymous GitHub API is 60 req/h; check at most once per hour
- All existing tests must continue to pass

---

## 2. Architecture Diagram

```
USER ACTION                    UI LAYER                       SERVICE LAYER                    PERSISTENCE
───────────                    ────────                       ─────────────                    ───────────

SettingsView                   SettingsController
  "Check For Updates"  ───→     _on_check_updates()
  click                        ───→ UpdateCenterService
  [last checked label]                .check_for_updates()
                                     ───→ GitHub API
                                           GET /repos/{owner}/{repo}/releases/latest
                                           [ETag/If-None-Match]
                                     ←─── UpdateCheckResult
                                     ───→ SettingsRepository
                                           set("update_last_checked", now)
                                           set("update_ignored_version", ...)  [if ignored]
                              ←─── result
                              ───→ UpdateDialog (modal)
                                    [version, release notes, download button,
                                     ignore version checkbox, remind later]
                              ←─── user choice
                              ───→ SettingsRepository (if ignore)
MainWindow startup
  QTimer.singleShot(5000)
  ───→ UpdateCenterService
        .check_for_updates()
        .is_newer_and_not_ignored()
  ───→ if update available:
        UpdateBanner (top of main window)
          "Trackora X.Y.Z available"
          [View Notes] [Dismiss]
        TrayService.show_notification()
          "Trackora X.Y.Z is ready to download"

User clicks banner
  ───→ UpdateDialog (modal)
```

---

## 3. Update Models

### 3.1 GitHubRelease (`services/update_center_service.py`)

```python
@dataclass
class GitHubRelease:
    tag_name: str             # "v2.0.0"
    version: str              # "2.0.0" (tag stripped of leading 'v')
    name: str                 # "Trackora 2.0.0"
    body: str                 # Release notes markdown
    published_at: str         # ISO-8601
    html_url: str             # "https://github.com/anomalyco/trackora/releases/tag/v2.0.0"
    prerelease: bool
    download_url: str         # First installer .exe asset URL (or empty)
```

### 3.2 UpdateCheckResult (`services/update_center_service.py`)

```python
@dataclass
class UpdateCheckResult:
    update_available: bool
    current_version: str      # __version__ at time of check
    latest_version: str | None
    release: GitHubRelease | None
    checked_at: str           # ISO-8601
    error: str | None         # None if success
    source: str               # "remote", "cache", or "error"
    previously_checked: bool  # True if returning cached result
```

---

## 4. UpdateCenterService (`services/update_center_service.py`)

### 4.1 Design

A new service that wraps and extends the existing `services/update_service.py`. The existing service provides the raw GitHub API fetch and version comparison. `UpdateCenterService` adds:

- SettingsRepository integration (last_checked, ignored_version)
- ETag/If-None-Match HTTP caching (rate-limit safe)
- Local cache file (JSON in `CACHE_DIR / "latest_release.json"`)
- Ignored-version filtering
- Rate-limit safety (minimum 1 hour between checks)

```python
class UpdateCenterService:
    def __init__(
        self,
        settings_repo: SettingsRepository,
        repo: str = "anomalyco/trackora",
        cache_dir: Path | None = None,
    ) -> None: ...

    def check_for_updates(self) -> UpdateCheckResult: ...
    def is_update_available(self) -> bool: ...
    def get_cached_result(self) -> UpdateCheckResult | None: ...
    def ignore_version(self, version: str) -> None: ...
    def clear_ignored_version(self) -> None: ...
    def clear_cache(self) -> None: ...
    def open_release_page(self) -> None: ...  # QDesktopServices.openUrl
```

### 4.2 check_for_updates() Flow

```
check_for_updates()
├── Read settings: last_checked, ignored_version
├── If checked < 1 hour ago:
│   └── Return cached result (previously_checked=True)
├── Fetch remote GitHub API:
│   ├── Success:
│   │   ├── Parse GitHubRelease from JSON
│   │   ├── Compare version against __version__
│   │   ├── Check if version is ignored
│   │   ├── Save to cache file (CACHE_DIR / "latest_release.json")
│   │   ├── Save etag to cache (CACHE_DIR / "latest_release_etag.txt")
│   │   ├── Update last_checked in SettingsRepository
│   │   └── Return UpdateCheckResult (source="remote")
│   └── Failure (network/parse):
│       ├── Try loading cache file
│       ├── If cache exists:
│       │   └── Return cached UpdateCheckResult (source="cache")
│       └── If no cache:
│           └── Return UpdateCheckResult (source="error", error=str)
└── Update last_checked in SettingsRepository
```

### 4.3 ETag/If-None-Match Caching

To avoid hitting GitHub API rate limits (60 req/h unauthenticated):

1. **First request**: No `If-None-Match` header. Receive `ETag` from response headers.
2. **Subsequent requests**: Send `If-None-Match: <etag>` header.
3. **304 Not Modified**: Return cached response without parsing. Set `previously_checked=True`.
4. **200 OK**: Parse new response. Update ETag cache.

ETag stored in `CACHE_DIR / "latest_release_etag.txt"`.

### 4.4 Version Comparison

Strict semver (`MAJOR.MINOR.PATCH`):
```python
current = tuple(int(x) for x in __version__.split("."))
latest = tuple(int(x) for x in release.version.split("."))
return latest > current  # True if newer
```

- Pre-release tags (e.g. `v2.1.0-beta.1`) are **ignored** unless `prerelease=False`
- Only exact numeric segments compared — `"2.0"` vs `"2.0.0"` difference is caught and logged
- Invalid version strings log a warning and return `is_newer = False`

### 4.5 Settings Keys

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `update_last_checked` | str (ISO-8601) | `""` | Timestamp of last API check. Empty = never checked. |
| `update_ignored_version` | str (semver) | `""` | Version the user dismissed. Empty = none ignored. |
| `update_auto_check_enabled` | int (0/1) | `1` | Whether to check on startup. |

Note: The existing migration `v2_0_0_add_update_center_settings.py` uses key names `update_check_enabled`, `update_channel`, `last_update_check` — these differ from the current plan. A new migration or update to the existing one will align key names with the implementation.

---

## 5. UI Components

### 5.1 SettingsView Integration

"Check for Updates" button and status labels added to the **About** group in `SettingsView`:

```
┌─ About ──────────────────────────────────────────┐
│ Build Channel:   Production                       │
│ Version:         1.1.0                            │
│ Data Directory:  /home/user/.local/share/Trackora │
│                                                    │
│ [Check for Updates]                                │
│ Last checked: 2026-06-20 12:34 UTC (up to date)   │
│                                                    │
│ [View Release Notes]  (if update available)        │
└────────────────────────────────────────────────────┘
```

**New signals:**
- `check_updates_requested = pyqtSignal()` — emitted when user clicks "Check for Updates"
- `view_release_notes_requested = pyqtSignal()` — emitted when user clicks "View Release Notes"

**New methods:**
- `set_last_checked(iso_timestamp: str) -> None`
- `set_update_status(message: str, is_update_available: bool) -> None`

### 5.2 UpdateDialog (`ui/dialogs/update_dialog.py`)

Modal dialog shown when user clicks "Check for Updates" or "View Release Notes":

```
┌─ Update Available ──────────────────────────────┐
│                                                   │
│  Trackora 2.0.0 is available!                     │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │ Release Notes                               │  │
│  │                                             │  │
│  │ ## What's New                               │  │
│  │ - Automatic Game Discovery                  │  │
│  │ - Update Center                             │  │
│  │ ...                                         │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  [Download]  [Ignore This Version]  [Remind Later]│
└───────────────────────────────────────────────────┘
```

| Aspect | Detail |
|--------|--------|
| **Type** | `QDialog` (modal) |
| **Title** | "Update Available" or "Trackora is up to date" |
| **Download** | Opens `github.com/{repo}/releases/tag/{tag}` in browser via `QDesktopServices.openUrl()` |
| **Ignore Version** | Saves version to `update_ignored_version` setting; closes dialog; hides any banner |
| **Remind Later** | Closes dialog; banner remains visible |
| **Up-to-date state** | Shows "Trackora 1.1.0 is the latest version." with a close button |
| **Error state** | Shows "Could not check for updates. See log for details." with close button |
| **Release notes** | Rendered in `QTextBrowser` with `setMarkdown()` |
| **Sizing** | Default 550×450, resizable |

### 5.3 UpdateBanner (`ui/widgets/update_banner.py`)

Non-intrusive banner at top of MainWindow (below sidebar, above content):

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🎉 Trackora 2.0.0 is available!  [View Release Notes]  [✕ Dismiss] │
└──────────────────────────────────────────────────────────────────────┘
```

| Aspect | Detail |
|--------|--------|
| **Type** | `QFrame` with colored background (accent color for new update, gray for dismissed) |
| **Position** | Placed at top of `MainWindow`'s central widget, above the stacked widget |
| **Dismiss** | Sets `update_ignored_version` in SettingsRepository to current latest version; banner hides permanently for that version |
| **View Notes** | Opens `UpdateDialog` with release notes |
| **Show** | Called after a startup check finds a newer, non-ignored version |
| **Auto-hide** | If the update was already ignored, banner never appears |
| **Animation** | Simple show/hide (no slide animation for v2.0.0) |

### 5.4 TrayService Integration

A new signal and action added to `TrayService`:

- New signal: `check_updates_requested = pyqtSignal()`
- New menu action: `"Check for Updates"` — placed above "Quit" separator
- On startup check finding a newer version: call `tray_service.show_notification("Trackora Update", "Trackora X.Y.Z is ready to download")`

---

## 6. MainWindow Integration

### 6.1 Startup Update Check

```python
# In MainWindow.__init__() or _build_views():
self._update_service = UpdateCenterService(
    settings_repo=self._settings_repo,
    repo="anomalyco/trackora",
)
# Schedule non-blocking startup check
QTimer.singleShot(5000, self._perform_startup_update_check)

# ...

def _perform_startup_update_check(self) -> None:
    if not self._settings_repo.get_bool("update_auto_check_enabled", default=True):
        return
    result = self._update_service.check_for_updates()
    if result.update_available and self._update_service.is_update_available():
        self._show_update_banner(result)
        self._tray.show_notification(
            "Trackora Update",
            f"Trackora {result.latest_version} is ready to download",
        )
```

### 6.2 Wiring SettingsController

```python
# SettingsController additions:
self._view.check_updates_requested.connect(self._on_check_updates)
self._view.view_release_notes_requested.connect(self._on_view_release_notes)

def _on_check_updates(self) -> None:
    result = self._update_service.check_for_updates()
    dialog = UpdateDialog(result, parent=self._parent_widget)
    if dialog.ignored_version:
        self._update_service.clear_ignored_version()  # no, we want to set it
        self._update_service.ignore_version(dialog.ignored_version)
    self._view.set_last_checked(result.checked_at)
    if result.update_available:
        self._view.set_update_status(f"Trackora {result.latest_version} available", True)
    else:
        self._view.set_update_status("Up to date", False)

def _on_view_release_notes(self) -> None:
    result = self._update_service.get_cached_result()
    if result and result.release:
        UpdateDialog(result, parent=self._parent_widget).exec()
```

---

## 7. Cache Strategy

### 7.1 In-Memory Cache (per session)

`UpdateCenterService` caches the last `UpdateCheckResult` in memory. Subsequent calls to `check_for_updates()` within the same session return the cached result if `last_checked` is less than 1 hour ago.

### 7.2 Filesystem Cache (survive restart)

```python
CACHE_DIR / "latest_release.json"       # GitHubRelease serialized
CACHE_DIR / "latest_release_etag.txt"   # ETag header value
CACHE_DIR / "latest_release_meta.json"  # current_version, checked_at, ignored_version at time of check
```

Filesystem cache used:
1. As fallback when network is unavailable (serve stale cache)
2. To persist ETag across restarts
3. To show "last checked" information even before first network check

### 7.3 SettingsRepository (persistent preferences)

- `update_last_checked`: persisting last check timestamp
- `update_ignored_version`: persisting ignored version across restarts
- `update_auto_check_enabled`: persisting auto-check preference

---

## 8. Existing Code Reuse

### 8.1 services/update_service.py (153 lines)

The existing `UpdateService` class provides:
- `UpdateInfo` dataclass — similar to but simpler than `GitHubRelease`
- `check_for_updates()` — calls `/releases/latest` API
- `_fetch_latest_release()` — raw GitHub API fetch with JSON parsing
- `_is_newer_version()` — semver tuple comparison
- Asset resolution logic (prefer installer .exe, fallback to first .exe)

**How it's reused:** The new `UpdateCenterService` will **not** subclass the existing `UpdateService`. Instead, it will incorporate the internals (`_fetch_latest_release`, `_is_newer_version`, asset resolution) directly into its own implementation, enhanced with ETag, caching, and SettingsRepository integration. The existing `update_service.py` file will remain untouched (dead code removal is out of scope for this phase).

### 8.2 services/update_announcements_service.py (269 lines)

Already wired in `MainWindow.__init__()`. This is a separate concern — feature announcements vs. version updates. **Not modified.**

### 8.3 database/repositories/settings_repository.py

Fully reused — `get()`, `set()`, `get_bool()`, `set_bool()` methods cover all Update Center persistence needs.

### 8.4 services/tray_service.py

Extended with:
- New `check_updates_requested` signal
- New "Check for Updates" menu action
- Existing `show_notification()` method reused for update tray notifications

---

## 9. UI Wiring Summary

```
MainWindow
├── Defines _update_service: UpdateCenterService
├── Defines _update_banner: UpdateBanner (hidden by default)
├── Startup: QTimer.singleShot(5000, _perform_startup_update_check)
└── _perform_startup_update_check():
    ├── Reads update_auto_check_enabled from SettingsRepository
    ├── Calls _update_service.check_for_updates()
    ├── If update_available AND not ignored:
    │   ├── Shows _update_banner
    │   └── Calls _tray.show_notification(...)
    └── On error: silently log

SettingsController
├── Receives UpdateCenterService via constructor
├── _on_check_updates():
│   ├── Calls _update_service.check_for_updates()
│   ├── Shows UpdateDialog(result)
│   ├── Handle ignore / dismiss
│   └── Updates SettingsView status labels
└── _on_view_release_notes():
    └── Shows UpdateDialog(cached_result)

SettingsView (About group)
├── "Check for Updates" button → check_updates_requested signal
├── "Last checked" label → set_last_checked()
├── "Status" label → set_update_status()
└── "View Release Notes" button → view_release_notes_requested signal
    (hidden unless update available)

UpdateDialog
├── Shows release notes in QTextBrowser (markdown)
├── "Download" → QDesktopServices.openUrl(release.html_url)
├── "Ignore This Version" → stores ignored_version, closes
└── "Remind Later" → closes, banner stays visible

UpdateBanner (ui/widgets/update_banner.py)
├── "Trackora X.Y.Z is available!" message
├── "View Release Notes" → opens UpdateDialog
├── "Dismiss" → ignores version, hides banner
└── Visible at top of MainWindow content area

TrayService
├── New signal: check_updates_requested
├── New menu action: "Check for Updates"
└── show_notification() called on new version detection
```

---

## 10. Updated Migration Keys

The existing migration `v2_0_0_add_update_center_settings.py` defines:

| Existing Key | New Key (to use) |
|---|---|
| `update_check_enabled` | `update_auto_check_enabled` |
| `update_channel` | _(removed — not used in v2.0.0)_ |
| `last_update_check` | `update_last_checked` |

**Decision:** The existing migration's key names are out of sync with the final design. Rather than modifying the existing migration (which could break existing databases), a **new migration** `v2_0_0_add_update_center_settings_v2` will be created that inserts the correct key names. The original migration will be left in place (idempotent — its keys will simply never be read by the new code).

---

## 11. Testing Strategy

### 11.1 Unit Tests

| Test file | Tests |
|-----------|-------|
| `tests/test_update_center_service.py` | `check_for_updates()` with mock `urlopen`; ETag/304 handling; version comparison; ignored version filtering; rate-limit (1h) guard; network failure → cache fallback; no cache → error result |
| `tests/test_update_center_service.py` | `ignore_version()` / `clear_ignored_version()`; `get_cached_result()` after successful check |
| `tests/test_update_dialog.py` | Dialog shows correct state for: update available, up-to-date, error; download opens URL; ignore stores version; buttons visible/hidden |
| `tests/test_update_banner.py` | Banner shows/hides; dismiss triggers ignore; View Notes opens dialog |
| `tests/test_settings_view_ext.py` | New signals emitted on button clicks; status labels updated |
| `tests/test_tray_updates.py` | "Check for Updates" action emits signal; notification shown for new version |

### 11.2 Integration Tests

| Test file | Tests |
|-----------|-------|
| `tests/test_update_center_integration.py` | Full flow: service → mock API → cache → SettingsRepository persistence; startup check via `QTimer.singleShot` mock; tray notification integration |

### 11.3 Architecture Tests

`tests/architecture/test_update_center_isolation.py` — verify service layer does not import PyQt6 or `ui.*`.

### 11.4 Test Fixtures

- Sample GitHub API JSON responses in `tests/fixtures/github_release_response.json`
- Sample ETag file content
- In-memory SQLite for SettingsRepository

---

## 12. Architecture Rules

```
Do NOT import:
  ├── ui/*                  in services/update_center_service.py
  ├── PyQt6                 in services/update_center_service.py
  └── trackora/__main__.py  in any update-center module

Do NOT:
  ├── Block the Qt event loop during API calls (already sync — use QTimer for async illusion)
  ├── Show UI errors on network failure (log warning, return gracefully)
  ├── Call GitHub API from UI layer (only through service layer)
  ├── Download or install updates automatically
  ├── Modify existing update_service.py (leave as dead code)
  ├── Modify update_announcements_service.py
  └── Add new dependencies (urllib is stdlib)

Allowed imports in services/update_center_service.py:
  ├── json, logging, ssl, time, datetime
  ├── urllib.request (Request, urlopen)
  ├── pathlib, dataclasses, typing
  └── database/repositories/settings_repository.py

Layer isolation:
  services/  →  ui/
  (service)     (settings_controller, main_window)
     │
     ├── database/repositories/ (settings_repo)
     └── trackora/ (__version__)
```

---

## 13. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| Create new `UpdateCenterService` rather than enhance existing `UpdateService` | Existing `update_service.py` has no SettingsRepository or ETag support; rewriting cleanly is safer than modifying dead code that has no tests | 2026-06-20 |
| New migration for correct key names | Existing migration's keys (`update_check_enabled`, `update_channel`, `last_update_check`) don't match the final design. Idempotent — leaving it in place is harmless. | 2026-06-20 |
| Manual check in Settings + startup auto-check | "Check for Updates" button satisfies immediate user need; startup check is optional (default enabled) | 2026-06-20 |
| ETag/If-None-Match instead of polling interval | GitHub rate limit is 60 req/h unauthenticated. ETag cache means most checks are 304 (zero data, no rate-limit impact) | 2026-06-20 |
| Filesystem cache as fallback | Survives restart; serves stale data when offline; no dependency on SettingsRepository (which is backed by the game database — could be locked) | 2026-06-20 |
| QTimer.singleShot(5000) for startup check | Matches existing pattern used for `UpdateAnnouncementsService`. Non-blocking; 5s delay ensures app is fully initialized before network call | 2026-06-20 |
| "Ignore This Version" persists across restarts | Saved in SettingsRepository `update_ignored_version`. Avoids re-notifying for same version every startup | 2026-06-20 |
| Release notes rendered in QTextBrowser with setMarkdown() | Qt's QTextBrowser supports basic Markdown (headings, lists, links, bold, italic). Good enough for GitHub release notes. No markdown library needed | 2026-06-20 |
| Download opens browser, not in-app | v2.0.0 is notification-only. GitHub Releases page handles download naturally. In-app download is a v2.1+ feature | 2026-06-20 |
| Banner at top of MainWindow, not overlay | Simple layout insertion into existing sidebar+content layout. No overlay/z-order complexity | 2026-06-20 |
