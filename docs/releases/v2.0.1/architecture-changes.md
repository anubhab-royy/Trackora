# Architecture Changes

## Purpose

Document every architectural modification introduced in Trackora v2.0.1.

---

## Expected Changes

### Startup

Introduce silent startup workflow while preserving existing startup architecture.

---

### Update Center

Expand Update Service to support:

- Release detection
- Update notifications
- Installer launching

No changes to the existing release infrastructure.

---

### Health Monitoring

Introduce Health Monitor Service responsible for observing:

- Tracking Service
- SQLite
- MongoDB
- Background Workers
- Update Service

Health Monitor must remain independent from business logic.

---

### Backup System

Introduce Backup Service.

Responsibilities:

- Manual backups
- Scheduled backups
- Restore
- Validation

The backup service must never access UI components directly.

---

### Support Centre

Improve MongoDB reliability.

No changes to service contracts.

SupportService remains dependent on AbstractReportService.

---

## Architecture Constraints

The following rules remain mandatory:

- UI never accesses SQLite directly.
- UI never accesses MongoDB directly.
- Services communicate through contracts.
- SQLite remains the source of truth.
- MongoDB remains support infrastructure only.

---

## Expected Outcome

No architectural regressions.

No layer violations.

No breaking API changes.
