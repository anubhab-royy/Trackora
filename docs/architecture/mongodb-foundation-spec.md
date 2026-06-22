# MongoDB Foundation Architecture Specification

**Version:** 2.0.0-draft  
**Status:** Architecture Design  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  
**Phase:** 11 — MongoDB Foundation

---

## 1. Purpose

Define the architectural foundation for integrating MongoDB into Trackora as an analytics and insights platform. This specification establishes boundaries, ownership rules, collection strategy, and future compatibility — without introducing MongoDB as a production dependency.

MongoDB's document-oriented data model is chosen for:
- Flexible schema evolution (game analytics, habit metrics, insight records)
- Rich aggregation pipeline (trend computation, period-over-period analysis)
- Embedded sub-documents (daily breakdowns within weekly aggregates)
- Time-series compatibility (session analytics, activity trends)
- Future cloud/self-hosted deployment flexibility

---

## 2. Design Principles

### P1 — SQLite is Source of Truth

SQLite owns all raw data. MongoDB stores **derived** and **aggregated** data only. No raw session, game, or setting data is written to MongoDB unless derived from SQLite.

### P2 — Local-First Always

All MongoDB features must function with a local MongoDB instance. Cloud sync is an opt-in feature for future versions. No feature may require a remote MongoDB connection.

### P3 — Privacy-First by Default

Only anonymous or explicitly opted-in data may leave the local machine. MongoDB collections are classified into privacy tiers:
- **Local Only**: game analytics, session analytics, aggregates
- **Opt-In**: insight records, recommendation records
- **Anonymous Only**: community intelligence inputs

### P4 — Additive, Not Disruptive

MongoDB must never break existing SQLite workflows. Adding MongoDB is purely additive — all current features, tests, and data paths continue working unchanged.

### P5 — Schema Versioning on Every Document

Every MongoDB document carries a `schema_version` field. This enables independent schema evolution across collections without breaking existing readers.

### P6 — No Core Runtime Dependency

The application must start and operate normally without MongoDB. If MongoDB is unavailable, SQLite-backed analytics continue to work as they do today. MongoDB is a "best effort" enhancement.

### P7 — Aggregation Over Raw Storage

MongoDB stores pre-computed aggregates rather than raw events. Raw session data belongs in SQLite. MongoDB holds daily/weekly/monthly rollups, trend snapshots, and insight records.

### P8 — No Raw Session Duplication

MongoDB must never become a second session database. MongoDB may contain:
- Aggregates
- Analytics
- Trends
- Insights
- Recommendations

MongoDB must not contain:
- Full session history copies
- Active session records
- Duplicate SQLite tables

Rationale:
- Avoid dual ownership of session data
- Avoid synchronization complexity
- Reduce storage growth
- Preserve SQLite as source of truth

This is a non-negotiable architecture rule. Every MongoDB collection must be auditable against this principle.

---

## 3. MongoDB Responsibilities

| Responsibility | Description |
|---------------|-------------|
| **Analytics Storage** | Pre-computed daily, weekly, monthly playtime aggregates |
| **Trend History** | Stored trend snapshots for period-over-period comparison |
| **Game Analytics** | Per-game lifetime, trend, and comparison data |
| **Session Analytics** | Session pattern analysis (length distribution, peak hours, frequency) |
| **Insight Records** | Future insight and recommendation data (wellbeing, habit analytics) |
| **Anonymous Metrics** | Privacy-preserved, aggregated usage patterns for community features |
| **Reporting Cache** | Optional local cache for support/analytics reports |
| **Analytics Infrastructure** | System collections for aggregation state, job tracking, and schema versioning |

MongoDB does NOT own:
- Raw game records
- Raw session records (full copies)
- Active session tracking
- User settings
- Authentication data
- Application configuration

---

## 4. SQLite Responsibilities

| Responsibility | Description |
|---------------|-------------|
| **Source of Truth** | All raw data is written to SQLite first |
| **Session Tracking** | Raw session start/end events |
| **Game Registry** | Game definitions, enabled/disabled state, discovery metadata |
| **Active Sessions** | Crash-recovery session state |
| **Settings** | All user and application settings |
| **Migration Tracking** | Schema version via `_migrations` table |
| **Local-first Operation** | Full offline capability without MongoDB |

