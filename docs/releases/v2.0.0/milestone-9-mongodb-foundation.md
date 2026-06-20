# Milestone 9 — MongoDB Foundation

**Version:** 2.0.0-draft  
**Status:** Planning / Phase 0  
**Document Type:** Milestone Specification  
**Owner:** Architecture Team  

---

## Purpose

Replace the Supabase REST API reporting backend with a MongoDB-backed reporting service. Create a contract-compliant `MongoReportService` that implements the existing `AbstractReportService` interface. Establish MongoDB Schema V1 for three collections: `reports`, `feedback`, `feature_requests`. Every document must carry a `schema_version` field to future-proof against schema evolution.

---

## Scope

### In Scope

- `MongoReportService` — concrete implementation of `AbstractReportService`
- MongoDB Schema V1 — three collections: `reports`, `feedback`, `feature_requests`
- `schema_version` field on every document
- MongoDB connection manager (configuration, connection lifecycle, error handling)
- Environment-aware MongoDB configuration (production/development databases)
- Offline queue compatibility (existing `ReportQueueService` must remain functional)
- Unit and integration tests
- Architecture enforcement tests

### Out of Scope

- MongoDB storage of game sessions, tracking data, or settings (SQLite remains system of record)
- MongoDB Schema V2+ (deferred to v2.1+)
- Migration of existing Supabase data to MongoDB
- Removal of Supabase code (may coexist; removal planned for v2.1 or v3.0)
- MongoDB Atlas / cluster configuration management
- Real-time change streams or subscriptions
- Index optimization beyond basic required indexes

---

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | MongoReportService shall implement all methods of AbstractReportService | Critical |
| FR-02 | MongoReportService shall submit bug reports to the `reports` collection | Critical |
| FR-03 | MongoReportService shall submit feature requests to the `feature_requests` collection | Critical |
| FR-04 | MongoReportService shall submit feedback to the `feedback` collection | Critical |
| FR-05 | MongoReportService shall submit crash reports to the `reports` collection with type `crash` | Critical |
| FR-06 | Every MongoDB document shall include a `schema_version` field set to `1` | Critical |
| FR-07 | Every MongoDB document shall include `app_version`, `os`, and `submitted_at` fields | Critical |
| FR-08 | MongoDB connection configuration shall be environment-aware (production/development databases) | High |
| FR-09 | Failure to connect to MongoDB shall not crash the application | Critical |
| FR-10 | SupportService must accept MongoReportService via DI (same as SupabaseReportService) | Critical |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | MongoDB submission timeout shall not exceed 15 seconds | <15s |
| NFR-02 | Unconfigured MongoReportService shall report as configured=false without error | Strict |
| NFR-03 | MongoReportService must not introduce UI or SQL imports | Strict |
| NFR-04 | MongoDB driver must be compatible with PyInstaller frozen builds | Verified |
| NFR-05 | All existing report submission flows (GitHub, Supabase) must continue working | Strict |

---

## Architecture

### MongoDB Schema V1

#### `reports` Collection

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "type": "bug | crash",
  "title": "string",
  "description": "string",
  "app_version": "string",
  "os": "string",
  "source": "support_center | crash_detector",
  "steps_to_reproduce": "string (optional)",
  "expected_behavior": "string (optional)",
  "actual_behavior": "string (optional)",
  "severity": "low | medium | high | critical (optional)",
  "status": "new",
  "submitted_at": "ISODate"
}
```

#### `feature_requests` Collection

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "title": "string",
  "description": "string",
  "use_case": "string",
  "priority": "low | medium | high",
  "app_version": "string",
  "os": "string",
  "source": "support_center",
  "status": "new",
  "submitted_at": "ISODate"
}
```

#### `feedback` Collection

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "subject": "string",
  "message": "string",
  "category": "string",
  "contact_ok": true,
  "app_version": "string",
  "os": "string",
  "submitted_at": "ISODate"
}
```

### Component Diagram

```
SupportService
     │
     ├── AbstractReportService (interface)
     │       │
     │       ├── GitHubIssueService    (unchanged)
     │       ├── SupabaseReportService (unchanged, deprecation planned)
     │       └── MongoReportService    (NEW)
     │               │
     │               ▼
     │       MongoDBConnectionManager
     │               │
     │               ▼
     │           MongoDB Atlas / Local
     │
     └── ReportQueueService (unchanged)
```

### MongoReportService

**File:** `services/support/mongo_report_service.py`

```
MongoReportService(AbstractReportService):
  - __init__(connection_string, db_name, timeout)
  - is_configured -> bool
  - submit_bug(report: BugReport) -> SubmitResult
  - submit_feature(request: FeatureRequest) -> SubmitResult
  - submit_feedback(feedback: FeedbackReport) -> SubmitResult
  - submit_report(type, title, body) -> SubmitResult
  - submit_crash(title, body) -> SubmitResult
```

### MongoDBConnectionManager

**File:** `trackora/core/mongodb_connection.py`

```
MongoDBConnectionManager:
  - __init__(config: MongoDBConfig)
  - connect() -> MongoClient
  - disconnect() -> None
  - is_connected() -> bool
  - get_database() -> Database
