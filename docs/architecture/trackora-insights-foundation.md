# Trackora Insights Foundation

**Version:** 2.0.0-draft  
**Status:** Architecture Design  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  
**Phase:** 11 — MongoDB Foundation

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Insight Categories](#2-insight-categories)
3. [Insight Explainability](#3-insight-explainability)
4. [Data Dependency Graph](#4-data-dependency-graph)
5. [Rebuild Strategy](#5-rebuild-strategy)
6. [Future Compatibility Rules](#6-future-compatibility-rules)
7. [Versioning Rules](#7-versioning-rules)
8. [Recommendation System Compatibility](#8-recommendation-system-compatibility)
9. [Wellbeing Metrics Compatibility](#9-wellbeing-metrics-compatibility)
10. [Privacy & Local-First Rules](#10-privacy--local-first-rules)
11. [Future Expansion Rules](#11-future-expansion-rules)
12. [Risk Analysis](#12-risk-analysis)

---

## 1. Purpose

### What Trackora Insights Is

Trackora Insights is a future feature set that transforms raw gaming session data into meaningful, actionable observations about gaming behaviour. Insights are the highest level of data transformation in the Trackora pipeline:

| Layer | Description | Examples |
|-------|-------------|----------|
| **Raw Data** | Unprocessed session records | SQLite `sessions` table |
| **Analytics** | Aggregated summaries | Daily playtime, weekly totals, session distributions |
| **Insights** | Interpreted observations | Consistency score, peak play hours, diversity metric |
| **Recommendations** | Actionable suggestions | "Take a break", "Revisit Stardew Valley" |

### What This Document Is

This document establishes the architectural foundation for future Trackora Insights features. It ensures that:

- Insight categories can be added without destructive migrations
- All insights are explainable to users
- The data pipeline (SQLite → Analytics → Insights) is strictly layered
- Privacy and local-first principles are preserved
- The architecture remains compatible with future v3/v4 releases

### What This Document Is NOT

- Not an implementation plan
- Not a UI specification
- Not a recommendation algorithm design
- Not a medical or psychological assessment framework
- Not a modification to support center collections

### Out of Scope

The following existing MongoDB collections exist for support/reporting purposes and are **independent** from Insight architecture:

| Collection | Purpose | Relationship to Insights |
|-----------|---------|------------------------|
| `bug_reports` | User-submitted bug reports | None |
| `feature_requests` | User-submitted feature requests | None |
| `feedback` | User feedback messages | None |
| `crash_reports` | Automatic crash diagnostics | None |

These collections must never be:
- Read by the insight computation pipeline
- Modified by insight generation logic
- Used as inputs for analytics aggregation
- Mixed into insight data models

---

## 2. Insight Categories

### Category Overview

| # | Category | Future Collection | Tier | Priority |
|---|----------|-------------------|------|----------|
| 1 | Gaming Habits | `insights_habits` | Opt-In | High |
| 2 | Play Patterns | `insights_habits` | Opt-In | High |
| 3 | Consistency Metrics | `insights_habits` | Opt-In | Medium |
| 4 | Game Diversity | `insights_habits` | Opt-In | Medium |
| 5 | Session Behaviour | `insights_habits` | Opt-In | Low |
| 6 | Wellbeing Metrics | `insights_habits` | Opt-In | Future |
| 7 | Recommendation Engine | `insights_recommendations` | Opt-In | Future |
| 8 | Trend Intelligence | `insights_habits` | Opt-In | Low |

All insight categories share the `insights_habits` collection, differentiated by `insight_type`. This avoids collection proliferation while enabling independent computation and versioning.

---

### 2.1 Gaming Habits

**Purpose:** Describe a user's typical gaming behaviour over time. Identifies preferences, routines, and long-term patterns.

**Inputs:**
- `analytics_daily` — daily playtime totals
- `analytics_weekly` — weekly summaries
- `analytics_sessions` — session length distributions and time-of-day data
- `analytics_games` — per-game lifetime stats

**Outputs:**

| Insight Type | Example Output | Data |
|-------------|----------------|------|
| `preferred_play_time` | "You typically play between 6–10 PM" | Time-of-day distribution |
| `preferred_play_day` | "Saturday is your most active day" | Weekday distribution |
| `typical_session_length` | "Most sessions are 30–60 minutes" | Duration distribution |
| `gaming_rhythm` | "You play in short bursts during weekdays and longer sessions on weekends" | Combined weekday + duration pattern |

**Rebuildability:**
- From SQLite: YES (via analytics regeneration)
- From analytics: YES
- From insights: YES (same methodology → same result)

**Explainability:**
- `reason_codes`: `["time_of_day_distribution", "weekday_distribution", "duration_distribution"]`
- `source_metrics`: `{ "analytics_sessions": ["time_of_day_distribution", "weekday_distribution", "duration_distribution"], ... }`

---

### 2.2 Play Patterns

**Purpose:** Analyse how a user's playtime varies across different contexts — weekdays vs weekends, morning vs evening, workdays vs holidays.

**Inputs:**
- `analytics_daily` — hourly breakdown, daily totals
- `analytics_sessions` — time-of-day distribution, weekday distribution
- `analytics_trends` — period-over-period comparisons

**Outputs:**

| Insight Type | Example Output | Data |
|-------------|----------------|------|
| `weekday_vs_weekend` | "You play 2x more on weekends" | Weekday/weekend ratio |
| `peak_hour_analysis` | "Your peak hour is 8 PM" | Hourly breakdown aggregation |
| `late_session_trend` | "Late-night sessions are increasing" | Trend of sessions after 11 PM |
| `session_gap_analysis` | "Longest gap between sessions: 3 days" | Gap between consecutive session dates |

**Rebuildability:**
- From SQLite: YES (via analytics regeneration)
- From analytics: YES
- From insights: YES

**Explainability:**
- `reason_codes`: `["weekday_ratio", "hourly_peak", "late_night_trend", "session_gaps"]`
- `source_metrics`: lists the specific metrics used

---

### 2.3 Consistency Metrics

**Purpose:** Quantify how regularly a user plays. Measures streaks, breaks, and predictability of gaming behaviour.

**Inputs:**
- `analytics_daily` — consecutive active days
- `analytics_weekly` — weekly active day counts
- `analytics_monthly` — monthly totals for trend

**Outputs:**

| Insight Type | Example Output | Data |
|-------------|----------------|------|
| `consistency_score` | 72/100 — "Consistent Player" | Active days ratio, session regularity |
| `current_streak` | "7-day streak" | Consecutive active days |
| `longest_streak` | "Longest streak: 14 days" | Historical max streak |
| `break_pattern` | "Average break: 1.5 days between sessions" | Gap statistics |
| `consistency_trend` | "Consistency is improving (+5% this month)" | Period-over-period comparison |

**Rebuildability:**
- From SQLite: YES (via analytics regeneration)
- From analytics: YES
- From insights: YES

**Explainability:**
- `reason_codes`: `["active_days_ratio", "streak_length", "gap_distribution", "period_comparison"]`
- `source_metrics`: ratio of active to total days, streak counts, gap mean/variance

---

### 2.4 Game Diversity

**Purpose:** Measure how broadly a user distributes their playtime across their game library. Identifies over-focus on single games and neglected library titles.

**Inputs:**
- `analytics_games` — per-game lifetime stats, per-game recent stats
- `analytics_daily` — per-game breakdown per day

**Outputs:**

| Insight Type | Example Output | Data |
|-------------|----------------|------|
| `diversity_score` | 65/100 — "Moderate diversity" | Herfindahl index or similar of game time distribution |
| `primary_game_focus` | "Counter-Strike 2: 55% of playtime" | Percentage of total time |
| `neglected_games` | "12 games with <1 hour played" | Games with minimal playtime |
| `library_exploration` | "You played 8 of 25 tracked games this month" | Active library ratio |
| `rotation_frequency` | "You switch games every 2 sessions on average" | Average sessions before game switch |

**Rebuildability:**
- From SQLite: YES (via analytics regeneration)
- From analytics: YES
- From insights: YES

**Explainability:**
- `reason_codes`: `["diversity_index", "primary_game_percent", "neglected_game_count", "active_library_ratio"]`
- `source_metrics`: full list of per-game totals, session counts

---

### 2.5 Session Behaviour

**Purpose:** Analyse patterns within individual gaming sessions — duration preferences, time-of-day clustering, session frequency.

**Inputs:**
- `analytics_sessions` — duration distribution, percentiles, time-of-day, weekday distribution
- `analytics_daily` — session counts per day

**Outputs:**

| Insight Type | Example Output | Data |
|-------------|----------------|------|
| `session_length_preference` | "Most sessions are short (15–30 min)" | Dominant duration bucket |
| `session_frequency` | "Average 3 sessions per active day" | Sessions per active day |
| `back_to_back_sessions` | "You often play multiple games in one sitting" | Consecutive sessions within short time window |
| `time_block_clustering` | "Sessions cluster in the evening block" | Time block with most session starts |

**Rebuildability:**
- From SQLite: YES (via analytics regeneration)
- From analytics: YES
- From insights: YES

**Explainability:**
- `reason_codes`: `["dominant_duration_bucket", "sessions_per_active_day", "session_clustering"]`
- `source_metrics`: duration distribution array, session count per day, session start time clustering

---

### 2.6 Wellbeing Metrics

**Purpose:** Provide users with awareness of gaming patterns that may affect sleep, daily routine, or life balance. No health claims. No medical interpretations.

**Inputs:**
- `analytics_daily` — hourly breakdown, late-night hours
- `analytics_sessions` — time-of-day distribution, late session frequency
- `analytics_trends` — trend of late-night sessions

**Outputs:**

| Insight Type | Example Output | Data |
|-------------|----------------|------|
| `late_night_gaming` | "15% of sessions start after 11 PM" | Sessions starting 23:00–06:00 / total sessions |
| `play_balance` | "Your longest daily session was 8 hours" | Max daily playtime (single day) |
| `session_intensity` | "Average session intensity: moderate" | Duration-based intensity classification |
| `weekly_balance` | "No extreme days this week" | Standard deviation of daily playtime |
| `break_reminder` | "You played for 3 hours without a break" | Consecutive playtime without inter-session gap |

**Rebuildability:**
- From SQLite: YES (via analytics regeneration)
- From analytics: YES
- From insights: YES

**Explainability:**
- `reason_codes`: `["late_night_ratio", "max_daily_playtime", "session_intensity_index", "daily_std_dev"]`
- `source_metrics`: session start hours, daily totals, session duration quantiles

**Boundaries:**
- No diagnostic language (not "gaming disorder" or "addiction")
- No absolute thresholds (not "more than X hours is unhealthy")
- User-facing labels are descriptive, not prescriptive
- All metrics are comparative to the user's own history, not population baselines

---

### 2.7 Recommendation Engine

**Purpose:** Generate actionable suggestions based on aggregated insight data. Recommendations are ephemeral — they expire and are regenerated.

**Note:** This section defines document structures only. Recommendation algorithms are out of scope.

**Inputs:**
- All `insights_habits` outputs
- `analytics_games` — per-game recency data
- `analytics_trends` — direction of change

**Outputs (as defined in Section 8):**

| Recommendation Type | Trigger Example |
|-------------------|----------------|
| `take_break` | Session exceeds user's typical duration |
| `explore_neglected` | Game untouched for >14 days with prior playtime |
| `continue_streak` | Active streak ≥5 days |
| `improve_balance` | Diversity score <30 for >30 days |
| `try_new_game` | All games stale for >7 days |
| `achievement_milestone` | Lifetime playtime crosses threshold (100h, 500h, etc.) |

**Rebuildability:**
- From SQLite: NO (requires analytics)
- From analytics: YES
- From insights: YES
- From recommendations: YES (but may differ — algorithms may change)

---

### 2.8 Trend Intelligence

**Purpose:** Surface longer-term behavioural trends that may not be visible in daily or weekly data. Combines multiple analytics dimensions into higher-level trend observations.

**Inputs:**
- `analytics_trends` — all trend types (daily, weekly, monthly, rolling)
- `analytics_monthly` — monthly totals
- `analytics_games` — per-game trends

**Outputs:**

| Insight Type | Example Output | Data |
|-------------|----------------|------|
| `seasonal_pattern` | "Playtime increases during winter months" | Monthly playtime over 12+ months |
| `declining_interest` | "Playtime in Game X has declined 40% over 3 months" | Per-game trend over rolling quarters |
| `emerging_pattern` | "You're playing more in the mornings recently" | Time-of-day shift over 30 days |
| `plateau_detection` | "Your weekly playtime has been stable for 6 weeks" | Variance of weekly totals |
| `growth_indicator` | "Game diversity is improving (+10% this quarter)" | Diversity trend over period |

**Rebuildability:**
- From SQLite: YES (via analytics regeneration)
- From analytics: YES
- From insights: YES

**Explainability:**
- `reason_codes`: `["monthly_trend_analysis", "per_game_trend", "time_of_day_shift", "weekly_variance"]`
- `source_metrics`: period-over-period comparisons, moving averages, variance calculations

---

## 3. Insight Explainability

### Mandatory Principle

Every future insight must be explainable to the user. An insight without explanation is not trusted.

### Explainability Document Structure

Every insight document must include:

```json
{
  "insight_type": "consistency_score",
  "analytics_generation_version": 1,

  "data": {
    "score": 72,
    "max_score": 100,
    "label": "Consistent Player"
  },

  "explainability": {
    "reason_codes": [
      "active_days_ratio",
      "streak_length",
      "gap_distribution"
    ],
    "source_metrics": {
      "active_days_ratio": { "value": 0.85, "description": "85% of days had at least one session" },
      "current_streak": { "value": 7, "description": "Current consecutive active days" },
      "average_gap_hours": { "value": 18, "description": "Average hours between sessions" }
    },
    "narrative": "You played on 85% of days this period with a 7-day active streak. Your session gaps average 18 hours.",
    "confidence": 0.85
  },

  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-07-20T06:00:00Z"),
  "source_collections": ["analytics_daily", "analytics_sessions"]
}
```

### Explainability Requirements

| Requirement | Description | Mandatory |
|------------|-------------|-----------|
| `reason_codes` | Machine-readable list of factors that produced this insight | Yes |
| `source_metrics` | The specific numeric values that drove the insight | Yes |
| `narrative` | Human-readable explanation of how the insight was derived | Yes |
| `confidence` | 0.0–1.0 score indicating confidence in the insight | Yes |
| `source_collections` | Which analytics collections were used as input | Yes |
| `analytics_generation_version` | Which generation of the computation produced this | Yes |

### reason_codes Taxonomy

Reason codes are hierarchical and namespaced:

| Namespace | Examples |
|-----------|----------|
| `active_days_*` | `active_days_ratio`, `active_days_count`, `active_days_trend` |
| `streak_*` | `streak_length`, `streak_history`, `streak_trend` |
| `gap_*` | `gap_distribution`, `gap_mean`, `gap_max` |
| `diversity_*` | `diversity_index`, `primary_game_percent`, `neglected_game_count` |
| `time_of_day_*` | `time_of_day_distribution`, `peak_hour`, `late_night_ratio` |
| `duration_*` | `duration_distribution`, `dominant_bucket`, `session_intensity` |
| `trend_*` | `period_comparison`, `direction`, `change_percent` |
| `weekday_*` | `weekday_distribution`, `weekday_vs_weekend` |
| `session_*` | `session_frequency`, `sessions_per_active_day`, `session_clustering` |

### Why Explainability Matters

1. **Trust**: Users are more likely to trust insights they understand
2. **Actionability**: An explained insight tells the user what to change
3. **Debugging**: If an insight seems wrong, explanation helps identify the cause
4. **Versioning**: When algorithms change, explanation shows what factors changed
5. **Privacy**: Users can see exactly what data produced each insight

---

## 4. Data Dependency Graph

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          SQLite (Source of Truth)                         │
│  ┌──────────┐  ┌──────────┐                                              │
│  │  games   │  │ sessions │                                              │
│  └──────────┘  └──────────┘                                              │
└────────────────────┬─────────────────────────────────────────────────────┘
                     │
                     ▼  (Analytics Aggregation Service)
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐  ┌──────────────────────┐
│ analytics_daily  │  │ analytics_sessions    │
│ analytics_weekly │  │ analytics_games       │
│ analytics_monthly│  │ analytics_trends      │
└────────┬─────────┘  └──────────┬───────────┘
         │                       │
         ▼                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          Insight Computation                              │
│                                                                           │
│  Reads from analytics_* collections only                                   │
│  Never reads from SQLite directly                                         │
│  Never reads from support collections (bug_reports, etc.)                │
│                                                                           │
│  Produces: insights_habits documents                                      │
└────────────────────┬─────────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     Recommendation Engine                                  │
│                                                                           │
│  Reads from insights_habits + analytics_games + analytics_trends          │
│                                                                           │
│  Produces: insights_recommendations documents                             │
└──────────────────────────────────────────────────────────────────────────┘
```

### Dependency Rules

| Rule | Description |
|------|-------------|
| D1 | No insight may depend directly on SQLite |
| D2 | No insight may depend directly on support center collections |
| D3 | All insights must read from analytics_* collections only |
| D4 | Recommendations may read from insights_* and analytics_* |
| D5 | The dependency chain is always: SQLite → analytics → insights → recommendations |
| D6 | No circular dependencies between insight categories |
| D7 | Adding a new insight type must not require changes to existing analytics collections |

### What Happens When a Dependency is Missing

| Missing Dependency | Effect | Recovery |
|-------------------|--------|----------|
| SQLite unavailable | No analytics → no insights | Restore SQLite |
| analytics collection empty | Insight computation produces no output | Regenerate analytics from SQLite |
| analytics collection stale | Insights based on outdated data | Insight document shows `valid_until` exceeded, triggers refresh |
| insight collection missing | Recommendations missing some inputs | Recommendations fall back to analytics-only mode |
| Specific insight type missing | That insight not displayed | Other insights unaffected |

---

## 5. Rebuild Strategy

### Multi-Tier Rebuild Chain

```
Level 0: SQLite (Source of Truth)
    │
    ▼  (always recoverable)
Level 1: analytics_* collections  (6 collections)
    │
    ▼  (always recoverable if Level 1 exists)
Level 2: insights_habits  (single collection, 8+ categories)
    │
    ▼  (always recoverable if Level 1 or Level 2 exists)
Level 3: insights_recommendations  (single collection)
```

### Rebuildability Per Category

| Insight Category | From SQLite? | From analytics? | From insights? | If Deleted |
|----------------|-------------|----------------|----------------|------------|
| Gaming Habits | YES (via analytics regen) | YES | YES | Regenerate from analytics_* |
| Play Patterns | YES (via analytics regen) | YES | YES | Regenerate from analytics_* |
| Consistency Metrics | YES (via analytics regen) | YES | YES | Regenerate from analytics_* |
| Game Diversity | YES (via analytics regen) | YES | YES | Regenerate from analytics_games |
| Session Behaviour | YES (via analytics regen) | YES | YES | Regenerate from analytics_sessions |
| Wellbeing Metrics | YES (via analytics regen) | YES | YES | Regenerate from analytics_* |
| Recommendation Engine | NO | YES | YES | Regenerate — output may differ |
| Trend Intelligence | YES (via analytics regen) | YES | YES | Regenerate from analytics_* |

### Cascade Rebuild Flow

```
User deletes MongoDB entirely
    │
    ▼
1. SQLite is intact (source of truth unchanged)
    │
    ▼
2. Regenerate all analytics_* collections from SQLite
    │
    ▼
3. Regenerate all insights_habits from analytics_*
    │
    ▼
4. Regenerate all insights_recommendations from insights_habits + analytics_*
    │
    ▼
5. System fully restored
```

### Partial Rebuild Flow

```
User deletes only insights_habits
    │
    ▼
1. analytics_* intact
    │
    ▼
2. Regenerate all insights_habits from analytics_*
    │
    ▼
3. Regenerate insights_recommendations from insights_habits + analytics_*
    │
    ▼
4. System fully restored
```

### Incremental Update

After a session ends, the aggregation service:
1. Incrementally updates `analytics_daily` (one document)
2. If week boundary crossed: updates `analytics_weekly`
3. If month boundary crossed: updates `analytics_monthly`
4. Updates `analytics_games` for affected game
5. Updates `analytics_sessions` for affected game
6. Updates `analytics_trends` if comparison periods changed
7. Flags affected `insights_habits` entries as stale for regeneration

This avoids full rebuilds on every session end.

---

## 6. Future Compatibility Rules

### Allowed Changes

These changes may be made to the insight architecture without requiring migration, version bumps, or user-visible changes:

| Change | Example | Category |
|--------|---------|----------|
| Add new optional field | Add `secondary_label` to insight data | Additive |
| Add new reason_code | Add `streak_trend` to consistency_score | Additive |
| Add new insight_type | Add `seasonal_pattern` to Trend Intelligence | Additive |
| Add new source_metric | Add `weekly_variance` to explainability | Additive |
| Add new collection | Add `insights_health` in future | Additive |
| Improve confidence calculation | More accurate confidence from more data | Non-breaking |
| Add optional sub-field to data | Add `data.trend` to existing insight | Additive |

### Restricted Changes

These changes require version management, migration, or deprecation windows:

| Change | Restriction | Required Action |
|--------|-------------|----------------|
| Remove required field | Breaking | Increment `schema_version`, deprecation window |
| Rename `insight_type` value | Breaking | Old name must still be recognized during transition |
| Remove `reason_code` | Breaking | May break reader expectations for explainability |
| Change numeric scale | Potentially breaking | Increment `analytics_generation_version`, update narrative |
| Restructure `data` object shape | Breaking | Increment `schema_version`, maintain backward compat |
| Change confidence formula | Non-breaking | Increment `analytics_generation_version` |
| Change source dependency | Breaking | Update documentation, ensure migration path |

### Prohibited Changes

These changes must never happen:

| Change | Reason |
|--------|--------|
| Make an insight depend directly on SQLite | Would bypass analytics layer, violate dependency graph |
| Read from support center collections | Architectural contamination |
| Store raw session data in insight documents | P8 violation, privacy risk |
| Remove an insight_type without deprecation | Breaking change for readers |
| Change `insight_type` enum without migration | Existing documents unreadable by type filter |

### Deprecation Policy

When an insight type or reason code is deprecated:

```
v2.0.0:  Insight type still produced, marked "deprecated" in system_schema
v2.1.0:  Insight type still produced, readers warned
v2.2.0:  Insight type no longer produced by default, opt-in only
v3.0.0:  Insight type collection may be removed
```

---

## 7. Versioning Rules

### schema_version

**Scope:** Per document in `insights_habits` and `insights_recommendations`

**Changes when:** The document structure changes (field added, removed, restructured)

**Rules:**

| Scenario | schema_version Change | Example |
|----------|----------------------|---------|
| New optional field added | No change | Add `data.trend` to an insight |
| New required field added | +1 | Add required `confidence` to all insights |
| Field removed | +1 | Remove deprecated field after deprecation window |
| Field type changed | +1 | `score` from int to float |
| Embedded document restructured | +1 | Restructure `explainability` object |

### analytics_generation_version

**Scope:** Per document in `insights_habits` and `insights_recommendations`

**Changes when:** The computation methodology changes (algorithm improved, bug fixed, formula changed)

**Rules:**

| Scenario | generation_version Change | Example |
|----------|--------------------------|---------|
| Improved consistency formula | +1 | Better streak detection algorithm |
| Bug fix in diversity calculation | +1 | Corrected game count |
| New weighting in habit score | +1 | Added recency weighting |
| Same formula, new input data | No change | This is not a methodology change |

### system_schema Tracking

Both versions are tracked in `system_schema.collections`:

```json
{
  "insights_habits": { "schema": 1, "generation": 3 },
  "insights_recommendations": { "schema": 1, "generation": 2 }
}
```

### Version Table: insights_habits

| Release | schema_version | generation_version | Change |
|---------|---------------|-------------------|--------|
| Initial | 1 | 1 | All 8 insight categories at generation 1 |
| Update A | 1 | 2 | Improved consistency formula (same doc shape) |
| Update B | 2 | 2 | Added `data.trend` field to all insight types |
| Update C | 2 | 3 | Fixed bug in diversity calculation |

### Version Table: insights_recommendations

| Release | schema_version | generation_version | Change |
|---------|---------------|-------------------|--------|
| Initial | 1 | 1 | All recommendation types at generation 1 |
| Update A | 1 | 2 | Improved recommendation priority logic |

---

## 8. Recommendation System Compatibility

### Purpose

This section defines the document structures for future recommendation records. It does NOT define recommendation algorithms.

### Document Structure

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "recommendation_type": "take_break",
  "priority": "medium",
  "title": "Time for a break?",
  "message": "You've been playing for 3 hours straight.",
  "reason_codes": ["session_exceeds_typical", "gap_exceeded"],
  "confidence": 0.85,
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-06-20T12:00:00Z"),
  "expiry_strategy": "absolute_time",
  "action": {
    "type": "dismiss",
    "label": "Got it"
  },
  "context": {
    "current_session_seconds": 10800,
    "game_id": 42,
    "game_name": "Counter-Strike 2"
  },
  "source_insights": ["consistency_score", "session_behaviour"],
  "source_generation_versions": {
    "consistency_score": 1,
    "session_behaviour": 2
  }
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `recommendation_type` | string | One of: `take_break`, `explore_neglected`, `continue_streak`, `improve_balance`, `try_new_game`, `achievement_milestone` |
| `priority` | string | `low`, `medium`, `high` |
| `title` | string | Short display title (≤60 chars) |
| `message` | string | Full recommendation text (≤200 chars) |
| `reason_codes` | array | Machine-readable list of triggers |
| `confidence` | float | 0.0–1.0 confidence in this recommendation |
| `generated_at` | ISODate | When recommendation was generated |
| `valid_until` | ISODate | When recommendation expires |
| `expiry_strategy` | string | `absolute_time`, `on_session_end`, `on_dismiss` |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `action` | object | Action payload (dismiss, launch_game, open_url) |
| `context` | object | Contextual metadata |
| `source_insights` | array | Insight types that triggered this |
| `source_generation_versions` | object | Map of insight_type → generation_version at time of generation |
| `dismissed` | bool | Whether user dismissed this |
| `display_count` | int | Times shown to user |

### Recommendation Types

| Type | Purpose | Expiry | Action |
|------|---------|--------|--------|
| `take_break` | Suggest break after long session | `on_session_end` | dismiss |
| `explore_neglected` | Suggest revisiting an untouched game | `absolute_time` (7d) | launch_game |
| `continue_streak` | Positive reinforcement for streak | `on_session_end` | dismiss |
| `improve_balance` | Suggest trying other games | `absolute_time` (7d) | dismiss |
| `try_new_game` | Suggest adding a new game | `absolute_time` (30d) | open_library |
| `achievement_milestone` | Celebrate playtime milestone | `on_dismiss` | dismiss |

### Expiry Strategies

| Strategy | Behavior | Example |
|----------|----------|---------|
| `absolute_time` | Recommendation expires at `valid_until` timestamp | "Try a new game" — valid for 30 days |
| `on_session_end` | Recommendation expires when current session ends | "Take a break" — irrelevant after session ends |
| `on_dismiss` | Recommendation expires only when user dismisses it | "Achievement milestone" — stays until acknowledged |

### Compatibility Requirements

| Requirement | Description |
|-------------|-------------|
| New recommendation types may be added at any time | Additive change, no migration needed |
| Existing types may gain new reason_codes | Additive, no version bump |
| Priority values (low/medium/high) are extensible | May add `critical` or `informational` in future |
| Action types (dismiss/launch_game/open_url) are extensible | May add `open_settings`, `show_insight` |
| `valid_until` format is stable | Always ISODate |
| `source_generation_versions` preserves methodology info | Enables detection of stale recommendations after algorithm update |

---

## 9. Wellbeing Metrics Compatibility

### Design Principles

| Principle | Description |
|-----------|-------------|
| W1 | No health claims — metrics describe behaviour, not health |
| W2 | No medical interpretations — never "gaming disorder", "addiction", "unhealthy" |
| W3 | User-controlled — all wellbeing metrics are opt-in |
| W4 | Self-referential — metrics compare user against own history, not population |
| W5 | Descriptive labels — "late-night gaming" not "sleep disruption" |
| W6 | No absolute thresholds — never "X hours is too much" |

### Document Structure

```json
{
  "_id": ObjectId,
  "schema_version": 1,
  "analytics_generation_version": 1,
  "insight_type": "play_balance",
  "period": "rolling_30d",
  "data": {
    "longest_daily_session_seconds": 28800,
    "average_daily_session_seconds": 7200,
    "days_with_long_sessions": 5,
    "long_session_threshold_seconds": 14400,
    "trend": "stable"
  },
  "explainability": {
    "reason_codes": ["max_daily_playtime", "long_session_frequency", "daily_average"],
    "source_metrics": {
      "max_daily_playtime": { "value": 28800, "description": "Longest single day this period" },
      "long_session_count": { "value": 5, "description": "Days exceeding 4 hours" },
      "daily_average": { "value": 7200, "description": "Average playtime per active day" }
    },
    "narrative": "Your longest session day was 8 hours. On 5 days you played more than 4 hours.",
    "confidence": 0.9
  },
  "generated_at": ISODate("2026-06-20T06:00:00Z"),
  "valid_until": ISODate("2026-07-20T06:00:00Z"),
  "source_collections": ["analytics_daily"]
}
```

### Wellbeing Metrics

| Metric | Data | Thresholds | Format |
|--------|------|------------|--------|
| `play_balance` | Max daily playtime, frequency of long sessions | No hard thresholds — user-relative | Descriptive with trend |
| `late_night_gaming` | Ratio of sessions starting 23:00–06:00 | No hard thresholds | Percentage + trend |
| `session_intensity` | Duration classification (short/medium/long/extended) | Duration buckets (4 tiers) | Distribution + trend |
| `weekly_consistency` | Std dev of daily playtime, active day ratio | No hard thresholds | Score 0–100 + trend |
| `break_pattern` | Longest continuous play without 15min+ gap | No hard thresholds | Duration + frequency |

### Banned Terminology

The following terms must never appear in wellbeing metric labels, descriptions, or narratives:

| Banned | Use Instead |
|--------|-------------|
| addiction | gaming pattern |
| unhealthy | extended play |
| disorder | behaviour |
| excessive | extended |
| problematic | — omit entirely |
| abuse | — omit entirely |
| warning | observation |
| dangerous | — omit entirely |
| should (prescriptive) | could, may, consider |

### UI Guidance

All wellbeing metrics displayed in the UI must:
1. Include the `narrative` text from explainability
2. Show the confidence level
3. Provide a link to "How is this calculated?" (explainability detail)
4. Avoid red/stop colours for high values (use neutral information styling)
5. Include a control to disable the metric category

---

## 10. Privacy & Local-First Rules

### What Remains Local

All data in the following collections remains on the local machine and must never be transmitted:

| Collection | Reason |
|-----------|--------|
| All `analytics_*` collections | Derived from local SQLite, no sync purpose |
| `system_*` collections | Operational metadata, no user-facing data |
| Raw SQLite data | Source of truth, always local |

### What May Be Exported

With explicit user action (export button), the following may be written to a user-chosen file path:

| Data | Export Format | Includes |
|------|--------------|----------|
| Analytics summaries | JSON/CSV | Aggregate playtime metrics |
| Insight data | JSON | Computed insights with explainability |
| Recommendations | JSON | Active recommendation records |

Export is always:
- User-initiated (never automatic)
- To a user-chosen file path
- Excluded from automatic backup/cloud sync

### What May Never Be Uploaded

The following must never leave the local machine under any circumstance:

| Data | Reason |
|------|--------|
| Raw session records | Contains exact play times, game identities |
| Active session state | Real-time tracking data |
| Game executable paths | System information |
| Process names | System information |
| Settings with paths | User configuration |

### Opt-In Data (Future Cloud Features)

If future versions introduce optional cloud sync, the following rules apply:

| Category | Sync Permission | User Control |
|----------|----------------|--------------|
| Aggregated analytics | Requires explicit opt-in | Per-category toggle in settings |
| Insight data | Requires explicit opt-in | Per-category toggle |
| Recommendation data | Requires explicit opt-in | Single toggle |
| Wellbeing metrics | Requires explicit opt-in | Single toggle (separate from other insights) |

### Opt-In Requirements

| Requirement | Description |
|-------------|-------------|
| Granularity | User can opt in to specific categories (not all-or-nothing) |
| Revocability | User can revoke consent at any time |
| Deletion on revoke | Cloud data deleted within 30 days of opt-out |
| Transparency | Clear description of what data is synced and why |
| No dark patterns | No nagging, no hiding opt-out, no default-enabled |

### Support Collection Independence

The existing support/reporting collections (`bug_reports`, `feature_requests`, `feedback`, `crash_reports`) are:

- Independent from Insight architecture
- Subject to their own privacy rules (defined in existing architecture)
- Never read by insight computation
- Never combined with insight data

---

## 11. Future Expansion Rules

### Adding New Insight Types

**Allowed without migration:**
1. Add new `insight_type` value to the `insights_habits` collection
2. Readers that don't know the type simply don't display it
3. The `system_schema.collections.insights_habits` entry is updated

**Rules:**
- New insight types must follow all explainability requirements
- New insight types must read from analytics_* only (never SQLite directly)
- New insight types must have a defined rebuild strategy
- New insight types must have at least one reason_code

### Adding New Recommendation Types

**Allowed without migration:**
1. Add new `recommendation_type` value to the `insights_recommendations` collection
2. New `action.type` values are supported
3. New `expiry_strategy` values are supported

**Rules:**
- New recommendation types must define all required fields
- New recommendation types must include reason_codes
- New recommendation types must have a defined expiry strategy

### Adding New Collections

Future insight collections may be added:

| Potential Collection | Purpose | When |
|---------------------|---------|------|
| `insights_social` | Future social/community features (opt-in only) | v3+ |
| `insights_trends_extended` | Long-term trend history beyond 5 years | v3+ |
| `insights_export` | User export history tracking | v3+ |

**Rules for new collections:**
- Must use `insights_*` prefix
- Must include `schema_version` and `analytics_generation_version`
- Must be optionally rebuildable
- Must not create circular dependencies

### Expanding Metrics

Existing insight types may gain new metrics:

```json
{
  "insight_type": "consistency_score",
  "data": {
    "score": 72,
    "max_score": 100,
    "label": "Consistent Player",
    "new_metric": {              // ← NEW: added in v2.1
      "value": 0.8,
      "description": "Week-over-week consistency"
    }
  }
}
```

**Rules:**
- New metrics should be added as optional fields within `data`
- New metrics should update the explainability block with new source_metrics
- New metrics do not require schema_version increment (additive change)
- New metrics increment analytics_generation_version if computation changes

### Restricting Changes

If a future version must restrict or remove an insight feature:

1. Mark as deprecated in `system_schema` (optional field)
2. Continue producing for at least one minor release
3. Remove in next major version
4. Document in CHANGELOG

---

## 12. Risk Analysis

### Data Evolution Risks

| Risk | Description | Likelihood | Impact | Mitigation |
|------|-------------|-----------|--------|------------|
| R01 | Insight type becomes obsolete | Medium | Low | Deprecation policy: mark, continue, remove over 3 releases |
| R02 | Metric scale changes (0–100 → 0–10) | Low | Medium | analytics_generation_version increment + UI version-aware display |
| R03 | New insight type requires data that analytics_* doesn't have | Medium | High | Add to analytics_* first, then insight type in next release |
| R04 | Wellbeing metric misinterpreted as medical advice | Low | Critical | Banned terminology list, descriptive-only language |

### Versioning Risks

| Risk | Description | Likelihood | Impact | Mitigation |
|------|-------------|-----------|--------|------------|
| R05 | Reader encounters unknown schema_version | Medium | Low | MongoDB ignores unknown fields, reader falls back gracefully |
| R06 | Reader encounters unknown analytics_generation_version | Medium | Low | Display "computed with older methodology" and show data anyway |
| R07 | system_schema out of sync with actual documents | Low | High | On next regeneration, system_schema is corrected automatically |
| R08 | Mixed generation versions across insight types | High | Low | Each insight type versioned independently — display as-is |

### Privacy Risks

| Risk | Description | Likelihood | Impact | Mitigation |
|------|-------------|-----------|--------|------------|
| R09 | User data shared without consent | Low | Critical | Opt-in requirement, clear labels, per-category control |
| R10 | Insight data reveals play patterns identifiable to user | Medium | Medium | No raw session data in insights, only derived metrics |
| R11 | Wellbeing data used for purposes user didn't intend | Low | High | Wellbeing metrics are opt-in only, separate toggle |

### Rebuildability Risks

| Risk | Description | Likelihood | Impact | Mitigation |
|------|-------------|-----------|--------|------------|
| R12 | Full rebuild from SQLite is expensive for large datasets | Medium | Medium | Incremental updates by default, full rebuild only on migration |
| R13 | analytics_* missing data causes incorrect insights | Low | Medium | Insight confidence score reflects data completeness |
| R14 | Recommendation output differs after rebuild (algorithm changed) | High | Low | Expected behaviour — recommendations are ephemeral |
| R15 | Cascading rebuild required after schema migration | Medium | Low | Automated pipeline: SQLite → analytics → insights → recommendations |

### Risk Summary

| Risk Level | Count | Key Concerns |
|-----------|-------|-------------|
| Critical | 1 | Wellbeing metric misinterpretation (mitigated by banned terminology) |
| High | 3 | Data availability for new insights, privacy breach, sync version conflict |
| Medium | 6 | Scale changes, rebuild costs, stale data, missing data |
| Low | 5 | Obsolete types, unknown versions, mixed generations |

---

## Appendix A: Collection Impact Matrix

| Trackora Version | New Collections | Changed Collections | Removed Collections |
|-----------------|----------------|---------------------|---------------------|
| v2.0 (Phase 11) | `analytics_*` (6), `insights_habits`, `insights_recommendations` (empty/stub), `system_*` (3) | None | None |
| v2.x (Insights) | None | `insights_habits` populated, `insights_recommendations` populated | None |
| v3.0 | `insights_trends_extended` (optional) | Potential `analytics_*` schema updates | None |
| v4.0 | `insights_social` (optional) | Potential `insights_*` schema updates | Deprecated insight types |

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Analytics** | Aggregated summaries computed from SQLite (daily, weekly, monthly totals) |
| **Insight** | Interpreted observation derived from analytics data (consistency score, play pattern) |
| **Recommendation** | Actionable suggestion derived from insights and analytics (take a break, explore neglected game) |
| **Explainability** | The property of an insight being traceable to its source data and computation |
| **reason_code** | Machine-readable identifier for a factor that influenced an insight |
| **source_metric** | A specific numeric value from analytics that contributed to an insight |
| **Confidence** | 0.0–1.0 score indicating how reliable an insight or recommendation is |
| **Narrative** | Human-readable explanation of how an insight was derived |
| **Wellbeing Metric** | A metric describing gaming behaviour without health claims or medical interpretation |
| **Expiry Strategy** | Rule determining when a recommendation becomes invalid |
