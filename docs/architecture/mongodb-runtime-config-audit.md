# MongoDB Runtime Configuration — Audit

## Root Cause

`trackora/__main__.py:202` constructs `MongoConnection()` with no URI argument:

```python
mongo = MongoConnection()
```

This delegates to `os.environ.get("MONGODB_URI", "")` (`mongo_connection.py:31`). However, **no code ever loads the `.env` file into `os.environ`**, so `MONGODB_URI` is never set, `self._uri` is `""`, `health_check()` returns `False`, and the system always falls back to the offline queue.

## Startup Sequence (__main__.py:main)

| Step | Line | What happens | Env loaded? |
|------|------|-------------|-------------|
| 1 | 59 | `LoggingService.setup()` | No |
| 2 | 68 | `_acquire_lock()` | No |
| 3 | 80 | `QApplication(sys.argv)` | No |
| 4 | 84 | `ensure_dirs()` | No |
| 5 | 85-87 | `DatabaseManager`, `db.initialize()` | No |
| 6 | 90-115 | Schema version, crash check, backup/migration | No |
| 7 | 188-197 | Repos and services created | No |
| 8 | **202** | **`MongoConnection()` — reads `MONGODB_URI` from env** | **No — BUG** |
| 9 | 210 | `MongoReportService(connection=mongo)` | No |
| 10 | 218-222 | `SupportService(...)` | No |

**Step 8 is the first point where `MONGODB_URI` is needed**, but no prior step has loaded the `.env` file.

## .env File Discovery

- File exists at project root: `/home/astra/Codebase/GitHub/Trackora/.env`
- `grep -R "load_dotenv" .` returns **no results**
- A stdlib-only `.env` loader already exists in `services/support/supabase_report_service.py:45-74` (`_discover_env_file` + `_load_env_vars`) — but it only applies the loaded vars to `SupabaseReportService`'s own config, not to `os.environ`.

## Existing .env Loader (supabase_report_service.py:45-74)

```python
def _discover_env_file() -> Path | None:
    """Look for a .env file relative to the project root or cwd."""

def _load_env_vars() -> dict[str, str]:
    """Read key=value pairs from .env file manually."""
```

This loader is **not reusable** — it returns a `dict` and was never intended to populate `os.environ`. It lives in a service that may be removed in the future.

## MongoConnection Construction Path

```
__main__.py:202  MongoConnection()
  → mongo_connection.py:31  os.environ.get("MONGODB_URI", "")
    → os.environ[MONGODB_URI] → KeyError → ""
      → __main__.py:203  mongo.is_available → False (self._available is None)
        → logger.warning("MongoDB reporting: not available — reports will be queued offline.")
```

## MongoReportService Construction Path

```
__main__.py:210  MongoReportService(connection=mongo)
  → mongo_report_service.py:52-54  stores self._connection
  → SupportService wraps it as github_service
  → SupportService.submit_*() calls:
    → report_service.submit_*() calls:
      → mongo_report_service._insert():
        → self._connection.is_available → False
        → returns SubmitResult(success=False, error_message="MongoDB not available.")
        → SupportService treats this as non-retryable → no queue either
```

Note: `health_check()` is **never called** in `__main__.py`. The check at line 203 (`if mongo.is_available`) evaluates `self._available` which is `None` → `False`. Even if `.env` were loaded, **`health_check()` must be called explicitly** (or `is_available` must trigger it) for the connection to be considered available.

Wait — this means even WITH the URI loaded, the connection would still be marked unavailable because `is_available` checks `self._available` (which is `None`/`False` until `health_check()` is called). The `__main__.py` code at line 203 says:

```python
mongo = MongoConnection()
if mongo.is_available:  # self._available is None → False
    ...
```

So there's a **second bug**: `health_check()` is never called. Even if we load the URI, `is_available` returns `False` because no ping was attempted.

Actually wait, let me re-read is_available:

```python
@property
def is_available(self) -> bool:
    return bool(self._available)
```

`self._available` defaults to `None` in `__init__`. `bool(None)` is `False`. So `is_available` is `False` until `health_check()` succeeds.

But in `_insert`:
```python
def _insert(self, report_type, doc):
    if not self._connection.is_available or self._connection.database is None:
        return SubmitResult(success=False, error_message="MongoDB not available.")
```

This returns early because `is_available` is `False`.

**Fix needed**: In `__main__.py`, after `MongoConnection()` construction, call `mongo.health_check()`. Or change `is_available` property to attempt a health check on first access.

The most explicit approach (preferred): call `health_check()` explicitly in `__main__.py`.

```python
mongo = MongoConnection()
if mongo.health_check():
    logger.info("MongoDB reporting: connected")
else:
    logger.warning("MongoDB reporting: not available — reports will be queued offline.")
```

## Startup Ordering Requirements

1. `.env` must be loaded **before** `MongoConnection()` is constructed.
2. `MongoConnection.health_check()` must be called **before** the availability check.
3. `MongoReportService` must receive a `MongoConnection` that has already been health-checked.
4. Missing `.env` or `MONGODB_URI` must **not** crash startup (graceful fallback to queue).

## Packaging Implications

- `.env` file is a development-time convenience. In packaged builds, `MONGODB_URI` would be set via system environment variables or the packaging platform's secrets mechanism.
- The `.env` loader should swallow `FileNotFoundError` gracefully — absence of `.env` is not an error.
- `python-dotenv` dependency is **not permitted** per architecture spec S8 ("Environment-only loading"). The stdlib-only approach from `supabase_report_service.py` should be reused or extracted.

## Recommendation

Extract the .env loading logic from `supabase_report_service.py` into a shared location (e.g., `trackora/core/env.py`) and call it at the top of `main()` in `__main__.py`, before line 202. Also change line 203 to call `health_check()` instead of checking the pre-populated `is_available` property.
