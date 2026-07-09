# Trackora v2.0.1 Development Log

This document records the chronological development and implementation logs for all completed engineering tickets during the Trackora v2.0.1 release cycle.

---

## 1. Reliability & Foundation Subsystem (T-201 – T-206)

### T-201: Silent Startup (`--silent` / `-s`)
- **Problem**: Starting Trackora automatically on Windows startup always rendered the main GUI window, interrupting the user's workspace.
- **Solution**: Added support for the `--silent` / `-s` command line argument inside `__main__.py`. The argument sets a runtime configuration. If present, the `MainWindow` is created but its `.show()` method is bypassed, allowing the application to initialize silently directly inside the system tray.
- **Impact**: Seamless background launch without user interruption.
- **Files Affected**: [__main__.py](file:///E:/Code&Programs/GitHub/Trackora/trackora/__main__.py), [mainwindow.py](file:///E:/Code&Programs/GitHub/Trackora/ui/mainwindow.py).

### T-202: Startup Service Validation
- **Problem**: Registry keys for autostart registration could fall out of sync if the application was moved or renamed, failing silently.
- **Solution**: Extended `StartupService` with explicit validation logic that queries registry paths and matches them against `sys.executable`. If there is a mismatch or corruption, it prompts repair workflows.
- **Impact**: High stability of the autostart feature.
- **Files Affected**: [startup_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/startup_service.py).

### T-203: Crash Recovery Improvements
- **Problem**: Unexpected program terminations (power loss, taskkill, etc.) left the tracking state open in the database, resulting in corrupted runtime data on the next launch.
- **Solution**: Refactored the crash recovery mechanism. On launch, the system checks the `startup_state.json` marker. If it indicates an unclean termination, the recovery manager resolves the orphaned active session by calculating its duration up to the last process check interval.
- **Impact**: Zero session duration corruption or lost records during system restarts.
- **Files Affected**: [session_manager.py](file:///E:/Code&Programs/GitHub/Trackora/tracker/session_manager.py), [crash_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/crash/crash_service.py).

### T-204: Background Health Monitor
- **Problem**: Thread lock contention or SQLite database write-blocks could hang background scanning loops without logging diagnostic data.
- **Solution**: Created a lightweight background worker `HealthMonitorService` that observes running threads, memory allocations, and SQLite read/write responsiveness. If delays exceed configured limits, warning profiles are logged.
- **Impact**: Diagnostic logs capture system contention before fatal locks happen.
- **Files Affected**: [health_monitor.py](file:///E:/Code&Programs/GitHub/Trackora/services/health/health_monitor.py).

### T-205: Database Backup Manager
- **Problem**: No automated or standardized mechanism was present to backup settings and tracking history locally.
- **Solution**: Implemented `BackupManager` to perform database ZIP compression with a JSON manifest carrying application version metadata, database properties, and a SHA-256 validation hash.
- **Impact**: Protects data history from accidental deletion.
- **Files Affected**: [backup_manager.py](file:///E:/Code&Programs/GitHub/Trackora/trackora/core/backup_manager.py).

### T-206: Database Restore Manager
- **Problem**: Restoring backup databases was prone to data corruption if the backup archive was incomplete or modified.
- **Solution**: Built the Restore engine, which extracts archives to temporary storage, verifies the SHA-256 checksum in the manifest, checks version compatibility, and replaces the database file atomically. If replacement fails, it performs a rollback from a backup snapshot.
- **Impact**: Risk-free database restore with transactional guarantees.
- **Files Affected**: [backup_manager.py](file:///E:/Code&Programs/GitHub/Trackora/trackora/core/backup_manager.py), [restore_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/backup/restore_service.py).

---

## 2. Update Center Subsystem (T-210 – T-215)

### T-210: Update Checker (Background Threading)
- **Problem**: Fetching releases from GitHub synchronously blocked the main UI thread, resulting in a frozen interface for up to several seconds during startup checks.
- **Solution**: Offloaded the update verification task to `UpdateCheckerThread` (inheriting from `QThread`), which emits signal callbacks when checks finish or fail.
- **Impact**: Non-blocking, smooth user experience.
- **Files Affected**: [update_checker_thread.py](file:///E:/Code&Programs/GitHub/Trackora/services/update_checker_thread.py), [update_center_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/update_center_service.py).

### T-211: GitHub Release Fetcher
- **Problem**: Update check URL was hardcoded to a mock repository `"anomalyco/trackora"`, producing HTTP 404 errors.
- **Solution**: Updated endpoint configurations to point to the active project repository `"anubhab-royy/Trackora"` and integrated ETag caching to conserve API rate limits.
- **Impact**: Release discovery works natively.
- **Files Affected**: [update_center_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/update_center_service.py).

### T-212: Version Comparator
- **Problem**: Naive string comparisons failed on complex semantic version blocks (e.g. comparing "2.0.0" against "2.0.1").
- **Solution**: Built a strict semver validator parsing major, minor, patch, and suffix variables, preventing false update notifications.
- **Impact**: Reliable version detection.
- **Files Affected**: [update_center_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/update_center_service.py).

### T-213: Update Banner
- **Problem**: Users lacked immediate visual cues of updates in the UI.
- **Solution**: Integrated a visual alert panel inside SettingsView displaying release names and update tags.
- **Impact**: Increased update visibility.
- **Files Affected**: [settings_view.py](file:///E:/Code&Programs/GitHub/Trackora/ui/settings/settings_view.py).

### T-214: Release Notes Dialog
- **Problem**: Users could not review release notes inside the application before upgrading.
- **Solution**: Implemented `UpdateDialog` which reads release notes payload from the GitHub release response and renders it inside a scrollable HTML view.
- **Impact**: High visibility of new features and fixes.
- **Files Affected**: [update_dialog.py](file:///E:/Code&Programs/GitHub/Trackora/ui/dialogs/update_dialog.py).

### T-215: Installer Launcher (Direct Link Handlers)
- **Problem**: Clicking "Download" redirected the user to the generic GitHub releases webpage, forcing them to find the installer asset manually.
- **Solution**: Re-routed buttons to fetch the `.exe` asset direct link (`browser_download_url`). Clicking download immediately triggers the browser download. It falls back to the HTML release page if the executable asset is missing.
- **Impact**: Quick upgrades.
- **Files Affected**: [update_dialog.py](file:///E:/Code&Programs/GitHub/Trackora/ui/dialogs/update_dialog.py), [update_center_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/update_center_service.py).

---

## 3. Game Management Subsystem (T-220 – T-224)

### T-220: Delete Game Workflow
- **Problem**: Deleting games required manually editing database files.
- **Solution**: Implemented the transactional delete workflow via `DeleteGameService`.
- **Impact**: In-app management of the tracked games list.
- **Files Affected**: [delete_game_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/delete_game_service.py), [games_controller.py](file:///E:/Code&Programs/GitHub/Trackora/ui/games/games_controller.py).

### T-221: Database Cleanup
- **Problem**: Deleting a game left orphan records in the `sessions` and `active_sessions` tables.
- **Solution**: Configured database cascades and transactional cascading queries in the repository to delete all related session rows whenever a game is deleted.
- **Impact**: Database remains clean and optimized.
- **Files Affected**: [delete_game_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/delete_game_service.py).

### T-222: Statistics Cleanup
- **Problem**: UI stats dashboard remained unchanged after deleting a game until the app was restarted.
- **Solution**: Added logic to recalculate and refresh lifetimes, daily, and weekly statistics immediately post-deletion.
- **Impact**: UI dashboard displays accurate statistics in real-time.
- **Files Affected**: [delete_game_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/delete_game_service.py).

### T-223: Cache Cleanup
- **Problem**: Playtime history graphs and cards loaded cached records of deleted games.
- **Solution**: Integrated cache invalidations in `CacheCleanupService` to flush all stats keys.
- **Impact**: Zero UI caching issues.
- **Files Affected**: [cache_cleanup_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/cache_cleanup_service.py).

### T-224: Confirmation Dialog
- **Problem**: Accidental clicks on game deletion could lead to irreversible loss of tracking history.
- **Solution**: Added `DeleteConfirmationDialog` confirming session counts, warning the user of the permanent deletion, and requiring explicit verification.
- **Impact**: Prevented accidental data losses.
- **Files Affected**: [delete_confirmation_dialog.py](file:///E:/Code&Programs/GitHub/Trackora/ui/dialogs/delete_confirmation_dialog.py).

---

## 4. Support Centre Subsystem (T-230 – T-234)

### T-230: MongoDB Validation
- **Problem**: Offline backup reports submitted to MongoDB Atlas crashed when connection credentials were invalid or transient.
- **Solution**: Added connection validations, verifying authentication and read/write scopes before database insertions.
- **Impact**: Robust database connection.
- **Files Affected**: [mongo_connection.py](file:///E:/Code&Programs/GitHub/Trackora/services/support/mongo_connection.py).

### T-231: Retry Pipeline
- **Problem**: Offline feedback reports queued during network drops were re-submitted sequentially on startup, potentially causing bottlenecks and thread hangs.
- **Solution**: Implemented an off-thread worker loop that validates reports and resubmits them asynchronously.
- **Impact**: High fault-tolerance.
- **Files Affected**: [support_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/support/support_service.py).

### T-232: Offline Queue Validation
- **Problem**: Corrupt or malformed local files inside the pending reports folder could break startup parser loops.
- **Solution**: Built a JSON validator layer (`QueueValidator`) that filters pending reports. If a file fails JSON schema checks, it is moved to a quarantine subdirectory to prevent loops.
- **Impact**: Clean startup parsing.
- **Files Affected**: [queue_validator.py](file:///E:/Code&Programs/GitHub/Trackora/services/support/queue_validator.py).

### T-233: Improved Logging
- **Problem**: Support center submissions lacked contextual diagnostics, making it hard to investigate failures.
- **Solution**: Integrated logging traces recording transaction steps, network states, ETag cache markers, and API HTTP codes.
- **Impact**: Direct debugging capability.
- **Files Affected**: [logging_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/logging_service.py).

### T-234: Submission Confirmation
- **Problem**: Clicking submit did not provide clear visual states indicating if the report was successfully sent, offline-queued, or failed.
- **Solution**: Implemented response dialogs notifying the user of the exact submission result.
- **Impact**: Explicit UX confirmation.
- **Files Affected**: [support_service.py](file:///E:/Code&Programs/GitHub/Trackora/services/support/support_service.py).

---

## 5. Testing & Verification (T-240 – T-244)

### T-240: Regression Testing
- **Problem**: Updates could introduce regression bugs in tracking or dashboard displays.
- **Solution**: Set up a test suite testing 1,531 regression checks, covering all edge cases.
- **Impact**: Zero functional regressions in v2.0.1.
- **Files Affected**: [tests/](file:///E:/Code&Programs/GitHub/Trackora/tests/).

### T-241: Upgrade Testing
- **Problem**: DB Schema upgrades from older versions (v1.0.0, v1.1.0, v2.0.0) could corrupt history or preferences.
- **Solution**: Created transactional migration verification pipelines applying consecutive updates and asserting integrity.
- **Impact**: Safe upgrade migrations.
- **Files Affected**: [tests/test_upgrade_validation.py](file:///E:/Code&Programs/GitHub/Trackora/tests/test_upgrade_validation.py).

### T-242: Installer Testing
- **Problem**: Installer builds could fail to register programs, clean directories, or terminate running instances.
- **Solution**: Set up automated tests validating Inno Setup configurations and binary structure.
- **Impact**: Production-ready setup files.
- **Files Affected**: [tests/test_installer_validation.py](file:///E:/Code&Programs/GitHub/Trackora/tests/test_installer_validation.py).

### T-243: Performance Validation
- **Problem**: New background workers could degrade UI frame rates or CPU/Memory overheads.
- **Solution**: Executed 46 performance benchmarks monitoring execution cycles and allocations.
- **Impact**: Satisfied all Non-Functional Requirements (NFRs).
- **Files Affected**: [tests/test_upgrade_performance.py](file:///E:/Code&Programs/GitHub/Trackora/tests/test_upgrade_performance.py).

### T-244: Release Candidate Validation
- **Problem**: Release validation could miss packaging risks or version discrepancies.
- **Solution**: Audited all build configs, fileversion headers, spec boundaries, and resolved minor bugs.
- **Impact**: Declared production-ready (GO).
- **Files Affected**: [Trackora.spec](file:///E:/Code&Programs/GitHub/Trackora/Trackora.spec), [version_info.txt](file:///E:/Code&Programs/GitHub/Trackora/version_info.txt).
