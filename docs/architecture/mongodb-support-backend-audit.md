# MongoDB Support Backend — Pre-Implementation Audit

**Version:** 1.0  
**Phase:** 12 — Step 1 (Audit Only)  
**Date:** 2026-06-20  
**Scope:** Support Center, Report Queue, Crash Reporting, Supabase Integration  
**Status:** Complete — Awaiting Review  

---

## 1. Overview

This document is the result of a full-codebase audit of Trackora's current Support Center architecture, conducted before any MongoDB implementation work begins.

**Audit scope:**
- Support Service (`services/support/support_service.py`)
- Report Queue Service (`services/support/report_queue_service.py`)
- Crash Service (`services/crash/crash_service.py`)
- Diagnostic Service (`services/crash/diagnostic_service.py`)
- Supabase Integration (`services/support/supabase_report_service.py`, `trackora/core/supabase_config.py`)
- Reporting Interface (`services/support/reporting_interface.py`)
- GitHub Issue Service (`services/support/github_issue_service.py`)
- Data Models (`models/support/bug_report.py`, `feature_request.py`, `feedback_report.py`)
- UI Layer (`ui/support_center/`, `ui/crash_dialog.py`, `ui/main_window.py`)
- Entry point wiring (`trackora/__main__.py`)
- Existing architecture documentation (`docs/architecture/`)

**Approved MongoDB scope (Phase A):**
- `bug_reports`
- `feature_requests`
- `feedback`
- `crash_reports`

Everything else (analytics, insights, recommendations, trends) is OUT OF SCOPE.

---

## 2. Current Support Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      UI Layer (PyQt6)                       │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ SupportCenter    │  │  CrashDialog     │                │
│  │ Widget/Controller │  │  (modal on crash │                │
│  └────────┬─────────┘  │   detection)      │                │
│           │            └────────┬─────────┘                │
└───────────┼─────────────────────┼──────────────────────────┘
            │                     │
            ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    SupportService                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  In-memory storage (list[BugReport], etc.)           │   │
│  │  Serialization (dict) for queue/backend              │   │
│  │  Retry classification (retryable vs non-retryable)   │   │
│  │  Queue submission on failure                         │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────────┐
          │               │                   │
          ▼               ▼                   ▼