SQLite remains the write path for all data. MongoDB is a read-enhanced derived layer.

---

## 5. Data Ownership Rules

### Rule 1 — Write Once, Read Optimized

Data is written to SQLite (source of truth) and aggregated into MongoDB (read optimization). No bidirectional sync. No dual-write transactions.

### Rule 2 — Derived Collections Are Ephemeral

MongoDB collections can be rebuilt from SQLite at any time. If MongoDB is wiped, no data is lost — only computed aggregates need regeneration.

### Rule 3 — Privacy Tier Enforcement

| Tier | Storage | Sync Permitted | Examples |
|------|---------|---------------|----------|
| Local | SQLite + local MongoDB | Never | Raw sessions, active sessions, settings |
| Aggregated | MongoDB only | Never | Daily/weekly/monthly aggregates |
| Opt-In | MongoDB + cloud | User consent required | Insight records, recommendations |
| Anonymous | MongoDB + cloud | Always anonymized | Community playtime distribution |

### Rule 4 — No Cross-Backend Foreign Keys

MongoDB documents may reference SQLite primary keys (e.g., `game_id`) but there are no enforced foreign key constraints. SQLite owns the key space.

### Rule 5 — No Raw Session Duplication

MongoDB must not store raw session records, full session history copies, or any data that duplicates SQLite tables. All MongoDB data must be derived (aggregated, analyzed, or summarized) from the SQLite source of truth. See Principle P8.

---

## 6. Analytics Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         TRACKORA APPLICATION                              │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                                ▼
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│      SQLite (Source of       │    │      MongoDB (Analytics)           │
│           Truth)             │    │                                    │
│  ┌──────────────────────┐   │    │  ┌─── analytics_* ──────────────┐  │
│  │ games                 │   │    │  │ analytics_games              │  │
│  │ sessions              │───┼────┼─►│ analytics_sessions           │  │
│  │ active_sessions       │   │    │  │ analytics_daily              │  │
│  │ settings              │   │    │  │ analytics_weekly             │  │
│  │ _migrations           │   │    │  │ analytics_monthly            │  │
│  └──────────────────────┘   │    │  │ analytics_achievements        │  │
│                              │    │  │ analytics_trends             │  │
│                              │    │  └──────────────────────────────┘  │
│                              │    │  ┌─── insights_* ──────────────┐  │
│                              │    │  │ insights_habits              │  │
│                              │    │  │ insights_recommendations     │  │
│                              │    │  └──────────────────────────────┘  │
│                              │    │  ┌─── system_* ────────────────┐  │
│                              │    │  │ system_metadata              │  │
│                              │    │  │ system_jobs                  │  │
│                              │    │  │ system_schema                │  │
│                              │    │  └──────────────────────────────┘  │
│                              │    └────────────────────────────────────┘
└──────────────────────────────┘
         │                              │
         │        ┌─────────────────────┘
         │        │  (aggregation service)
         ▼        ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     Analytics Aggregation Service                          │
│  Reads from SQLite repositories, computes aggregates, writes to           │
│  MongoDB collections. Idempotent — safe to re-run. Tracks state in        │
│  system_metadata and job history in system_jobs.                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Aggregation Flow

1. **Trigger**: Periodic schedule (hourly/daily), or on-demand after session end
2. **Checkpoint**: Read `system_metadata` for last processed session ID
3. **Read**: Analytics service reads from SQLite repositories (sessions since last checkpoint)
4. **Compute**: Business logic performs aggregations (sums, averages, distributions)
5. **Track**: Write job record to `system_jobs` with status `running`
6. **Write**: Result documents upserted into MongoDB analytics collections
7. **Complete**: Update `system_metadata` with new checkpoint and job status in `system_jobs`
8. **Serve**: UI queries MongoDB for pre-computed analytics (fallback to SQLite live calculation)

---

## 7. Collection Strategy

