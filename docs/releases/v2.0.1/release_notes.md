# Trackora v2.0.1 Release Notes

**Release Date**: July 9, 2026  
**Current Version**: v2.0.1  
**Previous Version**: v2.0.0  

---

## Overview

Trackora v2.0.1 is a maintenance and reliability release that enhances system stability, refines user experience pathways, and introduces off-thread checks and data protection capabilities. This release enforces architectural isolation and resolves edge case crash risks identified during initial v2.0.0 deployment.

---

## Highlights

- **Off-Thread Update Checker**: Prevents main GUI thread blocking by offloading release network checks to a background QThread.
- **Direct Installer Upgrade Pathway**: Downloads update binaries (`.exe` installers) directly from GitHub releases assets and triggers them natively.
- **Transactional Cascading Game Deletion**: Safely deletes game entries, cascade-removes historical sessions, flushes stats caches, and updates dashboard metrics atomically.
- **Support Center Offline Queue & Quarantine**: Protects diagnostic reports from network drops using atomic temporary files, JSON schema validation, and quarantine pools for corrupted payloads.
- **Database Backup & Recovery Suite**: Automated manifest validations and rollback restoration paths.

---

## New Features

### 1. Silent Startup
Users can run Trackora minimized on Windows startup using the `--silent` or `-s` command line parameters. The application initializes database checks, starts tray listeners, and runs in the tray without opening the main graphical dashboard window.

### 2. Cascading Game Deletion Workflow
Introduces in-app game deletions from the GamesView panel. A user-friendly confirmation dialog displays impacted session counts. Clicking confirm calls `DeleteGameService` to cascade delete database and metadata entries.

### 3. Update Dialog Release Notes View
The in-app update center dialog fetches remote GitHub markdown description payloads and parses them into a scrollable viewer, letting users view release notes before upgrading.

---

## Architecture Improvements

- **Thread Isolation**: All network operations (GitHub releases API, Support center submissions, Update Checker checks) are fully isolated from the main UI thread.
- **Centralized Version Mapping**: A unified script (`scripts/bump_version.py`) acts as the single source of truth for version definitions. Strict version consistency checks are enforced at build time.
- **Repository Isolation**: UI components communicate strictly via Service Facades. SQL operations and persistence interfaces are isolated in database repositories.

---

## Reliability Improvements

- **Startup Recovery Manager**: Unclean shutdowns are identified via `startup_state.json`. Trackora recovers open sessions automatically on subsequent launch.
- **Atomic File Writing**: Startup configurations, offline report files, and updates are written to `.tmp` directories before atomic renames to avoid partial-write corruptions.
- **Database Backup Manifest validation**: Manual and migration backups verify database SHA-256 integrity using manifests.

---

## Subsystem Updates

### Backup & Restore
Provides manual and automatic backup zip creations containing SQLite databases and manifests. The restore engine handles checksum extraction, atomic file replacement, and safety rollbacks.

### Update Center
Integrates strict semver checks. Manual checker clicks bypass the 1-hour caching cooldown, executing a direct GitHub releases query.

### Delete Workflow
Cleans up database games tables, cascading deletion to tracking sessions. Clears statistics caches in `CacheCleanupService` and refreshes dashboard widgets.

### Support Center & MongoDB Validation
Validates MongoDB database connections, retry pipelines, and report validations.

### Queue Validation & Retry Pipeline
Validates JSON structures inside the offline submission queue. Corrupt files are moved to quarantine. Concurrency is prevented using file-based worker locks.

### Logging Improvements
Traces operational pathways, ETag response states, network connectivity, and transaction SQL timings in `%APPDATA%\Trackora\logs\trackora.log`.

---

## Installer & Upgrade Support

- **Installer compilation**: Modern Inno Setup scripting detects active running instances of Trackora and terminates them before upgrading.
- **Upgrade Support**: Validated migrations for `v1.0.0 → v2.0.1`, `v1.1.0 → v2.0.1`, and `v2.0.0 → v2.0.1` without loss of preferences or tracking histories.

---

## Testing Summary

Trackora v2.0.1 has been tested across a comprehensive test harness containing **2,560 automated tests**:
- **Regression Tests**: 1,531 passed
- **Upgrade Tests**: 614 passed
- **Installer Tests**: 103 passed
- **Queue Validation**: 36 passed
- **Performance Benchmarks**: 46 passed
- **Total Executed**: 2,560
- **Total Passed**: 2,542 (18 skipped due to mock database absences or Windows chmod platform limitations)
- **Failure Rate**: 0.00%

---

## Performance Summary

All Non-Functional Requirements (NFRs) were validated:
- **Dashboard Load time**: 5.25 ms (Avg) — Target: ≤ 5000 ms
- **History default page load**: 0.56 ms — Target: ≤ 300 ms
- **Charts 30d activity**: 0.36 ms — Target: ≤ 300 ms
- **Database Migration time**: 44.91 ms — Target: ≤ 10000 ms
- **Report submission latency**: 2.46 ms — Target: ≤ 15000 ms
- **CPU Idle Overhead**: 0.00% when minimized to tray
- **Active Scanning CPU**: 0.15% average CPU usage
- **Memory Footprint**: 32 MB idle stabilized

---

## Known Limitations

1. **Unsigned Windows Installer**: Windows Defender SmartScreen may display warnings. Users can bypass this by clicking "More info" and selecting "Run anyway."
2. **Setup Wizard License Page**: The license agreement is not currently rendered in the installer wizard window (slated for v2.1.0).
3. **GitHub API Rate Limits**: Updates checks are subject to GitHub API rate limit controls (mitigated by ETag caches).

---

## Future Work

- Implement per-game playtime goal tracking and milestone achievements.
- Custom session tagging and categorization labels.
- Cross-platform support for Linux and macOS.
- Community plug-in hooks for launcher detection expansions.