```

### Configuration

**File:** `trackora/core/mongodb_config.py`

```
MongoDBConfig:
  - connection_string: str
  - db_name: str  (environment-aware: trackora_prod / trackora_dev)
  - timeout_ms: int
  - is_valid() -> bool
```

---

## Deliverables

| ID | Deliverable | File |
|----|-------------|------|
| D01 | MongoDB connection manager | `trackora/core/mongodb_connection.py` |
| D02 | MongoDB configuration | `trackora/core/mongodb_config.py` |
| D03 | MongoReportService | `services/support/mongo_report_service.py` |
| D04 | MongoDB Schema V1 models | `models/support/mongodb_schemas.py` |
| D05 | Unit tests | `tests/test_mongo_report_service.py` |
| D06 | Schema tests | `tests/test_mongodb_schema.py` |
| D07 | Integration tests | `tests/test_mongo_integration.py` |
| D08 | Architecture tests | `tests/architecture/test_mongo_config_isolation.py` |
| D09 | Environment-aware config wiring | Update `trackora/core/paths.py` if needed |
| D10 | DI wiring update | Update `trackora/__main__.py` and `SupportService` |

---

## Risks

See also AR-02, AR-06 in `v2.0.0-overview.md`.

| Risk | Impact | Mitigation |
|------|--------|------------|
| PyMongo / Motor dependency breaks PyInstaller build | High | Test PyInstaller build early in Phase 2; document hidden imports |
| MongoDB connection blocks application startup | Medium | Non-blocking connection; timeout < 5s; degrade gracefully on failure |
| MongoDB Atlas connection string hardcoded in source | Critical | Connection string from environment only; never in source; gitignore `.env` |
| Schema version forgotten in future documents | Medium | Schema enforcement layer in MongoDBConnectionManager; test validates every write |
| Existing Supabase users lose data on switch | Medium | MongoReportService is additive; SupabaseReportService remains functional; removal deferred |

---

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-01 | MongoReportService.submit_bug() creates a valid document in `reports` collection | Integration test |
| AC-02 | MongoReportService.submit_feature() creates a valid document in `feature_requests` collection | Integration test |
| AC-03 | MongoReportService.submit_feedback() creates a valid document in `feedback` collection | Integration test |
| AC-04 | MongoReportService.submit_crash() creates a document with `type: "crash"` in `reports` | Integration test |
| AC-05 | Every created document contains `schema_version: 1` | Integration test |
| AC-06 | Every created document contains `app_version`, `os`, `submitted_at` | Integration test |
| AC-07 | SupportService accepts MongoReportService via DI and works correctly | Integration test |
| AC-08 | Failed MongoDB connection returns `SubmitResult(success=False)` without raising | Unit test |
| AC-09 | Unconfigured MongoReportService reports `is_configured == False` | Unit test |
| AC-10 | All existing report tests pass (GitHubIssueService, SupabaseReportService, ReportQueueService) | Regression test |
| AC-11 | Architecture enforcement passes (MongoDB config not in UI) | Architecture test |
| AC-12 | PyInstaller build succeeds with MongoDB driver included | Build verification |

---

## Dependencies

### Internal Dependencies

| Dependency | Notes |
|------------|-------|
| `services/support/reporting_interface.py` | MongoReportService implements AbstractReportService — no contract changes needed |
| `services/support/support_service.py` | Must accept MongoReportService via existing DI pattern |
| `trackora/core/paths.py` | No changes required unless MongoDB config file path needed |
| `trackora/__main__.py` | Wiring update for new service |

### External Dependencies

| Dependency | Version | Justification | Approval Status |
|------------|---------|---------------|-----------------|
| `pymongo` | >=4.10 | MongoDB driver (sync) | **Pending** |
| `dnspython` | >=2.7 | SRV connection string support (Atlas) | **Pending** |

**Decision required:** Approval to add `pymongo` and `dnspython` to `requirements.txt`.

---

## Integration Points

| Point | Details |
|-------|---------|
| `trackora/__main__.py` | Instantiate `MongoDBConnectionManager` and `MongoReportService` if configured; pass to `SupportService` |
| `services/support/support_service.py` | Accept `MongoReportService` alongside existing backends; `_try_github_submit` logic already backend-agnostic |
| `models/support/` | No changes to existing domain models; MongoDB schema documents are built from same models |
| `.env` / environment | `MONGODB_CONNECTION_STRING` and `MONGODB_DB_NAME` environment variables |
| `ReportQueueService` | Already backend-agnostic; queued reports will submit via whatever backend is configured |

---

## Future Compatibility

### v2.1+

- MongoDB Schema V2 may add indexes, TTL, additional metadata fields
- SupabaseReportService deprecation and removal

### v3.0+

- MongoDB may store game sessions and statistics for cloud sync (opt-in)
- SchemaVersionManager extended to MongoDB collections
- MigrationManager extended with MongoDB migration support

### v4.0+

- Multi-backend support: SQLite (local SOR) + MongoDB (cloud replica)
- Real-time sync via MongoDB change streams

---

## References

- `services/support/reporting_interface.py` — AbstractReportService contract
- `services/support/supabase_report_service.py` — Reference implementation (follows same patterns)
- `services/support/support_service.py` — DI wiring for report backends
- `v2.0.0-overview.md` — Release overview, risk register, testing requirements