| Collection | Namespace | Tier | Purpose | Data Source |
|-----------|-----------|------|---------|-------------|
| `analytics_games` | analytics_* | Aggregated | Per-game lifetime stats, trends, comparisons | SQLite sessions + games |
| `analytics_sessions` | analytics_* | Aggregated | Session pattern analysis per game and overall | SQLite sessions |
| `analytics_daily` | analytics_* | Aggregated | Daily playtime totals with per-game breakdown | SQLite sessions |
| `analytics_weekly` | analytics_* | Aggregated | Weekly summaries with daily breakdown | SQLite sessions |
| `analytics_monthly` | analytics_* | Aggregated | Monthly summaries with daily breakdown | SQLite sessions |
| `analytics_achievements` | analytics_* | Aggregated | Milestone tracking (future) | Computed from sessions |
| `analytics_trends` | analytics_* | Aggregated | Stored trend snapshots for period comparison | Computed from aggregates |
| `insights_habits` | insights_* | Opt-In | Wellbeing and habit insights (future) | Computed from analytics |
| `insights_recommendations` | insights_* | Opt-In | Game recommendations (future) | Computed from analytics |
| `system_metadata` | system_* | System | Analytics generation state, aggregation checkpoints, schema version, last run timestamps | Internal |
| `system_jobs` | system_* | System | Aggregation job tracking (type, status, duration, failures, retries) | Internal |
| `system_schema` | system_* | System | Collection-level schema version tracking | Internal |

---

## 8. Collection Naming Convention

All MongoDB collections follow a three-namespace naming convention. Every collection must be prefixed with exactly one of:

### `analytics_*` — Derived Analytics

Stores pre-computed, aggregated data derived from SQLite. These collections hold the primary analytics payload that the UI queries for dashboards, charts, and reports.

Examples: `analytics_daily`, `analytics_weekly`, `analytics_monthly`, `analytics_games`, `analytics_trends`

Rules:
- All data must be regenerable from SQLite
- No raw or transactional data
- Idempotent upsert by composite key

### `insights_*` — Future Intelligence Outputs

Stores computed insight and recommendation data. These collections hold higher-order analysis that combines multiple analytics sources.

Examples: `insights_habits`, `insights_recommendations`

Rules:
- All data must be regenerable from analytics collections
- Require explicit user consent before cloud sync (Opt-In tier)
- Subject to stricter privacy review

### `system_*` — Operational Metadata

Stores infrastructure and operational data. These collections manage the analytics pipeline itself and contain no user-facing analytics data.

Examples: `system_metadata`, `system_jobs`, `system_schema`

Rules:
- Not user-facing
- Not syncable to cloud
- System-owned only — no application code reads user data from these collections
- Used for checkpointing, job tracking, and schema version management

### Naming Enforcement

All future collections must use one of the three prefixes. No collection may use a different prefix or no prefix. This convention enables:
- Clear data classification at a glance
- Simple backup/restore filtering by prefix
- Access control rules by namespace
- Collection-level lifecycle policies by prefix

---

## 9. Document Modeling Principles

### PR1 — Embed What You Query Together

Documents should embed related data that is always queried together. For example, a weekly aggregate embeds daily breakdowns as sub-documents rather than storing them in a separate collection.

### PR2 — Reference What You Query Separately

Use `game_id` references (matching SQLite primary keys) rather than embedding full game data in every analytics document. Game name can be cached in analytics documents for display purposes, but the `game_id` is the canonical reference.

### PR3 — Pre-Join at Write Time

Analytics documents should contain denormalized display fields (e.g., `game_name`) at write time so reads do not require joins or lookups. This is acceptable because:
- Aggregates are write-once, read-many
- Display fields change rarely (game renames are infrequent)
- Stale display data in aggregates is acceptable for historical analytics

### PR4 — Use Composite Keys for Idempotent Upserts

Documents should use natural composite keys (e.g., `{game_id, date}` for daily aggregates) so that re-running the aggregation updates existing documents rather than duplicating them.

### PR5 — Schema Version on Every Document

Every document includes `schema_version: int` as the first field. This allows readers to handle multiple schema structures during migration windows.

### PR5a — Analytics Generation Version on Every Analytics Document

Every analytics and insights document includes `analytics_generation_version: int` immediately after `schema_version`. This tracks the calculation methodology independently from the document structure.

