# Milestone 10 — Update Center

**Version:** 2.0.0-draft  
**Status:** Planning / Phase 0  
**Document Type:** Milestone Specification  
**Owner:** Architecture Team  

---

## Purpose

Provide users with visual and actionable awareness of new Trackora releases. Detect new GitHub releases, display an in-app update banner, show a system tray notification, and present release notes. In v2.0, the update center is **notification-only** — no automatic download or installation.

---

## Scope

### In Scope

- GitHub release detection (REST API)
- Version comparison against current application version
- In-app update banner (non-intrusive, dismissable)
- System tray notification for new releases
- Release notes display dialog
- Local cache of latest release info (offline support)
- Configurable poll interval
- Notification-only update flow (v2.0 constraint)

### Out of Scope

- Automatic download of update packages
- Automatic installation or replacement of application files
- Delta or differential updates
- Update channel selection (stable/beta/nightly)
- Background service for update checks when app is not running
- In-app update progress display
- Code signing verification of downloaded updates (future)

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | The system shall check for new GitHub releases at application startup | Critical |
| FR-02 | The system shall periodically check for updates (configurable interval, default 24h) | Medium |
| FR-03 | The system shall compare detected release version against current app version | Critical |
| FR-04 | The system shall display a non-intrusive update banner in the main window when a new release is available | High |
| FR-05 | The system shall show a system tray notification when a new release is detected | High |
| FR-06 | The system shall display release notes in a dedicated dialog | High |
| FR-07 | The system shall cache the latest release information locally for offline display | Medium |
| FR-08 | The system shall respect GitHub API rate limits (use ETag caching) | High |
| FR-09 | The system shall allow the user to dismiss the update banner | Medium |
| FR-10 | The system shall provide a "Check for Updates" action in the tray menu | High |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Update check at startup shall not block application launch | Async / non-blocking |
| NFR-02 | Update check shall complete within 5 seconds (including network) | <5s |
| NFR-03 | GitHub API calls shall use ETag/304 to avoid data transfer when no new release | Strict |
| NFR-04 | Cache shall survive application restart | Strict |
| NFR-05 | No UI imports in the update-checking service layer | Strict |
| NFR-06 | The update banner must not overlap or obscure critical UI elements | Verified |

---

## Architecture

### Component Diagram

```
GitHub API (releases/latest)
         │
         ▼
UpdateCenterService
  - check_for_updates()
  - get_cached_release()
  - clear_cache()
         │
         ├──► Cache file (%APPDATA%/Trackora/cache/latest_release.json)
         │
         ├──► TrayService (tray notification + menu action)
         │
         └──► MainWindow (update banner + release notes dialog)
```

### UpdateCenterService

**File:** `services/update_center_service.py`

```
UpdateCenterService:
  - __init__(current_version, cache_dir, github_repo, poll_interval)
  - check_for_updates() -> UpdateCheckResult
  - get_cached_release() -> UpdateCheckResult | None
  - clear_cache() -> None
  - open_release_page() -> None (opens browser)
```

**DTOs:**

```python
@dataclass
class GitHubRelease:
    tag_name: str
    version: str  # parsed from tag (e.g., "v2.0.0" -> "2.0.0")
    name: str
    body: str      # release notes (markdown)
    published_at: str
    html_url: str
    prerelease: bool

@dataclass
class UpdateCheckResult:
    update_available: bool
    current_version: str
    latest_version: str | None
    release: GitHubRelease | None
    checked_at: str
    error: str | None
    source: str  # "remote", "cache", or "error"
```

### Update Banner

**File:** `ui/widgets/update_banner.py`

- `UpdateBanner(QFrame)` — dismissable banner widget
- Displays: "Trackora X.Y.Z is available" + "View Release Notes" button + dismiss button
- Colors match current theme (light/dark)
- Animated slide-in from top of main window

### Release Notes Dialog

**File:** `ui/dialogs/release_notes_dialog.py`

- `ReleaseNotesDialog(QDialog)` — modal dialog
- Title: "Trackora X.Y.Z Release Notes"
- Body: rendered from GitHub release body markdown
- Button: "Open on GitHub" (opens browser)
- Button: "Dismiss"

### Tray Integration

**File:** `services/tray_service.py` (extended)

- New tray menu item: "Check for Updates"
- Tray notification: "Trackora X.Y.Z is available" (clickable -> opens release notes)
- Badged tray icon (optional, v2.0 stretch goal)

### Cache

**File:** `%APPDATA%/Trackora/cache/latest_release.json` (via `paths.py`)

```json
{
  "tag_name": "v2.0.0",
  "version": "2.0.0",
  "name": "Trackora 2.0.0",
  "body": "Release notes markdown...",
  "published_at": "2026-06-20T12:00:00Z",
  "html_url": "https://github.com/...",
  "prerelease": false,
  "cached_at": "2026-06-20T12:30:00Z"
}
```

---

## Deliverables

