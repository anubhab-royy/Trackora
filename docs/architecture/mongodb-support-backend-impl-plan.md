# MongoDB Support Backend — Implementation Plan

## Files to Create

| File | Purpose |
|------|---------|
| `services/support/mongo_connection.py` | `MongoConnection` — singleton connection manager with lazy init, health check, thread-safe access |
| `services/support/mongo_report_service.py` | `MongoReportService` — implements `AbstractReportService`, writes to 4 MongoDB collections |
| `tests/test_mongo_connection.py` | Unit/integration tests for `MongoConnection` |
| `tests/test_mongo_report_service.py` | Unit/integration tests for `MongoReportService` |

## Files to Modify

| File | Change |
|------|--------|
| `services/support/report_queue_service.py` | Add `"crash"` to `_REPORT_TYPE_MAP` and `_GITHUB_METHOD_MAP`; import `CrashReport` |
| `services/support/support_service.py` | Add `"crash"` to `_REPORT_TYPE_CLS_MAP` and `_GITHUB_METHOD_MAP`; add `_serialize_crash_report()`; add crash report to `_report_type()` |
| `ui/crash_dialog.py` | Inject `ReportQueueService`; queue crash report on backend failure; show queued status |
| `ui/main_window.py` | Pass `ReportQueueService` to `CrashDialog`; wire queue into crash submission path |
| `trackora/__main__.py` | Replace `SupabaseReportService()` with `MongoReportService(MongoConnection())` |
| `services/support/__init__.py` | Replace `SupabaseReportService` export with `MongoReportService`; add `MongoConnection` |
| `requirements.txt` | Add `pymongo>=4.6`, `dnspython>=2.4` |
| `Trackora.spec` | Add `--hidden-import` for `pymongo` and `dns` |

## Dependencies Between Steps

```
Step 1 (MongoConnection) ──┐
                            ├──► Step 3 (MongoReportService) ──┐
Step 2 (ReportQueue crash) ─┘                                  │
                                                                ├──► Step 5 (CrashDialog queue) ──┐
Step 4 (SupportService crash) ─────────────────────────────────┘                                   │
                                                                                                    ├──► Step 7 (DI Wiring)
Step 6 (Existing test pass) ───────────────────────────────────────────────────────────────────────┘
```

Step 1 and Step 2 can be done in parallel.

## TDD Steps

### Step 1 — MongoConnection (`RED → GREEN → REFACTOR`)

**RED:** Write tests for `MongoConnection`:

| Test | Description |
|------|-------------|
| 1.1 | Constructor with explicit URI stores it |
| 1.2 | Constructor with no URI reads `MONGODB_URI` from `os.environ` |
| 1.3 | Constructor with no URI and no env var leaves `is_available == False` |
| 1.4 | `is_available` returns `False` before any connection attempt (lazy) |
| 1.5 | `health_check()` returns `False` when not configured |
| 1.6 | `health_check()` returns `False` when ping fails (mock `admin.command`) |
| 1.7 | `health_check()` returns `True` when ping succeeds |
| 1.8 | `database` returns `None` when not configured |
| 1.9 | `database` returns `Database` instance when connected |
| 1.10 | `database` creates `MongoClient` lazily on first access (not in `__init__`) |
| 1.11 | Multiple calls to `database` return the same `MongoClient` (singleton within instance) |
| 1.12 | `health_check()` redacts credentials from log output |
| 1.13 | `close()` releases resources |
| 1.14 | `close()` is idempotent |
| 1.15 | Thread-safe: concurrent `database` access from 3 threads |

**GREEN:** Implement `MongoConnection` in `services/support/mongo_connection.py`:

```python
class MongoConnection:
    def __init__(self, uri: str | None = None) -> None:
        self._uri = uri or os.environ.get("MONGODB_URI", "")
        self._client: MongoClient | None = None
        self._available: bool | None = None
        self._lock = threading.Lock()

    @property
    def is_available(self) -> bool: ...

    @property
    def database(self) -> Database | None: ...

    def health_check(self) -> bool: ...

    def close(self) -> None: ...
```

