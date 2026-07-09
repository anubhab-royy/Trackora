# T-233: Improved Logging — Walkthrough

## Overview

This phase improves the observability of Trackora's Support Centre by
standardising log messages, introducing correlation IDs, enforcing
consistent log-level usage, and verifying no sensitive data leaks into
log output.

**Scope**: Every logging call inside `services/support/`.

**Constraint**: `LoggingService` is not redesigned; no third-party
logging frameworks are introduced; existing log-file format remains
unchanged.

---

## Purpose

Before T-233, logs were inconsistent:
- Some used a `"Diagnostics:"` prefix, others had no subsystem tag.
- Correlation between related events (submission → queue → retry) was
  impossible without manual grep.
- Log levels were applied unevenly (expected offline conditions logged
  at ERROR; execution details logged at INFO).
- No systematic protection against sensitive data (Mongo URI, tokens)
  appearing in logs.

After T-233, every log entry clearly indicates:
- **subsystem** — e.g. `[MongoDB]`, `[Support]`, `[Queue]`
- **operation** — e.g. `Validation started`, `Report submitted`
- **outcome** — e.g. `(Connected)`, `(AuthenticationFailed)`
- **reason** — e.g. `(ConfigurationMissing)`, `(DiskFull)`

---

## Logging Architecture

### Formatter (unchanged)

`LoggingService.setup()` provides:
```
%(asctime)s [%(levelname)-7s] %(name)s | %(message)s
2026-07-09 12:00:00 [INFO   ] services.support.support_service | [Support][a1b2c3d4] Submission started
```

### Subsystem tags

| Module                 | Tag                |
|------------------------|--------------------|
| `mongo_connection.py`  | `[MongoDB]`        |
| `mongo_report_service.py` | `[MongoDB]`    |
| `support_service.py`   | `[Support]`        |
| `report_queue_service.py` | `[Queue]`      |
| `queue_validator.py`   | `[QueueValidator]` |
| `github_issue_service.py` | `[GitHub]`     |
| `supabase_report_service.py` | `[Supabase]` |

Each module defines a `SUBSYSTEM` constant used in every log call.

---

## Correlation IDs

Long-running workflows carry an 8-character hex identifier (`uuid4().hex[:8]`).

### Workflows that get an ID

| Workflow              | Generated in              | Propagated to                              |
|-----------------------|---------------------------|--------------------------------------------|
| Bug/feature/feedback submission | `submit_bug_report()` etc. | `_submit_with_github_and_queue` → `_try_github_submit` → `_try_queue_report` |
| Crash submission      | `submit_crash_report()`   | same chain                                 |
| Queue processing      | `ReportQueueService.process_queue()` | `QueueValidator.validate_all()` |
| Queue retry           | `_queue_submit_fn()` closure | each `submit_fn` invocation           |

### Example log sequence

```
[Support][a1b2c3d4] Submission started (bug: Login crash)
[Support][a1b2c3d4] Backend submission failed: Connection refused
[Support][a1b2c3d4] Report queued locally
```

A single correlation ID ties the entire submission → queue → retry flow.

---

## Log Level Strategy

| Level   | Usage                                                    |
|---------|----------------------------------------------------------|
| DEBUG   | Validation steps, connection establishment, ping success, queue-scanning, parsed file details |
| INFO    | Submission success, validation success, queue processing start/end, service init, report queued |
| WARNING | Temporary network failures, configuration missing, quarantine, duplicate detected, queue deferred |
| ERROR   | Unexpected exceptions, unhandled failures, auth failures, corrupted queue, insert failures |

**Rule**: Never use ERROR for expected offline conditions. A backend
being unreachable is logged at WARNING or INFO, not ERROR.

---

## Security Review

### Verified safe patterns

- **Mongo URI**: Never logged. URI-validation errors report only the
  exception class, never the URI string.
- **GitHub token**: `_load_config()` logs `bool(token)` only.
- **Supabase anon-key**: Never included in log messages. DEBUG-level
  URL logging does not expose the key.
- **Report contents**: Queue and submission logs reference file names
  and report IDs, never full payloads.
- **Stack traces**: `logger.exception()` includes tracebacks but
  only in ERROR-level logs for unexpected failures.

### Patterns eliminated

- `"Diagnostics: Exception during … (Class: %s, Message: %s)"`
  → replaced with `"[MongoDB] Submit failed (%s: %s)"`
- `"Diagnostics: connection not marked available, performing health_check()"`
  → replaced with `"[MongoDB] Health check triggered"` at DEBUG

---

## Performance Considerations

- All log calls use **%-parameterized** formatting (`logger.info("fmt %s", arg)`)
  — never f-strings (`logger.info(f"fmt {arg}")`).
