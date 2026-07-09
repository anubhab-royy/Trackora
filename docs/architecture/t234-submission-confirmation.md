# T-234: Submission Confirmation — Walkthrough

## Overview

This phase completes the Support Centre by providing clear, consistent,
and user-friendly submission feedback after every report submission.

**Scope**: Strictly UI/UX — the reporting pipeline (MongoDB Validation,
Retry Pipeline, Offline Queue Validation, Improved Logging) is already
complete and must NOT be redesigned.

**Constraint**: `SupportService`, `MongoReportService`, `QueueValidator`,
and `LoggingService` are not modified. The UI consumes only the result
object returned by `SupportService`.

---

## Purpose

Before T-234, submission feedback was brittle:
- Exception messages were displayed directly to users (`f"Error: {exc}"`).
- The offline queue message was the same as the generic "saved locally"
  message, making it impossible to distinguish queued from unqueued.
- Permanent failure messages leaked implementation details (MongoDB
  terminology, GitHub token instructions).
- Rapid repeated clicks could trigger multiple submissions.
- No consistent icon system for success / info / warning / error states.

After T-234, every submission outcome produces a clear, user-friendly
confirmation with an appropriate icon. Implementation details never
reach the user.

---

## Architecture

```
User clicks Submit
    │
    ▼
SupportCenterWidget emits submit_requested(page_key)
    │
    ▼
SupportCenterController._on_submit(page_key)
    │
    ├── check _submitting_pages guard set  ─── early return if duplicate
    │
    ├── self._view.set_submitting(page_key, True)   ← disables button
    │
    ├── dispatch to _submit_bug / _submit_feature / _submit_feedback
    │       │
    │       ├── validate required fields (title + description)
    │       ├── build domain model (BugReport / FeatureRequest / FeedbackReport)
    │       ├── call SupportService method
    │       ├── clear form on local_stored
    │       └── call _show_submit_result(result)
    │               │
    │               ▼
    │       Maps result to one of:
    │         success  → "Your report has been submitted successfully."
    │         info     → "No internet connection… saved locally… auto-submit"
    │         warning  → auth / config / permission / invalid report
    │         error    → "An unexpected error occurred…"
    │               │
    │               ▼
    │       SupportCenterWidget.set_submit_result(page_key, type, msg)
    │           Shows icon (✓ ℹ ⚠ ✗) + color-coded text
    │
    └── finally: _submitting_pages.discard(page_key)
                 self._view.set_submitting(page_key, False)   ← re-enables button
```

### Result flow (no service changes)

```
SupportService
    └── SupportSubmitResult
            ├── local_stored: bool
            ├── github_success: bool
            ├── github_url: str | None
            ├── github_error: str | None
            └── queued: bool

SupportCenterController._show_submit_result()
    └── reads only these fields → no MongoDB, QueueValidator, or
        retry logic inspection
```

---

## Submission Flow

### 1. User clicks Submit
- Widget emits `submit_requested(page_key)` signal.
- Controller's `_on_submit` receives the signal.

### 2. Duplicate guard
- `_submitting_pages` set tracks pages currently being submitted.
- If `page_key in _submitting_pages`, the call is silently ignored.
- This prevents rapid repeated clicks from creating multiple submissions.

### 3. Loading state
- `set_submitting(page_key, True)` disables the button and changes
  text to "Submitting…".

### 4. Form validation
- Bug: title + description required.
- Feature: title + description required.
- Feedback: subject + message required.
- On failure: warning message shown, button re-enabled.

### 5. Service call
- Domain model constructed and passed to `SupportService`.
- On `local_stored == True`: form is cleared.
- Exceptions are caught → logged at ERROR → generic "unexpected error"
  shown to user.

### 6. Result mapping (see below)
- `_show_submit_result` maps the `SupportSubmitResult` to one of four
  result types.

### 7. Final state
- `_submitting_pages` cleared.
- Button re-enabled.

---

## Result Mapping

Every `SupportSubmitResult` maps to exactly one user-facing confirmation.
No ambiguous states, no silent failures.

| Condition                                           | Result Type  | Message                                                              |
|-----------------------------------------------------|--------------|----------------------------------------------------------------------|
| `local_stored == False`                             | `error`      | An unexpected error occurred while submitting the report.            |
| `github_success == True`                            | `success`    | Your report has been submitted successfully.                         |
| `queued == True`                                    | `info`       | No internet connection. … saved locally … auto-submit when reconnects. |
| `github_error` contains "auth"                      | `warning`    | Trackora couldn't authenticate with the support service.             |
| `github_error` contains "config" / "not configured" | `warning`    | … support service configuration is invalid.                          |
| `github_error` contains "permission" / "forbidden" / "denied" | `warning` | The report couldn't be submitted because access was denied.      |
| `github_error` contains "invalid" / "unsupported"   | `warning`    | The report contains invalid information … review your input.         |
| Any other `github_error`                            | `error`      | An unexpected error occurred while submitting the report.            |

### What is NEVER shown to the user
- MongoDB connection strings or status values
- Exception class names or tracebacks
- GitHub token instructions
- Queue file paths
- Validation status enums