| ID | Deliverable | File |
|----|-------------|------|
| D01 | UpdateCenterService | `services/update_center_service.py` |
| D02 | UpdateCheckResult and GitHubRelease models | `models/update_center.py` |
| D03 | Update banner widget | `ui/widgets/update_banner.py` |
| D04 | Release notes dialog | `ui/dialogs/release_notes_dialog.py` |
| D05 | Tray integration update | Update `services/tray_service.py` |
| D06 | MainWindow integration | Update `ui/main_window.py` |
| D07 | Cache path extension | Update `trackora/core/paths.py` (CACHE_DIR already exists) |
| D08 | Unit tests | `tests/test_update_center_service.py` |
| D09 | Unit tests | `tests/test_update_notification.py` |
| D10 | Integration tests | `tests/test_update_center_integration.py` |

---

## Risks

See also AR-05 in `v2.0.0-overview.md`.

| Risk | Impact | Mitigation |
|------|--------|------------|
| GitHub API rate limiting (unauthenticated: 60 req/h) | Medium | Use ETag/If-None-Match; cache aggressively; document rate limit handling |
| GitHub API endpoint changes | Medium | Use stable `/repos/{owner}/{repo}/releases/latest` endpoint; test in CI |
| User behind proxy/firewall blocking GitHub API | Low | Fail gracefully; serve from cache; no application crash |
| Release notes markdown rendering in Qt | Medium | Use simple QTextBrowser with limited markdown support; fallback to plain text |
| Notification spam on frequent polling | Low | Respect poll interval; never notify for same version twice |
| Pre-release versions detected as updates | Medium | Filter by `prerelease: false`; add `include_prerelease` setting (future) |

---

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-01 | UpdateCenterService correctly detects a newer GitHub release | Integration test (mock API) |
| AC-02 | UpdateCenterService correctly reports no update when on latest version | Integration test (mock API) |
| AC-03 | UpdateCenterService respects ETag caching (304 responses) | Unit test with mock |
| AC-04 | UpdateCenterService returns cached result when offline | Unit test |
| AC-05 | Update banner appears in main window when update is available | UI test |
| AC-06 | Update banner is dismissable and does not reappear for same version | UI test |
| AC-07 | Tray notification is shown for new releases | Integration test |
| AC-08 | Release notes dialog displays GitHub release body | UI test |
| AC-09 | "Check for Updates" action in tray menu works | Integration test |
| AC-10 | Cache survives application restart | Unit test (tmp_path) |
| AC-11 | Startup is not blocked by update check | Measured: <5s async |
| AC-12 | All existing tests pass | Regression |

---

## Dependencies

### Internal Dependencies

| Dependency | Notes |
|------------|-------|
| `trackora/core/paths.py` | CACHE_DIR already exists; no path extension needed unless renaming |
| `services/tray_service.py` | Must extend with update notification support |
| `ui/main_window.py` | Must integrate update banner widget |
| `trackora/__init__.py` | Consumes `__version__` for comparison |
| `services/update_announcements_service.py` | Existing service handles upcoming feature announcements; UpdateCenter is a separate concern for release detection |

### External Dependencies

| Dependency | Version | Justification | Approval Status |
|------------|---------|---------------|-----------------|
| `urllib` / `requests` | stdlib | Use stdlib `urllib` (existing pattern) — **no new dependency** | Not required |

**Decision:** Use stdlib `urllib` consistent with `UpdateAnnouncementsService` and `GitHubIssueService`. No new dependency needed.

---

## Integration Points

| Point | Details |
|-------|---------|
| `ui/main_window.py` | Add `UpdateBanner` widget below toolbar; wire to `UpdateCenterService` |
| `services/tray_service.py` | Add "Check for Updates" action; add notification display on detection |
| `trackora/__main__.py` | Instantiate `UpdateCenterService`; trigger initial check post-startup |
| `trackora/core/paths.py` | CACHE_DIR already defined; cache file path: `CACHE_DIR / "latest_release.json"` |

---

## User Flow

```
Application starts
        │
        ▼
UpdateCenterService.check_for_updates()
  (async, non-blocking)
        │
        ├── Remote success:
        │     ├── New version → tray notification + banner
        │     └── Same version → no action
        │
        └── Remote failure:
              └── Check cache
                    ├── Cache has newer → banner (with "last checked" timestamp)
                    └── No cache → silent
        │
        ▼
User clicks banner / tray notification
        │
        ▼
ReleaseNotesDialog displayed
        │
        ├── "Open on GitHub" → browser
        └── "Dismiss" → close
```

---

## Future Compatibility

### v2.1+

- Automatic download of update packages
- Download progress display
- Background update check service

### v3.0+

- Automatic installation on quit
- Update channel selection (stable, beta, nightly)
- Delta updates

### v4.0+

- In-app update verification (code signing)
- Rollback support
- Update notification preferences per channel

---

## References

- `services/update_announcements_service.py` — Existing announcement service pattern (reference for API, caching, fallback)
- `services/tray_service.py` — Existing tray service for notification extension
- `v2.0.0-overview.md` — Release overview, risk register, testing requirements
- GitHub REST API: `/repos/{owner}/{repo}/releases/latest`