**REFACTOR:** Ensure:
- Lock scoping is minimal (only around client creation, not every op)
- Log messages use redacted format: `"MongoDB: available"` not `"Connected to mongodb://..."``
- No import-time side effects

**Tests:** ~15 tests

---

### Step 2 — ReportQueueService Crash Type Support (`RED → GREEN → REFACTOR`)

**RED:** Write tests for crash report queueing:

| Test | Description |
|------|-------------|
| 2.1 | `save_report("crash", data)` writes valid JSON file |
| 2.2 | Saved crash JSON has `type: "crash"` |
| 2.3 | `process_queue()` calls `submit_fn("crash", data)` for crash entries |
| 2.4 | `reconstruct_model("crash", data)` returns `CrashReport` instance |
| 2.5 | `reconstruct_model("crash", invalid_data)` returns `None` |
| 2.6 | `get_github_method("crash")` returns `"submit_crash"` |
| 2.7 | Queue processes crash + bug + feature + feedback mixed entries correctly |

**GREEN:** Modify `services/support/report_queue_service.py`:

```python
from services.crash.diagnostic_service import CrashReport

_REPORT_TYPE_MAP: dict[str, type] = {
    "bug": BugReport,
    "feature": FeatureRequest,
    "feedback": FeedbackReport,
    "crash": CrashReport,
}

_GITHUB_METHOD_MAP: dict[str, str] = {
    "bug": "submit_bug",
    "feature": "submit_feature",
    "feedback": "submit_feedback",
    "crash": "submit_crash",
}
```

**REFACTOR:** Ensure `CrashReport` import does not create circular dependencies.

**Tests:** 7 tests

---

### Step 3 — MongoReportService (`RED → GREEN → REFACTOR`)

**RED:** Write tests for `MongoReportService`:

| Test | Description |
|------|-------------|
| 3.1 | `__init__` stores `MongoConnection` reference |
| 3.2 | `submit_bug()` returns `SubmitResult` with `success=True` when MongoDB available |
| 3.3 | `submit_bug()` inserts document into `bug_reports` collection with correct fields |
| 3.4 | `submit_bug()` inserts document with `schema_version: 1` |
| 3.5 | `submit_bug()` inserts document with `submitted_at` timestamp |
| 3.6 | `submit_bug()` returns `SubmitResult(success=False)` when MongoDB unavailable |
| 3.7 | `submit_feature()` inserts document into `feature_requests` with correct fields |
| 3.8 | `submit_feedback()` inserts document into `feedback` with correct fields |
| 3.9 | `submit_report(CRASH, title, body)` inserts document into `crash_reports` with correct fields |
| 3.10 | `submit_report(CRASH, ...)` returns `report_id` on success (string repr of ObjectId) |
| 3.11 | `submit_bug()` handles connection dropped mid-insert → returns `SubmitResult(success=False)` |
| 3.12 | All methods return `SubmitResult` with `success=False` and descriptive error when `MongoConnection` is unavailable |
| 3.13 | `submit_bug()` inserts document with `source: "support_center"` |
| 3.14 | `submit_report(CRASH, ...)` inserts document with `source: "crash_detector"` |
| 3.15 | `CollectionMap` maps all 4 `ReportType` values correctly |
| 3.16 | Indexes created on all 4 collections on first `_insert` call |

**GREEN:** Implement `MongoReportService` in `services/support/mongo_report_service.py`:

```python
class MongoReportService(AbstractReportService):
    def __init__(self, connection: MongoConnection) -> None: ...

    def submit_bug(self, report: BugReport) -> SubmitResult: ...
    def submit_feature(self, request: FeatureRequest) -> SubmitResult: ...
    def submit_feedback(self, feedback: FeedbackReport) -> SubmitResult: ...
    def submit_report(self, report_type: ReportType, title: str, body: str) -> SubmitResult: ...

    def _insert(self, collection_name: str, document: dict) -> SubmitResult: ...
    def _ensure_indexes(self) -> None: ...
    def _build_crash_document(self, title: str, body: str, crash_report: CrashReport | None) -> dict: ...