---

## UI Behaviour

### Icons

| Result Type | Icon | Color    |
|-------------|------|----------|
| success     | ✓    | `#a6e3a1` (green)  |
| info        | ℹ    | `#fab387` (orange)  |
| warning     | ⚠    | `#f9e2af` (yellow)  |
| error       | ✗    | `#f38ba8` (red)     |

Icons are Unicode characters rendered in the same QLabel as the message.
No image assets or icon fonts are required.

### Button states

| State          | Button enabled | Button text    |
|----------------|----------------|----------------|
| Idle           | Yes            | Submit         |
| Submitting     | No             | Submitting…    |
| After result   | Yes            | Submit         |

### Duplicate prevention

Two layers:
1. **Widget level**: `btn.setEnabled(False)` — Qt suppresses signals from
   disabled buttons, so `clicked` never fires.
2. **Controller level**: `_submitting_pages` set — if a signal somehow
   fires before the state is updated (e.g. programmatic invocation),
   the controller ignores it.

### Accessibility

- All form fields are native Qt widgets with built-in keyboard navigation.
- Submit button is focusable and activatable via Enter/Space.
- Escape key is handled by Qt's default dialog behaviour (not overridden).
- Status label has `setWordWrap(True)` for long messages.

---

## Affected Components

| File                     | Change summary                                                      |
|--------------------------|---------------------------------------------------------------------|
| `support_center_controller.py` | Rewrote `_show_submit_result` with 8-state mapping; added `_submitting_pages` guard; exceptions → generic message; removed `QMessageBox` import |
| `support_center_widget.py` | Changed `set_submit_result(success, message)` to `set_submit_result(type, message)`; added icon + color per type; `setWordWrap(True)` |

Not modified:
- `SupportService` — unchanged
- `MongoReportService` — unchanged
- `QueueValidator` — unchanged
- `LoggingService` — unchanged
- Any other service or model

---

## Testing Summary

**File**: `tests/test_support_center_controller.py` — 42 tests

| Domain                | Tests | What they verify                                     |
|-----------------------|-------|------------------------------------------------------|
| Initialisation        | 3     | Controller created, announcements loaded, view updated |
| Navigation            | 4     | `navigate_to`, page change clears result, refresh works |
| Submission flow       | 7     | Bug/feature/feedback submit, validation, dispatch, loading state |
| Result mapping        | 16    | Every SupportSubmitResult outcome → correct type + message |
| Exception handling    | 3     | Generic error shown, details in logs, button re-enabled |
| Duplicate prevention  | 5     | Duplicate ignored, flag cleared after success/exception, button states |
| Confirmation content  | 2     | No MongoDB terminology, no exception details in UI   |
| Backend integration   | 1     | End-to-end flow with mocked backend                  |
| Legacy                | 2     | MongoConnection database name tests preserved        |

### Key assertions verified

- `"submitted successfully"` for success
- `"No internet connection"` + `"saved locally"` for queued
- `"authenticate"` for auth errors (never `"token"`)
- `"configuration is invalid"` for config errors (never `"GitHub"`)
- `"access was denied"` for permission errors (never `"forbidden"`)
- `"invalid information"` for validation errors
- `"unexpected error"` for unknown / local-storage failures
- `"MongoDB"` never appears in any user-facing message
- Exception details logged but never shown in UI

---

## Manual Validation

### Setup
```bash
python -m trackora
```
Navigate to **Support Center** via the sidebar.

### Test 1 — Success
1. Fill all fields on the **Report Bug** page.
2. Click **Submit**.
3. Expected: ✓ "Your report has been submitted successfully." in green.

### Test 2 — Offline queue
1. Disconnect the internet.
2. Submit a bug report.
3. Expected: ℹ "No internet connection. Your report has been saved
   locally and will be submitted automatically when Trackora reconnects."
   in orange.
4. Reconnect internet and restart the app.
5. Expected: queued report is processed; no error shown.

### Test 3 — Authentication failure
1. Configure invalid MongoDB credentials.
2. Submit a bug report.
3. Expected: ⚠ "Trackora couldn't authenticate with the support service."
   in yellow.
4. Verify no credential details appear in the message.

### Test 4 — Configuration missing
1. Remove MongoDB configuration.
2. Submit a bug report.
3. Expected: ⚠ "Trackora couldn't submit the report because the support
   service configuration is invalid." in yellow.

### Test 5 — Spam-click
1. Rapidly click **Submit** 10+ times.
2. Expected: only one submission occurs, one confirmation shown.

### Test 6 — Keyboard accessibility
1. Tab to **Submit** button.
2. Press Enter.
3. Expected: submission starts as if clicked.

---

## Future Improvements

- **Timeout-aware confirmation**: Show a spinner if submission takes
  longer than N seconds (currently the button just says "Submitting…").
- **Dismissible result banners**: Allow users to dismiss the confirmation
  with a close button rather than navigating away and back.
- **Sound feedback**: Optional audio cues for success / error states.
- **Multi-report bulk operations**: If future work adds batch submission,
  the same result-mapping framework extends naturally.