- Python's logging module defers string formatting until the level
  check passes, so disabled levels pay only the cost of a single
  function call.
- Correlation ID generation (`uuid4().hex[:8]`) adds ~2 µs per
  top-level operation — negligible.

---

## Affected Components

| File                      | Log lines changed | Notes                                        |
|---------------------------|-------------------|----------------------------------------------|
| `mongo_connection.py`     | 15                | Added subsystem tag; consolidated duplicate validation-completed logs; changed intermediate steps to DEBUG |
| `mongo_report_service.py` | 10                | Removed `Diagnostics:` prefix; replaced `logger.info` with `logger.debug` for health checks; consolidated traceback logs |
| `support_service.py`      | 20                | Added correlation IDs; subsystem tag; structured queue-retry outcomes (discard/deferred/succeeded) |
| `report_queue_service.py` | 18                | Added correlation ID in `process_queue`; structured per-file outcomes; init/clear/cleanup logs tagged |
| `queue_validator.py`      | 9                 | Subsystem tag; standardised validation-start/completed/quarantine messages |
| `github_issue_service.py` | 10                | Subsystem tag; standardised submit-failed outcomes (AuthenticationFailed/Forbidden/NotFound/ConnectionError) |
| `supabase_report_service.py` | 10             | Subsystem tag; removed full URL from DEBUG logs; standardised HTTP error outcomes |

---

## Testing Summary

**File**: `tests/test_support_logging.py` — 56 tests

| Domain              | Tests | What they verify                                   |
|---------------------|-------|----------------------------------------------------|
| MongoConnection     | 8     | Log levels (INFO/DEBUG/WARNING/ERROR), subsystem tag, no URI leak, parameterised format |
| MongoReportService  | 6     | Success/failure logs, health check DEBUG, subsystem tag, index failure |
| SupportService      | 11    | Correlation IDs propagate, submission/queue/backed logs, crash path, offline handling |
| ReportQueueService  | 12    | Init/save/process logs, correlation ID, empty/Debug, concurrent skip, cleanup, permanent/transient outcomes |
| QueueValidator      | 5     | Start/completed, file validated DEBUG, quarantine, duplicate detection |
| GitHubIssueService  | 5     | Issue created, auth failure, network error, config warning, no token leak |
| SupabaseReportService | 5   | Submission success, auth failure, conflict, network error, no key leak |
| Correlation ID      | 2     | Uniqueness, format (8 hex chars)                  |
| Log level enforcement | 2   | No ERROR for offline conditions; empty queue is DEBUG |

---

## Manual Validation

### Setup
```bash
# Start the application
python -m trackora
```

### Scenario 1 — Normal submission
1. Submit a bug report.
2. Inspect `%APPDATA%\Trackora\logs\trackora.log`.
3. Confirm:
   - `[Support][<cid>] Submission started (bug: …)`
   - `[Support][<cid>] Report submitted to backend`
   - All logs share the same `[<cid>]`.

### Scenario 2 — Offline → Queue → Retry
1. Disconnect internet.
2. Submit a report.
3. Confirm:
   - `[Support][<cid>] Backend submission failed: …`
   - `[Support][<cid>] Report queued locally`
   - `[Queue][<cid>] Report saved to queue (…)`
4. Reconnect internet.
5. Trigger queue processing (restart or call `process_queue`).
6. Confirm:
   - `[Queue][<cid>] Queue processing started`
   - `[QueueValidator] Validation completed (1 valid, 0 invalid)`
   - `[Queue][<cid>] Queue retry succeeded (…)`
7. Verify the same correlation ID appears throughout.

### Scenario 3 — Crash report
1. Trigger a crash (or simulate via `submit_crash_report`).
2. Confirm:
   - `[Support][<cid>] Crash submission started (id: …)`

### Scenario 4 — Validation diagnostics
1. Open `MongoConnection` with an invalid URI.
2. Confirm:
   - `[MongoDB] Validation failed (InvalidURI: …)`
3. Open with empty URI:
   - `[MongoDB] Validation failed (ConfigurationMissing)`

### Security check
1. Grep logs for patterns: `mongodb://`, `secret`, `token`.
2. Confirm zero matches.

---

## Future Improvements

- **`contextvars` integration**: If Python 3.7+ is guaranteed,
  `contextvars` could propagate correlation IDs without explicit
  parameter threading.
- **Structured logging (JSON)**: A future phase could add a
  JSON-formatted handler for machine-parsable log ingestion while
  keeping the human-readable format as default.
- **Log sampling**: For high-frequency validation loops, a sampling
  rate could reduce DEBUG output in production.
- **Centralised correlation registry**: A lightweight context manager
  could auto-generate and track correlation IDs for arbitrary
  call chains beyond the Support Centre.
