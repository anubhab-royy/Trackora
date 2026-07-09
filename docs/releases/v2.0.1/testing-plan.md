# Testing Plan

## Objective

Validate every feature introduced in Trackora v2.0.1.

---

## Functional Testing

Silent Startup

- Startup after login
- Manual launch
- Tray behavior
- Dashboard behavior

Update Center

- Version detection
- Notification
- Release notes
- Installer launch

Game Management

- Delete game
- Delete statistics
- Delete cache
- Duplicate detection

Support Centre

- Bug report
- Feature request
- Feedback
- Offline queue
- Retry

Crash Recovery

- Unexpected termination
- Session recovery
- State restoration

Health Monitor

- SQLite unavailable
- MongoDB unavailable
- Tracking failure
- Worker failure

Backup

- Manual backup
- Scheduled backup
- Restore
- Validation

---

## Regression Testing

Tracking

Statistics

Discovery

Installer

Upgrade

Runtime

MongoDB

Packaging

---

## Performance Testing

Memory usage

CPU usage

Startup time

Background monitoring overhead

---

## Acceptance Criteria

- All tests pass.
- No regression introduced.
- Performance remains acceptable.
- Upgrade path validated.

---

## Executed Tests Status (Milestone Audit)

As of **July 6, 2026**:
- **Background Update Checker Thread**: 17 unit tests verifying instantiation, concurrency, execution, and error handling.
- **Auto-check Update Settings Controls**: 18 integration tests verifying toggle state propagation and settings persistence.
- **Version Consistency Validator**: 6 tests verifying dynamic PyInstaller spec, Inno Setup `#include` outputs, and idempotency of script.
- **Update Dialog Link Routing**: 9 tests asserting direct browser download links and correct QUrl packaging.
- **Manual Bypass Cooldown checks**: 3 regression tests verifying rate-limiting logic.

**Overall Test Results**: `124 / 124 passed successfully` (0 failures).

