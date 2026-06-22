# MongoDB Support Backend — Architecture Specification

**Version:** 1.0  
**Status:** Architecture Design  
**Type:** Architecture Specification  
**Phase:** 12 — Step 2  
**Scope:** Support Backend (bug_reports, feature_requests, feedback, crash_reports)  

---

## 1. Purpose

Define the architecture for replacing the Supabase REST API backend with local MongoDB as Trackora's support report storage.

MongoDB fully replaces Supabase. No dual-write strategy. No feature flags. No parallel backends.

### Scope

| Collection | Data Source | Replaces |
|-----------|-------------|----------|
| `bug_reports` | User input via Support Center UI | Supabase `reports` table (type=bug) |
| `feature_requests` | User input via Support Center UI | Supabase `reports` table (type=feature-request) |
| `feedback` | User input via Support Center UI | Supabase `reports` table (type=feedback) |
| `crash_reports` | Crash detection service | Supabase `reports` table (type=crash) |

### Out of Scope

- Analytics collections
- Insights collections
- Recommendation engine
- Trend analysis
- Cloud sync
- Remote MongoDB
- Supabase deprecation timeline (deferred to separate plan)

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Support Layer                                    │
│                                                                               │
│  ┌────────────────┐    ┌──────────────────┐    ┌────────────────────────┐   │
│  │ SupportCenter   │───►│ SupportService   │───►│ AbstractReportService  │   │
│  │ Controller      │    │ (orchestrator)   │    │ (ABC)                  │   │
│  └────────────────┘    └──────────────────┘    └──────────┬─────────────┘   │
│                                                            │                 │
│  ┌────────────────┐    ┌──────────────────┐                │                 │
│  │ CrashDialog    │───►│ CrashService     │                │                 │
│  │ (on crash)     │    │                  │                │                 │
│  └────────┬───────┘    └──────────────────┘                │                 │
│           │              ▲                                 │                 │
│           │              │ (startup detection)             │                 │
└───────────┼──────────────┼─────────────────────────────────┼─────────────────┘
            │              │                                   │
            │              │                                   ▼
            │              │               ┌───────────────────────────────────┐
            │              │               │         MongoReportService        │
            │              │               │  implements AbstractReportService  │
            │              │               │                                    │
            │              │               │  ┌─────────────────────────────┐  │
            │              │               │  │  MongoConnection              │  │
            │              │               │  │  • Singleton MongoClient     │  │
            │              │               │  │  • Lazy initialization       │  │
            │              │               │  │  • Thread-safe               │  │
            │              │               │  │  • Health check              │  │
            │              │               │  │  • Graceful degradation      │  │
            │              │               │  └─────────────────────────────┘  │
            │              │               └──────────────┬────────────────────┘
            │              │                               │
            │              │                               ▼
            │              │               ┌───────────────────────────────────┐
            │              │               │     Local MongoDB Instance         │
            │              │               │                                    │
            │              │               │  ┌─────────────────┐              │
            │              │               │  │ bug_reports      │              │
            │              │               │  ├─────────────────┤              │
            │              │               │  │ feature_requests │              │
            │              │               │  ├─────────────────┤              │
            │              │               │  │ feedback         │              │
            │              │               │  ├─────────────────┤              │
            │              │               │  │ crash_reports    │              │
            │              │               │  └─────────────────┘              │
            │              │               └───────────────────────────────────┘
            │              │
            ▼              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                             ReportQueueService                                │
