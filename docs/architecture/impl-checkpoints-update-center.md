# Update Center — TDD Checkpoints

## Step 1 — Version Models & DTOs

### RED
Write tests for dataclass models:
- `GitHubRelease` fields: `tag_name`, `version`, `name`, `body`, `published_at`, `html_url`, `prerelease`, `download_url`
- `GitHubRelease.version` strips leading `"v"` from `tag_name`
- `UpdateCheckResult` fields: `update_available`, `current_version`, `latest_version`, `release`, `checked_at`, `error`, `source`, `previously_checked`
- `UpdateCheckResult` with no release (error state, `release=None`)
- `UpdateCheckResult` with `source="cache"` and `previously_checked=False`
- `UpdateCheckResult` with `source="remote"`

**Test file:** `tests/test_update_center_service.py`
**New tests:** 6 tests

### GREEN
Define dataclasses at top of `services/update_center_service.py`:

```python
@dataclass
class GitHubRelease:
    tag_name: str
    version: str
    name: str
    body: str
    published_at: str
    html_url: str
    prerelease: bool = False
    download_url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", self.tag_name.lstrip("v"))

@dataclass
class UpdateCheckResult:
    update_available: bool
    current_version: str
    latest_version: str | None
    release: GitHubRelease | None
    checked_at: str
    error: str | None = None
    source: str = "remote"
    previously_checked: bool = False
```

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/test_update_center_service.py -x -v -k "Step1"
```

---

## Step 2 — Version Comparison

### RED
Write tests for `_is_newer_version(latest)`:
- `"2.0.0"` > `"1.1.0"` → True
- `"1.2.0"` > `"1.1.0"` → True
- `"1.1.1"` > `"1.1.0"` → True
- `"1.1.0"` == `"1.1.0"` → False
- `"1.0.0"` < `"1.1.0"` → False
- `"1.1.0.0"` vs `"1.1.0"` → False (invalid, logged)
- `"not_a_version"` → False (logged)
- `""` → False (logged)

**Test file:** `tests/test_update_center_service.py` (class `TestVersionComparison`)
**New tests:** 8 tests

### GREEN
```python
@staticmethod
def _is_newer_version(latest: str) -> bool:
    try:
        current = tuple(int(x) for x in __version__.split("."))
        latest_tuple = tuple(int(x) for x in latest.split("."))
        if len(current) != len(latest_tuple):
            logger.warning("Version segment mismatch: %s vs %s", __version__, latest)
            return False
        return latest_tuple > current
    except (ValueError, TypeError):
        logger.warning("Could not compare versions: %s vs %s", __version__, latest)
        return False
```

### REFACTOR
Ensure segment-count validation catches `"2.0"` vs `"2.0.0"` mismatches.

### Validation
```bash
python -m pytest tests/test_update_center_service.py -x -v -k "TestVersionComparison"
```

---

## Step 3 — GitHub API Fetch

### RED
Write tests for `_fetch_latest_release()`:
- Mock `urlopen` returning valid GitHub API JSON → parsed `GitHubRelease` with tag, body, assets
- Response has installer asset → `download_url` picks installer .exe
- Response has no installer but has exe → `download_url` picks first .exe
- Response has no assets → `download_url` is `""`
- `URLError` → raises `UpdateCheckError`
- Invalid JSON → raises `UpdateCheckError`
- HTTP 404 → raises `UpdateCheckError`

**Test file:** `tests/test_update_center_service.py` (class `TestAPIFetch`)
**New tests:** 7 tests

### GREEN
```python
_GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"
_CONNECTION_TIMEOUT = 5

class UpdateCheckError(Exception):
    """Raised when the update check fails."""

