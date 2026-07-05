# Architecture Changes

## Purpose

Document every architectural modification introduced in Trackora v2.0.1.

---

## Expected Changes

### Startup

Introduce silent startup workflow while preserving existing startup architecture.

---

### Update Center

Expand Update Service to support:

- Release detection
- Update notifications
- Installer launching

No changes to the existing release infrastructure.

---

### Health Monitoring

Introduce Health Monitor Service responsible for observing:

- Tracking Service
- SQLite
- MongoDB
- Background Workers
- Update Service

Health Monitor must remain independent from business logic.

---

### Backup System

Introduce Backup Service.

Responsibilities:

- Manual backups
- Scheduled backups
- Restore
- Validation

The backup service must never access UI components directly.

---

### Support Centre

Improve MongoDB reliability.

No changes to service contracts.

SupportService remains dependent on AbstractReportService.

---

## Architecture Constraints

The following rules remain mandatory:

- UI never accesses SQLite directly.
- UI never accesses MongoDB directly.
- Services communicate through contracts.
- SQLite remains the source of truth.
- MongoDB remains support infrastructure only.

---

## Implemented Changes in v2.0.1

### 1. Silent Startup Architecture
- **Trigger**: Trackora launched with the `--silent` argument.
- **Workflow**: `__main__.py` intercepts arguments, sets a configuration flag, and constructs `MainWindow`. `MainWindow` starts in tray-only mode: the widget's `show()` is bypassed, keeping the interface hidden until the tray icon is activated.

### 2. Off-Thread Update Checking
- **Thread Class**: `UpdateCheckerThread(QThread)` in `services/update_checker_thread.py`.
- **Purpose**: Prevents networking calls on the UI thread.
- **Wiring**: Emits PyQT signals `check_completed(UpdateCheckResult)` and `check_failed(str)`. Wired up to `MainWindow` and `SettingsController` to update UI elements asynchronously.

### 3. Dynamic Version Centralization
- **Single Source of Truth**: `trackora/__init__.py`.
- **Synchronization**: `scripts/bump_version.py` generates structural dependencies `version_info.txt` and `installer/version.iss` dynamically before PyInstaller/Inno Setup compilation.
- **Validation**: Strict verification via `test_version_consistency.py` failing build if files fall out of sync.

### 4. Direct Browser Link Handlers
- **QUrl wrapping**: Wraps text strings in `QUrl` before invoking `QDesktopServices.openUrl` to prevent type mismatch crashes in PyQt6 bindings.
- **Selection logic**: Dynamically reads GitHub release assets list, preferring direct `browser_download_url` for `.exe` setup files and falling back to `html_url`.

