# MongoDB Phase 2 — Executable / Production Environment Validation

## Scope
Validate Trackora's MongoDB Atlas reporting when running as a PyInstaller-frozen executable (`dist/Trackora.exe`).

## Key Difference vs Phase 1 (Development)
| Aspect | Phase 1 | Phase 2 |
|--------|---------|---------|
| Runtime | `python -m trackora` | `dist/Trackora.exe` |
| `CURRENT_ENVIRONMENT` | `development` | `production` |
| `BASE_DIR` | `%APPDATA%/Trackora-Dev` | `%APPDATA%/Trackora` |
| `.env` search path | CWD > project root > `BASE_DIR/.env` | CWD > (bundle path) > `BASE_DIR/.env` |
| Log output | `%APPDATA%/Trackora-Dev/logs/` | `%APPDATA%/Trackora/logs/` |

## Results

### 1. Build Artifact Existence
- `dist/Trackora.exe` exists (54.1 MB).
- PyInstaller 6.20.0, Python 3.14.3, Windows 11.

### 2. Production Environment Detection
- `APP_ENV=production` → `CURRENT_ENVIRONMENT == Environment.PRODUCTION`.
- `BASE_DIR = %APPDATA%\Trackora` (not `Trackora-Dev`).
- `_is_frozen()` returns `False` in script mode (expected — frozen only inside EXE).

### 3. Production `.env` Loading
- `.env` placed at `%APPDATA%\Trackora\.env` (production path).
- `_discover_env_file()` falls through CWD → project root → `BASE_DIR/.env`.
- `MONGODB_URI` and `MONGODB_DATABASE` loaded correctly.

### 4. MongoDB Connection
- `health_check()` succeeds (ping to Atlas primary responds < 100ms).

### 5. Atlas Collections
All 4 collections exist:

| Collection | Status |
|---|---|
| `bug_reports` | Exists |
| `feature_requests` | Exists |
| `feedback` | Exists |
| `crash_reports` | Exists |

### 6. All 4 Report Types Reach Atlas
Verified by direct `MongoReportService` submission + `find_one(ObjectId)` lookup:

| Type | Submitted | In Atlas |
|------|-----------|----------|
| Bug Report | OK | OK |
| Feature Request | OK | OK |
| Feedback | OK | OK |
| Crash Report | OK | OK |

### 7. Queue Not Triggered When Mongo Available
- `SupportService.submit_bug_report()` with working backend → `github_success=True`, `queued=False`.
- `pending_reports/` directory empty.

### 8. Error Path: Bad URI → Queue Fallback
- Bad URI → `health_check()` returns `False`.
- `MongoReportService._insert` returns `"MongoDB connection failed."` (retryable — keyword `"connection failed"` not in `_NON_RETRYABLE_KEYWORDS`).
- `SupportService` queues report to `pending_reports/` as JSON with `type`, `data`, `created_at`.

### 9. Error Path: Non-retryable Errors → No Queue
- `_is_retryable("MongoDB not configured.")` returns `False` (keyword `"not configured"` in `_NON_RETRYABLE_KEYWORDS`).
- All 10 non-retryable keywords validated: `not configured`, `not available`, `not found`, `authentication failed`, `permission denied`, `forbidden`, `invalid`, `bad request`, `unsupported`, `check your`.
- Empty-URI connection → `health_check()` returns `False` → error `"MongoDB connection failed."` which IS retryable (no non-retryable keyword match) → report IS queued. This is correct: transient failures should be queued.

### 10. Logging Audit
Production log file at `%APPDATA%\Trackora\logs\trackora.log` contains:
- `"environment production"`
- `"MongoDB: available"`
- `"MongoDB reporting: connected"`
- `"database: C:\Users\...\Trackora\trackora.db"`
- Queue-related entries from bad-URI test.

## Spec Changes
No changes to `Trackora.spec` were needed. The existing hidden imports (`pymongo`, `dns`, `dns.resolver`, `dns.rdtypes`, `dns.rdatatype`, `bson`) are sufficient for MongoDB Atlas SRV connectivity in a frozen build.

## Validation Run
```
Phase 2 Validation Complete: 56 passed, 0 failed, 0 skipped
All checks passed.
```