| Field | Tracks | Example Change |
|-------|--------|----------------|
| `schema_version` | Document structure (fields, types) | Adding a new field, removing a deprecated field |
| `analytics_generation_version` | Calculation methodology (algorithms, formulas) | Improving a habit score formula, changing percentile interpolation method |

This dual-versioning pattern allows the aggregation service to improve analytics algorithms without requiring document schema migrations, and to evolve document schemas without resetting generation counters.

### PR6 — Timestamps as ISODate

All datetime fields use MongoDB's native `ISODate` type for efficient range queries and aggregation pipeline operations.

---

## 10. Versioning Rules

### Document-Level Versioning

Every document carries a `schema_version` integer field:
- Initial version: `1`
- Incremented on breaking structural changes (field removal, type change)
- NOT incremented on additive changes (new optional fields)

### Analytics Generation Versioning

Every analytics and insights document carries an `analytics_generation_version` integer field immediately after `schema_version`:
- Initial version: `1`
- Incremented when calculation methodology changes (algorithm improvement, bug fix in aggregation, new weighting scheme)
- NOT incremented on document structure changes (that is `schema_version`)
- Both fields may increment independently in the same release

This enables the aggregation service to evolve analytics algorithms independently from document schemas.

### Collection-Level Versioning

The `system_schema` collection tracks the current schema version and analytics generation version of each analytics and insights collection:

```json
{
  "_id": "collection_schema",
  "schema_version": 1,
  "collections": {
    "analytics_games": { "schema": 1, "generation": 1 },
    "analytics_sessions": { "schema": 1, "generation": 1 },
    "analytics_daily": { "schema": 1, "generation": 1 },
    "analytics_weekly": { "schema": 1, "generation": 1 },
    "analytics_monthly": { "schema": 1, "generation": 1 },
    "analytics_achievements": { "schema": 1, "generation": 1 },
    "analytics_trends": { "schema": 1, "generation": 1 },
    "insights_habits": { "schema": 1, "generation": 1 },
    "insights_recommendations": { "schema": 1, "generation": 1 },
    "system_metadata": { "schema": 1 },
    "system_jobs": { "schema": 1 }
  },
  "updated_at": ISODate
}
```

### Migration vs Regeneration

Most schema changes in MongoDB analytics are handled by **regeneration** (delete and re-aggregate from SQLite) rather than **migration** (in-place document transformation). This is possible because:
- MongoDB is derived data, not source of truth
- Aggregation is idempotent
- Regeneration produces correct results with the new schema

True migrations are reserved for:
- Opt-In collections that may contain user-contributed data (insights, recommendations)
- Collections with externally-referenced data

---

## 11. Data Lifecycle

```
SQLite (raw sessions)
    │
    ▼
Analytics Aggregation Service
    │
    ├── Check system_metadata for last checkpoint
    ├── Process new sessions from SQLite
    ├── Write job record to system_jobs
    ├── Upsert aggregates to analytics_* collections
    └── Update system_metadata checkpoint
    │
    ▼
MongoDB (analytics, insights, system collections)
    │
    ├── analytics_* retained indefinitely (compact summaries)
    ├── insights_* retained per user preference
    ├── system_metadata retained indefinitely (single document)
    ├── system_jobs retained for 90 days (operational logs)
    ├── Rebuildable from SQLite at any time
    └── Subject to TTL only on:
        └── analytics_daily older than N years
        └── analytics_trends older than N years (recomputable)
```

### Retention Policy

| Collection | Retention | Rationale |
|-----------|-----------|-----------|
| `analytics_daily` | Indefinite | Compact summary (one document per day) |
| `analytics_weekly` | Indefinite | Compact summary (52 documents per year) |
| `analytics_monthly` | Indefinite | Most compact (12 documents per year) |
| `analytics_games` | Indefinite | One document per game |
| `analytics_sessions` | Indefinite | One document per game per period |
| `analytics_achievements` | Indefinite | Milestone records are permanent |
| `analytics_trends` | 5 years | Older trends recomputable from aggregates |
| `insights_habits` | Indefinite | User-generated insight data |
| `insights_recommendations` | 1 year | Recommendations become stale |
| `system_metadata` | Indefinite | Single document, minimal size |
| `system_jobs` | 90 days | Operational logs, retained for audit trail |
| `system_schema` | Indefinite | Single document, minimal size |