```

**Document building helpers (private):**

```python
_COLLECTION_MAP: dict[ReportType, str] = {
    ReportType.BUG: "bug_reports",
    ReportType.FEATURE: "feature_requests",
    ReportType.FEEDBACK: "feedback",
    ReportType.CRASH: "crash_reports",
}
```

**REFACTOR:** Ensure:
- `_insert()` is the single write path — all public methods delegate to it
- Error handling is centralized in `_insert()` — no try/except per method
- Document enrichment (schema_version, app_version, os, submitted_at, source) is applied in `_insert()`
- `_ensure_indexes()` is called once on first insert (track with `_indexes_created` flag)

**Tests:** ~16 tests

---

### Step 4 — SupportService Crash Report Support (`RED → GREEN → REFACTOR`)

**RED:** Write tests for crash serialization and routing:

| Test | Description |
|------|-------------|
| 4.1 | `_serialize_crash_report()` produces dict with correct fields |
| 4.2 | `_report_type("submit_crash")` returns `"crash"` |
| 4.3 | `_reconstruct_model("crash", data)` returns `CrashReport` |
| 4.4 | `_GITHUB_METHOD_MAP["crash"]` equals `"submit_crash"` |
| 4.5 | `_REPORT_TYPE_CLS_MAP["crash"]` equals `CrashReport` |
| 4.6 | `process_queue()` handles crash entries without error |

**GREEN:** Modify `services/support/support_service.py`:

```python
from services.crash.diagnostic_service import CrashReport

_REPORT_TYPE_CLS_MAP: dict[str, type] = {
    "bug": BugReport,
    "feature": FeatureRequest,
    "feedback": FeedbackReport,
    "crash": CrashReport,
}

_GITHUB_METHOD_MAP: dict[str, str] = {
    "bug": "submit_bug",
    "feature": "submit_feature",
    "feedback": "submit_feedback",
    "crash": "submit_crash",
}
```

Add `_serialize_crash_report()`:
```python
@staticmethod
def _serialize_crash_report(title: str, body: str, crash_type: str,
                             app_version: str, os_version: str,
                             os_platform: str, active_sessions: list,
                             tracked_games: int, was_tracking: bool,
                             stack_trace: str | None,
                             recent_log_entries: list[str]) -> dict[str, object]:
    return {
        "title": title,
        "body": body,
        "crash_type": crash_type,
        "app_version": app_version,
        "os_version": os_version,
        "os_platform": os_platform,
        "active_sessions": active_sessions,
        "tracked_games": tracked_games,
        "was_tracking": was_tracking,
        "stack_trace": stack_trace,
        "recent_log_entries": recent_log_entries,
    }
```

Update `_report_type()`:
```python
@staticmethod
def _report_type(github_method: str) -> str:
    mapping = {
        "submit_bug": "bug",
        "submit_feature": "feature",
        "submit_feedback": "feedback",
        "submit_crash": "crash",
    }
    return mapping.get(github_method, "unknown")