def _fetch_latest_release(self) -> GitHubRelease:
    url = _GITHUB_API_URL.format(repo=self._repo)
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Trackora"})
    context = ssl.create_default_context()
    try:
        response = urlopen(req, timeout=_CONNECTION_TIMEOUT, context=context)
    except URLError as e:
        raise UpdateCheckError(f"Network error: {e}") from e

    try:
        data = json.loads(response.read().decode("utf-8"))
    except json.JSONDecodeError as e:
        raise UpdateCheckError(f"Invalid JSON: {e}") from e

    tag = data.get("tag_name", "")
    body = data.get("body", "")
    html_url = data.get("html_url", "")
    published_at = data.get("published_at", "")
    prerelease = data.get("prerelease", False)

    download_url = self._resolve_download_url(data.get("assets", []))
    return GitHubRelease(
        tag_name=tag, name=data.get("name", ""), body=body,
        published_at=published_at, html_url=html_url,
        prerelease=prerelease, download_url=download_url,
    )
```

### REFACTOR
Extract asset resolution to `_resolve_download_url(assets)`. Mock `urlopen` via `unittest.mock.patch`.

### Validation
```bash
python -m pytest tests/test_update_center_service.py -x -v -k "TestAPIFetch"
```

---

## Step 4 — ETag/If-None-Match Caching

### RED
Write tests for ETag support:
- First fetch: no `If-None-Match` header sent, ETag from response saved to cache
- Second fetch: `If-None-Match` sent with saved ETag, 304 → returns cached result
- Second fetch: `If-None-Match` sent, 200 → updates ETag and cache
- No ETag cache file → sends without `If-None-Match`
- Corrupt ETag cache file → sends without `If-None-Match`

**Test file:** `tests/test_update_center_service.py` (class `TestETagCache`)
**New tests:** 5 tests

### GREEN
Store ETag in `CACHE_DIR / "latest_release_etag.txt"`. Add `If-None-Match` header to `Request` if ETag file exists. On 304 response (`response.code == 304`), return cached `GitHubRelease` from memory. On 200, update ETag file.

```python
def _load_etag(self) -> str | None:
    path = self._cache_dir / "latest_release_etag.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip() or None
    return None

def _save_etag(self, etag: str) -> None:
    path = self._cache_dir / "latest_release_etag.txt"
    path.write_text(etag, encoding="utf-8")
```

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/test_update_center_service.py -x -v -k "TestETagCache"
```

---

## Step 5 — SettingsRepository Integration

### RED
Write tests for settings integration:
- `check_for_updates()` updates `update_last_checked` to ISO timestamp
- Rate limit: if `last_checked` < 1 hour ago, return cached result without API call
- `ignore_version("2.0.0")` → `update_ignored_version` set in repo
- `clear_ignored_version()` → `update_ignored_version` cleared
- `is_update_available()` returns `False` when latest == ignored version
- `is_update_available()` returns `True` when latest > ignored version
- `get_cached_result()` returns last `UpdateCheckResult` from memory
- Auto-check disabled: `check_for_updates()` not called at startup

**Test file:** `tests/test_update_center_service.py` (class `TestSettingsIntegration`)
**New tests:** 8 tests

### GREEN
```python
def __init__(self, settings_repo, repo="anomalyco/trackora", cache_dir=None):
    self._settings_repo = settings_repo
    self._repo = repo
    self._cache_dir = cache_dir or CACHE_DIR
    self._last_result: UpdateCheckResult | None = None

def check_for_updates(self) -> UpdateCheckResult:
    # Rate-limit check
    last_checked = self._settings_repo.get_value("update_last_checked")
    if last_checked:
        try:
            last_dt = datetime.fromisoformat(last_checked)
            if (datetime.now(UTC) - last_dt).total_seconds() < 3600:
                return self._get_cached_or_error()
        except ValueError:
            pass

    # ... rest of check logic ...

    self._settings_repo.set("update_last_checked", now.isoformat())
    return result

def ignore_version(self, version: str) -> None:
    self._settings_repo.set("update_ignored_version", version)

def clear_ignored_version(self) -> None:
    self._settings_repo.set("update_ignored_version", "")

def is_update_available(self) -> bool:
    if self._last_result is None or not self._last_result.release:
        return False
    ignored = self._settings_repo.get_value("update_ignored_version")
    latest = self._last_result.release.version
    return self._is_newer_version(latest) and latest != ignored
```

### REFACTOR
Extract rate-limit check into `_is_rate_limited()` method.