│                                                                               │
│  • Unified queue for ALL report types: bug, feature, feedback, crash          │
│  • pending_reports/*.json — atomic writes                                     │
│  • Crash reports enter queue when MongoDB is unavailable                       │
│  • All types share: retry logic, failure handling, offline behavior            │
│  • Queue processed at startup; success → delete; failure → keep for retry      │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Architecture Rules

| Rule | Description |
|------|-------------|
| AR-01 | All 4 collections are permanently isolated from analytics and insights |
| AR-02 | No MongoDB query in analytics or insights code may reference support collections |
| AR-03 | `MongoReportService` is the sole writer to support collections |
| AR-04 | `ReportQueueService` is the sole fallback when MongoDB is unavailable |
| AR-05 | Credentials are read from environment variables only — never from source files |
| AR-06 | The application must start and operate without MongoDB (queue-only fallback) |
| AR-07 | No SQLite data is modified by the support backend |
| AR-08 | All 4 report types (bug, feature, feedback, crash) must share the same queue pipeline |
| AR-09 | Crash reports must be queued via `ReportQueueService` on MongoDB failure — same as support reports |

---

## 3. MongoConnection

### Responsibilities

- Manage a single `pymongo.MongoClient` instance
- Provide connection health status
- Provide graceful degradation when MongoDB is unavailable
- Centralize connection string resolution (environment variable only)
- Expose database and collection access to `MongoReportService`

### Connection Lifecycle

```
Application startup
    │
    ▼
MongoConnection.__init__()
    │
    ├── Read MONGODB_URI from environment
    ├── If empty → mark unavailable, log warning, return
    ├── Create MongoClient with timeout settings
    │
    ▼
health_check()
    │
    ├── ping admin database (timeout: 3s)
    │   ├── success → mark available
    │   └── failure → mark unavailable, log error, close client
    │
    ▼
Service ready
```

### Configuration

| Parameter | Source | Default | Required |
|-----------|--------|---------|----------|
| `MONGODB_URI` | Environment variable | — | Yes |
| Connection timeout | In-code constant | 5 seconds | — |
| Server selection timeout | In-code constant | 3 seconds | — |

**The connection string MUST NOT be hardcoded. No `mongodb_config.py`. No default URI.**

### Interface

```python
class MongoConnection:
    def __init__(self, uri: str | None = None) -> None: ...

    @property
    def is_available(self) -> bool: ...

    @property
    def database(self) -> Database | None: ...

    def health_check(self) -> bool: ...

    def close(self) -> None: ...
```

### States

| State | Condition | Behavior |
|-------|-----------|----------|
| **Unconfigured** | `MONGODB_URI` is empty or unset | `MongoReportService` falls back to queue-only |
| **Connected** | `health_check()` passes | Normal MongoDB operations |
| **Unavailable** | Connection fails or drops | `MongoReportService` falls back to queue-only; retries on next operation |

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Invalid URI | Log error, mark unavailable |
| Connection timeout | Log warning, mark unavailable |
| Authentication failure | Log error, mark unavailable (non-retryable for session) |
| Connection lost mid-operation | Return `SubmitResult(success=False)`, queue report |
| MongoDB process not running | Log warning, mark unavailable |

---

## 4. MongoDB Connection Strategy

### Singleton Architecture

```
MongoConnection (singleton per process)
    │
    └── owns → MongoClient (single instance)
                   │
                   └── manages → Connection Pool (internal to driver)
                                     │
                                     ├── Thread-1 → borrow → release
                                     ├── Thread-2 → borrow → release
                                     └── Thread-3 → borrow → release
```

One `MongoClient` per application process. The `MongoConnection` singleton owns the client lifecycle. All `MongoReportService` operations share the same client and pool.

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Singleton MongoClient** | `MongoClient` instances manage an internal connection pool. Creating multiple clients creates redundant pools, increases connection overhead, and defeats the driver's built-in pooling. Reusing a single client is the MongoDB-recommended best practice. |
| **Lazy initialization** | The `MongoClient` is NOT created in `__init__`. It is created on the first call to `database` or `health_check()`. This prevents startup from blocking if MongoDB is unavailable — the application starts in queue-only mode without ever attempting a connection. |
| **Thread-safe access** | `pymongo.MongoClient` is thread-safe. All access to `database` and collections is safe from multiple threads without additional locking. The singleton design ensures all threads share the same pool. |
| **Driver-managed reconnection** | The MongoDB driver handles reconnection automatically. If a connection drops, the driver retries on the next operation. `MongoConnection` does NOT implement custom reconnection logic — it relies on the driver's built-in retry behavior. |
| **Health check is advisory** | `health_check()` runs a `ping` to verify current connectivity. A passing health check does not guarantee future operations will succeed, and a failing health check does not mean the driver is in a broken state (it may reconnect automatically). The health check is used for startup logging and status reporting, not as a gate for operations. |

### Connection Pooling Rationale

| Benefit | Explanation |
|---------|-------------|
| **Reduced latency** | Reusing connections from the pool eliminates the TCP handshake and authentication overhead for each operation. |
| **Reduced resource usage** | A pool of 5–10 connections handles all application traffic without creating a new connection per request. |
| **Thread safety** | The pool is thread-safe — multiple threads can operate concurrently without connection conflicts. |
| **Scalability** | The pool grows to meet demand (up to `maxPoolSize`) and shrinks when idle, matching the application's workload. |
| **Production readiness** | Connection pooling is the standard pattern for all MongoDB driver usage in multi-threaded applications. |

### Pool Configuration

| Parameter | Recommended Value | Notes |
|-----------|-------------------|-------|
| `maxPoolSize` | 10 | Trackora is a single-user desktop app; 10 connections is generous |
| `minPoolSize` | 1 | Keep at least one connection warm |
| `maxIdleTimeMS` | 30000 (30s) | Close idle connections to free resources |
| `connectTimeoutMS` | 5000 (5s) | Fail fast if MongoDB is unreachable |
| `serverSelectionTimeoutMS` | 3000 (3s) | Timeout for finding an available server |

### Interface (Updated)

```python
class MongoConnection:
    def __init__(self, uri: str | None = None) -> None:
        """Construct without connecting — lazy init."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether the last health check or operation succeeded."""
        ...

    @property
    def database(self) -> Database | None:
        """Lazy-init MongoClient and return database handle.
        Returns None if not configured or connection failed."""
        ...

    def health_check(self) -> bool:
        """Ping the database to verify connectivity.
        Lazy-initializes the client if needed.
        Thread-safe. Logs redacted status."""
        ...

    def close(self) -> None:
        """Close the MongoClient connection and release resources."""
        ...
```

### Thread Safety Guarantees

| Scenario | Behavior |
|----------|----------|
| Concurrent `health_check()` calls | Single ping; all callers get the same result |
| Concurrent `database` access | All callers share the same `MongoClient`; driver handles concurrency |
| `health_check()` during active write | Driver queues operations; no race condition |
| `close()` during active operation | Driver drains pending operations before closing |
| Multiple threads accessing different collections | Shared pool; connections allocated per-operation |

### State Machine

```
                 ┌─────────────────────────────────────────────┐
                 │            Unconfigured                       │
                 │  (MONGODB_URI empty/not set)                  │
                 │  → database returns None                      │
                 │  → health_check() returns False               │
                 │  → is_available = False                       │
                 └─────────────────────────────────────────────┘
                                    │
                                    │ MONGODB_URI provided
                                    ▼
                 ┌─────────────────────────────────────────────┐
                 │          Initialized (lazy)                   │
                 │  (client NOT created yet)                     │
                 │  → database call triggers client creation     │
                 │  → health_check() call triggers client        │
                 │    creation + ping                            │
                 └─────────────────────────────────────────────┘
                                    │
                      ┌─────────────┴─────────────┐
                      ▼                           ▼
        ┌─────────────────────────┐    ┌─────────────────────────┐
        │      Connected           │    │     Unavailable          │
        │  (health_check OK)       │    │  (health_check failed)   │
        │  → database returns DB   │    │  → database returns None │
        │  → is_available = True   │    │  → is_available = False  │
        │  → operations succeed    │    │  → operations queued     │
        └─────────────────────────┘    └─────────────────────────┘
                      │                           │
                      │   connection lost          │   MONGODB_URI
                      │   (driver auto-retries)    │   changes (app
                      ▼                           ▼   restart)
        ┌─────────────────────────┐    ┌─────────────────────────┐
        │      Reconnecting       │    │  Re-initialize on next   │
        │  (driver-managed)       │    │  lazy access             │
        │  → operations may fail  │    └─────────────────────────┘
        │  → health_check polls   │
        │  → is_available updates │
        └─────────────────────────┘
```

---

## 5. MongoReportService

### Contract

Implements `AbstractReportService` (`services/support/reporting_interface.py`):

```python
class AbstractReportService(ABC):
    @abstractmethod
    def submit_bug(self, report: BugReport) -> SubmitResult: ...

    @abstractmethod
    def submit_feature(self, request: FeatureRequest) -> SubmitResult: ...

    @abstractmethod
    def submit_feedback(self, feedback: FeedbackReport) -> SubmitResult: ...

    @abstractmethod
    def submit_report(self, report_type: ReportType, title: str, body: str) -> SubmitResult: ...

    def submit_crash(self, title: str, body: str) -> SubmitResult: ...
```

### Behavior

| Method | MongoDB Collection | Document Source |
|--------|-------------------|-----------------|
| `submit_bug()` | `bug_reports` | `BugReport` fields + metadata |
| `submit_feature()` | `feature_requests` | `FeatureRequest` fields + metadata |
| `submit_feedback()` | `feedback` | `FeedbackReport` fields + metadata |
| `submit_report()` | `crash_reports` (when type=CRASH) | Inline title + body + metadata |
| `submit_crash()` | `crash_reports` | Delegates to `submit_report(CRASH, ...)` |

### Submission Flow

```
Submit method called
    │
    ▼
Is MongoConnection available?
    ├── NO  → return SubmitResult(success=False, error="MongoDB unavailable")
    │         (SupportService will queue this via ReportQueueService)
    │
    └── YES → build document from domain model
                │
                ▼
              Insert document into MongoDB collection
                │
                ├── Success → return SubmitResult(success=True, report_id=str(inserted_id))
                │
                └── Failure → log error
                              return SubmitResult(success=False, error=...)
                              (SupportService will queue this via ReportQueueService)
```

### Document Enrichment

Every document receives these additional fields before insertion:

| Field | Type | Source | Purpose |
|-------|------|--------|---------|
| `schema_version` | `int` | Constant (1) | Schema evolution tracking |
| `app_version` | `str` | `trackora.__version__` | Version at submission time |
| `os` | `str` | `platform.platform()` | OS context |
| `submitted_at` | `datetime` | `datetime.now(UTC)` | Server-side timestamp |
| `source` | `str` | `"support_center"` or `"crash_detector"` | Origin context |

### Model → Document Mapping

#### BugReport → `bug_reports`

```python
{
    "schema_version": 1,
    "title": str,
    "description": str,
    "steps_to_reproduce": str,
    "expected_behavior": str,
    "actual_behavior": str,
    "severity": str,          # "low" | "medium" | "high" | "critical"
    "app_version": str,
    "os": str,
    "submitted_at": datetime,
    "source": "support_center",
}
```

#### FeatureRequest → `feature_requests`

```python
{
    "schema_version": 1,
    "title": str,
    "description": str,
    "use_case": str,
    "priority": str,           # "low" | "medium" | "high"
    "app_version": str,
    "os": str,
    "submitted_at": datetime,
    "source": "support_center",
}
```

#### FeedbackReport → `feedback`

```python
{
    "schema_version": 1,
    "subject": str,
    "message": str,
    "category": str,           # "general" | "praise" | "complaint"
    "contact_ok": bool,
    "app_version": str,
    "os": str,
    "submitted_at": datetime,
    "source": "support_center",
}
```

#### CrashReport → `crash_reports`

```python
{
    "schema_version": 1,
    "crash_type": str,         # "unexpected_shutdown" | "unhandled_exception"
    "app_version": str,
    "os_version": str,
    "os_platform": str,
    "active_sessions": [       # list of session snapshots
        {"game_id": int, "game_name": str, "process_id": int}
    ],
    "tracked_games": int,
    "was_tracking": bool,
    "stack_trace": str | None,
    "recent_log_entries": [str],
    "submitted_at": datetime,
    "source": "crash_detector",
}
```

### Crash Report Serialization

`MongoReportService` receives a `CrashReport` dataclass (from `DiagnosticService`) when `submit_report(CRASH, ...)` is called. The document maps directly from `CrashReport` fields. The `title` and `body` arguments from `submit_report()` are stored as additional metadata:

```python
{
    "title": str,              # From submit_report(title)
    "body": str,               # From submit_report(body)
    "crash_type": str,         # From CrashReport
    "app_version": str,        # From CrashReport
    ...
}
```

---

## 6. Collection Schema

### Naming Convention

All collections use the `{entity}_reports` pattern — no prefix. This distinguishes support collections from future `analytics_*` and `insights_*` collections and prevents accidental cross-namespace queries.

### bug_reports

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | `ObjectId` | auto | MongoDB primary key |
| `schema_version` | `int` | yes | Currently 1 |
| `title` | `string` | yes | Bug summary |
| `description` | `string` | yes | Detailed description |
| `steps_to_reproduce` | `string` | no | Reproduction steps |
| `expected_behavior` | `string` | no | Expected outcome |
| `actual_behavior` | `string` | no | Actual outcome |
| `severity` | `string` | no | `"low"`, `"medium"`, `"high"`, `"critical"` |
| `app_version` | `string` | yes | Trackora version at submission |
| `os` | `string` | no | `platform.platform()` |
| `submitted_at` | `date` | yes | UTC timestamp |
| `source` | `string` | no | `"support_center"` |

### feature_requests

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | `ObjectId` | auto | MongoDB primary key |
| `schema_version` | `int` | yes | Currently 1 |
| `title` | `string` | yes | Feature name |
| `description` | `string` | yes | Feature description |
| `use_case` | `string` | no | How it would be used |
| `priority` | `string` | no | `"low"`, `"medium"`, `"high"` |
| `app_version` | `string` | yes | Trackora version at submission |
| `os` | `string` | no | `platform.platform()` |
| `submitted_at` | `date` | yes | UTC timestamp |
| `source` | `string` | no | `"support_center"` |

### feedback

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | `ObjectId` | auto | MongoDB primary key |
| `schema_version` | `int` | yes | Currently 1 |
| `subject` | `string` | yes | Feedback subject |
| `message` | `string` | yes | Feedback body |
| `category` | `string` | no | `"general"`, `"praise"`, `"complaint"` |
| `contact_ok` | `bool` | no | User consent to be contacted |
| `app_version` | `string` | yes | Trackora version at submission |
| `os` | `string` | no | `platform.platform()` |
| `submitted_at` | `date` | yes | UTC timestamp |
| `source` | `string` | no | `"support_center"` |

### crash_reports

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | `ObjectId` | auto | MongoDB primary key |
| `schema_version` | `int` | yes | Currently 1 |
| `crash_type` | `string` | yes | `"unexpected_shutdown"` or `"unhandled_exception"` |
| `title` | `string` | yes | Generated title (from crash dialog) |
| `body` | `string` | yes | Full crash report body |
| `app_version` | `string` | yes | Trackora version at crash |
| `os_version` | `string` | no | Full OS version string |
| `os_platform` | `string` | no | Short OS name |
| `active_sessions` | `array` | no | List of active game session snapshots |
| `tracked_games` | `int` | no | Count of tracked games |
| `was_tracking` | `bool` | no | Tracker active state |
| `stack_trace` | `string` | no | Captured traceback |
| `recent_log_entries` | `array` | no | Last N log lines |
| `submitted_at` | `date` | yes | UTC timestamp |
| `source` | `string` | no | `"crash_detector"` |

### Indexes

| Collection | Index | Purpose |
|-----------|-------|---------|
| `bug_reports` | `{submitted_at: -1}` | Chronological ordering |
| `feature_requests` | `{submitted_at: -1}` | Chronological ordering |
| `feedback` | `{submitted_at: -1}` | Chronological ordering |
| `crash_reports` | `{submitted_at: -1}` | Chronological ordering |
| `crash_reports` | `{crash_type: 1, submitted_at: -1}` | Filter by crash type |

Indexes are created by `MongoReportService` on first connection using `create_indexes()`.

---

## 7. Data Flow

### Support Report Submission

```
User fills form in SupportCenterWidget
    │
    ▼
SupportCenterController builds domain model (BugReport / FeatureRequest / FeedbackReport)
    │
    ▼
SupportService.submit_*()
    │
    ├── Assigns UUID id
    ├── Stores in-memory (list append)
    │
    ▼
SupportService._try_github_submit()
    │
    ▼
MongoReportService.submit_*()
    │
    ├── MongoConnection available?
    │   ├── YES → Insert document → return SubmitResult(success=True)
    │   └── NO  → return SubmitResult(success=False, error="MongoDB unavailable")
    │
    ▼
SupportService checks result
    │
    ├── Success → return SupportSubmitResult(local_stored=True, github_success=True)
    │
    └── Failure + retryable → ReportQueueService.save_report()
                              return SupportSubmitResult(local_stored=True, queued=True)
```

### Crash Report Submission

```
Application starts → CrashService.check_for_crash() detects crash
    │
    ▼
CrashService generates CrashReport via DiagnosticService
    │
    │   CrashReport saved to disk: BASE_DIR/crash_reports/{report_id}.json
    │
    ▼
CrashDialog shown to user
    │
    ├── "Send Report" clicked
    │   │
    │   ▼
    │   CrashDialog._on_send()
    │   │
    │   ├── Builds title + body from CrashReport
    │   ├── Calls report_service.submit_report(CRASH, title, body)
    │   │   │
    │   │   ▼
    │   │   MongoReportService.submit_report()
    │   │   │
    │   │   ├── MongoDB available?
    │   │   │   ├── YES → Insert into crash_reports → success
    │   │   │   │          Delete local crash report JSON
    │   │   │   │
    │   │   │   └── NO  → return SubmitResult(success=False, error=...)
    │   │   │
    │   │   └── Return SubmitResult to CrashDialog
    │   │
    │   ├── If success:
    │   │   └── Show "Crash report submitted"
    │   │
    │   ├── If failure + retryable:
    │   │   ├── Queue crash report via ReportQueueService.save_report("crash", data)
    │   │   ├── Crash report JSON stays on disk (dual persistence)
    │   │   └── Show "Report saved locally and will be sent automatically"
    │   │
    │   └── If failure + non-retryable:
    │       ├── Crash report JSON stays on disk
    │       └── Show specific configuration error
    │
    ├── "Review Report" → Display JSON content
    │
    └── "Dismiss" → Delete local crash report JSON (queue entry remains if any)
```

### Queue Processing (Application Startup)

All four report types (bug, feature, feedback, crash) share the same queue processing pipeline:

```
MainWindow.__init__()
    │
    ▼
MainWindow._process_report_queue()
    │
    ▼
SupportService.process_queue()
    │
    ▼
ReportQueueService.process_queue(submit_fn)
    │
    └── For each .json file (all types including crash):
        ├── Load payload → identify type ("bug"|"feature"|"feedback"|"crash")
        │
        ├── Call submit_fn(report_type, data)
        │   │
        │   ▼
        │   SupportService._queue_submit_fn() closure
        │   │
        │   ├── Maps report_type to method:
        │   │   ├── "bug"      → MongoReportService.submit_bug()
        │   │   ├── "feature"  → MongoReportService.submit_feature()
        │   │   ├── "feedback" → MongoReportService.submit_feedback()
        │   │   └── "crash"    → MongoReportService.submit_report(CRASH, ...)
        │   │
        │   ▼
        │   MongoReportService.submit_*()
        │       │
        │       ├── Success → return True (queue deletes .json)
        │       │            If crash: also delete local crash report JSON
        │       │
        │       └── Failure → return False (queue keeps .json for retry)
        │
        └── On successful crash submission:
            ├── Queue .json deleted by ReportQueueService
            └── Local crash report JSON also cleaned up
```

---

## 8. Error Handling

### Classification

| Error Category | Examples | Retryable | Queued |
|----------------|----------|-----------|--------|
| Connection | MongoDB not running, network timeout | Yes | Yes |
| Authentication | Invalid credentials | No | No |
| Write failure | Disk full, document exceeds size | Yes | Yes |
| Schema violation | Invalid field types | No | No |
| Unconfigured | `MONGODB_URI` not set | No | No |

The retry classification from `support_service.py` (`_is_retryable()`) applies to MongoDB errors the same way:

| Non-retryable keywords | Effect |
|------------------------|--------|
| `"not configured"` | Not queued — configuration issue |
| `"authentication failed"` | Not queued — credential issue |
| `"not found"` | Not queued — logical error |
| `"check your"` | Not queued — user-actionable |

### Graceful Degradation

When MongoDB is unavailable:
1. `MongoReportService` returns `SubmitResult(success=False)` with a descriptive error
2. `SupportService` detects retryable error, queues report via `ReportQueueService`
3. User sees "Report saved locally and will be sent automatically"
4. Reports are retried on next application startup
5. No data loss — queued reports persist as JSON files

---

## 9. Offline Behavior

The existing offline-first architecture is preserved. Changes are minimal:

| Aspect | Current Behavior | MongoDB Behavior |
|--------|-----------------|------------------|
| MongoDB available | Submit to Supabase | **Submit to MongoDB** |
| MongoDB unavailable | Queue to JSON | **Queue to JSON** (unchanged) |
| Startup queue processing | Submit queued to Supabase | **Submit queued to MongoDB** |
| Network required | Yes (Supabase is remote) | **No** (MongoDB is local) |
| Crash report send fail | Error shown, not queued | **Queued via ReportQueueService** — same as support reports |

The key improvement: MongoDB is local, so the "offline" scenario (network failure) that triggered the queue with Supabase should be near-zero with MongoDB. The queue now handles only MongoDB availability failures (process not running, disk full, corrupted state).

---

## 10. Crash Report Submission Architecture

### Overview

Crash reports use the same queue architecture as bug reports, feature requests, and feedback. There is a single unified submission pipeline for all support-related reports.

### Architecture

```
Crash detected at startup
    │
    ▼
CrashService.check_for_crash()
    │
    ├── StartupStateManager detects crash (previous state was "running")
    │
    ▼
DiagnosticService.collect_report()
    │
    ├── Builds CrashReport dataclass with:
    │   - Environment snapshot (OS, app version)
    │   - Active game sessions
    │   - Stack trace (if available)
    │   - Recent log entries
    │   - Tracking state
    │
    ▼
CrashReport saved to disk (BASE_DIR/crash_reports/{report_id}.json)
    │
    ├── Always written for crash recovery purposes
    ├── Serves as fallback if queue or MongoDB fails
    │
    ▼
CrashDialog presented to user
    │
    ├── "Send Report"
    │   │
    │   ▼
    │   CrashDialog._on_send()
    │   │
    │   ├── Builds title + body from CrashReport
    │   ├── Calls report_service.submit_report(CRASH, title, body)
    │   │   │
    │   │   ▼
    │   │   MongoReportService.submit_report()
    │   │   │
    │   │   ├── Builds crash_reports document
    │   │   ├── MongoDB available?
    │   │   │   ├── YES → Insert document → return SubmitResult(success=True)
    │   │   │   │          Delete local crash report JSON
    │   │   │   │
    │   │   │   └── NO  → return SubmitResult(success=False, error="MongoDB unavailable")
    │   │   │
    │   │   └── Return SubmitResult to CrashDialog
    │   │
    │   ├── If result.success:
    │   │   ├── Show success message with optional issue URL
    │   │   └── Report already deleted from disk
    │   │
    │   ├── If not result.success AND error is retryable:
    │   │   ├── Queue crash report via ReportQueueService.save_report("crash", data)
    │   │   ├── Crash report JSON stays on disk (dual persistence for safety)
    │   │   └── Show: "Report saved locally and will be sent automatically"
    │   │
    │   └── If not result.success AND error is NOT retryable:
    │       ├── Crash report JSON stays on disk
    │       └── Show specific error: "Configuration issue — check your MongoDB setup"
    │
    ├── "Review Report"
    │   ├── Display JSON in read-only text area
    │   └── No queue action
    │
    └── "Dismiss"
        ├── Delete local crash report JSON
        └── Queued report (if any) remains in queue for processing
```

### Queue Integration

Crash reports enter `ReportQueueService` through the same code path as support reports:

| Step | Component | Action |
|------|-----------|--------|
| 1 | `CrashDialog._on_send()` | Attempts MongoDB submission via `AbstractReportService.submit_report(CRASH, ...)` |
| 2 | `CrashDialog._on_send()` | On failure: calls `ReportQueueService.save_report("crash", serialized_data)` directly |
| 3 | `ReportQueueService` | Writes JSON atomically to `pending_reports/crash/{uuid}.json` |
| 4 | `SupportService.process_queue()` (next startup) | Iterates all queue files including crash types |
| 5 | `ReportQueueService.process_queue(submit_fn)` | Calls `submit_fn("crash", data)` for each crash entry |
| 6 | `SupportService._queue_submit_fn()` closure | Maps `"crash"` → `MongoReportService.submit_crash()` or `submit_report(CRASH, ...)` |
| 7 | `MongoReportService` | Inserts document into `crash_reports` collection |
| 8 | Success | Queue deletes the `.json` file; local crash report JSON also deleted |
| 9 | Failure | Queue keeps the `.json` file for next retry; local crash report JSON preserved |

### Retry Behavior

- **Classification:** Same `_is_retryable()` logic as support reports
- **Queue storage format** (same structure as support reports):

```json
{
  "type": "crash",
  "data": {
    "title": "Trackora Crash — unexpected_shutdown (2026-06-20T12:00:00)",
    "body": "### Application Version\n1.1.0\n...",
    "crash_type": "unexpected_shutdown",
    "app_version": "1.1.0",
    "os_version": "Windows-10-10.0.22631",
    "os_platform": "Windows",
    "active_sessions": [],
    "tracked_games": 5,
    "was_tracking": true,
    "stack_trace": null,
    "recent_log_entries": ["..."]
  },
  "created_at": "2026-06-20T12:00:00+00:00"
}
```

- **Disk cleanup policy:**
  - On successful MongoDB submission: delete both queue `.json` AND local crash report `.json`
  - On queue failure: keep both files; retry on next startup
  - On user "Dismiss": delete local crash report `.json` only (queue entry remains for processing)

### Dual Persistence Design

Crash reports have two independent persistence mechanisms:

| Mechanism | Location | Purpose | Cleanup Trigger |
|-----------|----------|---------|-----------------|
| Local JSON | `BASE_DIR/crash_reports/{report_id}.json` | Crash recovery; user review/retry in CrashDialog | User dismissal or successful MongoDB submission |
| Queue JSON | `BASE_DIR/pending_reports/{uuid}.json` | Offline retry via ReportQueueService | Successful MongoDB submission |

Both copies are maintained until MongoDB confirms receipt. This ensures crash reports are never lost due to a single point of failure.

### Failure Recovery Scenarios

| Scenario | Behavior |
|----------|----------|
| MongoDB down, queue write succeeds | Report queued; user notified; retried at next startup |
| MongoDB down, queue write fails | Report stays on disk; user sees error; can retry via CrashDialog on next startup |
| MongoDB up, queue write succeeds but MongoDB insert fails | Queue retry handles this — next startup sends again; duplicate detection via report_id if needed |
| MongoDB up, queue write fails | Report stays on disk; fallback to dialog retry |
| MongoDB up, submission succeeds | Both queue file and local crash report deleted |
| Application crashes after queue write but before MongoDB insert | Next startup processes queue; local crash report also available as safety net |

---

## 11. Dependencies

### New Dependencies

| Package | Version | Purpose | Trackora.spec Impact |
|---------|---------|---------|----------------------|
| `pymongo` | `>=4.6` | MongoDB driver | Add hidden import: `pymongo` |
| `dnspython` | `>=2.4` | DNS resolution for SRV URIs | Add hidden import: `dns` |

### Existing Dependencies (Unchanged)

| File | Dependencies | Role |
|------|-------------|------|
| `services/support/reporting_interface.py` | None (stdlib ABC) | Backend contract |
| `services/support/support_service.py` | stdlib, domain models | Orchestrator |
| `services/support/report_queue_service.py` | stdlib, domain models | Offline queue |
| `services/crash/diagnostic_service.py` | stdlib | Diagnostics |
| `services/crash/crash_service.py` | stdlib | Crash detection |
| `models/support/*.py` | stdlib | Domain models |

---

## 12. Files to Create

| File | Purpose |
|------|---------|
| `services/support/mongo_report_service.py` | `MongoReportService` — implements `AbstractReportService` |
| `services/support/mongo_connection.py` | `MongoConnection` — connection manager, health check |

### MongoReportService Structure

```
services/support/mongo_report_service.py
│
├── MongoReportService(AbstractReportService)
│   ├── __init__(connection: MongoConnection)
│   │
│   ├── submit_bug(report: BugReport) → SubmitResult
│   ├── submit_feature(request: FeatureRequest) → SubmitResult
│   ├── submit_feedback(feedback: FeedbackReport) → SubmitResult
│   ├── submit_report(type: ReportType, title: str, body: str) → SubmitResult
│   │   └── Handles crash reports (type=CRASH) the same way as support reports
│   │       └── Builds crash_reports document from title + body + metadata
│   │
│   └── _insert(collection_name: str, document: dict) → SubmitResult
│       └── Shared insertion helper with error handling
│
└── _COLLECTION_MAP: dict[ReportType, str]
    # Maps each ReportType to its MongoDB collection name
    # ReportType.CRASH → "crash_reports"
```

### Files Requiring ReportQueueService Crash Type Support

The following type-mapping tables must include the `"crash"` type so that crash reports can be queued and retried through the same pipeline as support reports:

| File | Map | Current Types | Add |
|------|-----|---------------|-----|
| `services/support/report_queue_service.py` | `_REPORT_TYPE_MAP` | `bug`, `feature`, `feedback` | `crash` → `CrashReport` |
| `services/support/report_queue_service.py` | `_GITHUB_METHOD_MAP` | `bug`, `feature`, `feedback` | `crash` → `submit_crash` |
| `services/support/support_service.py` | `_REPORT_TYPE_CLS_MAP` | `bug`, `feature`, `feedback` | `crash` → `CrashReport` |
| `services/support/support_service.py` | `_GITHUB_METHOD_MAP` | `bug`, `feature`, `feedback` | `crash` → `submit_crash` |

This ensures that when `ReportQueueService.process_queue()` encounters a queued crash report JSON file, it can reconstruct the `CrashReport` model and submit it via `MongoReportService.submit_crash()` or `submit_report(CRASH, ...)`.

### MongoConnection Structure

```
services/support/mongo_connection.py
│
├── MongoConnection
│   ├── __init__(uri: str | None = None)
│   │   ├── If uri is None/empty → read MONGODB_URI from os.environ
│   │   ├── If still empty → mark unavailable
│   │   └── Create MongoClient with timeout config
│   │
│   ├── health_check() → bool
│   │   ├── Ping admin database
│   │   ├── Update is_available flag
│   │   └── Return status
│   │
│   ├── database → Database | None
│   │   └── Return Database handle or None if unavailable
│   │
│   ├── close()
│   │   └── Close MongoClient connection
│   │
│   └── _validate_uri(uri: str) → bool
│       └── Basic validation of MongoDB URI format
│
└── _DEFAULT_DATABASE: str = "trackora_support"
    # Database name constant
```

---

## 13. Files to Modify

| File | Change |
|------|--------|
| `trackora/__main__.py` | Replace `SupabaseReportService()` with `MongoReportService(MongoConnection())` |
| `services/support/__init__.py` | Replace `SupabaseReportService` export with `MongoReportService` |
| `services/support/report_queue_service.py` | Add crash report type to `_REPORT_TYPE_MAP` and `_GITHUB_METHOD_MAP` |
| `services/support/support_service.py` | Add crash report support to `_REPORT_TYPE_CLS_MAP`, `_GITHUB_METHOD_MAP`, serialization, and `_report_type()` |
| `ui/crash_dialog.py` | Add `ReportQueueService` integration — queue crash report on backend failure; call `SupportService.process_queue()` or direct queue write |
| `ui/main_window.py` | Wire `ReportQueueService` into crash submission path; queue processing already handles crash reports after type map update |
| `requirements.txt` | Add `pymongo>=4.6`, `dnspython>=2.4` |
| `Trackora.spec` | Add hidden imports for `pymongo` |

### Files Unchanged

| File | Reason |
|------|--------|
| `services/support/reporting_interface.py` | ABC definition — no change needed |
| `services/support/github_issue_service.py` | Separate backend — no change needed |
| `services/crash/crash_service.py` | Backend-agnostic — no change needed |
| `services/crash/diagnostic_service.py` | Data collection — no change needed |
| `models/support/bug_report.py` | Domain model — no change needed |
| `models/support/feature_request.py` | Domain model — no change needed |
| `models/support/feedback_report.py` | Domain model — no change needed |
| `ui/support_center/support_center_controller.py` | No backend dependency — no change needed |
| `ui/support_center/support_center_widget.py` | Pure UI — no change needed |

### Files to Remove (after migration complete)

| File | Reason |
|------|--------|
| `services/support/supabase_report_service.py` | Replaced by `MongoReportService` |
| `trackora/core/supabase_config.py` | Hardcoded credentials — security risk |
| `tests/test_supabase_report_service.py` | Supabase-specific tests (replace with MongoDB tests) |

---

## 14. MongoDB Security Rules

### Overview

MongoDB connection secrets must be protected at every level: storage, transmission, logging, and source control. These rules replace the previous Supabase credential model (which hardcoded secrets in `trackora/core/supabase_config.py`).

### Security Rules

| ID | Rule | Description | Rationale |
|----|------|-------------|-----------|
| **S1** | No hardcoded secrets | `MONGODB_URI` must never appear as a string literal in any `.py` file | Hardcoded credentials are the most common source of secret leaks; the previous Supabase integration violated this with `trackora/core/supabase_config.py` |
| **S2** | No Git-committed credentials | Credentials must never be committed to version control | Once committed, secrets persist in Git history even if later removed |
| **S3** | `.env` is Git-ignored | Any `.env` file used for local development must be listed in `.gitignore` | Prevents accidental commits of environment secrets |
| **S4** | TLS required | MongoDB connections must use TLS (`mongodb+srv://` scheme or `?tls=true` option) | Protects credentials and data in transit; prevents man-in-the-middle attacks on MongoDB authentication |
| **S5** | Least-privilege user | The MongoDB user specified in `MONGODB_URI` must have read-write access only to the `trackora_support` database | Limits blast radius if credentials are compromised; the user must not have cluster admin or cross-database access |
| **S6** | No secrets in logs | Connection strings must never appear in log output at any log level | Logs are often written to files, collected by monitoring systems, or shared during debugging |
| **S7** | Redacted health-check logging | `health_check()` must log connection status without exposing credentials; e.g. `"MongoDB connection: available"` not `"Connected to mongodb://user:pass@..."` | Health checks run at startup and may be logged to startup logs, which are persisted |
| **S8** | Environment-only loading | Secrets must be loaded from `os.environ` only. No config file reader, no `python-dotenv` import in production code. `.env` support is for development convenience only | Environment variables are the platform-standard mechanism for secret injection; filesystem-based secrets introduce additional attack surface |
| **S9** | No credentials in ancillary outputs | MongoDB credentials must not appear in: source code, configuration files, test fixtures, screenshots, documentation examples, version-controlled files, crash reports, or diagnostic output | Credential leakage through ancillary channels is a known attack vector |

### URI Format

```
mongodb://username:password@host:port/trackora_support?authSource=admin
```

Connection strings using SRV format (TLS-enabled):

```
mongodb+srv://username:password@host.mongodb.net/trackora_support?retryWrites=true&w=majority
```

### Startup Validation

```
On application startup:
    1. Read MONGODB_URI from os.environ
    2. If set:
        a. Log "MongoDB URI: configured" (NEVER log the URI value)
        b. Create MongoConnection
        c. Run health_check()
        d. If health_check fails:
            - Log "MongoDB connection: unavailable" (redacted)
            - Mark unavailable
            - Continue startup (queue-only mode) — no crash, no block
    3. If not set:
        a. Log "MongoDB: not configured — queue-only mode"
        b. Mark unavailable
        c. Continue startup normally
```

### Enforcement

| Mechanism | Location | Description |
|-----------|----------|-------------|
| Code review | Pre-PR | All `MONGODB_URI` references inspected for compliance with S1–S9 |
| Secret scanning | CI pipeline | `.github/workflows/ci.yml` must include a secrets scan step |
| Log inspection test | Test suite | Automated test verifies no credential patterns in log output |
| `.gitignore` check | Pre-commit | Ensure `.env` and `*.env` are in `.gitignore` |

---

## 15. Supabase Removal Checklist

When Supabase is fully removed:

| Item | File | Action |
|------|------|--------|
| 1 | `services/support/supabase_report_service.py` | Delete file |
| 2 | `trackora/core/supabase_config.py` | Delete file |
| 3 | `services/support/__init__.py` | Remove `SupabaseReportService` import and export |
| 4 | `trackora/__main__.py` | Remove Supabase import and wiring |
| 5 | `tests/test_supabase_report_service.py` | Delete file |
| 6 | `tests/test_startup_integration.py` | Remove Supabase mock patch reference |
| 7 | `.env` files | Remove `SUPABASE_URL` and `SUPABASE_ANON_KEY` if present |

---

## 16. Integration Points

### Dependency Injection (__main__.py)

Before:
```python
from services.support.supabase_report_service import SupabaseReportService

report_service = SupabaseReportService()
if report_service.is_configured:
    logger.info("Supabase reporting: configured")
else:
    logger.warning("Supabase reporting: not configured — reports will be queued offline")

support_service = SupportService(
    github_service=report_service,
    queue_service=queue_service,
    announcements_service=announcements_service,
)
```

After:
```python
from services.support.mongo_connection import MongoConnection
from services.support.mongo_report_service import MongoReportService

mongo = MongoConnection()
if mongo.is_available:
    logger.info("MongoDB reporting: connected")
else:
    logger.warning("MongoDB reporting: not available — reports will be queued offline")

report_service = MongoReportService(connection=mongo)

support_service = SupportService(
    github_service=report_service,
    queue_service=queue_service,
    announcements_service=announcements_service,
)
```

### MainWindow

No changes needed. `MainWindow` already accepts `AbstractReportService` and defaults to `GitHubIssueService` only as a fallback when no report service is provided. The injected `MongoReportService` satisfies the interface.

---

## 17. Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-01 | `MongoReportService` implements `AbstractReportService` | Interface compliance test |
| AC-02 | All 4 collections created with `schema_version` field | Document inspection |
| AC-03 | `MongoConnection` reads URI from environment only | Unit test with empty env |
| AC-04 | Unconfigured MongoDB falls back to queue-only mode | Integration test |
| AC-05 | Report submission with MongoDB available inserts document | Integration test with test MongoDB |
| AC-06 | Report submission with MongoDB unavailable queues to JSON | Integration test |
| AC-07 | `MongoReportService` returns `SubmitResult` for all methods | Unit test |
| AC-08 | `bug_reports` collection contains all required fields | Schema validation test |
| AC-09 | `feature_requests` collection contains all required fields | Schema validation test |
| AC-10 | `feedback` collection contains all required fields | Schema validation test |
| AC-11 | `crash_reports` collection contains all required fields | Schema validation test |
| AC-12 | Existing `SupportService` tests pass without changes | `pytest` suite green |
| AC-13 | Existing `ReportQueueService` tests pass without changes | `pytest` suite green |
| AC-14 | Existing `CrashService` tests pass without changes | `pytest` suite green |
| AC-15 | Existing `DiagnosticService` tests pass without changes | `pytest` suite green |
| AC-16 | Application starts without MongoDB in queue-only mode | Manual test |
| AC-17 | Application starts with MongoDB and submits reports normally | Manual test |
| AC-18 | No Supabase references remain in DI wiring | Code review |
| AC-19 | No hardcoded MongoDB credentials in source | Code review |
| AC-20 | Indexes created on all 4 collections | Document inspection |
| AC-21 | Crash report submission queues via `ReportQueueService` when MongoDB unavailable | Integration test |
| AC-22 | Crash report queue entry correctly reconstructs into `CrashReport` model | Unit test |
| AC-23 | `MongoConnection` is a singleton — one `MongoClient` per process | Unit test |
| AC-24 | `MongoConnection` supports lazy initialization — no connection on construction | Unit test |
| AC-25 | `MongoConnection` is thread-safe under concurrent access | Concurrency test |
| AC-26 | Connection string never appears in log output | Log inspection test |
| AC-27 | `health_check()` redacts credentials from log messages | Log inspection test |
| AC-28 | TLS is enabled when `MONGODB_URI` uses `mongodb+srv://` scheme | Connection config review |

---

*End of Specification*
