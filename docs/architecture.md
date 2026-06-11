# Trackora Architecture

Version: 1.1

---

# System Overview

Trackora consists of six major layers:

1. Tracking Layer
2. Database Layer
3. Statistics Layer
4. UI Layer
5. System Services Layer
6. Support Layer

---

# High-Level Architecture

Windows OS

↓

Process Detection Service

↓

Session Manager

↓

SQLite Database

↓

Statistics Engine

↓

Dashboard UI

↓

User

---

# Tracking Layer

Responsibility:

Detect gaming activity.

Modules:

tracker/process_monitor.py

tracker/session_manager.py

Functions:

* Detect process start
* Detect process stop
* Track active sessions
* Handle crash recovery

Dependencies:

* psutil

---

# Database Layer

Responsibility:

Persist all data.

Modules:

database/database_manager.py

database/repositories/

Functions:

* Store games
* Store sessions
* Store settings
* Recovery state

Dependencies:

* SQLite

---

# Statistics Layer

Responsibility:

Generate analytics.

Modules:

statistics/statistics_service.py

Functions:

* Lifetime statistics
* Daily statistics
* Weekly statistics
* Monthly statistics
* Session counts
* Trends

---

# UI Layer

Responsibility:

User interaction.

Framework:

PyQt6

Modules:

ui/dashboard/

ui/settings/

ui/history/

ui/games/

ui/support_center/

Features:

* Dashboard
* Charts
* History
* Settings
* Game Management
* Support Center

---

# System Services Layer

Modules:

services/tray_service.py

services/startup_service.py

services/export_service.py

Responsibilities:

* System tray
* Windows startup
* Data export
* Notifications

---

# Support Layer

Responsibility:

Provide user-facing support features.

Modules:

models/support/

services/support/

ui/support_center/

Components:

* Bug reports
* Feature requests
* General feedback
* Upcoming updates display

Architecture:

models/support/ — Domain dataclasses (BugReport, FeatureRequest, FeedbackReport)

services/support/ — SupportService facade + GitHubIssueService (GitHub REST API) + ReportQueueService (offline queue)

ui/support_center/ — SupportCenterView + SupportCenterController (navigation + form submission)

Components detail:

* GitHubIssueService — creates GitHub Issues via REST API (POST /repos/{owner}/{repo}/issues)
  Labels: bug, feature-request, feedback
  Error handling: 401 (auth), 403 (rate limit), 404 (repo), network errors
* SupportService — orchestrates local storage + GitHub submission + offline queue
  Returns SupportSubmitResult with local_stored, github_success, queued
* ReportQueueService — persistent offline queue for transient failures
  Storage: %APPDATA%/Trackora/pending_reports/ (atomic JSON writes)
  On startup: auto-submits queued reports, deletes on success, keeps on failure
* SupportCenterController — handles form validation, submission, and result display

Settings keys (stored in database via SettingsRepository):

* github_token        — Personal Access Token (classic, with `public_repo` or `repo` scope)
* github_repo_owner   — GitHub username or organisation that owns the target repository
* github_repo_name    — Repository name to create issues in

Offline queue flow:

1. User submits a report via the UI.
2. SupportService stores locally and attempts GitHub submission.
3. If GitHub fails with a retryable error (network, timeout, rate limit), ReportQueueService saves the report as a JSON file atomically (write to .tmp, rename to .json).
4. Non-retryable errors (auth, config, repo not found) are NOT queued.
5. On next startup, MainWindow._process_report_queue() triggers SupportService.process_queue().
6. Each queued JSON file is read, the domain model is reconstructed, and GitHubIssueService is called.
7. Successful submissions delete the JSON file. Failed submissions remain for retry.

Queue guarantees:

* Atomic writes: never a partial file visible to readers.
* Crash-safe: orphaned .tmp files are cleaned on service initialisation.
* No duplication: UUID-based filenames ensure uniqueness.
* Detailed logging at every step.

Dependencies:

* urllib (stdlib, no extra install needed)

---

# Error Handling

Every module writes logs.

logs/

yyyy-mm-dd.log

Log Levels:

* INFO
* WARNING
* ERROR

---

# Recovery Strategy

Application Crash

↓

Read active_sessions

↓

Restore tracking state

↓

Continue monitoring

---

# Performance Targets

CPU Usage:

< 1%

Memory Usage:

< 100 MB

Startup Time:

< 3 Seconds

Database Response:

< 50 ms

---

# Security Model

* No user account required
* No mandatory cloud storage
* Local-only by default
* User-controlled exports