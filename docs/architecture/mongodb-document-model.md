# MongoDB Document Model Design

**Version:** 2.0.0-draft  
**Status:** Architecture Design  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  
**Phase:** 11 — MongoDB Foundation

---

## Table of Contents

1. [Document Versioning Strategy](#document-versioning-strategy)
2. [Collection Relationships](#collection-relationships)
3. [Rebuild Strategy](#rebuild-strategy)
4. [Storage Tier Classification](#storage-tier-classification)
5. [Collection Designs](#collection-designs)
   - [analytics_games](#analytics_games)
   - [analytics_daily](#analytics_daily)
   - [analytics_weekly](#analytics_weekly)
   - [analytics_monthly](#analytics_monthly)
   - [analytics_trends](#analytics_trends)
   - [analytics_sessions](#analytics_sessions)
   - [insights_habits](#insights_habits)
   - [insights_recommendations](#insights_recommendations)
   - [system_metadata](#system_metadata)
   - [system_jobs](#system_jobs)
   - [system_schema](#system_schema)

---

## Document Versioning Strategy

### schema_version

Every document across all collections carries a top-level `schema_version` integer field. This is mandatory and must be the first field in every document.

| schema_version | Meaning |
|----------------|---------|
| 1 | Initial version for all collections |

Rules:
- `schema_version` is incremented on **breaking** structural changes (field removal, type change, required→optional reversal)
- `schema_version` is NOT incremented on additive changes (new optional fields, new indexes)
- Readers must handle documents with `schema_version` equal to or lower than their expected version
- Writers always write the current `schema_version`

### analytics_generation_version

Every analytics and insights collection carries a top-level `analytics_generation_version` integer field. This is mandatory for all analytics and insights collections.

| Field | Tracks | Example Change |
|-------|--------|----------------|
| `schema_version` | Document structure | Adding/removing fields, changing types |
| `analytics_generation_version` | Calculation methodology | Improving a habit score formula, changing percentile algorithm |

**Why independent versioning is needed:**

- `schema_version` changes when the document shape changes (new fields, removed fields, type changes)
- `analytics_generation_version` changes when the **computation logic** changes while the document shape remains identical

**Example:**

| Version | schema_version | analytics_generation_version | Change |
|---------|---------------|------------------------------|--------|
| v1 | 1 | 1 | Initial analytics release |
| v2 | 1 | 2 | Habit score formula improved — same document fields, better calculation |
| v3 | 2 | 2 | New `peak_hour` field added to analytics_daily — document structure changed |

Rules:
- `analytics_generation_version` starts at `1` for all collections
- Incremented when computation methodology changes (algorithm improvement, bug fix in aggregation, new weighting scheme)
- NOT incremented when document structure changes (that is `schema_version`)
- Both fields may increment in the same release, but always independently
- Readers must compare `analytics_generation_version` to determine if cached results used an older methodology

### document_version (optional)

Certain collections may carry a secondary `document_version` field for sub-document or embedded-array versioning. This is **optional** and used only where embedded documents may evolve independently of the parent document schema.

| Collection | Uses document_version | Rationale |
|-----------|----------------------|-----------|
| `analytics_daily` | No | Single-layer document |
| `analytics_weekly` | Yes (on `daily_breakdown` entries) | Daily breakdown entries may gain fields without changing the weekly document schema |
| `analytics_monthly` | Yes (on `daily_breakdown` entries) | Same reasoning as weekly |
| `analytics_sessions` | Yes (on `distribution` buckets) | Distribution bucket structure may expand |
| All others | No | Single-layer documents |

---

## Collection Relationships

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              SQLite (Source of Truth)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  ┌──────────┐           │
│  │  games   │  │ sessions │  │ active_sessions   │  │ settings │           │
│  └──────────┘  └──────────┘  └──────────────────┘  └──────────┘           │
└──────────────────────┬─────────────────────────────────────────────────────┘
                       │
                       ▼  (Analytics Aggregation Service)
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
┌───────────────┐ ┌──────────┐ ┌────────────────┐
│ analytics_*   │ │insights_*│ │   system_*     │
│               │ │          │ │                │
│ analytics_    │ │ insights_│ │ system_        │
│  daily ───────┼─┤  habits  │ │  metadata      │
│  weekly ──────┼─┤  recom-  │ │  jobs          │
│  monthly ─────┼─┤  mend-   │ │  schema        │
│  games        │ │  ations  │ │                │
│  sessions     │ │          │ │                │
│  trends       │ │          │ │                │
└───────┬───────┘ └──────────┘ └────────────────┘
        │
        │  analytics_trends reads from analytics_daily/weekly/monthly
        │  insights_* reads from analytics_*
        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              UI / Dashboard                                 │
└────────────────────────────────────────────────────────────────────────────┘
```

### Key relationships

| Source | Target | Relationship | Description |
|--------|--------|-------------|-------------|
| SQLite `sessions` | `analytics_daily` | Derived | Each day's sessions → one analytics_daily document |
| `analytics_daily` | `analytics_weekly` | Aggregated | 7 daily documents → one analytics_weekly |
| `analytics_weekly` | `analytics_monthly` | Aggregated | ~4 weekly documents → one analytics_monthly |
| `analytics_daily` | `analytics_games` | Merged | Per-game daily data merged into game analytics document |
| `analytics_daily` + `analytics_weekly` + `analytics_monthly` | `analytics_trends` | Computed | Period-over-period comparison produces trend snapshots |
| `analytics_daily` | `analytics_sessions` | Summarized | Session distribution data extracted from daily aggregation |
| `analytics_*` | `insights_habits` | Computed | Higher-order habit analysis from aggregate data |
| `analytics_*` | `insights_recommendations` | Computed | Recommendation engine reads aggregate data, writes recommendations |
| `system_metadata` | All `analytics_*` | Checkpoint | Last processed session ID drives incremental aggregation |

---

## Rebuild Strategy

### Tiers

| Tier | Definition | Collections |
|------|------------|-------------|
| **SQLite Rebuildable** | Full collection can be regenerated from SQLite | analytics_games, analytics_daily, analytics_weekly, analytics_monthly, analytics_sessions, analytics_trends |
| **MongoDB Rebuildable** | Collection can be regenerated from other MongoDB collections | insights_habits, insights_recommendations |
| **Not Rebuildable** | Collection contains operational metadata that cannot be reconstructed | system_metadata (checkpoint state), system_jobs (job history), system_schema (version tracking) |

### What happens if collection is deleted?

| Collection | Effect | Recovery |
|-----------|--------|----------|
| `analytics_games` | Dashboard game stats unavailable | Full rebuild from SQLite |
| `analytics_daily` | Daily charts unavailable | Full rebuild from SQLite |
| `analytics_weekly` | Weekly charts unavailable | Full rebuild from SQLite |
| `analytics_monthly` | Monthly charts unavailable | Full rebuild from SQLite |
| `analytics_trends` | Trend data unavailable | Rebuild from analytics_* collections or full SQLite rebuild |
| `analytics_sessions` | Session distribution charts unavailable | Full rebuild from SQLite |
| `insights_habits` | Habit insights unavailable | Rebuild from analytics_* |
| `insights_recommendations` | Recommendations unavailable | Regenerate — may differ from previous output (algorithm may change) |
| `system_metadata` | Aggregation checkpoint lost | Full re-aggregation from session 0 (safe but slow) |
| `system_jobs` | Job history lost | No user impact — history is informational |
| `system_schema` | Schema version tracking lost | Can be recreated with current version values |

---

## Storage Tier Classification

| Tier | Collections | Sync Policy | Backup Priority |
|------|-------------|-------------|-----------------|
| **Analytics** | analytics_games, analytics_daily, analytics_weekly, analytics_monthly, analytics_trends, analytics_sessions | Never (local only) | High — rebuildable but expensive to regenerate |
| **Insights** | insights_habits, insights_recommendations | Opt-in with user consent | Medium — rebuildable from analytics |
| **System** | system_metadata, system_jobs, system_schema | Never (local only) | High — cannot be rebuilt from source data |

---

## Collection Designs

---

### analytics_games

#### 1. Purpose

Per-game analytics snapshot. Stores lifetime statistics, trend summaries, and comparison data for every tracked game. Used by the dashboard to display per-game stats and by the game list view for sorting and filtering.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service (after each session end, or on daily schedule) |
| **Reads** | UI dashboard controller, game list controller, trend analyzer, insight engine |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "game_id": 42,
  "game_name": "Counter-Strike 2",
  "platform": "steam",
  "platform_id": "730",
  "lifetime": {
    "total_seconds": 360000,
    "total_sessions": 150,
    "average_session_seconds": 2400,
    "longest_session_seconds": 14400,
    "shortest_session_seconds": 120,
    "median_session_seconds": 1800,
    "first_played": ISODate("2024-01-15T00:00:00Z"),
    "last_played": ISODate("2026-06-19T23:00:00Z")
  },
  "recent": {
    "last_7_days_seconds": 5400,
    "last_30_days_seconds": 36000,
    "last_90_days_seconds": 108000
  },
  "session_distribution": {
    "under_30min": 45,
    "30min_to_1h": 60,
    "1h_to_2h": 30,
    "2h_to_4h": 12,
    "over_4h": 3
  },
  "weekly_trend": {
    "direction": "up",
    "change_percent": 15.5,
    "comparison_period": "last_7_days_vs_previous_7"
  },
  "is_enabled": true,
  "is_auto_discovered": false,
  "generated_at": ISODate("2026-06-20T06:00:00Z")
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `game_id` | int | References SQLite `games.id` |
| `game_name` | string | Display name cached from SQLite `games.name` |
| `lifetime.total_seconds` | int | Total playtime across all sessions |
| `lifetime.total_sessions` | int | Total completed sessions |
| `lifetime.average_session_seconds` | int | Mean session duration |
| `lifetime.longest_session_seconds` | int | Maximum single session duration |
| `lifetime.first_played` | ISODate | Date of first recorded session |
| `lifetime.last_played` | ISODate | Date of most recent session |
| `generated_at` | ISODate | Timestamp of last aggregation |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `platform` | string | Gaming platform (steam, epic, etc.) |
| `platform_id` | string | Platform-specific game ID |
| `lifetime.shortest_session_seconds` | int | Minimum single session duration |
| `lifetime.median_session_seconds` | int | Median session duration |
| `recent.last_7_days_seconds` | int | Playtime in trailing 7 days |
| `recent.last_30_days_seconds` | int | Playtime in trailing 30 days |
| `recent.last_90_days_seconds` | int | Playtime in trailing 90 days |
| `session_distribution` | object | Count of sessions per duration bucket |
| `weekly_trend` | object | Trend direction, percent change, comparison period label |
| `is_enabled` | bool | Whether game tracking is enabled |
| `is_auto_discovered` | bool | Whether game was auto-discovered |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `game_id` (unique) | Fast lookup by game ID | Unique ascending |
| Primary | `game_name` | Sort and search by name | Ascending |
| Reporting | `lifetime.total_seconds` | Sort games by playtime | Descending |
| Reporting | `recent.last_30_days_seconds` | Find recent most-played games | Descending |
| Reporting | `lifetime.last_played` | Sort by recency | Descending |
| Rebuild | `generated_at` | Identify stale documents during rebuild | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Document | Indefinite | One document per game; compact and permanent |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** YES

Full rebuild: iterate `games` table, aggregate all `sessions` per game_id. All lifetime and recent fields can be computed from raw session data. Session distribution computed from duration_seconds. Weekly trend computed by comparing two trailing windows.

Rebuild cost: O(games × sessions) — acceptable for local execution.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Dashboard most-played | `find().sort({lifetime.total_seconds: -1}).limit(1)` | Top game document |
| Game list | `find({})` with optional `is_enabled` filter | All game documents |
| Game detail | `findOne({game_id: N})` | Single game document |
| Recent top games | `find().sort({"recent.last_30_days_seconds": -1}).limit(5)` | Top 5 documents |
| Rebuild stale check | `find({generated_at: {$lt: cutoff}})` | Stale documents needing refresh |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | 1 per tracked game (typically 10–500) |
| Update frequency | Once per session end, or daily batch |
| Storage per document | ~500 bytes |
| Total storage | ~5–250 KB |

---

### analytics_daily

#### 1. Purpose

One document per calendar day storing total playtime, per-game breakdown, session count, and activity metrics. Primary data source for daily charts, trend computation, and weekly/monthly rollups.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service (after day completes, or on next-day startup) |
| **Reads** | UI dashboard, chart widgets, weekly/monthly aggregation, trend analyzer, insight engine |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "date": ISODate("2026-06-19T00:00:00Z"),
  "date_key": "2026-06-19",
  "total_seconds": 14400,
  "total_sessions": 8,
  "games_played": 3,
  "hourly_breakdown": {
    "0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0,
    "6": 0, "7": 0, "8": 0, "9": 0, "10": 0, "11": 0,
    "12": 0, "13": 0, "14": 0, "15": 0, "16": 0, "17": 0,
    "18": 3600, "19": 5400, "20": 3600, "21": 1800, "22": 0, "23": 0
  },
  "per_game": [
    { "game_id": 42, "game_name": "Counter-Strike 2", "seconds": 7200, "sessions": 4 },
    { "game_id": 17, "game_name": "Stardew Valley", "seconds": 5400, "sessions": 3 },
    { "game_id": 88, "game_name": "Hades", "seconds": 1800, "sessions": 1 }
  ],
  "is_partial": false,
  "generated_at": ISODate("2026-06-20T00:15:00Z")
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `date` | ISODate | Calendar date (midnight UTC) |
| `date_key` | string | ISO date string for query convenience (e.g. "2026-06-19") |
| `total_seconds` | int | Total playtime across all games this day |
| `total_sessions` | int | Total completed sessions this day |
| `games_played` | int | Number of distinct games played |
| `per_game` | array | Array of per-game breakdown objects |
| `generated_at` | ISODate | Timestamp of last aggregation |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `hourly_breakdown` | object | Map of hour→seconds (24 entries, keys "0"–"23") |
| `is_partial` | bool | True if day is still in progress (current day) |
| `peak_hour` | int | Hour with highest playtime (0–23) |
| `average_session_seconds` | int | Mean session duration for this day |
| `longest_session_seconds` | int | Longest single session this day |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `date_key` (unique) | Fast lookup by date | Unique ascending |
| Primary | `date` (unique) | Range queries | Unique ascending |
| Reporting | `total_seconds` | Find peak days | Descending |
| Reporting | `games_played` | Find most diverse days | Descending |
| Rebuild | `generated_at` | Identify stale documents | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Document | Indefinite | One document per day; ~365 documents per year; negligible storage |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** YES

Full rebuild: query `sessions` grouped by `DATE(start_time)`. Sum `duration_seconds`, count sessions, aggregate per-game breakdown. Hourly breakdown requires extracting hour from `start_time`.

Rebuild cost: O(sessions) — single pass over session table with date grouping.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Day lookup | `findOne({date_key: "2026-06-19"})` | Single day document |
| Date range | `find({date: {$gte: start, $lte: end}}).sort({date: 1})` | All days in range |
| Last N days | `find().sort({date: -1}).limit(N)` | Most recent N days |
| Peak days | `find().sort({total_seconds: -1}).limit(10)` | Top 10 most-played days |
| Dashboard today | `findOne({date_key: today_string})` | Current day stats |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | 1 per calendar day (grows by 365/year) |
| Update frequency | Once per day (finalize), or once on next startup |
| Storage per document | ~1 KB (with per_game array for ~5 games) |
| Total storage | ~365 KB/year, ~3.6 MB over 10 years |

---

### analytics_weekly

#### 1. Purpose

One document per ISO week storing aggregated playtime with daily breakdown. Primary data source for weekly charts, weekly trend computation, and monthly rollup input.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service (after week completes) |
| **Reads** | UI dashboard, chart widgets, monthly aggregation, trend analyzer |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "year": 2026,
  "week_number": 25,
  "week_key": "2026-W25",
  "week_start": ISODate("2026-06-15T00:00:00Z"),
  "week_end": ISODate("2026-06-21T00:00:00Z"),
  "total_seconds": 86400,
  "total_sessions": 42,
  "games_played": 5,
  "average_daily_seconds": 12342,
  "active_days": 7,
  "daily_breakdown": [
    { "date_key": "2026-06-15", "total_seconds": 10800, "sessions": 5, "document_version": 1 },
    { "date_key": "2026-06-16", "total_seconds": 14400, "sessions": 7, "document_version": 1 },
    { "date_key": "2026-06-17", "total_seconds": 7200, "sessions": 4, "document_version": 1 },
    { "date_key": "2026-06-18", "total_seconds": 18000, "sessions": 9, "document_version": 1 },
    { "date_key": "2026-06-19", "total_seconds": 14400, "sessions": 8, "document_version": 1 },
    { "date_key": "2026-06-20", "total_seconds": 10800, "sessions": 5, "document_version": 1 },
    { "date_key": "2026-06-21", "total_seconds": 10800, "sessions": 4, "document_version": 1 }
  ],
  "per_game": [
    { "game_id": 42, "game_name": "Counter-Strike 2", "seconds": 43200, "sessions": 18 },
    { "game_id": 17, "game_name": "Stardew Valley", "seconds": 21600, "sessions": 12 },
    { "game_id": 88, "game_name": "Hades", "seconds": 10800, "sessions": 6 },
    { "game_id": 5, "game_name": "Elden Ring", "seconds": 7200, "sessions": 4 },
    { "game_id": 12, "game_name": "Celeste", "seconds": 3600, "sessions": 2 }
  ],
  "generated_at": ISODate("2026-06-22T00:15:00Z")
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `year` | int | ISO year |
| `week_number` | int | ISO week number (1–53) |
| `week_key` | string | Composite key "YYYY-WNN" |
| `week_start` | ISODate | Monday of the week (midnight) |
| `week_end` | ISODate | Sunday of the week (midnight) |
| `total_seconds` | int | Total playtime for the week |
| `total_sessions` | int | Total sessions for the week |
| `games_played` | int | Distinct games played |
| `daily_breakdown` | array | Array of per-day summaries |
| `generated_at` | ISODate | Timestamp of last aggregation |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `average_daily_seconds` | int | Mean playtime per active day |
| `active_days` | int | Days with at least one session |
| `per_game` | array | Array of per-game weekly totals |
| `daily_breakdown[].document_version` | int | Version of daily breakdown entry |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `week_key` (unique) | Fast lookup by ISO week | Unique ascending |
| Primary | `year`, `week_number` (unique compound) | Alternate key for joins | Unique compound |
| Reporting | `total_seconds` | Find peak weeks | Descending |
| Reporting | `year`, `total_seconds` | Year-over-year comparison | Compound descending |
| Rebuild | `generated_at` | Identify stale documents | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Document | Indefinite | 52 documents per year; ~5 KB each; negligible growth |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** YES

Full rebuild: query `sessions` grouped by ISO week and game. Alternatively, aggregate from `analytics_daily` documents for the week range.

Rebuild cost: O(sessions) or O(7 daily documents) — efficient either way.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Current week | `findOne({week_key: current_week})` | Single week document |
| Last N weeks | `find().sort({year: -1, week_number: -1}).limit(N)` | Most recent weeks |
| Year overview | `find({year: Y}).sort({week_number: 1})` | All weeks in a year |
| Weekly trend input | `find({week_key: {$in: [current, previous]}})` | Two weeks for trend comparison |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | 52–53 per year |
| Update frequency | Once per week |
| Storage per document | ~2 KB |
| Total storage | ~100 KB/year, ~1 MB over 10 years |

---

### analytics_monthly

#### 1. Purpose

One document per calendar month storing aggregated playtime with daily breakdown. Long-term trend data source. Most compact analytics collection (12 documents/year).

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service (after month completes) |
| **Reads** | UI dashboard, chart widgets, trend analyzer, insight engine |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "year": 2026,
  "month": 6,
  "month_key": "2026-06",
  "month_start": ISODate("2026-06-01T00:00:00Z"),
  "month_end": ISODate("2026-06-30T23:59:59Z"),
  "total_seconds": 518400,
  "total_sessions": 240,
  "games_played": 8,
  "average_daily_seconds": 17280,
  "active_days": 28,
  "daily_breakdown": [
    { "date_key": "2026-06-01", "total_seconds": 14400, "sessions": 6, "document_version": 1 },
    { "date_key": "2026-06-02", "total_seconds": 10800, "sessions": 5, "document_version": 1 }
  ],
  "weekly_summary": [
    { "week_key": "2026-W23", "total_seconds": 129600, "sessions": 58 },
    { "week_key": "2026-W24", "total_seconds": 144000, "sessions": 62 },
    { "week_key": "2026-W25", "total_seconds": 129600, "sessions": 60 },
    { "week_key": "2026-W26", "total_seconds": 115200, "sessions": 60 }
  ],
  "per_game": [
    { "game_id": 42, "game_name": "Counter-Strike 2", "seconds": 259200, "sessions": 100 },
    { "game_id": 17, "game_name": "Stardew Valley", "seconds": 129600, "sessions": 70 }
  ],
  "generated_at": ISODate("2026-07-01T00:15:00Z")
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `year` | int | Calendar year |
| `month` | int | Calendar month (1–12) |
| `month_key` | string | Composite key "YYYY-MM" |
| `month_start` | ISODate | First day of month (midnight) |
| `month_end` | ISODate | Last day of month (midnight) |
| `total_seconds` | int | Total playtime for the month |
| `total_sessions` | int | Total sessions for the month |
| `games_played` | int | Distinct games played |
| `daily_breakdown` | array | Array of per-day summaries |
| `generated_at` | ISODate | Timestamp of last aggregation |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `average_daily_seconds` | int | Mean playtime per active day |
| `active_days` | int | Days with at least one session |
| `weekly_summary` | array | Summary of each ISO week within the month |
| `per_game` | array | Array of per-game monthly totals |
| `daily_breakdown[].document_version` | int | Version of daily breakdown entry |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `month_key` (unique) | Fast lookup by month | Unique ascending |
| Primary | `year`, `month` (unique compound) | Alternate key | Unique compound |
| Reporting | `total_seconds` | Find peak months | Descending |
| Reporting | `year`, `total_seconds` | Year-over-year comparison | Compound descending |
| Rebuild | `generated_at` | Identify stale documents | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Document | Indefinite | 12 documents per year; ~3 KB each; negligible growth |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** YES

Full rebuild: query `sessions` grouped by calendar month. Alternatively, aggregate from `analytics_weekly` documents for the month range.

Rebuild cost: O(sessions) or O(4–5 weekly documents) — efficient either way.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Current month | `findOne({month_key: current_month})` | Single month document |
| Last N months | `find().sort({year: -1, month: -1}).limit(N)` | Most recent months |
| Year overview | `find({year: Y}).sort({month: 1})` | All months in a year |
| Monthly trend input | `find({month_key: {$in: [current, previous]}})` | Two months for trend comparison |
| Long-term chart | `find().sort({year: 1, month: 1})` | All months (full history) |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | 12 per year |
| Update frequency | Once per month |
| Storage per document | ~3 KB |
| Total storage | ~36 KB/year, ~360 KB over 10 years |

---

### analytics_trends

#### 1. Purpose

Stores pre-computed trend results. Uses MongoDB's computed-value pattern to avoid recalculating trends on every read. Each document represents a trend snapshot for a specific period type at a specific time.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service (after daily/weekly/monthly aggregation completes) |
| **Reads** | UI dashboard, trend charts, insight engine |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "trend_type": "weekly",
  "reference_key": "2026-W25",
  "comparison_key": "2026-W24",
  "current_period_seconds": 86400,
  "previous_period_seconds": 64800,
  "change_seconds": 21600,
  "change_percent": 33.3,
  "direction": "up",
  "is_neutral": false,
  "games_with_increase": 3,
  "games_with_decrease": 2,
  "top_gainer": { "game_id": 42, "game_name": "Counter-Strike 2", "increase_seconds": 10800 },
  "top_loser": { "game_id": 17, "game_name": "Stardew Valley", "decrease_seconds": 3600 },
  "generated_at": ISODate("2026-06-22T00:15:00Z"),
  "source": "analytics_weekly"
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `trend_type` | string | One of: `daily`, `weekly`, `monthly`, `rolling_7d`, `rolling_30d`, `rolling_90d` |
| `reference_key` | string | Period key for the current period (e.g. "2026-06-19", "2026-W25", "2026-06") |
| `comparison_key` | string | Period key for the comparison period |
| `current_period_seconds` | int | Total playtime in the reference period |
| `previous_period_seconds` | int | Total playtime in the comparison period |
| `change_seconds` | int | Difference (current − previous) |
| `direction` | string | One of: `up`, `down`, `flat` |
| `generated_at` | ISODate | Timestamp of trend computation |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `change_percent` | float | Percentage change (null if previous was zero) |
| `is_neutral` | bool | True if both periods had zero playtime |
| `games_with_increase` | int | Count of games with higher playtime |
| `games_with_decrease` | int | Count of games with lower playtime |
| `top_gainer` | object | Game with largest absolute increase |
| `top_loser` | object | Game with largest absolute decrease |
| `source` | string | Source collection used for computation (e.g. "analytics_weekly") |
| `confidence_score` | float | Confidence indicator (0.0–1.0, lower when data is sparse) |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `trend_type`, `reference_key` (unique compound) | Fast lookup by type + period | Unique compound |
| Primary | `trend_type`, `generated_at` | Latest trend by type | Compound descending |
| Reporting | `change_percent` | Find largest trends | Descending |
| Reporting | `trend_type`, `direction` | Filter by direction | Compound |
| Rebuild | `generated_at` | Identify stale/recomputable documents | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Rolling trends (7d, 30d, 90d) | 5 years | Older trends recomputable from analytics_daily |
| Daily trends | 1 year | Fine-grained, recomputable |
| Weekly trends | 5 years | Medium granularity |
| Monthly trends | Indefinite | Most compact, useful for long-term history |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** YES — Indirectly

Trends are computed from analytics_daily/weekly/monthly, which are themselves rebuildable from SQLite. Direct rebuild from SQLite is possible but requires re-aggregating all sessions first.

**Can Be Rebuilt From MongoDB?** YES

Full rebuild from analytics_daily, analytics_weekly, and analytics_monthly collections without touching SQLite.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Dashboard weekly trend | `findOne({trend_type: "weekly", reference_key: current_week})` | Current trend |
| All trends for period | `find({trend_type: {$in: ["daily", "weekly", "monthly"]}, reference_key: period})` | All trend types |
| Trend history | `find({trend_type: "monthly"}).sort({reference_key: -1}).limit(12)` | Last 12 monthly trends |
| Direction filter | `find({trend_type: "weekly", direction: "down"}).sort({change_percent: 1}).limit(5)` | Biggest weekly declines |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | ~470/year (365 daily + 52 weekly + 12 monthly + ~40 rolling snapshots) |
| Update frequency | Once per period completion |
| Storage per document | ~300 bytes |
| Total storage | ~140 KB/year |

---

### analytics_sessions

#### 1. Purpose

Stores session analytics — NOT raw sessions. This collection contains session-length distributions, percentile summaries, and aggregate session metrics. It complies with P8 (No Raw Session Duplication) by storing only computed statistics, never individual session records.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service (periodic or on-demand) |
| **Reads** | UI dashboard, chart widgets, insight engine |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "game_id": 42,
  "game_name": "Counter-Strike 2",
  "period": "lifetime",
  "total_sessions": 150,
  "total_seconds": 360000,
  "duration_distribution": {
    "buckets": [
      { "label": "0–15m", "min_seconds": 0, "max_seconds": 900, "count": 10, "document_version": 1 },
      { "label": "15–30m", "min_seconds": 900, "max_seconds": 1800, "count": 35, "document_version": 1 },
      { "label": "30–60m", "min_seconds": 1800, "max_seconds": 3600, "count": 60, "document_version": 1 },
      { "label": "1–2h", "min_seconds": 3600, "max_seconds": 7200, "count": 30, "document_version": 1 },
      { "label": "2–4h", "min_seconds": 7200, "max_seconds": 14400, "count": 12, "document_version": 1 },
      { "label": "4h+", "min_seconds": 14400, "max_seconds": null, "count": 3, "document_version": 1 }
    ]
  },
  "percentiles": {
    "p10": 600,
    "p25": 1200,
    "p50": 1800,
    "p75": 3600,
    "p90": 7200,
    "p95": 10800,
    "p99": 14400
  },
  "time_of_day_distribution": {
    "morning": { "hours": "6–12", "count": 10, "total_seconds": 18000 },
    "afternoon": { "hours": "12–18", "count": 30, "total_seconds": 54000 },
    "evening": { "hours": "18–24", "count": 90, "total_seconds": 216000 },
    "night": { "hours": "0–6", "count": 20, "total_seconds": 72000 }
  },
  "weekday_distribution": {
    "monday": { "count": 20, "total_seconds": 48000 },
    "tuesday": { "count": 18, "total_seconds": 43200 },
    "wednesday": { "count": 22, "total_seconds": 52800 },
    "thursday": { "count": 20, "total_seconds": 48000 },
    "friday": { "count": 25, "total_seconds": 60000 },
    "saturday": { "count": 25, "total_seconds": 60000 },
    "sunday": { "count": 20, "total_seconds": 48000 }
  },
  "generated_at": ISODate("2026-06-20T06:00:00Z")
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `game_id` | int | References SQLite `games.id` |
| `game_name` | string | Display name cached from SQLite |
| `period` | string | Aggregation period: `lifetime`, `rolling_30d`, `rolling_90d` |
| `total_sessions` | int | Total sessions in the period |
| `total_seconds` | int | Total playtime in the period |
| `generated_at` | ISODate | Timestamp of last aggregation |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `duration_distribution` | object | Binned session duration counts |
| `duration_distribution.buckets[].document_version` | int | Version of bucket entry |
| `percentiles` | object | Session duration percentiles (p10 through p99) |
| `time_of_day_distribution` | object | Session counts by time-of-day block |
| `weekday_distribution` | object | Session counts by day of week |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `game_id`, `period` (unique compound) | Fast lookup by game + period | Unique compound |
| Primary | `game_id`, `total_sessions` | Sort games by session count | Compound descending |
| Reporting | `percentiles.p50` | Median session duration | Descending |
| Reporting | `period`, `generated_at` | Staleness check by period | Compound |
| Rebuild | `generated_at` | Identify stale documents | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Lifetime period | Indefinite | Permanent per-game summary |
| Rolling 30d | 90 days | Overlapping windows, short useful life |
| Rolling 90d | 180 days | Overlapping windows, medium useful life |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** YES

Full rebuild: query all sessions for a game_id, compute duration distribution (bucket by duration_seconds), compute percentiles (sort and sample), compute time-of-day (extract hour from start_time), compute weekday (extract day from start_time). P8 compliance verified — no raw session rows stored, only computed statistics.

Rebuild cost: O(sessions) per game — must iterate all sessions for the game.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Game session analytics | `findOne({game_id: 42, period: "lifetime"})` | Full session analytics for a game |
| Session length comparison | `find({period: "lifetime"}, {game_id: 1, percentiles: 1})` | Percentile data across games |
| Dashboard peak hours | `findOne({game_id: 42}, {time_of_day_distribution: 1})` | Time-of-day breakdown |
| All games summary | `find({period: "lifetime"}, {game_id: 1, total_sessions: 1, total_seconds: 1})` | Quick overview |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | 3 per game (lifetime + 2 rolling periods) × 500 games = 1,500 |
| Update frequency | On session end (lifetime), or daily (rolling) |
| Storage per document | ~800 bytes |
| Total storage | ~1.2 MB |

---

### insights_habits

#### 1. Purpose

Future gaming habit analysis. This collection stores computed insight records describing a user's play patterns, consistency, schedule preferences, and behavioral metrics. Designed for Trackora Insights (Phase D).

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Insight Computation Engine (future Phase D) |
| **Reads** | UI insight dashboard, notification system, recommendation engine |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "insight_type": "consistency_score",
  "period": "rolling_30d",
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-07-20T06:00:00Z"),
  "data": {
    "score": 72,
    "max_score": 100,
    "label": "Consistent Player",
    "description": "You play regularly with moderate variation in session length."
  },
  "source_collections": ["analytics_daily", "analytics_sessions"]
}
```

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "insight_type": "schedule_pattern",
  "period": "rolling_90d",
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-09-20T06:00:00Z"),
  "data": {
    "preferred_day": "saturday",
    "preferred_time_block": "evening",
    "weekday_avg_seconds": 7200,
    "weekend_avg_seconds": 14400,
    "weekend_warrior_ratio": 2.0,
    "most_consistent_hour": 20
  },
  "source_collections": ["analytics_sessions"]
}
```

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "insight_type": "balance_metric",
  "period": "rolling_30d",
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-07-20T06:00:00Z"),
  "data": {
    "games_rotated": 4,
    "primary_game_percent": 55,
    "diversity_score": 65,
    "recommendation": "Try exploring your backlog — you have 12 games with <1 hour playtime."
  },
  "source_collections": ["analytics_games"]
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `insight_type` | string | Type of insight: `consistency_score`, `schedule_pattern`, `balance_metric`, `peak_hours`, `session_trend`, `burnout_risk` |
| `period` | string | Period over which insight was computed: `rolling_7d`, `rolling_30d`, `rolling_90d`, `lifetime` |
| `generated_at` | ISODate | When insight was computed |
| `data` | object | Insight payload (shape varies by insight_type) |
| `source_collections` | array | Collections used to compute this insight |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `valid_until` | ISODate | When this insight becomes stale and should be recomputed |
| `game_id` | int | If insight is game-specific |
| `confidence` | float | Confidence score (0.0–1.0) for the insight |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `insight_type`, `period` (compound) | Latest insight of each type | Compound descending by generated_at |
| Primary | `insight_type`, `generated_at` | History of specific insight type | Compound descending |
| Reporting | `valid_until` | Find expired insights | Ascending |
| Reporting | `game_id`, `insight_type` | Game-specific insights | Compound |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Rolling insights | Indeterminate (regenerated on schedule) | Each computation replaces previous; old documents can be archived or deleted |
| Historical snapshots | 1 year (optional) | If versioned snapshots are kept |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** NO — Indirectly via analytics

Insights are computed from analytics collections, not directly from SQLite. They can be rebuilt from `analytics_*` collections. If analytics collections exist, full insight regeneration is possible. If only SQLite exists, analytics must be regenerated first.

**Can Be Rebuilt From MongoDB?** YES

Full rebuild from `analytics_daily`, `analytics_sessions`, `analytics_games`.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Dashboard insights | `find({valid_until: {$gt: now}})` | All valid current insights |
| Specific insight | `findOne({insight_type: "consistency_score", period: "rolling_30d"}, {sort: {generated_at: -1}})` | Latest consistency score |
| Stale cleanup | `find({valid_until: {$lt: now}})` | Expired insights for regeneration |
| Game-specific | `find({game_id: 42, insight_type: "burnout_risk"})` | Burnout risk for a specific game |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | ~20–50 active insights (each generation replaces previous for the same type/period) |
| Update frequency | Daily or weekly, depending on insight type |
| Storage per document | ~500 bytes |
| Total storage | ~10–25 KB (active set) |

---

### insights_recommendations

#### 1. Purpose

Stores recommendation engine output. Each document is a single recommendation. Recommendations are computed from analytics data and stored for the UI to display. This collection stores recommendations only — not the input data or computation rules.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Recommendation Engine (future Phase E) |
| **Reads** | UI recommendation widget, notification system |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "recommendation_type": "take_break",
  "priority": "medium",
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-06-21T06:00:00Z"),
  "title": "Time for a break?",
  "message": "You've been playing for 3 hours straight. Taking a 15-minute break every hour can help maintain focus.",
  "action": {
    "type": "dismiss",
    "label": "Got it"
  },
  "context": {
    "current_session_seconds": 10800,
    "game_id": 42,
    "game_name": "Counter-Strike 2"
  },
  "source_insights": ["consistency_score", "schedule_pattern"]
}
```

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "recommendation_type": "explore_neglected",
  "priority": "low",
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-07-20T06:00:00Z"),
  "title": "Revisit Stardew Valley",
  "message": "You haven't played Stardew Valley in 2 weeks. Your farm misses you!",
  "action": {
    "type": "launch_game",
    "label": "Launch",
    "game_id": 17,
    "executable_path": "C:\\Games\\Stardew Valley\\Stardew Valley.exe"
  },
  "context": {
    "days_since_last_played": 14,
    "previous_total_seconds": 129600,
    "game_id": 17,
    "game_name": "Stardew Valley"
  },
  "source_insights": ["balance_metric"]
}
```

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "recommendation_type": "continue_streak",
  "priority": "high",
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-06-21T06:00:00Z"),
  "title": "7-day streak!",
  "message": "You've played every day this week. Keep it going!",
  "action": {
    "type": "dismiss",
    "label": "Let's go!"
  },
  "context": {
    "streak_days": 7
  },
  "source_insights": ["consistency_score"]
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_generation_version` | int | Analytics generation version (currently 1) |
| `recommendation_type` | string | One of: `take_break`, `explore_neglected`, `continue_streak`, `improve_balance`, `try_new_game`, `achievement_milestone` |
| `priority` | string | One of: `low`, `medium`, `high` |
| `generated_at` | ISODate | When recommendation was generated |
| `valid_until` | ISODate | When recommendation expires |
| `title` | string | Short display title |
| `message` | string | Full recommendation text |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `action` | object | Optional action payload (dismiss, launch_game, open_url) |
| `context` | object | Contextual metadata (game_id, current session length, streak count) |
| `source_insights` | array | insight_types that triggered this recommendation |
| `dismissed` | bool | Whether user has dismissed this recommendation |
| `display_count` | int | Number of times shown to user |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `priority`, `generated_at` | Active recommendations sorted by priority | Compound descending |
| Primary | `recommendation_type`, `generated_at` | Recommendations of a specific type | Compound descending |
| Reporting | `valid_until` | Expired recommendations for cleanup | Ascending |
| Reporting | `dismissed` | Filter undismissed recommendations | Ascending sparse |
| Reporting | `context.game_id` | Game-specific recommendations | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Active recommendations | Until `valid_until` | Automatically expire |
| Dismissed recommendations | 30 days | Short retention after dismissal |
| Expired undismissed | 7 days | Clean up stale recommendations |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** NO

Recommendations depend on insight data and recommendation rules. They can be regenerated from `insights_habits` (MongoDB) but not directly from SQLite.

**Can Be Rebuilt From MongoDB?** YES — with potential differences

Regeneration produces recommendations based on current analytics data. The output may differ from the original due to algorithm changes or state differences. This is acceptable — recommendations are ephemeral and replaced on each generation.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Active recommendations | `find({valid_until: {$gt: now}, dismissed: {$ne: true}}).sort({priority: -1})` | All active, undismissed recommendations |
| High priority | `find({priority: "high", valid_until: {$gt: now}})` | Urgent recommendations |
| Dismiss | `updateOne({_id: id}, {$set: {dismissed: true}})` | Mark as dismissed |
| Stale cleanup | `deleteMany({valid_until: {$lt: cutoff}})` | Remove expired recommendations |
| Game-specific | `find({"context.game_id": 42})` | Recommendations about a specific game |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | ~5–20 active at any time |
| Update frequency | Generated on session end or daily |
| Storage per document | ~400 bytes |
| Total storage | ~2–8 KB (active set, excluding expired history) |

---

### system_metadata

#### 1. Purpose

Analytics control-plane metadata. Tracks generation state, aggregation checkpoints, schema version, and last successful run. Used by the Analytics Aggregation Service to drive incremental aggregation. Not user-facing.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service |
| **Reads** | Analytics Aggregation Service (startup), diagnostic tools |

#### 3. Example Document

```json
{
  "_id": "analytics_state",
  "schema_version": 1,
  "analytics_schema_version": 1,
  "analytics_generation_version": 1,
  "last_aggregation_run": ISODate("2026-06-20T06:00:00Z"),
  "last_session_processed": 15234,
  "aggregation_state": {
    "daily": { "last_completed": "2026-06-19", "status": "completed" },
    "weekly": { "last_completed": "2026-W25", "status": "completed" },
    "monthly": { "last_completed": "2026-06", "status": "completed" },
    "trends": { "last_completed": "2026-06-20", "status": "completed" },
    "sessions": { "last_completed": "2026-06-20", "status": "completed" },
    "games": { "last_completed": "2026-06-20", "status": "completed" }
  },
  "last_error": null,
  "error_count": 0,
  "generated_at": ISODate("2026-06-20T06:00:00Z")
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `_id` | string | Fixed value: `"analytics_state"` |
| `schema_version` | int | Document schema version (currently 1) |
| `analytics_schema_version` | int | Current schema version for analytics collections |
| `analytics_generation_version` | int | Current analytics generation version for all collections |
| `last_aggregation_run` | ISODate | Timestamp of most recent aggregation attempt |
| `last_session_processed` | int | SQLite sessions.id of the last processed session (for incremental aggregation) |
| `generated_at` | ISODate | Timestamp of last metadata update |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `aggregation_state` | object | Per-collection status tracking (last_completed, status) |
| `last_error` | string | Error message from last failed aggregation (null if no error) |
| `error_count` | int | Running count of consecutive failures |
| `total_jobs_run` | int | Lifetime count of aggregation jobs executed |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `_id` (unique) | Single document lookup | Unique (default _id index) |

No additional indexes needed — there is exactly one document with a fixed `_id`.

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Document | Indefinite | Single document, minimal size, essential for incremental aggregation |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** NO

The checkpoint state (`last_session_processed`) and run timestamps are operational metadata that cannot be reconstructed from source data. If deleted, the aggregation service must fall back to a full re-aggregation from session 0, which is safe but slow.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| State lookup | `findOne({_id: "analytics_state"})` | Full metadata document |
| Checkpoint read | `findOne({_id: "analytics_state"}, {last_session_processed: 1})` | Last processed session ID |
| State update | `updateOne({_id: "analytics_state"}, {$set: {last_aggregation_run: now, ...}})` | Update checkpoint |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | Exactly 1 |
| Update frequency | Once per aggregation run (daily, or more frequent) |
| Storage per document | ~500 bytes |
| Total storage | ~500 bytes (fixed) |

---

### system_jobs

#### 1. Purpose

Operational job history. Records every aggregation job execution for auditing, debugging, and monitoring. Each document represents one job run. Retained for 90 days for operational visibility.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Analytics Aggregation Service |
| **Reads** | Diagnostic tools, support debugging |

#### 3. Example Document

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "job_type": "daily_aggregation",
  "status": "completed",
  "started_at": ISODate("2026-06-20T00:00:00Z"),
  "completed_at": ISODate("2026-06-20T00:00:12Z"),
  "duration_ms": 12000,
  "sessions_processed": 15,
  "target_period": "2026-06-19",
  "collections_written": ["analytics_daily", "analytics_games", "analytics_sessions"],
  "error": null,
  "retry_attempt": 0,
  "trigger": "schedule"
}
```

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "job_type": "monthly_aggregation",
  "status": "failed",
  "started_at": ISODate("2026-07-01T00:00:00Z"),
  "completed_at": ISODate("2026-07-01T00:00:05Z"),
  "duration_ms": 5000,
  "sessions_processed": 0,
  "target_period": "2026-06",
  "collections_written": [],
  "error": "Connection timeout reading SQLite sessions",
  "retry_attempt": 0,
  "retry_of": null,
  "trigger": "schedule"
}
```

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "job_type": "monthly_aggregation",
  "status": "completed",
  "started_at": ISODate("2026-07-01T00:01:00Z"),
  "completed_at": ISODate("2026-07-01T00:01:15Z"),
  "duration_ms": 15000,
  "sessions_processed": 240,
  "target_period": "2026-06",
  "collections_written": ["analytics_monthly"],
  "error": null,
  "retry_attempt": 1,
  "retry_of": ObjectId("...previous_failed_job_id..."),
  "trigger": "retry"
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Document schema version (currently 1) |
| `job_type` | string | One of: `daily_aggregation`, `weekly_aggregation`, `monthly_aggregation`, `trend_computation`, `session_analytics`, `game_analytics`, `full_rebuild`, `insight_generation`, `recommendation_generation` |
| `status` | string | One of: `running`, `completed`, `failed`, `cancelled` |
| `started_at` | ISODate | When job started execution |
| `duration_ms` | int | Execution duration in milliseconds |
| `trigger` | string | How job was triggered: `schedule`, `manual`, `startup`, `retry`, `on_session_end` |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `completed_at` | ISODate | When job completed (null if still running) |
| `sessions_processed` | int | Number of sessions processed in this job |
| `target_period` | string | Period key the job operated on (e.g. "2026-06-19", "2026-W25", "2026-06") |
| `collections_written` | array | List of collections that received writes |
| `error` | string | Error message (null if successful) |
| `retry_attempt` | int | Which retry attempt this is (0 for first try) |
| `retry_of` | ObjectId | References the failed job document that this job retries |
| `metadata` | object | Free-form key-value metadata for extensibility |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `job_type`, `started_at` | Job history by type | Compound descending |
| Primary | `status`, `started_at` | Failed/recent jobs | Compound descending |
| Reporting | `started_at` | Time-range queries | Descending |
| Reporting | `duration_ms` | Find slow jobs | Descending |
| Cleanup | `started_at` (TTL-ready) | Expire old job records | Ascending |

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Job documents | 90 days | Operational logs for debugging and monitoring |
| Failed job documents | 180 days | Extended retention for failure analysis |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** NO

Job records are operational logs that cannot be reconstructed. They represent execution history, not derived data.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Recent jobs | `find().sort({started_at: -1}).limit(20)` | Last 20 job executions |
| Failed jobs | `find({status: "failed"}).sort({started_at: -1}).limit(10)` | Most recent failures |
| Job type history | `find({job_type: "daily_aggregation"}).sort({started_at: -1}).limit(30)` | Last 30 daily job runs |
| Job duration analysis | `find({job_type: "full_rebuild"}, {duration_ms: 1, sessions_processed: 1, started_at: 1})` | Performance tracking |
| TTL cleanup | `deleteMany({started_at: {$lt: cutoff}})` | Retention-based cleanup |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | ~4,000 (capped by 90-day retention with ~44 jobs/day) |
| Update frequency | Once per job (append-only) |
| Storage per document | ~350 bytes |
| Total storage | ~1.4 MB (capped by retention) |

---

### system_schema

#### 1. Purpose

Collection-level schema version and analytics generation version tracking. Maintains the current `schema_version` and `analytics_generation_version` for every analytics and insights collection. Used by the aggregation service to ensure documents are written with the correct version and by readers to determine expected document structure and methodology.

#### 2. Ownership

| Role | Entity |
|------|--------|
| **Writes** | Schema migration logic (future Phase B+), Analytics Aggregation Service |
| **Reads** | Analytics Aggregation Service (before writes), UI analytics service |

#### 3. Example Document

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
      "change": "Initial analytics generation — all collections at generation 1"
    }
  ],
  "migration_history": [
    {
      "migration_id": "v2_0_0_analytics_initial",
      "applied_at": ISODate("2026-06-20T00:00:00Z"),
      "from_version": 0,
      "to_version": 1,
      "collections_affected": "*",
      "checksum": "sha256hash..."
    }
  ],
  "generated_at": ISODate("2026-06-20T06:00:00Z")
}
```

#### 4. Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `_id` | string | Fixed value: `"collection_schema"` |
| `schema_version` | int | Document schema version (currently 1) |
| `collections` | object | Map of collection name → version object `{schema: int, generation: int}` |
| `generated_at` | ISODate | Timestamp of last update |

#### 5. Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `migration_history` | array | History of schema migrations applied |
| `migration_history[].migration_id` | string | Unique migration identifier |
| `migration_history[].applied_at` | ISODate | When migration was applied |
| `migration_history[].from_version` | int | Version before migration |
| `migration_history[].to_version` | int | Version after migration |
| `migration_history[].collections_affected` | string | Affected collections ("*" for all) |
| `migration_history[].checksum` | string | SHA-256 checksum of migration logic |
| `generation_history` | array | History of analytics generation version changes |
| `generation_history[].generation_id` | string | Unique generation identifier |
| `generation_history[].applied_at` | ISODate | When generation was updated |
| `generation_history[].from_generation` | int | Generation before update |
| `generation_history[].to_generation` | int | Generation after update |
| `generation_history[].collections_affected` | string | Affected collections ("*" for all) |
| `generation_history[].change` | string | Description of what changed in the generation |

#### 6. Index Strategy

| Index | Fields | Purpose | Type |
|-------|--------|---------|------|
| Primary | `_id` (unique) | Single document lookup | Unique (default _id index) |

No additional indexes needed — there is exactly one document with a fixed `_id`.

#### 7. Retention Policy

| Scope | Retention | Rationale |
|-------|-----------|-----------|
| Document | Indefinite | Single document, minimal size, essential for schema versioning |
| Migration history | Indefinite (embedded array) | Permanent audit trail |

#### 8. Rebuildability Classification

**Can Be Rebuilt From SQLite?** NO

Schema version state is operational metadata. If deleted, can be recreated with current version values (all collections at version 1), but migration history is permanently lost.

#### 9. Query Patterns

| Pattern | Query | Returns |
|---------|-------|---------|
| Lookup version | `findOne({_id: "collection_schema"}, {collections: 1})` | All collection versions |
| Specific version | `findOne({_id: "collection_schema"}, {"collections.analytics_daily": 1})` | Single collection version |
| Update version | `updateOne({_id: "collection_schema"}, {$set: {"collections.analytics_daily": 2}, $push: {migration_history: {...}}})` | Schema upgrade |

#### 10. Growth Expectations

| Metric | Estimate |
|--------|----------|
| Document count | Exactly 1 |
| Update frequency | On schema migration (rare — perhaps once per major version) |
| Storage per document | ~1 KB (including migration history array) |
| Total storage | ~1 KB (grows slowly with migration history) |

---

## Validation Checklist

| Criterion | Status |
|-----------|--------|
| P8 respected (no raw session duplication) | Verified — analytics_sessions stores distributions/percentiles only |
| All 11 collections designed | Complete |
| Rebuildability documented per collection | Complete |
| Index strategy documented per collection | Complete |
| Retention documented per collection | Complete |
| Versioning documented | Complete (schema_version + analytics_generation_version + optional document_version) |
| Query patterns documented per collection | Complete |
| Ownership documented per collection | Complete |