┌─────────────────┐ ┌────────────┐ ┌────────────────────┐
│ AbstractReport  │ │ ReportQueue│ │ UpdateAnnouncements│
│ Service (ABC)   │ │ Service    │ │ Service            │
├─────────────────┤ ├────────────┤ ├────────────────────┤
│ SupabaseReport  │ │ JSON files │ │ GitHub Raw JSON    │
│ Service         │ │ pending_   │ │ → cache → fallback │
│ GitHubIssue     │ │ reports/   │ │                    │
│ Service         │ │            │ │                    │
└────────┬────────┘ └────────────┘ └────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    External Backends                         │
│  ┌───────────────────┐  ┌──────────────────┐               │
│  │ Supabase REST API │  │ GitHub REST API  │               │
│  │ /rest/v1/reports  │  │ /repos/*/issues  │               │
│  └───────────────────┘  └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Support Service Audit

**File:** `services/support/support_service.py` (400 lines)

### Responsibilities
- Orchestrate support submissions (bug reports, feature requests, feedback)
- Store submissions **in memory** (`list[BugReport]`, `list[FeatureRequest]`, `list[FeedbackReport]`)
- Delegate backend submission to an `AbstractReportService` implementation
- Queue failed submissions via `ReportQueueService` for offline retry
- Provide announcements/upcoming updates data to the UI
- Reconstruct domain models from queued JSON data during retry

### Submission Flow
1. UI controller calls `submit_bug_report()`, `submit_feature_request()`, or `submit_feedback()`
2. A UUID `id` is assigned to the model
3. The report is appended to the in-memory list
4. `_submit_with_github_and_queue()` attempts backend submission via `_try_github_submit()`
5. If backend fails with a **retryable** error, `_try_queue_report()` saves to `ReportQueueService`
6. A `SupportSubmitResult` DTO is returned to the UI

### External Integrations
- `AbstractReportService` (ABC) — currently backed by `SupabaseReportService` or `GitHubIssueService`
- `ReportQueueService` — offline queue
- `UpdateAnnouncementsService` — remote announcements fetch

### Dependencies
- `models.support.bug_report`, `.feature_request`, `.feedback_report`
- `services.support.reporting_interface.AbstractReportService`
- `services.update_announcements_service`

### Retry Behavior
- Only transient errors are queued:
  - **Retryable:** network errors, timeouts, rate limits, server errors (5xx)
  - **Non-retryable:** "not configured", "authentication failed", "not found", "check your"
- Classification is done via substring matching against `_NON_RETRYABLE_KEYWORDS`
- Retry happens at next application startup via `process_queue()`

### Queue Usage
- `process_queue()` is called once from `MainWindow._process_report_queue()` at startup
- It delegates to `ReportQueueService.process_queue()` with a closure that calls `AbstractReportService`

### Key Observation
- **In-memory only** — reports are NOT persisted to SQLite or any persistent local store
- If the application crashes before queue submission, the report is lost
- The only persistence mechanism is the offline queue (JSON files), which only triggers on backend failure

---

## 4. Report Queue Audit

**File:** `services/support/report_queue_service.py` (263 lines)

### Queue Structure
- **Filesystem-based** using JSON files in `BASE_DIR/pending_reports/`
- One file per queued report
- UUID-based filename to prevent collisions

### Queue Storage Format
```json
{
  "type": "bug|feature|feedback",
  "data": { ... model fields ... },
  "created_at": "2026-06-20T12:00:00+00:00"
}
```

### Retry Logic
- `process_queue()` iterates all `.json` files in the storage directory
- For each file:
  1. Load and validate JSON
  2. Check `type` is known (`bug`, `feature`, `feedback`)
  3. Call `submit_fn(report_type, data)`
  4. On success → delete the `.json` file
  5. On failure → keep the file for next retry
- Failed submissions remain indefinitely; there is no max-retry or backoff

### Failure Handling
- Corrupted JSON → logged, file stays for next attempt
- Unknown report type → logged, file stays
- OS errors → logged, file stays
- No automatic cleanup of permanently-failed reports

### Offline Behavior
- Files are written atomically (write to `.tmp`, rename to `.json`)
- Orphaned `.tmp` files are cleaned on `__init__`
- No network dependency for queue operations

### Data Lifecycle
- Created: on backend submission failure (retryable errors only)
- Processed: on next application startup
- Deleted: on successful submission
- Orphaned: failures accumulate; never automatically removed
- No TTL, no max-age, no size limit

### Key Observation
- The `save_report()` method does NOT check for duplicate or re-queue an already-queued report
- The `reconstruct_model()` method is duplicated in both this file and `support_service.py`
- Crash reports are NOT queued (they go directly via `submit_report()` on the `AbstractReportService`)

---

## 5. Crash Reporting Audit

### Crash Service

**File:** `services/crash/crash_service.py` (221 lines)

**Flow:**
1. `StartupStateManager` maintains `startup_state.json` in `BASE_DIR/`
   - `mark_running()` called at startup
   - `mark_closed_cleanly()` called on clean exit
2. `CrashService.check_for_crash()` is called **before** `mark_startup()`
   - If previous state was `"running"` → crash detected
   - `DiagnosticService.collect_report()` generates a `CrashReport`
   - `DiagnosticService.save_report()` writes to `BASE_DIR/crash_reports/`
3. `MainWindow._check_for_crashes()` shows `CrashDialog` with three options:
   - **Send Report** → calls `AbstractReportService.submit_report(ReportType.CRASH, ...)`
   - **Review Report** → displays JSON in read-only text area
   - **Dismiss** → deletes the crash report JSON file
4. Crash dialog submission uses the `AbstractReportService` interface (Supabase or GitHub)

### Diagnostic Service

**File:** `services/crash/diagnostic_service.py` (188 lines)

**Diagnostic collection:**
- `report_id` (UUID4)
- `timestamp` (ISO-8601 UTC)
- `app_version` (from `trackora.__version__`)
- `os_version` (via `platform.platform()`)
- `os_platform` (via `platform.system()`)
- `active_sessions` (from `TrackingState`)
- `tracked_games` count
- `stack_trace` (if available)
- `recent_log_entries` (last 50 lines from `trackora.log`)
- `crash_type` (`"unexpected_shutdown"` or `"unhandled_exception"`)
- `was_tracking` (boolean)

**Persistence:**
- Written as JSON to `BASE_DIR/crash_reports/{report_id}.json`
- Atomic writes (`.tmp` + rename)
- No automatic upload — user must explicitly choose "Send Report"

**Queue Integration:**
- Crash reports are NOT integrated with `ReportQueueService`
- If the backend is unavailable when user clicks "Send Report", the error is shown in the dialog but the report is NOT queued for retry
- The report JSON remains on disk regardless (unless user explicitly dismisses)

### Key Observation
- Crash reports are a **separate data flow** from support reports
- No offline queue for crash reports
- The `CrashReport` dataclass has no MongoDB equivalent planned for its current model — but `crash_reports` is in scope

---

## 6. Supabase Integration Audit

### Files Containing Supabase References

| File | Line(s) | Role |
|------|---------|------|
| `services/support/supabase_report_service.py` | 1–395 | **Primary Supabase implementation** — REST API client for report submission |
| `services/support/__init__.py` | 10, 22 | Exports `SupabaseReportService` |
| `trackora/core/supabase_config.py` | 1–2 | **Hardcoded** Supabase URL and anonymous key |
| `trackora/__main__.py` | 33, 199–209 | Wires `SupabaseReportService` as default backend |
| `ui/main_window.py` | 100, 116–117 | Accepts `AbstractReportService`; fallback to `GitHubIssueService` |
| `tests/test_supabase_report_service.py` | 1–681 | Full test suite |

### SupabaseReportService Responsibilities (`services/support/supabase_report_service.py`)
- Implements `AbstractReportService` ABC
- Submits bug reports, feature requests, feedback, and crash reports to Supabase `reports` table
- Uses `urllib` only (stdlib) — no `supabase-py` SDK
- Reads config from: constructor args → environment variables → `.env` file → empty string
- Posts JSON to `{SUPABASE_URL}/rest/v1/reports` with `apikey` and `Authorization` headers
- 15-second timeout
- HTTP error handling: 401/403 (auth), 409 (conflict), 4xx (client), 5xx (server)

### SupabaseConfig (`supabase_report_service.py:82-96`)
```python
@dataclass
class SupabaseConfig:
    url: str
    anon_key: str
```

### Credentials (`trackora/core/supabase_config.py`)
**HARDCODED** in source — contains live Supabase URL and anonymous key:
```
SUPABASE_URL="https://uphwhrcmmdnekgoojzza.supabase.co"
SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIs..."
```

This is a **security concern** — while the key is "anonymous" (RLS-protected), hardcoding credentials in source is not best practice.

### Data Flow (Supabase)
1. `SupportService` receives user submission
2. Calls `SupabaseReportService.submit_bug/feature/feedback/report()`
3. Service constructs a JSON row with `type`, `title`, `description`, `app_version`, `os`, `status`, `source`, `payload`
4. POSTs to `${base}/rest/v1/reports` via `urllib.request.urlopen()`
5. Returns `SubmitResult(success=True)` on HTTP 2xx
6. On failure: returns `SubmitResult(success=False, error_message=...)` with categorized error

### Dependencies
- `urllib` (stdlib)
- `json` (stdlib)
- `os` (stdlib)
- `platform` (stdlib)
- No external SDKs

### Key Observations
- `SupabaseReportService` is **not interchangeable** in the current DI wiring
- The entry point (`__main__.py`) creates `SupabaseReportService()` directly, not via configuration
- `GitHubIssueService` is only used as a fallback in `MainWindow` when no `report_service` is passed
- The Supabase table name `reports` is hardcoded
- No Supabase query/read capability exists — write-only

---

## 7. Offline-First Architecture Audit

### How Reports Behave Without Internet
1. User submits report via UI
2. `SupportService` stores in-memory, attempts backend submission
3. Backend fails with network error (retryable)
4. `ReportQueueService.save_report()` writes JSON atomically to `pending_reports/`
5. User sees "Report saved locally and will be sent automatically"
6. `MainWindow._process_report_queue()` runs at **next startup only**
7. Queue processed: success → delete, fail → keep for next retry

### How Reports Are Retried
- Only at application startup
- No periodic retry, no background timer, no exponential backoff
- `process_queue()` is synchronous and blocks startup (briefly)
- No maximum retry count — reports stay forever until they succeed or are purged

### What Data Is Persisted
- Queued reports: JSON files in `BASE_DIR/pending_reports/`
- Each file contains `type`, `data` (serialized model), `created_at`
- Crash reports: JSON files in `BASE_DIR/crash_reports/`
- No persistent storage for successfully submitted reports

### What Happens During Application Restart
1. `MainWindow.__init__()` calls `_check_for_crashes()` first
2. Then `_crash_service.mark_startup()`
3. Then `_process_report_queue()` — processes all pending JSON files
4. No crash report queue processing exists

### What Happens During Upload Failure
- Report stays in queue forever
- Logged at WARNING level
- No user notification of failure (unless the UI polls `count_pending()`)

### Key Observations
- **No persistent storage of submitted reports** — once submitted and deleted from queue, there is no local record
- The queue processes at startup only — if the app stays running for weeks, queued reports sit there
- Crash reports have NO offline queue — if "Send Report" fails, the user must manually retry
- No `created_at` timestamp on individual queue JSON files is used for TTL or ordering
- Queue files are sorted alphabetically (UUID order), not by creation time

---

## 8. Current Data Models

### BugReport (`models/support/bug_report.py`)

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `title` | `str` | — | Required |
| `description` | `str` | — | Required |
| `steps_to_reproduce` | `str` | — | — |
| `expected_behavior` | `str` | — | — |
| `actual_behavior` | `str` | — | — |
| `severity` | `str` | `"medium"` | `low`, `medium`, `high`, `critical` |
| `created_at` | `datetime` | `now(UTC)` (naive) | — |
| `id` | `str \| None` | `None` | Set by `SupportService` (UUID4) |

**Serialization format:** `dict` with `title`, `description`, `steps_to_reproduce`, `expected_behavior`, `actual_behavior`, `severity` (excludes `created_at` and `id`)

**Persistence format:** Part of queue JSON payload under `data` key

### FeatureRequest (`models/support/feature_request.py`)

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `title` | `str` | — | Required |
| `description` | `str` | — | Required |
| `use_case` | `str` | — | — |
| `priority` | `str` | `"medium"` | `low`, `medium`, `high` |
| `created_at` | `datetime` | `now(UTC)` (naive) | — |
| `id` | `str \| None` | `None` | Set by `SupportService` (UUID4) |

**Serialization format:** `dict` with `title`, `description`, `use_case`, `priority`

### FeedbackReport (`models/support/feedback_report.py`)

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `subject` | `str` | — | Required |
| `message` | `str` | — | Required |
| `category` | `str` | `"general"` | `general`, `praise`, `complaint` |
| `contact_ok` | `bool` | `False` | — |
| `created_at` | `datetime` | `now(UTC)` (naive) | — |
| `id` | `str \| None` | `None` | Set by `SupportService` (UUID4) |

**Serialization format:** `dict` with `subject`, `message`, `category`, `contact_ok`

### CrashReport (`services/crash/diagnostic_service.py:24-51`)

| Field | Type | Description |
|-------|------|-------------|
| `report_id` | `str` | UUID4 |
| `timestamp` | `str` | ISO-8601 UTC |
| `app_version` | `str` | From `trackora.__version__` |
| `os_version` | `str` | Via `platform.platform()` |
| `os_platform` | `str` | Via `platform.system()` |
| `active_sessions` | `list[dict]` | Snapshot of active sessions |
| `tracked_games` | `int` | Count of tracked games |
| `stack_trace` | `str \| None` | Captured traceback |
| `recent_log_entries` | `list[str]` | Last 50 log lines |
| `crash_type` | `str` | `"unexpected_shutdown"` or `"unhandled_exception"` |
| `was_tracking` | `bool` | Whether tracker was active |

**Serialization format:** Direct dict of all fields via `DiagnosticService.serialize()`

**Persistence format:** Full JSON file at `BASE_DIR/crash_reports/{report_id}.json`

---

## 9. Reusable Components (For MongoDB Migration)

These components can be reused as-is or with minimal adaptation:

| Component | File | Reuse Strategy |
|-----------|------|----------------|
| `AbstractReportService` | `services/support/reporting_interface.py` | **Reuse as-is** — new `MongoReportService` implements the same ABC |
| `ReportType` enum | `services/support/reporting_interface.py:25-29` | **Reuse as-is** — covers all 4 MongoDB collections |
| `SubmitResult` | `services/support/reporting_interface.py:32-45` | **Reuse as-is** — return type for all backends |
| `SupportService` | `services/support/support_service.py` | **Reuse with new backend** — depends on `AbstractReportService`, not concrete impl |
| `SupportSubmitResult` | `services/support/support_service.py:36-57` | **Reuse as-is** — no change needed |
| `ReportQueueService` | `services/support/report_queue_service.py` | **Reuse as-is** — works with any backend |
| `QueueProcessResult` | `services/support/report_queue_service.py:53-59` | **Reuse as-is** |
| `ReportQueueService.reconstruct_model()` | `services/support/report_queue_service.py:244-258` | **Reuse** — model reconstruction for queue retry |
| `DiagnosticService` | `services/crash/diagnostic_service.py` | **Reuse as-is** — environment snapshot collection |
| `CrashReport` dataclass | `services/crash/diagnostic_service.py:24-51` | **Reuse as-is** — serializable data container |
| `CrashService` | `services/crash/crash_service.py` | **Reuse as-is** — crash detection logic is backend-agnostic |
| `StartupStateManager` | `services/crash/crash_service.py:53-143` | **Reuse as-is** — file-based state tracking |
| `BugReport`, `FeatureRequest`, `FeedbackReport` | `models/support/*.py` | **Reuse as-is** — domain dataclasses remain unchanged |
| `SupportCenterController` | `ui/support_center/support_center_controller.py` | **Reuse as-is** — no direct backend dependency |
| `SupportCenterWidget` | `ui/support_center/support_center_widget.py` | **Reuse as-is** — pure UI, no backend dependency |
| `CrashDialog` | `ui/crash_dialog.py` | **Reuse as-is** — uses `AbstractReportService` |
| Serialization helpers | `support_service.py:248-279` | **Reuse** — but should be unified with model-level serialization |
| Retry classification (`_is_retryable`) | `support_service.py:69-74` | **Reuse as-is** — backend-agnostic |
| Atomic file write pattern | Multiple files | **Reuse pattern** — consistent across queue, crash reports, cache |

### Components Needing Minor Adaptation

| Component | File | Adaptation Needed |
|-----------|------|-------------------|
| `MainWindow` | `ui/main_window.py` | **Minor** — wire `MongoReportService` instead of `SupabaseReportService` |
| `__main__.py` | `trackora/__main__.py` | **Minor** — DI wiring change |
| `services/support/__init__.py` | `services/support/__init__.py` | **Minor** — add `MongoReportService` to exports |
| `CrashDialog._on_send()` | `ui/crash_dialog.py:134-168` | **Minor** — add offline queue for crash report failures |

---

## 10. Replacement Candidates (Supabase-Specific)

These components must be replaced or removed during MongoDB migration:

| Component | File | Reason | Action |
|-----------|------|--------|--------|
| `SupabaseReportService` | `services/support/supabase_report_service.py` | Supabase-specific REST client | **Replace** with `MongoReportService` |
| `SupabaseConfig` | `services/support/supabase_report_service.py:82-96` | Supabase credential model | **Remove** — replaced by MongoDB connection config |
| `supabase_config.py` | `trackora/core/supabase_config.py` | Hardcoded Supabase credentials | **Remove** — security risk, no longer needed |
| Supabase DI wiring | `trackora/__main__.py:199-209` | Creates `SupabaseReportService()` | **Replace** with `MongoReportService` |
| Supabase export | `services/support/__init__.py:10` | Exports `SupabaseReportService` | **Add** `MongoReportService`; keep for deprecation window |
| Supabase test suite | `tests/test_supabase_report_service.py` | Tests Supabase-specific behavior | **Add** `MongoReportService` tests; keep Supabase tests until deprecation |

### Supabase REST API Endpoints

| Endpoint | Used By | Purpose |
|----------|---------|---------|
| `POST {base}/rest/v1/reports` | `SupabaseReportService._submit_report()` | Submit all report types to single `reports` table |

### Supabase-specific Configuration

| Config Key | Location | Value |
|------------|----------|-------|
| `SUPABASE_URL` | `supabase_config.py`, env var, `.env` | `https://uphwhrcmmdnekgoojzza.supabase.co` |
| `SUPABASE_ANON_KEY` | `supabase_config.py`, env var, `.env` | `eyJh...` (anon key) |
| `SUPABASE_URL` env | `supabase_report_service.py:36` | `"SUPABASE_URL"` |
| `SUPABASE_ANON_KEY` env | `supabase_report_service.py:37` | `"SUPABASE_ANON_KEY"` |

### MongoDB Connection Config (To Be Added)

| Config Item | Proposed Source | Notes |
|-------------|----------------|-------|
| `MONGODB_URI` | Environment variable only | NEVER in source code |
| MongoDB database name | Configurable default | e.g. `trackora_support` |

---

## 11. Risk Assessment

### Architecture Risks

| Risk | Description | Severity | Mitigation |
|------|-------------|----------|------------|
| Dual-backend complexity | Supporting both Supabase and MongoDB during migration increases maintenance burden | **Medium** | Feature-flag backend selection; remove Supabase after deprecation window |
| In-memory-only reports | Submitted reports are stored only in memory — lost on crash if queue not triggered | **High** | MongoDB provides persistent local storage; this is a primary benefit of migration |
| No persistent report history | Users cannot view past submissions within the app | **Medium** | MongoDB provides queryable history; not available in current architecture |
| Duplicate `reconstruct_model` logic | Both `support_service.py` and `report_queue_service.py` have nearly identical model reconstruction | **Low** | Consolidate into a single utility during migration |

### Migration Risks

| Risk | Description | Severity | Mitigation |
|------|-------------|----------|------------|
| Data loss during Supabase→MongoDB cutover | Reports submitted during migration window could be lost | **High** | Additive implementation: both backends active simultaneously during deprecation |
| PyMongo dependency breaks build | PyMongo may cause PyInstaller issues (hidden imports) | **Medium** | Test PyInstaller build early; document hidden imports in `.spec` file |
| MongoDB connection blocks startup | If MongoDB is unreachable, app should not hang | **Medium** | Non-blocking connection; timeout; graceful fallback to queue-only mode |
| Connection string leaked | MongoDB URI exposed in source or config | **Critical** | Environment variable only; add to `.gitignore`; never hardcode |
| Schema version skew | Reports submitted by older app version may lack new fields | **Low** | Schema version field on every document; additive field evolution |

### Offline Risks

| Risk | Description | Severity | Mitigation |
|------|-------------|----------|------------|
| Queue processes only at startup | Reports queued mid-session wait until next launch | **Medium** | Consider periodic retry timer (out of current scope for Phase A) |
| Crash reports not queued | "Send Report" failure in CrashDialog is not retried | **High** | Integrate crash report submission with `ReportQueueService` |
| No max retry for queue | Failed reports accumulate indefinitely | **Low** | Add max-retry or dead-letter mechanism (out of scope for Phase A) |
| Queue has no TTL | Old unreachable reports never expire | **Low** | Optional TTL on queue files (out of scope for Phase A) |

### Data-Loss Risks

| Risk | Description | Severity | Mitigation |
|------|-------------|----------|------------|
| MongoDB write failure | If MongoDB write fails, report may not be stored locally | **Medium** | Always write to local queue on MongoDB failure (same pattern as current Supabase flow) |
| Queue file corruption | Filesystem corruption could lose queued reports | **Low** | Atomic writes minimize risk; filesystem is APPDATA (reliable) |
| No local backup of submitted reports | Once submitted to MongoDB and queue deleted, report has no local copy | **Low** | Acceptable — MongoDB is the primary store; backup handled by BackupManager |

### Dependency Risks

| Risk | Description | Severity | Mitigation |
|------|-------------|----------|------------|
| PyMongo not in requirements.txt | New dependency not yet listed | **Medium** | Add `pymongo>=4.6` and `dnspython>=2.4` to `requirements.txt` |
| PyMongo + PyInstaller | Known issue with hidden imports | **Medium** | Test build; add `--hidden-import` flags to `Trackora.spec` |
| MongoDB not installed | End users don't have MongoDB running locally | **High** | Ship with embedded MongoDB-ready connection; consider cloud MongoDB Atlas as default; provide setup docs |

---

## 12. File Impact Assessment

### Files Likely Affected by MongoDB Integration

| File | Purpose | Expected Future Change |
|------|---------|----------------------|
| `services/support/supabase_report_service.py` | Supabase REST API backend | **Replace** with `MongoReportService` (or keep during deprecation) |
| `trackora/core/supabase_config.py` | Hardcoded Supabase credentials | **Remove** |
| `trackora/__main__.py` | DI wiring, report_service creation | **Modify** — wire `MongoReportService` |
| `ui/main_window.py` | Queue processing, crash dialog wiring | **Minor** — accept `MongoReportService` via ABC |
| `services/support/__init__.py` | Package exports | **Modify** — export `MongoReportService` |
| `models/support/bug_report.py` | Bug report dataclass | **None** — reused as-is |
| `models/support/feature_request.py` | Feature request dataclass | **None** — reused as-is |
| `models/support/feedback_report.py` | Feedback dataclass | **None** — reused as-is |
| `services/support/support_service.py` | Orchestrator service | **None** — depends on ABC, not concrete |
| `services/support/report_queue_service.py` | Offline queue | **None** — reused as-is |
| `services/support/reporting_interface.py` | ABC for backends | **None** — reused as-is |
| `services/support/github_issue_service.py` | GitHub Issues backend | **None** — unchanged; separate backend |
| `services/crash/crash_service.py` | Crash detection | **None** — unchanged |
| `services/crash/diagnostic_service.py` | Diagnostic collection | **None** — unchanged |
| `ui/crash_dialog.py` | Crash report submission UI | **Minor** — may add queue integration |
| `ui/support_center/support_center_controller.py` | Support center controller | **None** — unchanged |
| `ui/support_center/support_center_widget.py` | Support center UI | **None** — unchanged |
| `tests/test_supabase_report_service.py` | Supabase service tests | **Add** `test_mongo_report_service.py`; keep for deprecation |
| `tests/test_support_service.py` | Support service tests | **None** — unchanged (mock backend) |
| `tests/test_report_queue_service.py` | Queue tests | **None** — unchanged |
| `tests/test_crash_service.py` | Crash service tests | **None** — unchanged |
| `tests/test_diagnostic_service.py` | Diagnostic tests | **None** — unchanged |
| `requirements.txt` | Python dependencies | **Add** `pymongo`, `dnspython` |
| `Trackora.spec` | PyInstaller build config | **Add** hidden imports for pymongo |
| `docs/architecture/mongodb-roadmap.md` | MongoDB implementation roadmap | **None** — reference document |
| `docs/architecture/mongodb-foundation-spec.md` | MongoDB foundation spec | **None** — reference document |
| `docs/architecture/mongodb-document-model.md` | MongoDB document model | **None** — reference document |

### Files to Create

| File | Purpose |
|------|---------|
| `services/support/mongo_report_service.py` | MongoDB implementation of `AbstractReportService` |
| `services/support/mongo_connection.py` | MongoDB connection manager (connection pooling, retry, health check) |
| `tests/test_mongo_report_service.py` | Unit tests for `MongoReportService` |

---

## 13. Architecture Findings

### Strength: Clean Backend Abstraction

The `AbstractReportService` ABC (`services/support/reporting_interface.py`) provides a clean contract that any backend — including MongoDB — can implement. `SupportService` already depends on this ABC, not on concrete implementations. This is the strongest architectural asset for migration.

### Strength: Offline Queue Infrastructure

`ReportQueueService` is well-implemented with atomic writes, crash-safe initialization, UUID-based deduplication, and comprehensive logging. It works with any backend and should be preserved.

### Strength: UI/Service Separation

The Support Center UI (`SupportCenterWidget`, `SupportCenterController`) has zero knowledge of the backend. All backend interaction goes through `SupportService` → `AbstractReportService`. The crash dialog similarly uses the ABC.

### Weakness: No Persistent Local Storage

Submitted reports exist only in memory and in the remote backend (Supabase). There is no local queryable archive. MongoDB will address this by providing persistent local storage.

### Weakness: Supabase Credentials in Source

`trackora/core/supabase_config.py` contains live Supabase credentials hardcoded in the repository. This is a security anti-pattern. MongoDB credentials must NOT follow this pattern.

### Weakness: Crash Reports Not Queued

Crash reports bypass the `ReportQueueService` entirely. If the "Send Report" backend call fails, the user sees an error but the report is not queued for retry. This should be addressed.

### Weakness: Duplicate Model Reconstruction

Both `support_service.py` and `report_queue_service.py` define `_REPORT_TYPE_MAP`, `_GITHUB_METHOD_MAP`, and reconstruction logic. These should be consolidated.

### Weakness: Startup-Only Queue Processing

The queue processes only once at startup. For long-running sessions, queued reports remain unsubmitted. Consider a periodic retry timer in a future iteration.

---

## 14. Recommendations

### For MongoDB Implementation (Phase A)

1. **Create `MongoReportService`** implementing `AbstractReportService`
   - One MongoDB collection per report type (`bug_reports`, `feature_requests`, `feedback`, `crash_reports`)
   - Map each domain model directly to a MongoDB document
   - Include `schema_version`, `submitted_at`, `source`, `app_version` in every document
   - Write operations only (no reads needed for Phase A)

2. **Create `MongoConnection`** — connection manager with:
   - Timeout on connection (fail fast, don't block startup)
   - Graceful degradation: if MongoDB is unreachable, fall back to queue-only mode
   - Connection pooling via `pymongo.MongoClient`

3. **Preserve `ReportQueueService`** as fallback when MongoDB is unavailable

4. **Wire via DI** in `__main__.py`: prefer `MongoReportService`, fall back to queue

5. **Do NOT remove Supabase** immediately — keep `SupabaseReportService` available during a deprecation window controlled by a configuration flag

6. **Add crash report to queue**: integrate `CrashDialog._on_send()` failure with `ReportQueueService`

7. **Consolidate model reconstruction**: unify `_REPORT_TYPE_MAP` and reconstruction logic into a single shared utility

8. **Add `pymongo>=4.6` and `dnspython>=2.4`** to `requirements.txt`

9. **Update `Trackora.spec`** with `--hidden-import` for `pymongo`

10. **Connection string via environment only** — never hardcode; validate at startup

---

## 15. Final Verdict

### 1. Is Trackora ready for MongoDB Support Backend integration?

**Yes, with minor reservations.**

The architecture is well-prepared for this transition:

- The `AbstractReportService` ABC provides a clean extension point
- `SupportService` is backend-agnostic
- `ReportQueueService` is a robust offline fallback
- The UI layer has zero backend coupling
- All 4 approved MongoDB collections map cleanly to existing domain models

**Reservations:**
- Crash report submission has no offline queue fallback (must be added)
- Duplicate model reconstruction code should be consolidated first
- MongoDB connection management adds new failure modes that need graceful handling

### 2. Which components should be reused?

| Component | Reuse Decision |
|-----------|---------------|
| `AbstractReportService` | **Reuse** — implement `MongoReportService` against this ABC |
| `ReportType` enum | **Reuse** — add coverage for all 4 collections |
| `SubmitResult` / `SupportSubmitResult` | **Reuse** — return types unchanged |
| `SupportService` | **Reuse** — no changes needed |
| `ReportQueueService` | **Reuse** — fallback offline queue |
| `QueueProcessResult` | **Reuse** |
| `DiagnosticService` | **Reuse** — collect diagnostics unchanged |
| `CrashReport` dataclass | **Reuse** — insert directly into MongoDB |
| `CrashService` | **Reuse** — detection logic unchanged |
| `StartupStateManager` | **Reuse** — file-based, unrelated to backend |
| `BugReport`, `FeatureRequest`, `FeedbackReport` | **Reuse** — domain models unchanged |
| `SupportCenterController` | **Reuse** — no backend dependency |
| `SupportCenterWidget` | **Reuse** — pure UI |
| `CrashDialog` | **Reuse** — uses `AbstractReportService` |
| Serialization helpers | **Reuse with consolidation** — unify into shared utility |
| `_is_retryable()` | **Reuse** — backend-agnostic classification |
| Atomic file write pattern | **Reuse pattern** — consistent across the codebase |

### 3. Which components should be replaced?

| Component | Replacement | Action |
|-----------|-------------|--------|
| `SupabaseReportService` | `MongoReportService` | **Replace** — new implementation |
| `SupabaseConfig` | `MongoConnection` | **Replace** — new connection management |
| `supabase_config.py` | None | **Remove** — credentials must not be in source |
| Supabase DI wiring (`__main__.py`) | MongoDB DI wiring | **Modify** — wire `MongoReportService` |
| `SupabaseReportService` in `__init__.py` | Add `MongoReportService` | **Add** — keep Supabase export during deprecation |

### 4. What is the safest migration path?

**Recommended approach: Additive Migration**

```
Step 1:  Create MongoReportService (implements AbstractReportService)
Step 2:  Create MongoConnection (connection manager)
Step 3:  Add both to DI wiring alongside SupabaseReportService
Step 4:  Feature-flag backend selection (default: MongoDB)
Step 5:  Run both backends in parallel during deprecation window
Step 6:  Add crash report queue integration
Step 7:  Consolidate duplicate model reconstruction code
Step 8:  After deprecation window: remove SupabaseReportService and supabase_config.py
```

**Why additive:**
- Zero risk of data loss — both backends active simultaneously
- Users can roll back by switching the feature flag
- No downtime — migration happens transparently
- Existing Supabase data preserved until explicit deprecation

**Blocking concerns before Step 1:**
1. Ensure MongoDB is available or provide setup instructions for end users
2. PyMongo + PyInstaller compatibility verified in build pipeline
3. Connection string is read from environment, never hardcoded
4. `requirements.txt` updated with `pymongo` and `dnspython`

---

## Appendix: Supabase Reference Map

### All Files Importing SupabaseReportService

```
trackora/__main__.py:33          → from services.support.supabase_report_service import SupabaseReportService
services/support/__init__.py:10  → from services.support.supabase_report_service import SupabaseReportService
tests/test_supabase_report_service.py:16 → from services.support.supabase_report_service import ...
```

### All Files Referencing Supabase (non-import)

```
trackora/__main__.py:199-209    → Creates SupabaseReportService(), checks is_configured
trackora/core/supabase_config.py:1-2 → Hardcoded SUPABASE_URL and SUPABASE_ANON_KEY
services/support/supabase_report_service.py:1-395 → Full implementation
tests/test_supabase_report_service.py:1-681 → Test suite
tests/test_startup_integration.py:482 → Mock patch path reference
```

### Supabase → MongoDB Collection Mapping

| Supabase `type` value | Current Supabase Target | MongoDB Collection | Domain Model |
|-----------------------|------------------------|-------------------|--------------|
| `bug` | `reports` table | `bug_reports` | `BugReport` |
| `feature-request` | `reports` table | `feature_requests` | `FeatureRequest` |
| `feedback` | `reports` table | `feedback` | `FeedbackReport` |
| `crash` | `reports` table | `crash_reports` | `CrashReport` |

---

*End of Audit Report*</response>