```

**REFACTOR:** Ensure:
- No circular import between `support_service.py` and `diagnostic_service.py`
- `CrashReport` reconstruction works with queued data fields (queue stores flat dict, not `CrashReport` instance)

**Tests:** 6 tests

---

### Step 5 — CrashDialog Queue Integration (`RED → GREEN → REFACTOR`)

**RED:** Write tests for queue-aware crash submission:

| Test | Description |
|------|-------------|
| 5.1 | Dialog injects `ReportQueueService` and stores reference |
| 5.2 | Successful MongoDB submission deletes both local crash report JSON and queue file |
| 5.3 | MongoDB failure + retryable error → calls `ReportQueueService.save_report("crash", data)` |
| 5.4 | MongoDB failure + retryable error → shows queued status message |
| 5.5 | MongoDB failure + non-retryable error → does NOT queue, shows config error |
| 5.6 | Queue write failure is handled gracefully (log error, show local-save message) |
| 5.7 | Dismiss button deletes local crash report JSON but leaves queue entry intact |
| 5.8 | Review button does not modify queue |

**GREEN:** Modify `ui/crash_dialog.py`:

```python
class CrashDialog(QDialog):
    def __init__(
        self,
        report: CrashReport,
        report_path: Path,
        github_service: AbstractReportService | None = None,
        queue_service: ReportQueueService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        ...
        self._queue_service = queue_service

    def _on_send(self) -> None:
        # existing submission logic
        ...
        if result.success:
            self._delete_report_file()
            # queue file already deleted by process_queue if applicable
        elif self._is_retryable(result.error_message) and self._queue_service:
            self._queue_crash_report()
            self._status_label.setText(
                "Report saved locally and will be sent automatically."
            )
        else:
            self._status_label.setText(
                f"Failed to submit: {result.error_message}"
            )

    def _queue_crash_report(self) -> None:
        data = self._build_queue_data()
        try:
            self._queue_service.save_report("crash", data)
            logger.info("Crash report queued for retry: %s", self._report.report_id)
        except Exception as exc:
            logger.exception("Failed to queue crash report: %s", exc)

    def _build_queue_data(self) -> dict:
        return {
            "title": self._report_title,
            "body": self._report_body,
            "crash_type": self._report.crash_type,
            "app_version": self._report.app_version,
            ...
        }

    @staticmethod
    def _is_retryable(error_message: str | None) -> bool:
        if error_message is None:
            return False
        lower = error_message.lower()
        return not any(kw in lower for kw in [
            "not configured", "authentication failed", "not found", "check your",
        ])
```

**REFACTOR:** Ensure:
- `_is_retryable()` is extracted as a static method — avoid duplicating logic from `support_service.py`
- Queue write failure does not crash the dialog — exception caught, user informed
- Status messaging is clear for all three outcomes: submitted / queued / error

**Tests:** 8 tests

---

### Step 6 — Existing Test Pass (`GREEN` Only)

**No RED phase** — these tests must pass without changes.

Run all existing tests to verify backward compatibility:

```bash
python -m pytest tests/test_support_service.py -x -v
python -m pytest tests/test_report_queue_service.py -x -v
python -m pytest tests/test_crash_service.py -x -v
python -m pytest tests/test_diagnostic_service.py -x -v
python -m pytest tests/test_support_center_controller.py -x -v
python -m pytest tests/test_github_issue_service.py -x -v
python -m pytest tests/test_reporting_interface.py -x -v
```

**Expected:** All existing tests pass without modification.

**Validation:** 7 test suites, 100% pass rate.

---

### Step 7 — Dependency Injection Wiring (`GREEN` Only)

**No RED phase** — wiring changes only. Verify by running the application.

**GREEN:** Modify `trackora/__main__.py`:

```python
# Before:
from services.support.supabase_report_service import SupabaseReportService

report_service = SupabaseReportService()
if report_service.is_configured:
    logger.info("Supabase reporting: configured")
else:
    logger.warning("Supabase reporting: not configured — reports will be queued offline")

# After:
from services.support.mongo_connection import MongoConnection
from services.support.mongo_report_service import MongoReportService

mongo = MongoConnection()
if mongo.is_available:
    logger.info("MongoDB reporting: connected")
else:
    logger.warning("MongoDB reporting: not available — reports will be queued offline")

report_service = MongoReportService(connection=mongo)
```

Modify `services/support/__init__.py`:

```python
from services.support.mongo_connection import MongoConnection
from services.support.mongo_report_service import MongoReportService
# Remove: from services.support.supabase_report_service import SupabaseReportService

__all__ = [
    ...
    "MongoConnection",
    "MongoReportService",
    # Remove: "SupabaseReportService",
]
```

Modify `ui/main_window.py` — pass `ReportQueueService` to `CrashDialog`:

```python
dialog = CrashDialog(
    report=result.report,
    report_path=result.report_path,
    github_service=self._report_service,
    queue_service=self._queue_service,   # new
    parent=self,
)
```

**Validation:**
```bash
# Application starts without MongoDB (queue-only mode)
MONGODB_URI="" python -m trackora
# Application starts with MongoDB
MONGODB_URI="mongodb://localhost:27017/trackora_support" python -m trackora
```

---

### Step 8 — Integration Tests (`RED → GREEN → REFACTOR`)

**RED:** Write integration tests for end-to-end flows:

| Test | Description |
|------|-------------|
| 8.1 | Full flow: SupportService → MongoReportService → MongoDB insert for BugReport |
| 8.2 | Full flow: SupportService → MongoReportService → MongoDB insert for FeatureRequest |
| 8.3 | Full flow: SupportService → MongoReportService → MongoDB insert for FeedbackReport |
| 8.4 | Full flow: CrashDialog → MongoReportService → MongoDB insert for CrashReport |
| 8.5 | Full flow: SupportService → MongoReportService failure → ReportQueueService → restart → queue processed |
| 8.6 | Full flow: CrashDialog → MongoReportService failure → ReportQueueService → restart → queue processed → crash_reports inserted |
| 8.7 | Queue processing: all 4 types in mixed queue → all submitted → queue directory empty |
| 8.8 | Offline: MongoDB unavailable → all 4 report types queued → MongoDB restored → queue processed → all inserted |
| 8.9 | MongoConnection: app starts without MongoDB → queue-only → MongoDB starts → next operation connects |

**GREEN:** Implement integration tests using a test MongoDB instance or `mongomock`.

**REFACTOR:** Ensure tests clean up after themselves (drop test collections after each test).

**Tests:** 9 integration tests

---

## Completion Checklist

- [ ] Step 1: MongoConnection — 15 unit tests, implementation, singleton + lazy + thread-safe
- [ ] Step 2: ReportQueueService crash type — 7 tests, type maps updated
- [ ] Step 3: MongoReportService — 16 tests, implements AbstractReportService, 4 collections
- [ ] Step 4: SupportService crash support — 6 tests, serialization + reconstruction
- [ ] Step 5: CrashDialog queue integration — 8 tests, queue on failure
- [ ] Step 6: Existing tests pass — 7 test suites, 100%
- [ ] Step 7: DI wiring — __main__.py, __init__.py, main_window.py
- [ ] Step 8: Integration tests — 9 end-to-end tests
- [ ] `requirements.txt` updated with `pymongo>=4.6` and `dnspython>=2.4`
- [ ] `Trackora.spec` updated with hidden imports
- [ ] Full regression: `python -m pytest --tb=short`
- [ ] PyInstaller build test: `pyinstaller Trackora.spec`

## Validation Commands

```bash
# Step 1: MongoConnection
python -m pytest tests/test_mongo_connection.py -x -v

# Step 2: ReportQueueService crash type
python -m pytest tests/test_report_queue_service.py -x -v

# Step 3: MongoReportService
python -m pytest tests/test_mongo_report_service.py -x -v

# Step 4: SupportService crash support
python -m pytest tests/test_support_service.py -x -v

# Step 5: CrashDialog queue
python -m pytest tests/test_crash_dialog.py -x -v

# Step 6: Existing test regression
python -m pytest tests/test_support_service.py tests/test_report_queue_service.py tests/test_crash_service.py tests/test_diagnostic_service.py tests/test_support_center_controller.py tests/test_github_issue_service.py tests/test_reporting_interface.py -x -v

# Step 8: Integration
python -m pytest tests/test_mongo_connection.py tests/test_mongo_report_service.py -x -v

# Full regression
python -m pytest --tb=short

# PyInstaller smoke test
pyinstaller Trackora.spec --clean --noconfirm 2>&1 | tail -20
```

## Risk Mitigation During Implementation

| Risk | Mitigation |
|------|------------|
| PyMongo hidden imports break PyInstaller | Add `--hidden-import=pymongo` and `--hidden-import=dns` to `.spec`; run PyInstaller build test early |
| MongoDB unavailable in CI | Use `mongomock` for unit tests; integration tests skip if no real MongoDB |
| Circular imports (crash ↔ support) | Keep `CrashReport` import local to the type-map block; `support_service.py` imports `diagnostic_service.py`, not vice versa |
| Crash dialog refactoring risk | Keep `CrashDialog` backward-compatible: `queue_service` parameter is optional (`None` default) |
| Singleton enforcement | Enforce at DI layer (`__main__.py` creates one instance); class-level singleton is not required |