---

## 12. Privacy Model

### Tier 0 — Local Data (No Sync)

All data in SQLite remains local. MongoDB analytics stored on the same machine remain local. No data in Tier 0 may be transmitted over a network.

**Collections:** All `analytics_*`, `system_*` collections when running local MongoDB

### Tier 1 — Aggregated Data (Anonymous)

If MongoDB is remote (future cloud feature), only anonymous, aggregated data may be synced. Anonymous means:
- No game names that could identify a user's library
- No timestamps that could identify playing patterns
- Only statistical distributions (histograms, percentiles)
- Minimum count thresholds (≥10 users) before publication

### Tier 2 — Opt-In Data (User Consent)

Insight records and recommendation records require explicit user consent before sync. Consent is:
- Granular per feature category
- Revocable at any time
- Stored in SQLite settings
- Reversible (opt-out deletes cloud data)

**Collections:** `insights_habits`, `insights_recommendations`

### Tier 3 — Anonymous Community Data (Future)

Community intelligence inputs (e.g., "average playtime per session by game") are:
- Always aggregated to minimum group size
- Never attributable to individual users
- Stripped of identifiable metadata
- Published on a "best effort" basis from opted-in users

---

## 13. Local-first Compatibility

### MongoDB Can Be Local

For users who do not want cloud features, MongoDB runs as a local process or is embedded. Analytics are computed and stored entirely on the local machine.

### No MongoDB = No Degradation

If MongoDB is not installed or unavailable:
- The application starts normally
- All SQLite analytics continue working
- The UI falls back to live computation from SQLite
- No errors, warnings, or degraded UX

### Detection and Fallback

```
┌──────────────────────────────────────┐
│      AnalyticsService (facade)        │
│                                      │
│  get_lifetime_stats():               │
│    if mongodb_available:             │
│       return from_mongodb()          │
│    else:                             │
│       return from_sqlite_legacy()    │
└──────────────────────────────────────┘
```

The `AnalyticsService` facade abstracts the backend choice. UI code never knows whether data came from MongoDB or SQLite.

---

## 14. Future Insights Compatibility

### Analytics Pipeline (Phase D)

```
SQLite ──► Aggregation Service ──► MongoDB analytics collections
                                        │
                                        ▼
                                 Computation Pipeline
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                     insights_habits     insights_recommendations
                              │                   │
                              ▼                   ▼
                        Wellbeing Metrics   Habit Analytics
```

The analytics pipeline is designed to be:
- **Extensible**: New insight types add new collections without changing existing ones
- **Pluggable**: Computation stages are isolated modules
- **Idempotent**: Re-running produces identical results
- **Versioned**: Pipeline outputs carry schema_version for future evolution

### Aggregation Pipeline (Future)

MongoDB's native aggregation pipeline enables:
- `$match` / `$group` for period-over-period computation
- `$bucket` for session length distributions
- `$percentile` (MongoDB 7+) for percentile calculations
- `$lookup` across analytics collections (rare — prefer embedded data)
- `$merge` for upserting results into output collections

---

## 15. Future Validation Strategy

### Requirement

When MongoDB implementation begins (Phase B — Parallel Analytics Storage), every collection must define a JSON Schema validation document. Validation must enforce both `schema_version` and `analytics_generation_version` as required fields. Validation is NOT implemented in Phase 11 and becomes mandatory in Phase B.

### Validation Coverage

Each collection's validation schema must enforce:

| Element | Requirement |
|---------|-------------|
| Required fields | All non-optional fields must be declared `required` |
| Field types | Every field must specify its BSON type |
| Enum validation | Fields with enumerated values must use `enum` |
| schema_version | Must validate `schema_version` is present and matches expected version |
| document_version | Optional — may validate `document_version` if versioned sub-documents exist |

### Example Validation Document