### Validation
```bash
python -m pytest tests/test_update_center_service.py -x -v -k "TestSettingsIntegration"
```

---

## Step 6 — Local Cache File Persistence

### RED
Write tests for filesystem cache:
- After remote fetch success → `latest_release.json` written with valid JSON
- JSON contains: version, tag_name, name, body, published_at, html_url, prerelease, download_url
- Failed fetch + valid cache → return result with `source="cache"` using cached data
- Failed fetch + no cache → return result with `source="error"`, `error` populated
- `clear_cache()` removes cache file
- `get_cached_result()` with in-memory cache → returns in-memory (no file read)
- `get_cached_result()` with no in-memory but valid file → returns file cache

**Test file:** `tests/test_update_center_service.py` (class `TestCachePersistence`)
**New tests:** 7 tests

### GREEN
```python
_CACHE_FILENAME = "latest_release.json"

def _save_cache(self, release: GitHubRelease, checked_at: str) -> None:
    data = {
        "tag_name": release.tag_name,
        "version": release.version,
        "name": release.name,
        "body": release.body,
        "published_at": release.published_at,
        "html_url": release.html_url,
        "prerelease": release.prerelease,
        "download_url": release.download_url,
        "cached_at": checked_at,
    }
    tmp = self._cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(self._cache_path))

def _load_cache(self) -> GitHubRelease | None:
    if not self._cache_path.is_file():
        return None
    try:
        data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        return GitHubRelease(**{k: data[k] for k in GitHubRelease.__dataclass_fields__})
    except (json.JSONDecodeError, KeyError):
        return None
```

### REFACTOR
Atomic write via `with_suffix(".tmp")` + `os.replace`.

### Validation
```bash
python -m pytest tests/test_update_center_service.py -x -v -k "TestCachePersistence"
```

---

## Step 7 — check_for_updates() Orchestration

### RED
Write full orchestration tests:
- Happy path: remote → newer → `update_available=True`, `source="remote"`
- No update: remote → same version → `update_available=False`
- Rate-limited: checked 5 min ago → `previously_checked=True`, no API call
- Offline + cache → `source="cache"`, `update_available` from cache
- Offline + no cache → `source="error"`, `error` not None
- Ignored version → `update_available=False` (ignored matches latest)
- Prerelease detected → `update_available=False`
- Two calls in sequence: second returns cached (rate-limited)

**Test file:** `tests/test_update_center_service.py` (class `TestCheckForUpdates`)
**New tests:** 8 tests

### GREEN
```python
def check_for_updates(self) -> UpdateCheckResult:
    now = datetime.now(UTC).replace(tzinfo=None)
    checked_at = now.isoformat()

    # Rate-limit: skip API call if checked < 1h ago
    if self._is_rate_limited():
        cached = self._get_cached_or_error()
        if cached:
            cached.previously_checked = True
            return cached

    # Fetch from GitHub
    try:
        release = self._fetch_latest_release()
    except UpdateCheckError as e:
        self._settings_repo.set("update_last_checked", checked_at)
        cached = self._load_cache()
        if cached:
            return UpdateCheckResult(
                update_available=self._is_newer_version(cached.version),
                current_version=__version__,
                latest_version=cached.version,
                release=cached, checked_at=checked_at,
                source="cache",
            )
        return UpdateCheckResult(
            update_available=False, current_version=__version__,
            latest_version=None, release=None,
            checked_at=checked_at, error=str(e), source="error",
        )

    # Parse and compare
    ignored = self._settings_repo.get_value("update_ignored_version")
    is_newer = self._is_newer_version(release.version)
    is_ignored = release.version == ignored or release.prerelease
    update_available = is_newer and not is_ignored

    self._save_cache(release, checked_at)
    self._settings_repo.set("update_last_checked", checked_at)
    self._last_result = UpdateCheckResult(
        update_available=update_available,
        current_version=__version__,
        latest_version=release.version,
        release=release, checked_at=checked_at,
        source="remote",
    )
    return self._last_result
```

