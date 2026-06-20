# MongoDB Post-Validation Audit

## Call Graph

```
SupportCenterController._submit_bug()           [controller:90]
  → SupportService.submit_bug_report(report)    [support_service:104]
    → SupportService._submit_with_github_and_queue()  [support_service:157]
      → SupportService._try_github_submit()     [support_service:184]
        → MongoReportService.submit_bug(report) [mongo_report_service:60]
          → MongoReportService._insert()        [mongo_report_service:113]
            → MongoConnection.is_available      [mongo_connection:41]  → True ✓
            → MongoConnection.database          [mongo_connection:48]  → None ✗
              → pymongo.client.get_default_database()  → None
            ← SubmitResult(success=False, "MongoDB not available.")
      ← (False, None, "MongoDB not available.")
      → SupportService._is_retryable("MongoDB not available.") → True
      → SupportService._try_queue_report()  → queued to disk
    ← SupportSubmitResult(local_stored=True, github_success=False, queued=True)
  ← SupportSubmitResult
  → SupportCenterController._show_submit_result()
    → "Report saved locally and will be sent automatically."
```

## Actual Runtime Flow

| Step | File:Line | Action | Result |
|------|-----------|--------|--------|
| 1 | `__main__.py:202-204` | `MongoConnection()` + `health_check()` | `True` — ping succeeds |
| 2 | `controller:90` | `self._service.submit_bug_report(report)` | Delegates to SupportService |
| 3 | `support_service:104-116` | Store locally, call `_submit_with_github_and_queue` | Local store succeeds |
| 4 | `support_service:162-163` | `_try_github_submit("submit_bug", report)` | Calls MongoReportService |
| 5 | `mongo_report_service:60-72` | `submit_bug()` → `_insert()` | Builds doc, calls `_insert` |
| 6 | `mongo_report_service:114` | **CHECK:** `self._connection.is_available` | **`True`** ✅ |
| 7 | `mongo_report_service:114` | **CHECK:** `self._connection.database is None` | **`True`** 🚫 |
| 8 | `mongo_report_service:115-117` | Return `SubmitResult(False, "MongoDB not available.")` | Early return |
| 9 | `support_service:198-203` | `result.success` is `False` | Logs warning, returns error |
| 10 | `support_service:169` | `_is_retryable("MongoDB not available.")` | `True` — none of the non-retryable keywords match |
| 11 | `support_service:170` | `_try_queue_report(...)` | Report written to offline queue |
| 12 | `controller:152-156` | `_show_submit_result` → `queued=True` | **Shows "Report saved locally and will be sent automatically."** |

## Queue Fallback Trigger

**Exact trigger**: `mongo_report_service.py:114`

```python
if not self._connection.is_available or self._connection.database is None:
    return SubmitResult(success=False, error_message="MongoDB not available.")
```

The **first** condition (`is_available`) is `True` (health check passed).
The **second** condition (`database is None`) is `True` — this is what triggers the fallback.

## Root Cause

### Why `database` is `None`

`MongoConnection.database` property (`mongo_connection.py:48-58`):

```python
@property
def database(self) -> Database | None:
    if not self._uri:
        return None
    client = self._get_or_create_client()
    return client.get_default_database()  # ← pymongo
```

`pymongo.MongoClient.get_default_database()` returns `None` when the connection URI **contains no database name in its path**:

```
MONGODB_URI=mongodb+srv://astra37:****@trackora-support.czdzzup.mongodb.net/?appName=trackora-support
                                                           ^^
                                                  No database name here
```

The URI has query parameters (`?appName=...`) but no database path component (e.g., `/trackora_support`).

### Missing `MONGODB_DATABASE` integration

The `.env` file contains a separate variable:

```
MONGODB_DATABASE=trackora_support
```

But `MongoConnection.__init__` (`mongo_connection.py:30-31`) only reads `MONGODB_URI`:

```python
def __init__(self, uri: str | None = None) -> None:
    self._uri = uri or os.environ.get("MONGODB_URI", "")
```

It **never reads `MONGODB_DATABASE`**, so the database name is lost.

## Summary

| Item | Value |
|------|-------|
| `health_check()` | `True` — Atlas is reachable |
| `is_available` | `True` — set by successful health_check |
| `database` | `None` — URI has no database path |
| `_insert()` fallback | Triggered at `mongo_report_service.py:114` |
| User-visible message | "Report saved locally and will be sent automatically." |
| Atlas collections created | **None** — `insert_one` never called |

## Fix Options

| Option | Change | Risk |
|--------|--------|------|
| **A** — Add database name to URI | Change `.env` to `mongodb+srv://...@host/trackora_support?appName=...` | Lowest — single char `/` |
| **B** — Read `MONGODB_DATABASE` in `MongoConnection` | Fall back to `os.environ.get("MONGODB_DATABASE")` when `get_default_database()` returns `None` | Low — env var already exists |

**Option B is preferred** because it decouples the database name from the connection string, matching the existing two-variable pattern in `.env`.