```json
{
  "$jsonSchema": {
    "bsonType": "object",
    "required": ["schema_version", "game_id", "date", "total_seconds"],
    "properties": {
      "schema_version": {
        "bsonType": "int",
        "minimum": 1,
        "maximum": 1,
        "description": "Must match current schema version for this collection"
      },
      "game_id": {
        "bsonType": "int",
        "description": "References SQLite games.id — no FK enforcement"
      },
      "date": {
        "bsonType": "date",
        "description": "Calendar date of the aggregate"
      },
      "total_seconds": {
        "bsonType": "int",
        "minimum": 0,
        "description": "Total playtime in seconds"
      }
    }
  }
}
```

### Schema Versioning and Validation Interaction

- `schema_version` is validated as a required field with an expected value range
- When a schema version increases, the validation document must be updated in the same deployment
- Old documents with previous `schema_version` remain readable but may fail validation on write — this is acceptable because analytics collections are write-once (upsert replaces the old document entirely)
- For `insights_*` collections, backward-compatible validation is required during migration windows

### Rationale

Schema versioning and validation work together to support safe schema evolution:
- Schema versioning tells readers what structure to expect
- Validation prevents writers from producing malformed documents
- Together they enable zero-downtime collection evolution across application restarts

---

## 16. Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-01 | All SQLite tables and repositories remain unchanged | No SQLite schema or repository modifications |
| AC-02 | No MongoDB driver listed in requirements.txt | Dependency not added |
| AC-03 | No MongoDB connection code exists in production files | Architecture review |
| AC-04 | No MongoDB imports exist outside spec documents | Architecture review |
| AC-05 | Application starts and operates without MongoDB | Manual test on clean system |
| AC-06 | All existing tests pass without MongoDB installed | `pytest` suite green |
| AC-07 | Architecture specification documents exist for all 4 follow-up phases | File existence check |
| AC-08 | Document models defined for all 12 target collections (8 analytics, 2 insights, 2 system) | Spec completeness review |
| AC-09 | Privacy tiers clearly defined and documented | Spec review |
| AC-10 | Fallback path documented for each MongoDB feature | Spec review |
| AC-11 | No cloud dependencies introduced | Dependency audit |
| AC-12 | Upgrade Foundation compatibility confirmed | Cross-spec review |
| AC-13 | P8 (No Raw Session Duplication) is auditable against every collection | Principle traceability check |
| AC-14 | Collection naming convention applied to all 12 collections | Convention compliance review |

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Aggregate** | Pre-computed summary data (e.g., total playtime per day) |
| **Analytics Generation Version** | Integer field on analytics documents tracking calculation methodology independently from document schema |
| **Analytics Namespace** | Collections prefixed `analytics_*` — derived, aggregated data |
| **Derived Data** | Data computed from source-of-truth (SQLite) — safe to regenerate |
| **Insight Namespace** | Collections prefixed `insights_*` — future intelligence outputs |
| **Insight Record** | High-level analysis output (e.g., "you play most on weekends") |
| **Local-First** | Application functions fully without network or remote services |
| **Opt-In** | Feature requiring explicit user consent for data sync |
| **Privacy Tier** | Classification level determining sync and sharing permissions |
| **Recommendation Record** | Computed suggestion (e.g., "you might enjoy game X") |
| **Schema Version** | Integer field on every document enabling schema evolution |
| **Source of Truth** | The authoritative data store (SQLite) — all other stores are derived |
| **System Namespace** | Collections prefixed `system_*` — operational metadata, not user-facing |
| **Trend Snapshot** | A point-in-time record of computed trend data |

## Appendix B: Future Phase Reference

| Phase | Name | Focus |
|-------|------|-------|
| A | MongoDB Foundation (current) | Architecture, document models, versioning strategy, naming convention, validation strategy |
| B | Parallel Analytics Storage | Aggregation service writing to MongoDB, JSON Schema validation, system_metadata checkpointing, system_jobs tracking |
| C | Analytics Synchronization | Syncing analytics between local MongoDB and cloud |
| D | Trackora Insights | Wellbeing metrics, habit analytics, gaming patterns via insights_* collections |
| E | Advanced Intelligence | Recommendations, community features, predictive analytics |