### REFACTOR
Split `check_for_updates()` into `_check_remote()`, `_check_offline()`, `_check_cached()` for testability.

### Validation
```bash
python -m pytest tests/test_update_center_service.py -x -v -k "TestCheckForUpdates"
```

---

## Step 8 — UpdateDialog

### RED
Write tests for `UpdateDialog`:
- Update available → title = "Update Available", version shown, release notes in QTextBrowser
- Up-to-date → title = "Up to Date", "Trackora X is the latest version"
- Error → title = "Update Check Failed", error message shown
- "Download" → `QDesktopServices.openUrl` called with `release.html_url`
- "Ignore This Version" → `dialog.ignored_version == "2.0.0"`, dialog closes
- "Remind Later" → `dialog.ignored_version` is None, dialog closes
- Up-to-date/error modes: no Download/Ignore/Remind buttons, only Close
- Release notes rendered as markdown

**Test file:** `tests/test_update_dialog.py`
**New tests:** 8 tests

### GREEN
```python
class UpdateDialog(QDialog):
    ignored_version: str | None = None

    def __init__(self, result: UpdateCheckResult, parent=None):
        super().__init__(parent)
        self._result = result
        self.ignored_version = None
        self._setup_ui()

    def _setup_ui(self):
        # Common: title label
        # Available: QTextBrowser with release body, Download/Ignore/Remind buttons
        # Up-to-date: info label, Close button
        # Error: error label, Close button
        ...
```

**Test file:** `tests/test_update_dialog.py`
**New imports:** `unittest.mock.patch("PyQt6.QtGui.QDesktopServices.openUrl")`

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/test_update_dialog.py -x -v
```

---

## Step 9 — UpdateBanner

### RED
Write tests for `UpdateBanner`:
- Hidden by default (`isVisible()` is `False`)
- `show("2.0.0", release_notes)` → visible, text includes version
- `dismiss()` → hidden, emits `ignored("2.0.0")`
- "View Release Notes" button → emits `view_notes_requested`
- `hide()` → hidden, no signal emitted
- Has correct object name `"UpdateBanner"`

**Test file:** `tests/test_update_banner.py`
**New tests:** 6 tests

### GREEN
```python
class UpdateBanner(QFrame):
    ignored = pyqtSignal(str)
    view_notes_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateBanner")
        self._version = ""
        self._setup_ui()
        self.hide()

    def show(self, version: str, release_notes: str = "") -> None:
        self._version = version
        self._label.setText(f"Trackora {version} is available!")
        super().show()

    def dismiss(self) -> None:
        self.ignored.emit(self._version)
        self.hide()
```

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/test_update_banner.py -x -v
```

---

## Step 10 — SettingsView Integration + Controller

### RED
Write tests for SettingsView updates:
- "Check for Updates" button in About group → emits `check_updates_requested`
- `set_last_checked("2026-06-20T12:00:00")` → label text updated
- `set_update_status("Up to date", False)` → "View Release Notes" hidden
- `set_update_status("Trackora 2.0.0 available", True)` → "View Release Notes" visible
- "View Release Notes" button → emits `view_release_notes_requested`
- Status label shows provided message

**Test file:** `tests/test_settings_view_ext.py` (or inline in existing settings tests)
**New tests:** 6 tests

Write tests for SettingsController additions:
- `_on_check_updates()` calls `_update_service.check_for_updates()`
- `_on_check_updates()` with ignore → calls `_update_service.ignore_version()`
- `_on_check_updates()` no ignore → no ignore call
- `_on_view_release_notes()` gets cached result, opens dialog
- Status labels updated after check

**Test file:** `tests/test_settings_controller.py`
**New tests:** 5 tests

