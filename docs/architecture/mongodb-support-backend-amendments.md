# MongoDB Support Backend Spec — Amendment Completion Report

**Date:** 2026-06-20  
**Document:** `mongodb-support-backend-spec.md`  
**Status:** Amendments Applied, Pending Review  

---

## Summary

Three amendments were applied to `docs/architecture/mongodb-support-backend-spec.md`. The document grew from 855 lines to 1189 lines (334 lines added).

---

## Amendment 1 — Crash Reports Must Use ReportQueueService (Required)

### Sections Modified

| Section | Change |
|---------|--------|
| **§2 Architecture Overview** | Replaced architecture diagram to show crash reports flowing through `ReportQueueService` alongside support reports. Added AR-08 and AR-09 requiring unified queue pipeline for all 4 report types. |
| **§7 Data Flow — Crash Report Submission** | Replaced old flow where crash reports bypassed the queue. New flow shows crash report queuing via `ReportQueueService.save_report("crash", data)` on MongoDB failure, with dual persistence (local JSON + queue JSON). |
| **§7 Data Flow — Queue Processing** | Removed the note `(Crash reports: NOT in queue — see Section 9)`. Updated diagram to show all 4 types sharing the same pipeline. Added crash report cleanup of local JSON on successful queue processing. |
| **§9 Offline Behavior** | Updated table row from `"Error shown, not queued"` to `"Queued via ReportQueueService — same as support reports"`. |
| **§10 Crash Report Submission Architecture** | **Replaced entirely.** The old "Crash Report Queue Gap" section (which deferred the problem) was replaced with a full architecture section documenting: crash generation, queue insertion, retry behavior, MongoDB submission, dual persistence design, failure recovery scenarios, and queue storage format. |
| **§12 Files to Create** | Added crash type mapping tables showing what must be added to `_REPORT_TYPE_MAP` and `_GITHUB_METHOD_MAP` in both `report_queue_service.py` and `support_service.py`. |
| **§13 Files to Modify** | Added `report_queue_service.py`, `support_service.py`, `crash_dialog.py`, and `main_window.py` to the modification list. Removed `crash_dialog.py` from the "Files Unchanged" list. |
| **§17 Acceptance Criteria** | Added AC-21 (crash report queues when MongoDB unavailable) and AC-22 (queue entry reconstruction). |

### Diagrams Modified

1. **§2 Architecture Overview** — Entire diagram replaced to show unified queue
2. **§7 Crash Report Submission** — Entire flow diagram replaced
3. **§7 Queue Processing** — Entire flow diagram replaced

### Acceptance Criteria Added/Changed

| ID | Type | Description |
|----|------|-------------|
| AC-21 | Added | Crash report submission queues via `ReportQueueService` when MongoDB unavailable |
| AC-22 | Added | Crash report queue entry correctly reconstructs into `CrashReport` model |

### New Risks Discovered

| Risk | Severity | Description |
|------|----------|-------------|
| Dual persistence cleanup | Low | Crash reports have two JSON files (local + queue). Cleanup logic must handle both consistently. On successful submission, both must be deleted. On failure, both must be preserved. Race condition if app crashes between deleting one and the other. |
| Crash dialog UX complexity | Low | The crash dialog previously had a simple success/fail/dismiss flow. Adding queue logic introduces a third outcome: "queued for retry". The dialog status messaging must handle this third state clearly. |

### Conflicts Found

None. The crash report queue integration is additive — it does not conflict with any existing architecture decisions.

---

## Amendment 2 — MongoDB Connection Strategy (Recommended)

### Sections Modified

| Section | Change |
|---------|--------|
| **§4 MongoDB Connection Strategy** | **New section** (118 lines). Documents singleton architecture, lazy initialization, thread safety, driver-managed reconnection, connection pooling rationale, pool configuration, updated interface, thread safety guarantees, and connection state machine. |

### Diagrams Modified

1. **§2 Architecture Overview** — `MongoConnection` block updated to show: singleton, lazy init, thread-safe
2. **§4 Connection Strategy** — New singleton architecture diagram and state machine diagram

### Acceptance Criteria Added/Changed

| ID | Type | Description |
|----|------|-------------|
| AC-23 | Added | `MongoConnection` is a singleton — one `MongoClient` per process |
| AC-24 | Added | `MongoConnection` supports lazy initialization — no connection on construction |
| AC-25 | Added | `MongoConnection` is thread-safe under concurrent access |

### New Risks Discovered

| Risk | Severity | Description |
|------|----------|-------------|
| Singleton lifetime | Low | If the application creates a new `MongoConnection` after closing the previous one, the singleton guarantee must be enforced at the DI level, not just the class level. |
| Lazy-init race on first access | Low | If two threads call `database` simultaneously before any connection is established, both could trigger client creation. Mitigated by `pymongo.MongoClient` being safe to construct from multiple threads (driver handles this). |

### Conflicts Found

None. The connection strategy aligns with MongoDB driver best practices.

---

## Amendment 3 — MongoDB Security Rules (Recommended)

### Sections Modified

| Section | Change |
|---------|--------|
| **§14 MongoDB Security Rules** | **Entirely replaced.** Old 5-rule section expanded to 9 rules (S1–S9) with full rationale, enforcement mechanisms, TLS configuration, least-privilege user guidance, credential redaction requirements, and startup validation with redacted logging. |

### Diagrams Modified

None. This was a text-only section.

### Acceptance Criteria Added/Changed

| ID | Type | Description |
|----|------|-------------|
| AC-26 | Added | Connection string never appears in log output |
| AC-27 | Added | `health_check()` redacts credentials from log messages |
| AC-28 | Added | TLS is enabled when `MONGODB_URI` uses `mongodb+srv://` scheme |

### New Risks Discovered

| Risk | Severity | Description |
|------|----------|-------------|
| `.env` leakage | Medium | If `.env` is used for development convenience, it must be in `.gitignore`. A single accidental commit exposes credentials permanently in Git history. |
| Log-based credential leak | Low | If an exception or stack trace includes the `MONGODB_URI` value (e.g., in a connection error), it could appear in logs. Must verify no exception handler logs the raw URI. |
| Least-privilege enforcement | Medium | The application code cannot enforce the MongoDB user's permissions. The DBA/user must configure the MongoDB user correctly. Documentation must include setup instructions. |

### Conflicts Found

None.

---

## Document-Wide Changes

| Aspect | Before | After |
|--------|--------|-------|
| Total sections | 16 | 17 |
| Total lines | 855 | 1189 |
| Acceptance criteria | 20 (AC-01 through AC-20) | 28 (AC-01 through AC-28) |
| Architecture rules | 7 (AR-01 through AR-07) | 9 (AR-01 through AR-09) |
| Security rules | 5 (CR-01 through CR-05) | 9 (S1 through S9) |

### Renumbering

Inserting a new section (MongoDB Connection Strategy) as §4 required renumbering all subsequent sections. All cross-references were verified — no internal references to section numbers were found in the document.

---

## Final Recommendation

The amended specification is consistent, complete, and ready for implementation planning.

**Blocking concerns resolved:**
- Crash report queue gap: eliminated — crash reports now share the unified pipeline
- Connection management: fully specified — singleton, lazy, thread-safe
- Security: comprehensive rules with enforcement mechanisms — no hardcoded credentials

**Remaining concerns (documented in spec):**
- Dual persistence cleanup for crash reports requires careful implementation
- Singleton enforcement at DI level must be verified in code review

Approve for Step 3 (Implementation Plan).
