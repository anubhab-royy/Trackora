# MongoDB Implementation Roadmap

**Version:** 2.0.0-draft  
**Status:** Architecture Design  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  
**Phase:** 11 — MongoDB Foundation

---

## Table of Contents

1. [Critical Architecture Rule — Support Isolation](#1-critical-architecture-rule--support-isolation)
2. [Phase A — Support Backend](#2-phase-a--support-backend)
3. [Phase B — Parallel Analytics Storage](#3-phase-b--parallel-analytics-storage)
4. [Phase C — Analytics Synchronization](#4-phase-c--analytics-synchronization)
5. [Phase D — Trackora Insights](#5-phase-d--trackora-insights)
6. [Phase E — Advanced Intelligence Features](#6-phase-e--advanced-intelligence-features)
7. [Dependency Matrix](#7-dependency-matrix)
8. [Upgrade Safety Rules](#8-upgrade-safety-rules)
9. [Data Preservation Rules](#9-data-preservation-rules)
10. [Version Compatibility Matrix](#10-version-compatibility-matrix)
11. [Disaster Recovery Roadmap](#11-disaster-recovery-roadmap)
12. [Long-Term Governance](#12-long-term-governance)
13. [Recommended MongoDB Adoption Timeline](#13-recommended-mongodb-adoption-timeline)

---

## 1. Critical Architecture Rule — Support Isolation

### Permanent Separation

Support collections and analytics/insights collections are **permanently isolated**. This separation is non-negotiable and must survive every future version.

| Backend | Collections | Purpose | Isolated From |
|---------|-------------|---------|---------------|
| **Support** | `bug_reports`, `feature_requests`, `feedback`, `crash_reports` | User support, bug tracking, crash reporting | Everything |
| **Analytics** | `analytics_games`, `analytics_daily`, `analytics_weekly`, `analytics_monthly`, `analytics_trends`, `analytics_sessions` | Derived playtime aggregates | Support data |
| **Insights** | `insights_habits`, `insights_recommendations` | Interpreted observations, recommendations | Support data |

### Forbidden Data Flows

```
Support Data (bug_reports, feature_requests, feedback, crash_reports)
    │
    ├──→ Recommendation Engine     ✗ FORBIDDEN
    ├──→ Habit Metrics             ✗ FORBIDDEN
    ├──→ Wellbeing Metrics         ✗ FORBIDDEN
    ├──→ Trend Analysis            ✗ FORBIDDEN
    └──→ Any analytics input       ✗ FORBIDDEN
```

### Rationale

| Reason | Explanation |
|--------|-------------|
| Privacy | Support data may contain personal information not intended for analytics |
| Data quality | Support data is user-curated, not behaviourally measured |
| Semantic mismatch | A bug report contains no gaming behaviour data |
| Architectural clarity | Mixing support and analytics creates unmaintainable coupling |
| Regulatory | User-identifiable support data must not flow into analytics pipelines |

### Enforcement

- No MongoDB query in analytics or insights code may reference support collections
- No aggregation pipeline may join analytics with support collections
- No insight computation may read from support collections
- Architecture tests must verify this separation

---

## 2. Phase A — Support Backend

**Status:** Planning complete (existing milestone-9 specification)  
**Target Version:** v2.0.x  
**Dependencies:** MongoDB driver approval (`pymongo`, `dnspython`)

### Goal

Replace Supabase REST API as the primary support storage backend with local MongoDB. The existing Supabase backend may coexist during a deprecation window, but MongoDB becomes the default.

### Scope

| Collection | Purpose | Data Source |
|-----------|---------|-------------|
| `bug_reports` | User-submitted bug reports | User input via support center UI |
| `feature_requests` | User-submitted feature requests | User input via support center UI |
| `feedback` | User feedback messages | User input via support center UI |
| `crash_reports` | Automatic crash diagnostics | Crash detection service |

### Requirements

| Area | Requirement |
|------|-------------|
| **Purpose** | Replace Supabase as the default support storage backend; offline-capable local storage |
| **Data ownership** | `SupportService` writes, `SupportCenterController` reads, `ReportQueueService` queues on failure |
| **Retention** | Indefinite (support data is user-generated and should persist) |
| **Indexes** | By `type` + `status` for queue processing; by `submitted_at` for ordering; by `app_version` for triage |
| **Versioning** | `schema_version` on every document (currently v1); no `analytics_generation_version` (not analytics data) |
| **Backup strategy** | MongoDB backup (or collection export) included in BackupManager scope |
| **Migration from Supabase** | One-time export: Supabase → JSON → MongoDB import; Supabase data preserved during deprecation window |

### Isolation Requirements

Phase A collections are permanently isolated from Phases B–E:
- No analytics aggregation may read from support collections
- No insight may use support data as input
- No recommendation may reference support data

### Exit Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| A1 | All 4 support collections created with schema_version field | Document inspection |
| A2 | `MongoReportService` implements `AbstractReportService` contract | Interface compliance test |
| A3 | Unconfigured MongoDB falls back to local queue only | Unit test |
| A4 | Existing Supabase users continue working during migration | Regression test |
| A5 | Support data survives application restart and upgrade | Integration test |
| A6 | Architecture tests verify support collections are isolated from analytics | Architecture test |

### Success Metrics

| Metric | Target |
|--------|--------|
| Report submission success rate | ≥99.5% (matching or exceeding Supabase) |
| Offline queue fallback triggers correctly | 100% of network failures |
| Migration from Supabase data loss | 0% |
| Existing test pass rate | 100% |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| PyMongo dependency breaks PyInstaller build | High | Test build early; document hidden imports in Trackora.spec |
| MongoDB connection blocks startup | Medium | Non-blocking connection with timeout; graceful degradation |
| Connection string exposed in source | Critical | Environment variable only; never in source; `.env` in `.gitignore` |
| Existing Supabase users lose data | Medium | Additive implementation; Supabase removal deferred to v2.1+ |

---

## 3. Phase B — Parallel Analytics Storage

**Status:** Architecture defined (Phase 11)  
**Target Version:** v2.x  
**Dependencies:** Phase A complete, MongoDB driver stable

### Goal

Introduce `analytics_*` collections that store pre-computed aggregates derived from SQLite. Analytics remain optional — if MongoDB is unavailable, the application falls back to live SQLite computation.

### Collections Introduced

| Collection | Purpose | Rebuildable |
|-----------|---------|-------------|
| `analytics_games` | Per-game lifetime stats and trends | YES — from SQLite |
| `analytics_daily` | Daily playtime aggregates | YES — from SQLite |
| `analytics_weekly` | Weekly summaries with daily breakdown | YES — from SQLite |
| `analytics_monthly` | Monthly summaries with daily breakdown | YES — from SQLite |
| `analytics_trends` | Computed trend snapshots | YES — from SQLite or analytics |
| `analytics_sessions` | Session distributions and percentiles | YES — from SQLite |

### Requirements

| Area | Requirement |
|------|-------------|
| **Synchronization model** | Write-only from SQLite to MongoDB; no bidirectional sync; no dual-write transactions |
| **Rebuild model** | Regeneration from SQLite is the default; full collection regeneration on schema version change |
| **Versioning model** | `schema_version` + `analytics_generation_version` on every document; tracked in `system_schema` |
| **Rollback strategy** | Deploy previous app version; run analytics pipeline; regeneration produces compatible documents |
| **Optionality** | Application starts and operates normally without MongoDB; falls back to SQLite live queries |

### Exit Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| B1 | All 6 analytics collections created with dual versioning | Document inspection |
| B2 | Analytics aggregation service reads from SQLite, writes to MongoDB | Integration test |
| B3 | Application starts without MongoDB and falls back to SQLite | Integration test |
| B4 | Regeneration from SQLite produces correct aggregate data | Comparison test |
| B5 | Schema upgrade increments `schema_version` correctly | Unit test |
| B6 | Generation upgrade increments `analytics_generation_version` correctly | Unit test |
| B7 | `system_schema` tracks all 6 analytics collection versions | Integration test |
| B8 | `system_metadata` tracks `analytics_generation_version` | Integration test |
| B9 | `system_jobs` records every aggregation run | Integration test |

### Success Metrics

| Metric | Target |
|--------|--------|
| Analytics query latency (MongoDB vs SQLite) | ≥50% reduction for dashboard queries |
| Fallback to SQLite on MongoDB unavailable | 100% transparent to user |
| Storage growth per month | ≤1 MB (all analytics collections combined) |
| Regeneration time for 10k sessions | ≤5 seconds |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Analytics diverge from SQLite due to missed updates | Medium | Incremental updates by default; full regeneration on reconciliation |
| Storage growth higher than expected | Low | Analytics documents are small and bounded by time |
| Regeneration is slow for very large datasets | Medium | Incremental updates minimize regeneration scope |
| User confuses MongoDB analytics for source of truth | Low | Documentation and UI labeling: "derived from SQLite" |

---

## 4. Phase C — Analytics Synchronization

**Status:** Architecture defined (Phase 11)  
**Target Version:** v2.x (after Phase B)  
**Dependencies:** Phase B complete

### Goal

Formalize the SQLite → Analytics Pipeline → MongoDB data flow with explicit job management, incremental updates, failure handling, and recovery procedures.

### Scope

| Component | Role |
|-----------|------|
| SQLite | Data source — provides raw session data |
| Analytics Aggregation Service | Orchestrator — reads SQLite, writes MongoDB |
| `system_metadata` | Checkpoint — tracks last processed session, generation version |
| `system_jobs` | Audit — records every aggregation run with status and duration |
| `analytics_*` collections | Target — receive computed aggregates |

### Requirements

| Area | Requirement |
|------|-------------|
| **Aggregation jobs** | Each aggregation run records to `system_jobs` with job_type, status, duration, sessions_processed, error |
| **Incremental updates** | After session end, only update affected `analytics_daily` doc + `analytics_games` + `analytics_sessions` for that game |
| **Full regeneration** | On schema version change, generation version change, or manual trigger; regenerate entire collection from SQLite |
| **Failure handling** | Failed jobs recorded in `system_jobs` with error message; configurable retry count |
| **Version upgrades** | On `schema_version` increment: regeneration. On `analytics_generation_version` increment: regeneration. On both: regeneration. |
| **Recovery procedures** | MongoDB unavailable → SQLite fallback. MongoDB restored → incremental catch-up from `system_metadata` checkpoint. |

### Exit Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| C1 | Incremental update after single session end updates correct collections | Integration test |
| C2 | Full regeneration produces identical analytics to incremental updates | Comparison integration test |
| C3 | `system_jobs` contains correct records after aggregation | Integration test |
| C4 | MongoDB outage and recovery does not lose or duplicate analytics | Chaos test |
| C5 | Schema version upgrade triggers full regeneration | Integration test |
| C6 | Generation version upgrade triggers full regeneration | Integration test |
| C7 | Fallback to SQLite during MongoDB outage is transparent | Integration test |

### Success Metrics

| Metric | Target |
|--------|--------|
| Incremental update time per session end | ≤100ms |
| Full regeneration time (10k sessions, all collections) | ≤10 seconds |
| Job record accuracy | 100% |
| Recovery after MongoDB outage — data loss | 0% |
| Recovery after MongoDB outage — duplicate analytics | 0% |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Incremental update misses session if crash occurs before write | Low | Next startup runs partial regeneration from checkpoint |
| Full regeneration during active gameplay causes temporary stale dashboard | Low | Regeneration runs in background; dashboard uses cached data |
| `system_metadata` checkpoint gets out of sync | Low | On next successful job, checkpoint is corrected |

---

## 5. Phase D — Trackora Insights

**Status:** Architecture defined (Phase 5)  
**Target Version:** v3.0  
**Dependencies:** Phase C complete, analytics pipeline stable

### Goal

Activate `insights_habits` and `insights_recommendations` collections with computed insight and recommendation data. Turn raw analytics into interpreted, explainable observations.

### Requirements

| Area | Requirement |
|------|-------------|
| **Dependencies** | All `analytics_*` collections must be populated; `system_metadata` must track generation version |
| **Inputs** | `analytics_daily`, `analytics_weekly`, `analytics_monthly`, `analytics_sessions`, `analytics_games`, `analytics_trends` |
| **Outputs** | `insights_habits` documents with `insight_type` categorization; `insights_recommendations` documents |
| **Versioning** | Both collections carry `schema_version` and `analytics_generation_version` |
| **Recovery** | Deleted insights: regenerate from analytics_*. Deleted analytics: regenerate from SQLite first. |
| **Deprecation policy** | Insight types follow 3-release deprecation: produce → warn → remove |

### Insight Explainability Mandate

Every insight document must contain:

| Field | Description | Mandatory |
|-------|-------------|-----------|
| `reason_codes` | Machine-readable list of factors that produced this insight | Yes |
| `source_metrics` | The specific numeric values that drove the insight | Yes |
| `narrative` | Human-readable explanation of derivation | Yes |
| `confidence` | 0.0–1.0 score | Yes |
| `source_collections` | Which analytics collections were used | Yes |
| `analytics_generation_version` | Which generation of computation produced this | Yes |

No black-box scores are permitted. Every score must be explainable in terms of its inputs.

### Exit Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| D1 | `insights_habits` contains documents for ≥6 of 8 insight categories | Integration test |
| D2 | Every insight document includes complete explainability block | Document inspection |
| D3 | `insights_recommendations` contains active recommendations | Integration test |
| D4 | Recommendations expire correctly based on `valid_until` / `expiry_strategy` | Unit test |
| D5 | Insight regeneration from analytics produces same output (same generation) | Comparison test |
| D6 | Recommendation regeneration may differ (algorithm improvements expected) | Documentation |
| D7 | Insight deprecation follows 3-release policy | Process verification |
| D8 | No insight depends on support collections | Architecture test |
| D9 | Wellbeing metrics use banned-terminology-free language | Automated scan |

### Success Metrics

| Metric | Target |
|--------|--------|
| Insight generation time per category | ≤2 seconds |
| Recommendation relevance (user rating, if implemented) | ≥70% positive |
| Explainability completeness | 100% of documents |
| Banned terminology violations | 0 |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Insight quality poor due to insufficient data | Medium | Confidence score reflects data volume; minimum data thresholds |
| Wellbeing metrics misinterpreted | Critical | Banned terminology list; descriptive-only labels; no thresholds |
| Recommendation algorithm changes produce inconsistent UX | Low | `source_generation_versions` tracks methodology; UI can show "updated" |
| Explainability block becomes stale | Low | Regenerated with each insight; source_metrics always current |

---

## 6. Phase E — Advanced Intelligence Features

**Status:** Future concept  
**Target Version:** v3.x or v4.0  
**Dependencies:** Phase D complete, user adoption of insights

### Goal

Future expansion of the insights and recommendations system. This phase does not define algorithms — it ensures the architecture is ready for:

- New insight categories
- Improved recommendation algorithms
- Optional community-aggregated anonymous insights
- Long-term trend history beyond 5 years

### Scope (Future — Not Designed)

| Feature | Description | Collections Affected |
|---------|-------------|---------------------|
| Advanced trend intelligence | Longer trend windows, pattern recognition across categories | `insights_habits`, potentially `insights_trends_extended` |
| Recommendation improvements | Better priority, context-awareness, personalization | `insights_recommendations` |
| New insight categories | Additional behavioural metrics as usage patterns emerge | `insights_habits` |
| Anonymous community insights | Opt-in aggregate comparisons ("compared to other Trackora users") | New `insights_community` collection (Opt-In only) |
| Exportable insight history | User-facing export of insights over time | New `insights_history` collection |

### Architecture Readiness

Current architecture already supports Phase E:

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Add new insight types | Ready | `insight_type` is a string enum — new values are additive |
| Add new collections | Ready | Collections follow `insights_*` naming convention |
| Versioning for new types | Ready | Dual-versioning pattern inherited by all collections |
| Explainability for new types | Ready | All insight types require explainability block |
| Deprecation for old types | Ready | 3-release policy documented |
| Rebuildability for new types | Ready | Insights rebuildable from analytics_* |

### Exit Criteria

| ID | Criterion |
|----|-----------|
| E1 | New insight types can be added to `insights_habits` without schema migration |
| E2 | New recommendation types can be added to `insights_recommendations` without schema migration |
| E3 | New collections follow `insights_*` naming and dual-versioning conventions |
| E4 | Architecture tests verify no breaking changes to existing insight types |

### Success Metrics

| Metric | Target |
|--------|--------|
| Time to add new insight type (architecture only) | ≤1 day |
| New insight type adoption without migration | 100% |
| Backward compatibility of existing insight data | 100% |

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Community insights (anonymous) leak identifiable data | Critical | Minimum group size (≥10 users), stripped identifiers, opt-in only |
| New insight types require data not yet collected | Medium | Analytics schema must accommodate future needs; prefer flexible optional fields |
| Algorithm complexity makes explainability difficult | Medium | Explainability is a hard requirement — algorithms must be interpretable by design |

---

## 7. Dependency Matrix

```
Phase A: Support Backend (v2.0.x)
    │
    │  No dependency on Phases B–E
    │  Support collections permanently isolated
    ▼
Phase B: Parallel Analytics Storage (v2.x)
    │
    ├── Depends on: Phase A (MongoDB driver proven in production)
    ├── Depends on: SQLite schema stability
    └── Blocked by: MongoDB driver approval
    │
    ▼
Phase C: Analytics Synchronization (v2.x)
    │
    ├── Depends on: Phase B (analytics collections exist)
    └── Blocked by: Analytics pipeline design
    │
    ▼
Phase D: Trackora Insights (v3.0)
    │
    ├── Depends on: Phase C (analytics pipeline stable)
    ├── Depends on: analytics_* collections populated
    └── Blocked by: Insight algorithm design
    │
    ▼
Phase E: Advanced Intelligence (v3.x / v4.0)
    │
    ├── Depends on: Phase D (insights adopted by users)
    └── Blocked by: Feature prioritization
```

### Critical Path

The critical path to full MongoDB adoption is:

```
MongoDB driver approval → Phase A → Phase B → Phase C → Phase D → Phase E
```

No phase can begin before its predecessor completes.

### Blocker Summary

| Blocker | Blocks | Risk | Unblock Condition |
|---------|--------|------|-------------------|
| MongoDB driver approval (`pymongo`, `dnspython`) | Phase A | High | Dependency review and approval |
| Analytics pipeline design | Phase C | Medium | Architecture design (Phase 11 provides this) |
| Insight algorithm design | Phase D | Medium | Future product design |
| User adoption of insights | Phase E | Low | Requires Phase D to ship first |

---

## 8. Upgrade Safety Rules

### Rule US1 — No SQLite Data Loss

No phase may modify, delete, or corrupt SQLite data. SQLite is the source of truth and must survive every MongoDB change.

| Phase | SQLite Risk | Mitigation |
|-------|-------------|------------|
| A | None | Support collections are MongoDB-only |
| B | None | MongoDB is read-only from SQLite |
| C | None | SQLite is read-only source |
| D | None | Insights read from analytics, not SQLite |
| E | None | Same as D |

### Rule US2 — Regeneration Over Migration

When MongoDB data needs to change, prefer regeneration (delete and recompute from SQLite) over migration (in-place document transformation).

| Phase | Expected Regeneration Events | Migration Events |
|-------|----------------------------|-----------------|
| B | Schema changes, generation changes, bug fixes | None |
| C | Version upgrades, recovery | None |
| D | Insight algorithm improvements, schema changes | Only for user-annotated insight data |
| E | New insight types, algorithm improvements | Only if user annotations exist |

### Rule US3 — Version-Aware Fallback

If a newer MongoDB schema version is encountered by an older application, the application must:

1. Read what it can (unknown fields ignored by MongoDB)
2. Log a warning about version mismatch
3. Continue operating with available data
4. Never crash or refuse to start due to MongoDB version mismatch

### Rule US4 — Additive-Only Public Schemas

MongoDB public schemas (collections exposed to multiple application versions) must evolve additively. Field removal requires a deprecation window of at least 3 releases.

---

## 9. Data Preservation Rules

### Rule DP1 — Support Collections Must Survive Upgrades

| Collection | Upgrade Behavior | Rationale |
|-----------|-----------------|-----------|
| `bug_reports` | Preserved verbatim | User-generated data, cannot be recreated |
| `feature_requests` | Preserved verbatim | User-generated data |
| `feedback` | Preserved verbatim | User-generated data |
| `crash_reports` | Preserved verbatim | Diagnostics, cannot be recreated |

### Rule DP2 — Analytics Collections May Regenerate

| Collection | Upgrade Behavior | Rationale |
|-----------|-----------------|-----------|
| All `analytics_*` | MAY regenerate from SQLite | Derived data, SQLite is source of truth |
| Behaviour | Increment `analytics_generation_version` on methodology change | Ensures readers can detect stale data |

### Rule DP3 — Insights Collections May Regenerate

| Collection | Upgrade Behavior | Rationale |
|-----------|-----------------|-----------|
| `insights_habits` | MAY regenerate from analytics_* | All input data preserved in analytics |
| `insights_recommendations` | MAY regenerate from insights_* + analytics_* | Ephemeral by design |

Exception: If future versions add user annotations to insights (e.g., "this insight was useful"), those annotations must be preserved through migration.

### Rule DP4 — System Collections May Migrate

| Collection | Upgrade Behavior | Rationale |
|-----------|-----------------|-----------|
| `system_metadata` | MAY migrate | Checkpoint state can be reset (triggers full regeneration) |
| `system_jobs` | MAY truncate (retention-based) | Operational logs, 90-day default retention |
| `system_schema` | MAY migrate | Version info can be recreated from current analysis |

### Rule DP5 — Cross-Phase Data Flow

```
Phase A writes → Support collections (permanent, never regenerated)
Phase B writes → Analytics collections (regenerable from SQLite)
Phase C manages → Aggregation pipeline (operational metadata)
Phase D writes → Insights collections (regenerable from Analytics)
Phase E may write → Extended collections (regenerable from Analytics)
```

---

## 10. Version Compatibility Matrix

### Collection Versions by Phase

| Collection | Phase A | Phase B | Phase C | Phase D | Phase E |
|-----------|---------|---------|---------|---------|---------|
| `bug_reports` | s1 | s1 | s1 | s1 | s1 |
| `feature_requests` | s1 | s1 | s1 | s1 | s1 |
| `feedback` | s1 | s1 | s1 | s1 | s1 |
| `crash_reports` | s1 | s1 | s1 | s1 | s1 |
| `analytics_games` | — | s1, g1 | s1, g1 | s1, g1+ | s1+, g1+ |
| `analytics_daily` | — | s1, g1 | s1, g1 | s1, g1+ | s1+, g1+ |
| `analytics_weekly` | — | s1, g1 | s1, g1 | s1, g1+ | s1+, g1+ |
| `analytics_monthly` | — | s1, g1 | s1, g1 | s1, g1+ | s1+, g1+ |
| `analytics_trends` | — | s1, g1 | s1, g1 | s1, g1+ | s1+, g1+ |
| `analytics_sessions` | — | s1, g1 | s1, g1 | s1, g1+ | s1+, g1+ |
| `insights_habits` | — | — | — | s1, g1 | s1, g1+ |
| `insights_recommendations` | — | — | — | s1, g1 | s1, g1+ |
| `system_metadata` | s1 | s1, g1 | s1, g1 | s1, g1+ | s1, g1+ |
| `system_jobs` | s1 | s1 | s1 | s1 | s1 |
| `system_schema` | — | s1 | s1 | s1 | s1 |

**Key:** `s` = schema_version, `g` = analytics_generation_version, `—` = collection does not exist yet, `+` = may have been incremented from initial value

### Cross-Phase Reader Compatibility

| Phase | Can Read From | Notes |
|-------|--------------|-------|
| A | Support collections | No analytics/insights exist yet |
| B | Support + Analytics | System collections active |
| C | Same as B | Same collections, formalized pipeline |
| D | Support + Analytics + Insights | All collections active |
| E | All of the above | Extended collections are additive |

### Upgrade Path: Phase A → Phase B

```
Phase A running with support collections
    │
    ▼
Install Phase B
    │
    ├── Support collections: unchanged (s1)
    ├── Analytics collections: created (s1, g1)
    ├── System collections: created (s1)
    └── Phase A readers: unaffected (don't query new collections)
    │
    ▼
Phase B running
```

### Upgrade Path: Phase B → Phase D

```
Phase B running with analytics
    │
    ▼
Install Phase D
    │
    ├── Analytics collections: may get version bumps (s1→s2, g1→g2)
    ├── Insights collections: created (s1, g1)
    ├── System collections: updated with new versions
    └── Phase B readers: handle higher schema_version gracefully
    │
    ▼
Phase D running
```

---

## 11. Disaster Recovery Roadmap

### Support Backend Lost (Phase A Collections)

| Scenario | Recovery | Data Loss | Downtime |
|----------|----------|-----------|----------|
| Collection dropped | Restore from BackupManager backup | None (within backup window) | Minutes |
| Database deleted | Full restore from filesystem backup | None (within backup window) | Minutes |
| Individual document corrupted | Delete and resubmit via report queue | That one report | Seconds |
| No backup exists | Reports lost; user can resubmit | All reports since last backup | N/A |

**Recovery command (conceptual):**
```
Restore MongoDB collection from BackupManager archive
```

### Analytics Lost (Phase B/C Collections)

| Scenario | Recovery | Data Loss | Downtime |
|----------|----------|-----------|----------|
| Collection dropped | Regenerate from SQLite | None | Regeneration time |
| Database deleted | Regenerate all analytics from SQLite | None | Regeneration time |
| Stale data (missed sessions) | Incremental update from `system_metadata` checkpoint | None | Incremental time |
| Corrupted aggregates | Delete collection → regenerate from SQLite | None | Regeneration time |

**Recovery command (conceptual):**
```
Run Analytics Aggregation Service: full regeneration
```

### Insights Lost (Phase D Collections)

| Scenario | Recovery | Data Loss | Downtime |
|----------|----------|-----------|----------|
| Collection dropped | Regenerate from analytics_* | None | Regeneration time |
| Database deleted | Regenerate analytics first, then insights | None | Cascade regeneration time |
| Stale insight data | Regenerate from analytics_* | None | Regeneration time |
| User annotations lost | Cannot recover (user-generated) | Annotations only | N/A |

**Recovery command (conceptual):**
```
Run Insight Computation Engine: full regeneration
```

### System Collections Lost

| Collection | Recovery | Data Loss |
|-----------|----------|-----------|
| `system_metadata` | Recreate with default values (last_session_processed = 0) | Checkpoint state → full regeneration on next run |
| `system_jobs` | None needed | Job history only |
| `system_schema` | Recreate with current version values | Migration history lost |

### Full System Loss

```
1. Restore or recreate SQLite (source of truth — may need filesystem restore)
2. If SQLite intact:
     a. Regenerate all analytics_* from SQLite
     b. Regenerate all insights_* from analytics_*
     c. Restore support collections from backup (or accept loss)
3. If SQLite lost:
     a. Full data loss for session history
     b. Restore from BackupManager (SQLite + MongoDB backup)
```

---

## 12. Long-Term Governance

### Deprecation Windows

| Deprecation Type | Window | Example |
|-----------------|--------|---------|
| Insight type removal | 3 releases (e.g., v2.0 → v2.1 → v2.2 → v3.0) | Deprecate → warn → stop producing → remove |
| Recommendation type removal | 3 releases | Same as insight |
| Document field removal | 3 releases | Deprecate → warn → stop writing → remove field |
| Collection removal | 2 major versions | Announce in vN → remove in vN+2 |
| `schema_version` value retirement | 2 major versions | Readers only support s1–s3; s4 documents migrate |

### Version Support Policy

| Application Version | Supported MongoDB Schema Versions | Notes |
|--------------------|-----------------------------------|-------|
| Current release | Current + previous 2 schema versions | Readers handle s_current, s_current-1, s_current-2 |
| Current – 1 release | Current – 1 + current – 2 | Older app may miss newer schema fields |
| Current – 2 releases | May work but not guaranteed | Recommend upgrade |
| Current – 3+ releases | Not supported | Must upgrade |

### Backward Compatibility Policy

| Aspect | Policy | Duration |
|--------|--------|----------|
| Reader compatibility | Readers handle documents with schema_version ≤ their expected version | Permanent |
| `analytics_generation_version` | Readers display data from any generation version | Permanent (may show "older methodology" label) |
| Document field additions | New fields are optional; old readers ignore them | Permanent |
| Document field removals | Deprecation window enforced; old field kept for 3 releases | 3 releases |

### Forward Compatibility Policy

| Aspect | Policy | Caveat |
|--------|--------|--------|
| New optional fields | Old readers ignore them automatically | MongoDB native behavior |
| New collections | Old readers never query them | No code changes needed |
| Higher schema_version | Old readers read known fields, skip unknown | May miss new fields |
| Higher generation_version | Old readers display data from newer methodology | Data is correct, methodology may differ |

### Collection Retirement Policy

When a collection is retired:

| Step | Detail |
|------|--------|
| 1. Announce | Document in CHANGELOG: "Collection X is deprecated in vN" |
| 2. Stop writing | In vN+1, no new documents written to collection |
| 3. Stop reading | In vN+2, readers no longer query collection |
| 4. Remove | In vN+3, collection may be dropped from system_schema |

---

## 13. Recommended MongoDB Adoption Timeline

### Recommendation Summary

| Phase | Target Version | What Ships |
|-------|---------------|------------|
| A | **v2.0.x** | Support backend: `bug_reports`, `feature_requests`, `feedback`, `crash_reports` |
| B | **v2.x** | Analytics storage: all 6 `analytics_*` collections |
| C | **v2.x** (same release as B, or immediately after) | Analytics pipeline formalized |
| D | **v3.0** | Insights: `insights_habits`, `insights_recommendations` |
| E | **v3.x / v4.0** | Advanced features |

### Justification

#### v2.0.x — Phase A (Support Backend)

**Why v2.0.x and not later:**
- Support backend is the simplest MongoDB use case — 4 collections, no aggregation, no analytics
- Replaces an existing external dependency (Supabase) with local storage
- Proves MongoDB driver works in production (PyInstaller, threading, etc.)
- Does NOT touch SQLite — lowest risk entry point
- Provides operational experience with MongoDB before analytics use cases

**What ships:** Phase A collections + `MongoReportService` + connection management + offline queue integration

#### v2.x — Phases B + C (Analytics Storage + Pipeline)

**Why v2.x (after A is stable):**
- Analytics collections are derived data — low risk if regeneration works correctly
- SQLite remains source of truth — any MongoDB failure falls back gracefully
- Dual-versioning pattern proven in Phase A can be extended
- Pipeline formalization (Phase C) must ship with or immediately after B to ensure data consistency

**What ships:** All 6 `analytics_*` collections + `system_metadata` + `system_jobs` + `system_schema` + aggregation service + incremental updates + full regeneration

#### v3.0 — Phase D (Trackora Insights)

**Why v3.0 and not v2.x:**
- Insights are the most complex feature — they depend on stable analytics pipeline (Phase C)
- Insights introduce user-facing interpreted data — needs careful UX testing
- Wellbeing metrics require additional product and legal review (banned terminology, no health claims)
- Insights introduce opt-in data model — requires settings UI and consent management
- The 2.x release cycle should focus on getting analytics right (performance, accuracy, reliability)
- v3.0 is a natural boundary: analytics mature in v2.x, insights debut in v3.0

**What ships:** `insights_habits` with 7+ insight categories + `insights_recommendations` with recommendation engine + explainability framework + opt-in consent UI

#### v3.x / v4.0 — Phase E (Advanced Intelligence)

**Why later:**
- Requires user adoption of Phase D insights to justify investment
- Community/aggregate features require significant privacy and legal review
- Advanced trend intelligence depends on sufficient historical data (needs months of analytics)
- Recommendation engine improvements depend on user feedback data

**What may ship:** Community insights (anonymous, opt-in), extended trend history, new insight categories, improved recommendation algorithms

---

## Appendix A: Phase Comparison Summary

| Aspect | Phase A | Phase B | Phase C | Phase D | Phase E |
|--------|---------|---------|---------|---------|---------|
| **Collections** | 4 support | 6 analytics + 3 system | Same as B | 2 insights | Extended insights |
| **New dependencies** | pymongo, dnspython | None | None | None | None |
| **SQLite impact** | None | Read-only | Read-only | Read-only | Read-only |
| **User-visible** | Bug reports stored locally | Faster dashboards | Same | Insights, recommendations | Community features |
| **Regeneration** | N/A | Default | Formalized | Default | Default |
| **Rollback** | Backup restore | Regeneration | Regeneration | Regeneration | Regeneration |
| **Risk** | Low | Low–Medium | Low | Medium | Medium–High |
| **Target version** | v2.0.x | v2.x | v2.x | v3.0 | v3.x / v4.0 |

## Appendix B: Collection Lifecycle Summary

| Collection | Introduced In | Active Until | Retired In | Retirement Reason |
|-----------|--------------|--------------|------------|-------------------|
| `bug_reports` | Phase A | Indefinite | — | Core support feature |
| `feature_requests` | Phase A | Indefinite | — | Core support feature |
| `feedback` | Phase A | Indefinite | — | Core support feature |
| `crash_reports` | Phase A | Indefinite | — | Core support feature |
| `analytics_games` | Phase B | Indefinite | — | Core analytics |
| `analytics_daily` | Phase B | Indefinite | — | Core analytics |
| `analytics_weekly` | Phase B | Indefinite | — | Core analytics |
| `analytics_monthly` | Phase B | Indefinite | — | Core analytics |
| `analytics_trends` | Phase B | Indefinite | — | Core analytics |
| `analytics_sessions` | Phase B | Indefinite | — | Core analytics |
| `insights_habits` | Phase D | Indefinite | — | Core insights |
| `insights_recommendations` | Phase D | Indefinite | — | Core recommendations |
| `system_metadata` | Phase B | Indefinite | — | Operational |
| `system_jobs` | Phase B | Indefinite | — | Operational |
| `system_schema` | Phase B | Indefinite | — | Operational |