### GREEN
```python
# SettingsView additions:
class SettingsView(QWidget):
    check_updates_requested = pyqtSignal()
    view_release_notes_requested = pyqtSignal()

    def _build_about_group(self) -> QGroupBox:
        ...
        self._check_updates_btn = QPushButton("Check for Updates")
        self._check_updates_btn.clicked.connect(self.check_updates_requested.emit)
        layout.addRow(self._check_updates_btn)

        self._last_checked_label = QLabel("")
        layout.addRow("Last checked:", self._last_checked_label)

        self._update_status_label = QLabel("")
        layout.addRow("", self._update_status_label)

        self._view_notes_btn = QPushButton("View Release Notes")
        self._view_notes_btn.setObjectName("SecondaryButton")
        self._view_notes_btn.clicked.connect(self.view_release_notes_requested.emit)
        self._view_notes_btn.hide()
        layout.addRow("", self._view_notes_btn)

    def set_last_checked(self, iso: str) -> None:
        self._last_checked_label.setText(iso)

    def set_update_status(self, message: str, is_available: bool) -> None:
        self._update_status_label.setText(message)
        self._view_notes_btn.setVisible(is_available)

# SettingsController additions:
class SettingsController:
    def __init__(self, ..., update_service: UpdateCenterService):
        ...
        self._update_service = update_service

    def _connect_signals(self) -> None:
        ...
        self._view.check_updates_requested.connect(self._on_check_updates)
        self._view.view_release_notes_requested.connect(self._on_view_release_notes)

    def _on_check_updates(self) -> None:
        result = self._update_service.check_for_updates()
        dialog = UpdateDialog(result, parent=self._parent_widget)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.ignored_version:
                self._update_service.ignore_version(dialog.ignored_version)
        self._update_status_after_check(result)

    def _update_status_after_check(self, result: UpdateCheckResult) -> None:
        self._view.set_last_checked(result.checked_at)
        if result.update_available and result.release:
            self._view.set_update_status(
                f"Trackora {result.release.version} available", True
            )
        elif result.error:
            self._view.set_update_status("Check failed. See logs.", False)
        else:
            self._view.set_update_status("Up to date", False)

    def _on_view_release_notes(self) -> None:
        result = self._update_service.get_cached_result()
        if result and result.release:
            UpdateDialog(result, parent=self._parent_widget).exec()
```

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/test_settings_controller.py -x -v
```

---

## Step 11 — MainWindow Integration

### RED
Write integration tests:
- `MainWindow.__init__()` creates `UpdateCenterService` with `SettingsRepository`
- `MainWindow.__init__()` creates hidden `UpdateBanner`
- `QTimer.singleShot` called for startup check
- Auto-check disabled → no banner, no notification
- Update available → banner shown, tray notification sent
- Update ignored → no banner, no notification
- Network error → no crash (logged)
- Tray "Check for Updates" action connected
- `_perform_startup_update_check` uses `is_update_available()` for banner decision

**Test file:** `tests/test_update_center_integration.py`
**New tests:** 9 tests

### GREEN
```python
# In MainWindow.__init__() (after _build_views, before _setup_tray):
self._update_service = UpdateCenterService(
    settings_repo=self._settings_repo,
    repo="anomalyco/trackora",
)

self._update_banner = UpdateBanner(self._content)
self._update_banner.ignored.connect(self._on_update_banner_ignored)
self._update_banner.view_notes_requested.connect(self._on_view_release_notes)
self._content.layout().insertWidget(0, self._update_banner)
self._update_banner.hide()

QTimer.singleShot(5000, self._perform_startup_update_check)

# In _setup_tray:
self._tray.check_updates_requested.connect(self._on_check_updates_from_tray)

# New methods:
def _perform_startup_update_check(self) -> None:
    if not self._settings_repo.get_bool("update_auto_check_enabled", default=True):
        return
    try:
        result = self._update_service.check_for_updates()
        if result.update_available and self._update_service.is_update_available():
            self._update_banner.show(result.release.version, result.release.body)
            self._tray.show_notification(
                "Trackora Update",
                f"Trackora {result.release.version} is ready to download",
            )
    except Exception as e:
        logger.warning("Startup update check failed: %s", e)

def _on_update_banner_ignored(self, version: str) -> None:
    self._update_service.ignore_version(version)

def _on_view_release_notes(self) -> None:
    result = self._update_service.get_cached_result()
    if result and result.release:
        UpdateDialog(result, parent=self).exec()

