# MongoDB Versioning & Migration Strategy

**Version:** 2.0.0-draft  
**Status:** Architecture Design  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  
**Phase:** 11 — MongoDB Foundation

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Versioning Model Overview](#2-versioning-model-overview)
3. [Document Versioning](#3-document-versioning)
4. [Analytics Generation Versioning](#4-analytics-generation-versioning)
5. [Collection-Level Version Tracking](#5-collection-level-version-tracking)
6. [Document Evolution Rules](#6-document-evolution-rules)
7. [Collection Migration Strategy](#7-collection-migration-strategy)
8. [Regeneration vs Migration Decision Tree](#8-regeneration-vs-migration-decision-tree)
9. [Backward Compatibility](#9-backward-compatibility)
10. [Forward Compatibility](#10-forward-compatibility)
11. [Breaking Change Handling](#11-breaking-change-handling)
12. [Migration Workflow](#12-migration-workflow)
13. [Rollback Workflow](#13-rollback-workflow)
14. [Multi-Version Coexistence](#14-multi-version-coexistence)
15. [Future v3/v4 Upgrade Paths](#15-future-v3v4-upgrade-paths)
16. [Relationship to SQLite Migrations](#16-relationship-to-sqlite-migrations)
17. [Testing Strategy](#17-testing-strategy)
18. [Acceptance Criteria](#18-acceptance-criteria)

---

## 1. Purpose

Define a comprehensive versioning and migration strategy for MongoDB collections in Trackora. This strategy covers:

- How documents evolve over time
- How schema changes are applied across collections
- How computation methodology changes independently from document structure
- How readers handle mixed-version documents during migration windows
- How rollbacks work when a deployment is reversed
- How future major versions (v3, v4) coexist with v2 collections

The strategy is built on Trackora's architectural principles:
- **MongoDB is derived data** — most migrations are regenerations from SQLite
- **SQLite is source of truth** — MongoDB can always be rebuilt
- **Privacy-first** — schema changes respect privacy tier boundaries
- **Local-first** — all versioning logic works offline

---

## 2. Versioning Model Overview

Trackora MongoDB uses a **three-axis versioning model**:

| Axis | Field | Scope | Tracks |
|------|-------|-------|--------|
| Schema | `schema_version` | Per document | Document structure (fields, types, required/optional) |
| Generation | `analytics_generation_version` | Per document | Calculation methodology (algorithms, formulas, aggregation logic) |
| Collection | `system_schema.collections` | Per collection | Current schema + generation version for each collection |

### Why three axes?

```
schema_version:  1  →  2  (added "peak_hour" field to analytics_daily)
                      ↓
analytics_generation_version:  1  →  2  (improved habit score formula)
                      ↓
collection_version:  tracks both independently per collection
```

Each axis can change independently. A release might:
- Change only schema (add new optional fields to existing documents)
- Change only generation (improve aggregation algorithm without touching document shape)
- Change both (restructure documents AND update computation logic)
- Change neither (add new indexes, no version increment needed)

### Which collections carry which version fields?

| Collection | schema_version | analytics_generation_version |
|-----------|---------------|------------------------------|
| `analytics_games` | Required | Required |
| `analytics_daily` | Required | Required |
| `analytics_weekly` | Required | Required |
| `analytics_monthly` | Required | Required |
| `analytics_trends` | Required | Required |
| `analytics_sessions` | Required | Required |
| `insights_habits` | Required | Required |
| `insights_recommendations` | Required | Required |
| `system_metadata` | Required | Required (tracks current generation for all collections) |
| `system_jobs` | Required | Not applicable (operational logs) |
| `system_schema` | Required | Not applicable (tracks versions, not analytics data) |

---

## 3. Document Versioning

### schema_version

Every document carries `schema_version` as its first field. This is the primary mechanism for schema evolution.

**Rules:**

| Rule | Detail |
|------|--------|
| Initial value | `1` for all collections on first creation |
| Increment condition | Breaking structural changes only |
| Breaking change examples | Field removal, type change, required→optional reversal, embedded document restructuring |
| Non-breaking change examples | Adding optional fields, adding indexes, adding enum values |
| Reader behavior | Must handle documents with `schema_version` ≤ expected version |
| Writer behavior | Always writes current `schema_version` |

**Schema version lifecycle per collection:**

```
schema_version = 1     Initial release
     ↓
schema_version = 2     Field removed from document
     ↓
schema_version = 3     Embedded sub-document restructured
     ↓
     ...               Future releases
```

### Version Compatibility Matrix

| Reader Version | Document Version | Behavior |
|---------------|------------------|----------|
| v1 | v1 | Full read |
| v2 | v1 | Full read (backward compatible) |
| v1 | v2 | Partial read — known fields only, unknown fields ignored |
| v2 | v2 | Full read |
| v2 | v3 | Partial read — known fields only, unknown fields ignored |
| v3 | v1 | Full read (backward compatible) |

Older readers always ignore unknown fields. MongoDB's schemaless nature makes this automatic — no special handling required.

---

## 4. Analytics Generation Versioning

### analytics_generation_version

Every analytics and insights document carries `analytics_generation_version` immediately after `schema_version`. This tracks the methodology used to compute the data, independently from the document structure.

**Rules:**

| Rule | Detail |
|------|--------|
| Initial value | `1` for all collections on first creation |
| Increment condition | Calculation methodology changes |
| Increment examples | Improved habit score formula, changed percentile interpolation method, fixed aggregation bug, added new weighting scheme, changed distribution bucket boundaries |
| Non-increment examples | Same formula applied to new data, cosmetic field name changes (that's schema_version) |
| Reader behavior | May use `analytics_generation_version` to determine if cached results were computed with an outdated methodology |
| Writer behavior | Always writes current `analytics_generation_version` |

### Interaction with schema_version

| Scenario | schema_version | analytics_generation_version | Meaning |
|----------|---------------|------------------------------|---------|
| Initial release | 1 | 1 | Baseline |
| Bug fix in aggregation formula | 1 | 2 | Same document shape, better calculation |
| New field added to document | 2 | 2 | Document restructured, same methodology |
| New methodology + new field | 2 | 2 | Both changed in same release |
| Algorithm improvement only | 1 | 3 | Same doc shape, third iteration of calculation |

### Why independent versioning matters for Insights

As Trackora Insights evolves, habit scoring and recommendation algorithms will improve significantly. Without `analytics_generation_version`:

- An improved habit score could not be distinguished from a stale one
- Users comparing "this week's insights" vs "last week's" would see methodology changes mixed with real behavioral changes
- The system could not detect when recommendations should be regenerated due to algorithmic improvements

With `analytics_generation_version`:

- The UI can display "insights updated to generation 2" when methodology changes
- Trend analysis can filter out methodology shifts from actual behavioral shifts
- The aggregation service can detect stale documents needing regeneration

---

## 5. Collection-Level Version Tracking

### system_schema collection

A single document in `system_schema` tracks the current versions for every collection:

```json
{
  "_id": "collection_schema",
  "schema_version": 1,
  "collections": {
    "analytics_games": { "schema": 1, "generation": 1 },
    "analytics_daily": { "schema": 1, "generation": 1 },
    "analytics_weekly": { "schema": 1, "generation": 1 },
    "analytics_monthly": { "schema": 1, "generation": 1 },
    "analytics_trends": { "schema": 1, "generation": 1 },
    "analytics_sessions": { "schema": 1, "generation": 1 },
    "insights_habits": { "schema": 1, "generation": 1 },
    "insights_recommendations": { "schema": 1, "generation": 1 },
    "system_metadata": { "schema": 1 },
    "system_jobs": { "schema": 1 }
  },
  "generation_history": [
    {
      "generation_id": "gen_analytics_v1",
      "applied_at": ISODate("2026-06-20T00:00:00Z"),
      "from_generation": 0,
      "to_generation": 1,
      "collections_affected": "*",
      "change": "Initial analytics generation"
    }
  ],
  "migration_history": [
    {
      "migration_id": "v2_0_0_analytics_initial",
      "applied_at": ISODate("2026-06-20T00:00:00Z"),
      "from_version": 0,
      "to_version": 1,
      "collections_affected": "*",
      "checksum": "SHA-256-hash"
    }
  ],
  "generated_at": ISODate("2026-06-20T06:00:00Z")
}
```

### system_metadata collection

The `system_metadata` document also tracks the globally active analytics generation version:

```json
{
  "_id": "analytics_state",
  "analytics_generation_version": 1,
  "analytics_schema_version": 1,
  ...
}
```

### Startup version check flow

```
Application startup
    │
    ▼
Read system_metadata.analytics_generation_version
    │
    ├── matches app's expected version  →  proceed normally
    │
    └── is lower than app's expected version
            │
            ▼
        Read system_schema for per-collection versions
            │
            ├── analytics collections need update
            │       → trigger regeneration or migration
            │
            └── only generation needs bump
                    → update system_schema and system_metadata
                    → flag stale documents for regeneration
```

---

## 6. Document Evolution Rules

### Rule D1 — Additive Changes Are Preferred

When evolving a document, prefer adding optional fields over:
- Modifying existing field types
- Removing fields
- Restructuring embedded documents

**Rationale:** Additive changes do not require incrementing `schema_version` and do not break readers.

### Rule D2 — Breaking Changes Require schema_version Increment

Any change that could cause a reader to misinterpret data requires a `schema_version` increment. Examples:
- Changing a field's type (e.g., `int` → `float`)
- Removing a field entirely
- Restructuring an embedded document
- Changing a required field to optional (readers expecting the field may crash)

### Rule D3 — Methodology Changes Require analytics_generation_version Increment

Any change to how data is computed requires a generation increment, even if the document shape is identical. Examples:
- Changing the habit score formula
- Using a different percentile calculation method
- Fixing a bug in the aggregation query
- Changing distribution bucket boundaries

### Rule D4 — One Version Per Collection Per Change

Each version increment applies to a single collection. Different collections may have different `schema_version` and `analytics_generation_version` values at the same point in time.

Example scenario:

| Collection | schema_version | analytics_generation_version | Why |
|-----------|---------------|------------------------------|-----|
| `analytics_daily` | 1 | 1 | Unchanged |
| `analytics_games` | 2 | 1 | Added `session_distribution` field |
| `analytics_trends` | 1 | 2 | Improved trend calculation |
| `insights_habits` | 1 | 3 | Third revision of habit scoring |

### Rule D5 — System Collections Change Rarely

`system_metadata`, `system_jobs`, and `system_schema` are operational infrastructure. Their `schema_version` should change only when the operational metadata structure itself changes — not when analytics collections evolve.

---

## 7. Collection Migration Strategy

Trackora uses two strategies for evolving MongoDB data:

### Strategy A: Regeneration (Preferred)

Delete documents in a collection and recompute them from SQLite.

| Aspect | Detail |
|--------|--------|
| **When to use** | Schema changes, generation changes, bug fixes, data corruption recovery |
| **Effort** | Low — computation logic already exists |
| **Risk** | Low — no data loss (SQLite is source of truth) |
| **Downtime** | Collection unavailable during regeneration (seconds to minutes) |
| **Rollback** | Trivial — don't regenerate, or regenerate with old logic |

**Regeneration workflow:**

```
1. Read all sessions from SQLite
2. Apply new aggregation logic
3. Upsert into target MongoDB collection
4. Update system_schema with new version
5. Update system_metadata generation version
```

### Strategy B: True Migration (Exception)

Transform documents in-place without touching SQLite.

| Aspect | Detail |
|--------|--------|
| **When to use** | Opt-In collections (insights_*), collections with user-contributed data, collections where SQLite rebuild is expensive |
| **Effort** | Medium — requires migration script per version step |
| **Risk** | Medium — in-place transformation may fail partway |
| **Downtime** | Collection unavailable during migration |
| **Rollback** | Requires inverse migration script or restore from backup |

**True migration workflow:**

```
1. Read system_schema to determine current version
2. For each document in collection:
     a. Read document
     b. Transform to new schema/generation
     c. Write transformed document
3. Verify transformed document count matches
4. Update system_schema with new version
```

---

## 8. Regeneration vs Migration Decision Tree

```
Is the data rebuildable from SQLite?
    │
    ├── YES ──────────────────────────► Use Regeneration (Strategy A)
    │                                      │
    │                                      └── All analytics_* collections
    │
    └── NO
            │
            Is it an Opt-In (insights_*) collection with user data?
            │
            ├── YES ───────────────────► Use True Migration (Strategy B)
            │
            └── Is it a system collection (system_*)?
                    │
                    ├── YES ───────────► Use True Migration (Strategy B)
                    │                       (or manual version bump)
                    │
                    └── NO ────────────► Investigate — this should not happen
```

### Decision Summary by Collection

| Collection | Default Strategy | Exception |
|-----------|-----------------|-----------|
| `analytics_games` | Regeneration | — |
| `analytics_daily` | Regeneration | — |
| `analytics_weekly` | Regeneration | — |
| `analytics_monthly` | Regeneration | — |
| `analytics_trends` | Regeneration | — |
| `analytics_sessions` | Regeneration | — |
| `insights_habits` | Regeneration | True migration if user annotations are added |
| `insights_recommendations` | Regeneration | True migration if user feedback (dismissed/kept) is stored |
| `system_metadata` | True migration | Single document — manual update |
| `system_jobs` | True migration | Append-only logs — no migration needed for schema changes |
| `system_schema` | True migration | Single document — manual update |

---

## 9. Backward Compatibility

### Reader Compatibility

All MongoDB readers must be compatible with documents written by older versions of the application.

**Rules:**

| Rule | Detail |
|------|--------|
| R1 | Readers must ignore unknown fields (automatic with MongoDB) |
| R2 | Readers must handle missing optional fields (use defaults or null checks) |
| R3 | Readers must not assume field ordering beyond `schema_version` being first |
| R4 | Readers must tolerate `analytics_generation_version` values higher than expected (fall back to simpler display) |
| R5 | Readers must tolerate `schema_version` values higher than expected (read known fields, skip unknown) |

### Writer Compatibility

Writers must not create documents that older readers cannot handle.

**Rules:**

| Rule | Detail |
|------|--------|
| W1 | Writers must not remove fields that older readers expect (increment `schema_version` instead, and keep old fields until all readers upgrade) |
| W2 | Writers must not rename fields without a deprecation window |
| W3 | Writers should add new fields as optional for at least one minor release before considering them required |

### Deprecation Window

When a field is to be removed:

```
v2.0.0:  Field marked as deprecated in documentation, still written
v2.1.0:  Field still written, readers warned about removal
v2.2.0:  Field still written (regeneration still produces it)
v3.0.0:  Field may be removed (schema_version incremented)
```

This two-major-release deprecation window ensures users upgrading from very old versions never encounter broken readers.

---

## 10. Forward Compatibility

Forward compatibility means documents written by a newer version of the application can still be processed by an older version.

### Automatic Forward Compatibility

MongoDB's document model provides automatic forward compatibility for most changes:
- **New optional fields**: Old readers simply ignore them
- **New collections**: Old readers never query them
- **Higher `schema_version`**: Old readers read known fields, skip unknown

### Limited Forward Compatibility

Some changes break forward compatibility:
- **Required field removal**: Old reader writes field, new reader expects it → old data is fine, new reader works
- **New required fields**: Old writer doesn't produce them → new reader may crash → **must use regeneration**
- **Type changes**: Old writer produces int, new reader expects string → **breaks forward compat**

### Forward Compatibility Constraints

| Change | Forward Compatible? | Mitigation |
|--------|-------------------|------------|
| Adding optional field | Yes | Automatic |
| Adding required field | No | Must be added as optional first, made required in a later release |
| Removing field | Yes (reader ignores unknown) | But old reader may still have code referencing it → use deprecation window |
| Changing field type | No | Must add new field with new name, deprecate old field |
| Changing embedded structure | Depends | Prefer additive changes to embedded documents |

---

## 11. Breaking Change Handling

### What Constitutes a Breaking Change

A change is breaking if:
- An older reader cannot read a newer document without data loss or errors
- A newer reader cannot read an older document without errors
- A computation produces different (and incompatible) results for the same input

### Breaking Change Process

```
1. Identify the change is breaking
       │
       ▼
2. Is regeneration possible?
       │
       ├── YES → Regenerate all documents in the collection
       │           │
       │           └── Increment schema_version or analytics_generation_version
       │
       └── NO  → True migration required
                    │
                    ├── Write migration script
                    ├── Test on development data
                    ├── Run on production data
                    └── Verify correctness
       │
       ▼
3. Update system_schema
4. Update system_metadata (if generation version changed)
5. Document the change in CHANGELOG
```

### Breaking Change Types and Handling

| Type | Example | Handling | Version Impact |
|------|---------|----------|----------------|
| Field removal | Remove `is_partial` from analytics_daily | Regenerate collection | schema_version++ |
| Type change | `average_daily_seconds` float→int | New field, deprecate old | schema_version++ |
| Field addition (required) | Add required `peak_hour` | Add as optional first, then required in next release | schema_version++ (when made required) |
| Algorithm change | Different percentile method | Regenerate with new algorithm | analytics_generation_version++ |
| Bucket boundary change | 0–15m → 0–10m, 10–30m | Regenerate analytics_sessions | analytics_generation_version++ |
| New collection | Add analytics_achievements | No breaking change — new collection | No version impact |

### Emergency Breaking Change

If a bug produces incorrect data that must be fixed immediately:

```
1. Identify affected documents
2. Regenerate affected collection(s)
3. Increment analytics_generation_version
4. Update system_schema
5. Deploy fix
```

No schema migration is needed because regeneration produces correct data directly.

---

## 12. Migration Workflow

### Regeneration Workflow (Strategy A)

```
┌──────────────────────────────────────────────────────────────────────┐
│                  Analytics Aggregation Service                         │
│                                                                       │
│  1. Read system_metadata → get last_session_processed                 │
│  2. Read system_schema → get target versions for each collection      │
│  3. For each analytics collection that needs regeneration:            │
│       a. Read raw data from SQLite                                    │
│       b. Apply current aggregation logic                              │
│       c. Upsert documents into MongoDB collection                     │
│       d. Verify document count and integrity                          │
│  4. Update system_schema → set new versions                           │
│  5. Update system_metadata → update generation version                │
│  6. Write completion record to system_jobs                            │
└──────────────────────────────────────────────────────────────────────┘
```

### True Migration Workflow (Strategy B)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Migration Manager (MongoDB)                        │
│                                                                       │
│  1. Create backup of affected MongoDB collections                     │
│  2. Record start in system_jobs (status: "running")                   │
│  3. For each document in target collection:                           │
│       a. Read document                                                │
│       b. Apply transformation function                                │
│       c. Validate transformed document against schema                 │
│       d. Write transformed document                                   │
│  4. Verify total count matches original                               │
│  5. Update system_schema → set new version                            │
│  6. Record completion in system_jobs (status: "completed")            │
│  7. Old backup retained for rollback window (7 days)                  │
└──────────────────────────────────────────────────────────────────────┘
```

### Migration Script Structure

Each migration should be an idempotent function:

```python
# Future migration script pattern (conceptual — not production code)
def migrate_analytics_daily_v1_to_v2(mongo_client, db_name):
    """
    Migration: analytics_daily schema_version 1 → 2
    Change: Add 'peak_hour' field computed from hourly_breakdown
    """
    db = mongo_client[db_name]
    collection = db["analytics_daily"]

    updated = 0
    for doc in collection.find({"schema_version": 1}):
        if "hourly_breakdown" in doc and not ("peak_hour" in doc):
            peak = max(doc["hourly_breakdown"], key=lambda h: doc["hourly_breakdown"][h])
            collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"peak_hour": int(peak), "schema_version": 2}}
            )
            updated += 1

    return updated
```

---

## 13. Rollback Workflow

### Rollback via Regeneration (Strategy A)

Since analytics collections are rebuildable from SQLite, rolling back is straightforward:

```
1. Deploy previous version of the application
2. Run the Analytics Aggregation Service
3. System reads old system_schema versions
4. Regeneration produces documents matching the old methodology
```

No explicit rollback script needed — regeneration naturally produces the correct output for whatever code version runs it.

### Rollback via Restore (Strategy B)

For collections that use true migrations:

```
1. Identify the migration that needs rollback
2. If backup exists (retained for 7 days):
     a. Drop the affected collection(s)
     b. Restore from backup
     c. Update system_schema to pre-migration versions
3. If no backup exists:
     a. Regenerate from SQLite (if possible)
     b. OR run inverse migration script
     c. OR accept data loss and start fresh
```

### Rollback Scenarios

| Scenario | Rollback Method | Risk |
|----------|----------------|------|
| Analytics release with wrong aggregation logic | Regenerate with fixed logic (or old version) | None |
| Insight release with broken habit score | Regenerate insights_habits | None (if SQLite-backed) |
| True migration failed mid-way | Restore from backup | None (if backup exists) |
| Schema migration broke field mapping | Restore from backup OR regenerate from SQLite | Low |
| User downgrades application version | Regeneration on startup produces compatible docs | None |

### Downgrade Protection

When the application starts with a lower version than last run:

```
1. Read system_schema
2. Read system_metadata.analytics_generation_version
3. Compare with app's expected generation version

If app is OLDER than the stored generation version:
    ├── App CAN still read analytics_* documents
    │   (older generation docs are a subset of newer — additive fields ignored)
    │
    ├── App SHOULD NOT write new analytics
    │   (would overwrite newer-generation documents with older methodology)
    │
    └── App MUST fall back to SQLite live computation
        (same as if MongoDB were unavailable)
```

If the app must write (e.g., after a forced downgrade), it regenerates all analytics collections. This is safe because:
- Regeneration rewrites documents with the app's current generation version
- The `system_schema` is updated to match
- The `system_metadata` generation version is updated
- On next upgrade, the newer app detects its generation is newer and regenerates again

---

## 14. Multi-Version Coexistence

### What Multi-Version Coexistence Means

Multiple `schema_version` or `analytics_generation_version` values may exist in the same collection simultaneously during migration windows. This happens when:
- A migration is applied incrementally (not all documents updated atomically)
- A user runs a version that only regenerates a subset of documents
- Two application versions alternated writes to the same database

### How Coexistence Works

```
Collection: analytics_daily

Document 1: { schema_version: 1, generation_version: 1, date: "2026-01-15", ... }
Document 2: { schema_version: 2, generation_version: 1, date: "2026-06-19", ... }
Document 3: { schema_version: 1, generation_version: 2, date: "2026-03-10", ... }
```

Readers must handle all three documents correctly:
- Document 1: schema v1, generation v1 — baseline
- Document 2: schema v2, generation v1 — new structure, old methodology  
- Document 3: schema v1, generation v2 — old structure, new methodology

### Reader Strategy for Mixed Versions

```python
# Conceptual reader logic (not production code)
def read_daily_stats(document):
    # Schema version tells us the document structure
    if document["schema_version"] >= 2:
        peak_hour = document.get("peak_hour")  # field added in schema v2
    else:
        peak_hour = compute_peak_hour(document.get("hourly_breakdown"))

    # Generation version tells us the methodology quality
    if document["analytics_generation_version"] >= 2:
        confidence = "high"  # improved algorithm
    else:
        confidence = "low"   # legacy algorithm

    return {...}
```

### When Coexistence is Safe

| Scenario | Safe? | Explanation |
|----------|-------|-------------|
| Different schema_version in same collection | Yes | Readers handle per-document — unknown fields ignored |
| Different generation_version in same collection | Yes | Display may note "mixed generation" but no data loss |
| Different schema_version during regeneration | Yes | Regeneration is atomic per collection — old docs replaced during scan |
| Different generation_version after partial regeneration | Yes | Readers display data, may flag as stale |

### When Coexistence Requires Action

If a reader detects a mix of versions that could cause incorrect analytics:

```
1. Reader logs warning: "Mixed schema versions in analytics_daily"
2. Suggestion: run full regeneration to normalize versions
3. Analytics service may auto-trigger regeneration at next scheduled run
```

---

## 15. Future v3/v4 Upgrade Paths

### v2.x (Current) — MongoDB Foundation

- Analytics collections at initial versions (schema_version: 1, generation: 1)
- System collections tracking versions
- Regeneration is the primary evolution mechanism

### v3.0 — Parallel Analytics Storage

**Expected changes:**
- Some analytics collections may gain fields as usage patterns are better understood
- `analytics_achievements` collection becomes active (if implemented)
- Generation versions may increment as aggregation algorithms improve
- True migrations may be introduced for `insights_*` collections if user annotations are added

**Upgrade path from v2.x to v3.0:**

```
1. Application detects v2 analytics → reads system_schema
2. For each collection:
     a. If generation version is below v3 target → regenerate with v3 logic
     b. If schema version is below v3 target → regenerate or migrate
3. All migrations use regeneration (preferred) or true migration (exception)
4. Update system_schema to v3 versions
```

**Breaking changes possible:**
- New required fields in analytics collections (if optional→required transition window completes)
- Algorithm changes that produce materially different aggregates (generation version increment)

### v4.0 — Advanced Intelligence

**Expected changes:**
- `insights_*` collections may have complex schemas with user annotations
- `insights_habits` may store user-corrected data (e.g., "mark this insight as inaccurate")
- True migrations become more common for Opt-In collections
- Cloud sync may introduce remote schema version management

**Upgrade path from v3.x to v4.0:**

```
1. Application detects v3 analytics → reads system_schema
2. For analytics_* collections:
     → Regeneration preferred (as always)
3. For insights_* collections:
     → If user annotations exist → backup → migration → verify
     → If no user annotations → regenerate from analytics_*
4. Update system_schema to v4 versions
```

**Potential breaking changes:**
- Schema restructuring in `insights_*` for new insight types
- Deprecated fields removed (end of deprecation window from v3.x)
- New collections added for recommendations

### v5.0+ — Long-Term Evolution

- Historical schema versions may be pruned from reader code (only supporting v3+ for example)
- Very old documents may be re-generated to normalize versions
- `system_schema` may need cleanup of migration history for extremely old entries

---

## 16. Relationship to SQLite Migrations

### Independent Versioning

SQLite and MongoDB have independent version tracking:

```
SQLite:  _migrations table  +  schema.json  +  MigrationManager
MongoDB: system_schema      +  system_metadata  +  Regeneration/Migration
```

These are not synchronized. A MongoDB migration may be triggered by:
- A change in the Analytics Aggregation Service code
- A change in how SQLite data should be aggregated
- A pure MongoDB schema evolution (no SQLite change)

### When SQLite Migrations Trigger MongoDB Actions

| SQLite Change | MongoDB Action | Reason |
|--------------|----------------|--------|
| New column added to `games` | Regenerate `analytics_games` | New data available for aggregation |
| New column added to `sessions` | Regenerate affected collections | Aggregation logic may use new field |
| Schema migration completed | No automatic action | MongoDB aggregates independently |
| Data migration (e.g., session time correction) | Regenerate affected collections | Wrong data in aggregates |

### When MongoDB Changes Without SQLite

| MongoDB Change | SQLite Impact | Reason |
|----------------|--------------|--------|
| analytics_generation_version increment | None | Pure algorithm improvement |
| New MongoDB-only field derived from SQLite | None | Computed field, not stored in SQLite |
| Collection index change | None | Performance optimization |
| schema_version increment for optional field | None | Additive change, backward compatible |

---

## 17. Testing Strategy

### Version Compatibility Tests

| Test | Description |
|------|-------------|
| Read v1 documents with v2 reader | Verify all v1 fields can be read |
| Read v2 documents with v1 reader | Verify known fields readable, unknown fields ignored |
| Read mixed-version collection | Verify reader handles per-document version checking |
| Write with current version | Verify documents have correct schema_version and analytics_generation_version |

### Migration Tests

| Test | Description |
|------|-------------|
| Regeneration from empty SQLite | Produces empty MongoDB collection |
| Regeneration from populated SQLite | Produces correct aggregate data |
| Regeneration idempotency | Running twice produces identical documents |
| True migration (if applicable) | Transformation produces correct output |
| Migration rollback via regeneration | Rollback leaves correct data |

### Version Tracking Tests

| Test | Description |
|------|-------------|
| system_schema reflects actual versions | Each collection's stored version matches document versions |
| system_metadata matches system_schema | Generation version is consistent |
| New document uses correct versions | Writer sets schema_version and analytics_generation_version |
| Old document update preserves version | If regeneration re-processes old data, it gets current version |

### Upgrade/Downgrade Tests

| Test | Description |
|------|-------------|
| Upgrade from v2 to v3 | Existing documents readable after upgrade |
| Downgrade from v3 to v2 | Newer documents readable by older reader (forward compat) |
| Upgrade after downgrade | No data loss, no orphan documents |

---

## 18. Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-V01 | Every analytics document contains both `schema_version` and `analytics_generation_version` | Document model review |
| AC-V02 | `system_schema` tracks both versions per collection | Document model review |
| AC-V03 | Readers handle `schema_version` values up to 2 versions ahead of their own | Unit test |
| AC-V04 | Readers handle `analytics_generation_version` values up to 3 versions ahead of their own | Unit test |
| AC-V05 | Unknown fields in documents are silently ignored (MongoDB native) | Unit test |
| AC-V06 | Regeneration from SQLite produces documents with current `schema_version` | Integration test |
| AC-V07 | Rollback via regeneration produces correct data for the old version | Integration test |
| AC-V08 | `system_schema` is updated after every regeneration or migration | Integration test |
| AC-V09 | `system_metadata.analytics_generation_version` matches `system_schema` | Integration test |
| AC-V10 | Mixed-version collection (v1 + v2 documents) is queryable without error | Integration test |
| AC-V11 | Downgraded application falls back to SQLite live computation gracefully | Integration test |
| AC-V12 | Version compatibility tests pass for all 8 analytics/insights collections | Test suite |
| AC-V13 | No MongoDB migration can cause data loss in SQLite (SQLite is never modified) | Architecture review |

---

## Appendix A: Version History Tracking

Every `schema_version` and `analytics_generation_version` change should be recorded in the version history below as this specification evolves.

| Date | Collection | Version Type | From | To | Reason |
|------|-----------|-------------|------|----|--------|
| — | — | — | — | — | Initial specification |

## Appendix B: Quick Reference Card

| Concept | Field | Scope | Increment When |
|---------|-------|-------|----------------|
| Document structure | `schema_version` | Per document | Breaking field/type changes |
| Calculation methodology | `analytics_generation_version` | Per document | Algorithm/formula changes |
| Collection tracking | `system_schema.collections` | Per collection | Either version changes |
| Global tracking | `system_metadata` | Global | Generation version changes |

| Operation | Collections Affected | Strategy |
|-----------|---------------------|----------|
| New field (optional) | 1 | Regeneration |
| New field (required) | 1 | Add optional first → later make required |
| Field removal | 1 | Regeneration after deprecation window |
| Algorithm change | 1–N | Regeneration |
| Bug fix in aggregation | 1 | Regeneration |
| New collection | 1 | Fresh computation |
| Schema restructure | 1 | Regeneration or true migration |
