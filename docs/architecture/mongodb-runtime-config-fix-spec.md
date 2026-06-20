# MongoDB Runtime Configuration — Fix Specification

## Requirements

| ID | Description | Verification |
|----|-------------|--------------|
| R1 | Environment variables loaded before `MongoConnection` creation | Audit startup order |
| R2 | Environment variables loaded before `MongoReportService` creation | Audit startup order |
| R3 | Missing `MONGODB_URI` must not crash startup | Startup with no URI succeeds |
| R4 | Missing `MONGODB_URI` must produce structured warning log | Log contains expected warning |
| R5 | Support Center remains operational through queue fallback | Submit succeeds when MongoDB unavailable |
| R6 | No credentials written to logs | Log capture shows no URI/secret values |
| R7 | Compatible with development and packaged builds | Loader fails gracefully when `.env` absent |
| R8 | Compatible with Atlas SRV connection strings | SRV URI passes through unmodified |

## Second Bug Discovered During Audit

`__main__.py:203` checks `mongo.is_available`, which returns `self._available` (default `None` → `False`). **`health_check()` is never called**, so even with a valid URI, the connection is always reported as unavailable.

**Fix**: Replace `if mongo.is_available` with `if mongo.health_check()`.

## Design

### 1. Extract .env loader to `trackora/core/env.py`

Reuse the stdlib-only pattern from `services/support/supabase_report_service.py:45-74`:

```python
# trackora/core/env.py
def load_env_file(path: str | Path | None = None) -> None:
    """Load .env file entries into os.environ (stdlib-only)."""
```

This function:
- Searches for `.env` in CWD then project root (relative to script)
- Parses `KEY=VALUE` lines, skipping comments/blanks
- Calls `os.environ.setdefault(key, value)` for each pair
- Logs (redacted) how many variables were loaded, never the values
- Silently returns if no `.env` is found

### 2. Call `load_env_file()` at top of `main()` in `__main__.py`

```python
def main() -> None:
    LoggingService.setup()
    logger = logging.getLogger(__name__)

    # Load .env before any service that reads environment variables
    from trackora.core.env import load_env_file
    load_env_file()

    # ... rest of startup ...
```

### 3. Change `__main__.py:203` to call `health_check()`

```python
mongo = MongoConnection()
if mongo.health_check():
    logger.info("MongoDB reporting: connected")
else:
    logger.warning("MongoDB reporting: not available — reports will be queued offline.")
```

### 4. Verify `MongoConnection` behavior

- `health_check()` with `self._uri == ""` returns `False` (already correct)
- `health_check()` with valid URI + unreachable server returns `False` after timeout (already correct — `serverSelectionTimeoutMS=5000`)
- `_insert` checks `is_available` which is now set by the prior `health_check()` call (already correct)

## Non-Goals

- No changes to `MongoConnection` or `MongoReportService` logic
- No `python-dotenv` dependency added
- No changes to `supabase_report_service.py` (existing loader stays in place)
- No changes to `SupportService`, `ReportQueueService`, or other service code
- No changes to main window or UI code

## Files Changed

| File | Change |
|------|--------|
| `trackora/core/env.py` | **New** — `load_env_file()` function |
| `trackora/__main__.py` | Import + call `load_env_file()` before line 202; change `is_available` to `health_check()` |
| `tests/test_env_loader.py` | **New** — tests for .env loading |