def _on_check_updates_from_tray(self) -> None:
    result = self._update_service.check_for_updates()
    UpdateDialog(result, parent=self).exec()
```

### REFACTOR
Ensure `_perform_startup_update_check` never blocks the event loop (runs synchronously but is dispatched via timer).

### Validation
```bash
python -m pytest tests/test_update_center_integration.py -x -v
```

---

## Step 12 — Migration + Architecture Isolation + Validation

### RED (Migration)
Write tests for `v2_0_0_add_update_center_settings_v2`:
- `upgrade()` inserts `update_last_checked`, `update_ignored_version`, `update_auto_check_enabled`
- Idempotent — second insert does not error
- `verify()` returns empty list when keys present
- `verify()` returns missing keys when absent
- `downgrade()` removes keys
- `app_version == "2.0.0"`

**Test file:** `tests/test_update_center_migration.py`
**New tests:** 6 tests

### RED (Architecture)
Write `test_update_center_isolation.py`:
- `services/update_center_service.py` does not import `ui.*`, `PyQt6`, `PyQt5`
- `services/update_center_service.py` only imports stdlib + `database.repositories` + `trackora`
- `ui/dialogs/update_dialog.py` does not import `database.*` or `tracker.*`
- `ui/widgets/update_banner.py` does not import `database.*` or `tracker.*`
- `ui/settings/settings_view.py` does not import `database.*` or `tracker.*`
- Allowed import chains verified via AST analysis

**Test file:** `tests/architecture/test_update_center_isolation.py`
**New tests:** 6 tests

### GREEN
Create migration following existing pattern:
```python
class V2_0_0AddUpdateCenterSettingsV2(Migration):
    migration_id = "v2_0_0_add_update_center_settings_v2"
    description = "Add Update Center settings keys (corrected)"
    app_version = "2.0.0"
    requires_backup = False
    requires_downtime = False

    _DEFAULTS = {
        "update_last_checked": "",
        "update_ignored_version": "",
        "update_auto_check_enabled": "1",
    }

    def upgrade(self, connection):
        cursor = connection.cursor()
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        for key, value in self._DEFAULTS.items():
            cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)", (key, value, now))

    def verify(self, connection):
        cursor = connection.cursor()
        cursor.execute("SELECT key FROM settings WHERE key IN (?, ?, ?)", *self._DEFAULTS)
        existing = {row[0] for row in cursor.fetchall()}
        missing = set(self._DEFAULTS) - existing
        return [f"Missing keys: {missing}"] if missing else []

    def downgrade(self, connection):
        cursor = connection.cursor()
        for key in self._DEFAULTS:
            cursor.execute("DELETE FROM settings WHERE key = ?;", (key,))
```

### GREEN (Architecture)
AST-based import check. Same pattern as `test_discovery_isolation.py`.

### REFACTOR
None.

### Validation
```bash
python -m pytest tests/architecture/test_update_center_isolation.py -x -v
python -m pytest tests/test_update_center_migration.py -x -v
```

---

## Final Validation

### RED
Full Update Center regression suite — all tests must pass.

### GREEN
```bash
# Service + models + DTOs
python -m pytest tests/test_update_center_service.py -x -v

# UI components
python -m pytest tests/test_update_dialog.py -x -v
python -m pytest tests/test_update_banner.py -x -v

# Integration
python -m pytest tests/test_update_center_integration.py -x -v

# Architecture
python -m pytest tests/architecture/test_update_center_isolation.py -x -v

# Migration
python -m pytest tests/test_update_center_migration.py -x -v

# Full Update Center suite
python -m pytest tests/test_update_center_service.py tests/test_update_dialog.py tests/test_update_banner.py tests/test_update_center_integration.py tests/architecture/test_update_center_isolation.py tests/test_update_center_migration.py -x -v

# Full regression (all tests)
python -m pytest --tb=short

# With CXXABI workaround if needed:
LD_LIBRARY_PATH="" python -m pytest --tb=short
```

### REFACTOR
Address any test failures, flakiness, or import issues.

### Validation
All tests pass. Architecture enforcement intact.
