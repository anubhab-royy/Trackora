# MongoDB Architecture Validation

**Version:** 2.0.0-draft  
**Status:** Architecture Validation  
**Document Type:** Architecture Specification  
**Owner:** Architecture Team  
**Phase:** 11 — MongoDB Foundation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Consistency Review](#2-architecture-consistency-review)
3. [Data Ownership Review](#3-data-ownership-review)
4. [Collection Validation](#4-collection-validation)
5. [Upgrade Safety Review](#5-upgrade-safety-review)
6. [Support Backend Review](#6-support-backend-review)
7. [Analytics Architecture Review](#7-analytics-architecture-review)
8. [Insights Architecture Review](#8-insights-architecture-review)
9. [Dependency Review](#9-dependency-review)
10. [Risk Review](#10-risk-review)
11. [Architecture Scorecard](#11-architecture-scorecard)
12. [Final Verdict](#12-final-verdict)

---

## 1. Executive Summary

### Overall Assessment

The MongoDB Foundation architecture is **internally consistent, upgrade-safe, data-safe, and compatible with existing Trackora systems**. All approved phases align with Trackora's architectural principles: SQLite as source of truth, local-first operation, privacy-first design, and additive-only changes.

**Validation result: READY WITH MINOR REVISIONS**

Two items require revision (detailed in Section 4). Both are documentation gaps rather than fundamental design flaws. Once resolved, the architecture is ready for future implementation phases.

### Critical Architecture Rules Validation

| Rule | Status | Finding |
|------|--------|---------|
| V1 — SQLite source of truth | **APPROVED** | No MongoDB collection owns runtime data |
| V2 — Support isolation | **APPROVED** | Support collections permanently isolated from analytics |
| V3 — Regeneration over migration | **APPROVED** | All analytics_* and insights_* can regenerate |
| V4 — User data survives upgrades | **APPROVED** | Support collections preserved verbatim |
| V5 — Insight explainability | **APPROVED** | reason_codes, source_metrics, generation_version required |
| V6 — No dual ownership | **APPROVED** | Every data type has exactly one owner |
| V7 — Upgrade Foundation compat | **APPROVED** | Compatible with SchemaVersionManager, BackupManager, MigrationManager |
| V8 — Local-first compliance | **APPROVED** | Full functionality without MongoDB |
| V9 — Offline-first compliance | **APPROVED** | MongoDB unavailable → SQLite fallback |
| V10 — Future scalability | **APPROVED** | Roadmap covers v2.0.x through v4.0 |

---

## 2. Architecture Consistency Review

### Cross-Phase Consistency

| Documents | Consistent? | Notes |
|-----------|-------------|-------|
| Phase 2 ↔ Phase 3 | **Yes** | Collection names, naming conventions, versioning all match |
| Phase 2 ↔ Phase 4 | **Yes** | Versioning rules in Phase 2 are fully specified in Phase 4 |
| Phase 2 ↔ Phase 5 | **Yes** | Insights architecture respects isolation rules from Phase 2 |
| Phase 2 ↔ Phase 6 | **Yes** | Roadmap phases match collection introduction order |
| Phase 3 ↔ Phase 4 | **Yes** | Document versioning strategy matches document model |
| Phase 3 ↔ Phase 5 | **Yes** | insight_types map to collections designed in Phase 3 |
| Phase 4 ↔ Phase 5 | **Yes** | Dual-versioning extends to insights collections |
| Phase 4 ↔ Phase 6 | **Yes** | Migration strategy matches roadmap regeneration preference |
| Phase 5 ↔ Phase 6 | **Yes** | Insights activation scheduled in Phase D, consistent with dependencies |

### Contradictions Found

**None.** All phases are consistent with each other. No contradictions exist between any two phases.

### Phase 1 (Audit) vs All Phases

The initial audit correctly identified:
- All 5 SQLite tables
- 4 repositories
- All analytics calculations
- Future MongoDB candidates

All later phases build on this foundation without contradicting any audit findings.

---

## 3. Data Ownership Review

### Ownership Matrix

| Data Type | Owner | Storage | Derivation |
|-----------|-------|---------|------------|
| Raw game records | **SQLite** (games table) | SQLite | Direct user input or auto-discovery |
| Raw session records | **SQLite** (sessions table) | SQLite | Automatic tracking |
| Active session state | **SQLite** (active_sessions table) | SQLite | Runtime tracking |
| User settings | **SQLite** (settings table) | SQLite | User configuration |
| Bug reports | **MongoDB Support** | MongoDB | User input |
| Feature requests | **MongoDB Support** | MongoDB | User input |
| Feedback | **MongoDB Support** | MongoDB | User input |
| Crash reports | **MongoDB Support** | MongoDB | Automatic diagnostics |
| Daily playtime aggregates | **MongoDB Analytics** | MongoDB | Derived from SQLite |
| Weekly playtime aggregates | **MongoDB Analytics** | MongoDB | Derived from SQLite |
| Monthly playtime aggregates | **MongoDB Analytics** | MongoDB | Derived from SQLite |
| Game analytics | **MongoDB Analytics** | MongoDB | Derived from SQLite |
| Session analytics | **MongoDB Analytics** | MongoDB | Derived from SQLite |
| Trend snapshots | **MongoDB Analytics** | MongoDB | Derived from SQLite |
| Gaming habit insights | **MongoDB Insights** | MongoDB | Derived from analytics |
| Recommendations | **MongoDB Insights** | MongoDB | Derived from analytics + insights |
| Analytics metadata | **MongoDB System** | MongoDB | Operational internal |
| Job history | **MongoDB System** | MongoDB | Operational internal |
| Schema tracking | **MongoDB System** | MongoDB | Operational internal |

### Dual Ownership Assessment

| Data Type | Dual Owner? | Assessment |
|-----------|-------------|------------|
| Session durations | No | SQLite writes → MongoDB reads aggregates only |
| Game names | No | SQLite writes → MongoDB caches (can be stale, acceptable) |
| Settings | No | SQLite only → never replicated to MongoDB |
| Active sessions | No | SQLite only |
| Support reports | No | MongoDB only |
| Aggregates | No | MongoDB only (derived from SQLite) |

**Verdict: APPROVED** — No dual ownership exists.

---

## 4. Collection Validation

### Current Support Collections

| Collection | Status | Justification |
|-----------|--------|---------------|
| `bug_reports` | **APPROVED** | Well-defined purpose, isolation guaranteed, versioned |
| `feature_requests` | **APPROVED** | Same assessment |
| `feedback` | **APPROVED** | Same assessment |
| `crash_reports` | **APPROVED** | Same assessment |

### Future Analytics Collections

| Collection | Status | Justification |
|-----------|--------|---------------|
| `analytics_games` | **APPROVED** | P8 compliant (aggregates only, no raw sessions), rebuildable from SQLite |
| `analytics_daily` | **APPROVED** | One doc per day, rebuildable, dual-versioned |
| `analytics_weekly` | **APPROVED** | Same assessment |
| `analytics_monthly` | **APPROVED** | Same assessment |
| `analytics_trends` | **APPROVED** | Computed-value pattern, rebuildable |
| `analytics_sessions` | **APPROVED** | P8 compliant — distributions and percentiles only, no raw sessions |

### Future Insights Collections

| Collection | Status | Justification |
|-----------|--------|---------------|
| `insights_habits` | **NEEDS REVISION** | See note below |
| `insights_recommendations` | **APPROVED** | Well-defined, ephemeral, explainable |

**Revision R01 — insights_habits: wellbeing threshold documentation**

The architecture defines banned terminology and descriptive-only labels for wellbeing metrics, but does not explicitly document what numeric thresholds (if any) trigger wellbeing-related insight types. The Phase 5 spec says "no hard thresholds — user-relative" but this is not carried forward into the collection validation. Recommendation: Add a note to `insights_habits` document model in Phase 3 that wellbeing metric `data` objects must not contain absolute threshold values — only user-relative comparisons and trends.

### Future System Collections

| Collection | Status | Justification |
|-----------|--------|---------------|
| `system_metadata` | **APPROVED** | Single document, essential for incremental aggregation |
| `system_jobs` | **APPROVED** | Operational logs, 90-day retention |
| `system_schema` | **NEEDS REVISION** | See note below |

**Revision R02 — system_schema: migration history preservation**

The `system_schema` collection has an optional `migration_history` array. If the document is deleted and recreated, migration history is permanently lost. The Phase 4 strategy acknowledges this but offers no mitigation. Recommendation: Document that `system_schema` should be backed up as part of BackupManager scope to preserve migration and generation history across disaster recovery.

---

## 5. Upgrade Safety Review

### Versioning Strategy

| Aspect | Assessment |
|--------|------------|
| `schema_version` — increment on breaking changes | **APPROVED** |
| `analytics_generation_version` — increment on methodology changes | **APPROVED** |
| `system_schema` — per-collection tracking | **APPROVED** |
| Mixed-version coexistence | **APPROVED** — readers handle per-document version checking |
| Forward compatibility (old reader, new doc) | **APPROVED** — MongoDB ignores unknown fields |
| Backward compatibility (new reader, old doc) | **APPROVED** — older schema versions fully readable |

### Migration Strategy

| Strategy | Assessment |
|----------|------------|
| Regeneration (Strategy A) for analytics_* | **APPROVED** — default, idempotent, low risk |
| True migration (Strategy B) for insights_* with user annotations | **APPROVED** — exception only, with backup |
| Rollback via regeneration | **APPROVED** — deploy old version, regenerate |
| Downgrade protection | **APPROVED** — fallback to SQLite live computation |

### Compatibility with Milestone 8 (Upgrade Foundation)

| Milestone 8 Component | Compatible? | Notes |
|-----------------------|-------------|-------|
| `SchemaVersionManager` | **Yes** | MongoDB versioning is independent; no conflict |
| `BackupManager` | **Yes** | MongoDB collections can be added to backup scope; existing SQLite backup unchanged |
| `MigrationManager` | **Yes** | MongoDB uses regeneration, not SQLite migration; no conflict |
| `_migrations` table | **Yes** | MongoDB unaffacted; no changes to SQLite migration tracking |
| `schema.json` | **Yes** | MongoDB does not modify schema.json |
| Startup lifecycle | **Yes** | MongoDB is optional; startup does not require it |

### Verdict on Upgrade Safety

**APPROVED** — All upgrade paths are documented and safe. No upgrade scenario results in data loss.

---

## 6. Support Backend Review

### Phase A Roadmap

| Requirement | Status | Finding |
|-------------|--------|---------|
| Support collections isolated | **APPROVED** | Explicitly forbidden from analytics input |
| Data preservation | **APPROVED** | Preserved verbatim across upgrades |
| Migration from Supabase | **APPROVED** | Additive deployment (Supabase not removed immediately) |
| Index design | **APPROVED** | By type + status, submitted_at, app_version |
| Versioning | **APPROVED** | schema_version v1; no generation version needed |
| Backup strategy | **APPROVED** | Included in BackupManager scope |

### Isolation Guarantees

| Forbidden Flow | Documented? | Enforceable? |
|----------------|-------------|--------------|
| Support data → Recommendation Engine | Yes | Yes (architecture tests specified) |
| Support data → Habit Metrics | Yes | Yes |
| Support data → Wellbeing Metrics | Yes | Yes |
| Support data → Trend Analysis | Yes | Yes |
| Support data → Any analytics input | Yes | Yes |

### Verdict on Support Backend

**APPROVED** — Support collections are well-defined, properly isolated, and have a clear migration path from Supabase.

---

## 7. Analytics Architecture Review

### Collection Design

| Requirement | Status |
|-------------|--------|
| All 6 analytics collections rebuildable from SQLite | **APPROVED** |
| P8 compliance (no raw session duplication) | **APPROVED** — analytics_sessions stores distributions only |
| Dual versioning (schema + generation) | **APPROVED** |
| Composite key for idempotent upserts | **APPROVED** — e.g., `{game_id, date}` for daily |
| Index strategy documented | **APPROVED** |
| Retention policy documented | **APPROVED** |
| Query patterns documented | **APPROVED** |
| Growth expectations documented | **APPROVED** |

### System Collection Design

| Requirement | Status |
|-------------|--------|
| `system_metadata` tracks checkpoint | **APPROVED** |
| `system_jobs` records audit trail | **APPROVED** |
| `system_schema` tracks versions | **APPROVED** (with R02 revision) |

### Dual-Versioning Consistency

| Collection | schema_version | analytics_generation_version | Consistent? |
|-----------|---------------|------------------------------|-------------|
| All analytics_* | Required | Required | **Yes** |
| All insights_* | Required | Required | **Yes** |
| Support collections | Required | Not applicable | **Yes** |
| System collections | Required | Not applicable (except system_metadata) | **Yes** |

### Verdict on Analytics Architecture

**APPROVED** — All 6 analytics collections are well-designed, rebuildable, and properly versioned.

---

## 8. Insights Architecture Review

### Category Design

| Category | Status | Notes |
|----------|--------|-------|
| Gaming Habits | **APPROVED** | Well-defined inputs and outputs |
| Play Patterns | **APPROVED** | Clear data sources |
| Consistency Metrics | **APPROVED** | Explainable decomposition |
| Game Diversity | **APPROVED** | Based on per-game distribution |
| Session Behaviour | **APPROVED** | Distribution-based, no raw data |
| Wellbeing Metrics | **APPROVED** | Banned terminology, descriptive labels, no health claims |
| Recommendation Engine | **APPROVED** | Ephemeral, explainable, type-defined |
| Trend Intelligence | **APPROVED** | Multi-input trend detection |

### Explainability Compliance

| Requirement | Status | Evidence |
|-------------|--------|----------|
| `reason_codes` | **APPROVED** | Taxonomy defined, namespaced, hierarchical |
| `source_metrics` | **APPROVED** | Required in every insight document |
| `generation_version` | **APPROVED** | analytics_generation_version required |
| `narrative` | **APPROVED** | Human-readable explanation required |
| `confidence` | **APPROVED** | 0.0–1.0 required on all insights |
| `source_collections` | **APPROVED** | Traced in explainability block |

### Wellbeing Safeguards

| Safeguard | Status | Finding |
|-----------|--------|---------|
| Banned terminology list | **APPROVED** | 9 banned terms documented |
| No health claims | **APPROVED** | "Descriptive, not prescriptive" principle |
| No absolute thresholds | **APPROVED** | User-relative comparisons only |
| No medical interpretations | **APPROVED** | Explicitly stated |
| Opt-in requirement | **APPROVED** | Wellbeing metrics are opt-in only |
| Separate wellbeing toggle | **APPROVED** | Separate from other insight categories |

### Verdict on Insights Architecture

**APPROVED** — All categories are explainable, wellbeing safeguards are comprehensive, and the architecture supports future category additions.

---

## 9. Dependency Review

### Phase Dependency Chain

```
Phase A ──► Phase B ──► Phase C ──► Phase D ──► Phase E
   │            │            │            │            │
   ▼            ▼            ▼            ▼            ▼
Support    Analytics     Pipeline     Insights     Advanced
Backend    Storage       Formalized   Activation   Features
```

| Edge | Dependency | Satisfied? | Notes |
|------|-----------|------------|-------|
| A → B | MongoDB driver proven in production | **Pending** (Phase A not yet implemented) | Must be verified during Phase A |
| B → C | Analytics collections exist | **Pending** | Phase B must ship first |
| C → D | Analytics pipeline stable | **Pending** | Phase C must prove stability |
| D → E | User adoption of insights | **Pending** | Requires Phase D user metrics |

### Missing Dependencies

**None identified.** The dependency chain is complete and correctly ordered.

### Cross-Phase Dependency Verification

| Dependency | Documented In | Carried Forward To |
|-----------|---------------|-------------------|
| MongoDB driver approval | Phase 6 | Phase A |
| Analytics pipeline stability | Phase 6 | Phase D |
| Insight algorithm design | Phase 6 | Phase D |
| Explainability framework | Phase 5 | Phase D |
| Isolation enforcement | Phase 6 | All phases |

### Verdict on Dependencies

**APPROVED** — All dependencies are identified, documented, and correctly ordered.

---

## 10. Risk Review

### Risks from Phase 1 (Audit)

| Risk | Current Status | Classification |
|------|---------------|----------------|
| R01 — All analytics computed live from SQLite | Mitigated — MongoDB provides cached aggregates | **Mitigated** |
| R02 — No pre-computed aggregates | Mitigated — analytics_* collections introduced in Phase B | **Mitigated** |
| R03 — Trend analysis recomputed on every request | Mitigated — analytics_trends caches results | **Mitigated** |
| R04 — No data export to analytics backend | Accepted — local-first design | **Accepted** |
| R05 — No schema for achievements/gamification | Accepted — future feature | **Accepted** |
| R06 — Milestone-9 scope too narrow | Mitigated — Phase 11 provides broad foundation | **Mitigated** |
| R07 — No multi-backend version awareness | Mitigated — system_schema tracks all collections | **Mitigated** |

### Risks from Phase 2 (Foundation Spec)

| Risk | Current Status | Classification |
|------|---------------|----------------|
| — | — | No risks documented in Phase 2 |

### Risks from Phase 3 (Document Model)

| Risk | Current Status | Classification |
|------|---------------|----------------|
| R01 — analytics_sessions percentile computation expensive | Accepted — acceptable for local execution | **Accepted** |
| R02 — insights_* not SQLite-rebuildable directly | Mitigated — two-stage rebuild documented | **Mitigated** |
| R03 — hourly_breakdown storage cost for sparse data | Accepted — optional generation | **Accepted** |
| R04 — Overlapping rolling window trend computation | Accepted — simplicity over optimization | **Accepted** |
| R05 — system_jobs 90-day retention may be too short | Accepted — extended retention for failures (180d) | **Accepted** |

### Risks from Phase 4 (Versioning Strategy)

| Risk | Current Status | Classification |
|------|---------------|----------------|
| — | — | No risks documented in Phase 4 |

### Risks from Phase 5 (Insights Foundation)

| Risk | Current Status | Classification |
|------|---------------|----------------|
| R01 — Wellbeing metric misinterpreted as medical | Mitigated — banned terminology, descriptive labels | **Mitigated** |
| R02 — New insight needs data analytics_* doesn't have | Mitigated — extend analytics first, insight in next release | **Mitigated** |
| R03 — Mixed generation versions across insight types | Accepted — each type versioned independently | **Accepted** |
| R04 — Full rebuild expensive for large datasets | Mitigated — incremental updates by default | **Mitigated** |
| R05 — Recommendation output differs after rebuild | Accepted — expected, ephemeral by design | **Accepted** |

### Risks from Phase 6 (Roadmap)

| Risk | Current Status | Classification |
|------|---------------|----------------|
| Support data lost during Phase A migration | Mitigated — additive deployment, backup | **Mitigated** |
| Analytics diverge from SQLite | Mitigated — full regeneration capability | **Mitigated** |
| MongoDB driver breaks PyInstaller build | Mitigated — early build testing specified | **Mitigated** |
| Wellbeing metrics misinterpreted | Mitigated — banned terminology, descriptive labels | **Mitigated** |
| Insight quality poor with insufficient data | Mitigated — confidence scoring | **Mitigated** |

### Consolidated Risk Summary

| Classification | Count | Key Risks |
|---------------|-------|-----------|
| **Mitigated** | 14 | Appropriate mitigations documented |
| **Accepted** | 7 | Low-impact or acceptable trade-offs |
| **Unresolved** | 0 | No unresolved risks |

### Verdict on Risks

**APPROVED** — All risks are either mitigated with documented plans or accepted as conscious trade-offs. No unresolved risks remain.

---

## 11. Architecture Scorecard

| Criterion | Score | Justification |
|-----------|-------|---------------|
| **Data Safety** | **Excellent** | SQLite is never modified by MongoDB; all analytics regenerable; support collections preserved verbatim; rollback via regeneration always available |
| **Upgrade Safety** | **Excellent** | Three-axis versioning handles schema, methodology, and collection evolution independently; mixed-version coexistence safe; downgrade protection via SQLite fallback |
| **Maintainability** | **Good** | Clear repository/service separation; explicit data ownership; regeneration over migration reduces migration complexity. Score held back by Phase 11 being architecture-only — maintainability will be proven during implementation |
| **Scalability** | **Good** | Analytics caching reduces live computation; incremental updates prevent full rebuilds; bounded storage growth. Score reflects local-first constraint — cloud scalability would need re-evaluation |
| **Simplicity** | **Excellent** | Three namespaces (analytics_*, insights_*, system_*); dual versioning covers all cases; regeneration as default strategy avoids complex migration frameworks |
| **Future Readiness** | **Excellent** | Roadmap extends through v4.0; new insight types additive; new collections follow naming convention; versioning accommodates future methodology changes without schema migrations |

### Overall Score

| Criterion | Score |
|-----------|-------|
| Data Safety | Excellent |
| Upgrade Safety | Excellent |
| Maintainability | Good |
| Scalability | Good |
| Simplicity | Excellent |
| Future Readiness | Excellent |

---

## 12. Final Verdict

### Verdict: READY WITH MINOR REVISIONS

### Findings Summary

| Classification | Count |
|---------------|-------|
| **APPROVED** | 64 |
| **NEEDS REVISION** | 2 |
| **REJECTED** | 0 |

### Required Revisions

| ID | Phase | Severity | Description |
|----|-------|----------|-------------|
| R01 | Phase 3 — insights_habits | Minor | Document that wellbeing metric `data` objects must not contain absolute threshold values — only user-relative comparisons and trends |
| R02 | Phase 2 / Phase 3 — system_schema | Minor | Document that `system_schema` should be included in BackupManager backup scope to preserve migration and generation history |

Both revisions are documentation-only. No architectural changes are required.

### Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| ✓ SQLite remains source of truth | **Confirmed** — No MongoDB collection owns runtime data |
| ✓ Support collections isolated | **Confirmed** — Permanently separated from analytics |
| ✓ No dual ownership | **Confirmed** — Every data type has exactly one owner |
| ✓ Regeneration over migration | **Confirmed** — Default strategy for all analytics and insights |
| ✓ Upgrade-safe | **Confirmed** — Three-axis versioning, mixed-version coexistence, downgrade protection |
| ✓ Offline-first | **Confirmed** — MongoDB unavailable → SQLite fallback |
| ✓ Local-first | **Confirmed** — Full functionality without MongoDB |
| ✓ Future version compatibility | **Confirmed** — Roadmap covers v2.0.x through v4.0 |
| ✓ Milestone 8 compatibility | **Confirmed** — SchemaVersionManager, BackupManager, MigrationManager all unaffected |
| ✓ Trackora architecture compatibility | **Confirmed** — All Trackora architectural layers preserved |

### Recommended Changes to Prior Phases

| Phase | Change Required | Priority |
|-------|----------------|----------|
| **Phase 3** — Document Model | Add note to `insights_habits`: wellbeing metric data must avoid absolute thresholds | Low |
| **Phase 2** — Foundation Spec (or Phase 3) | Add note to `system_schema` retention: include in BackupManager scope | Low |

Both changes are optional documentation clarifications. Neither blocks future implementation.

---

## Appendix A: Full Validation Checklist

| Item | Status |
|------|--------|
| SQLite remains source of truth | ✓ |
| No MongoDB collection becomes owner of runtime data | ✓ |
| Support collections permanently isolated from analytics | ✓ |
| No support data flows into analytics, insights, recommendations, wellbeing, or trends | ✓ |
| analytics_* collections can regenerate from SQLite | ✓ |
| insights_* collections can regenerate from analytics_* | ✓ |
| Support collections preserved verbatim across upgrades | ✓ |
| Every insight has reason_codes | ✓ |
| Every insight has source_metrics | ✓ |
| Every insight has generation_version | ✓ |
| Every data type has exactly one owner | ✓ |
| Compatible with SchemaVersionManager | ✓ |
| Compatible with BackupManager | ✓ |
| Compatible with MigrationManager | ✓ |
| Compatible with Startup Integration | ✓ |
| Compatible with Automatic Game Discovery | ✓ |
| Compatible with Update Center | ✓ |
| Compatible with Support Center | ✓ |
| Compatible with SQLite Architecture | ✓ |
| Compatible with Repository Layer | ✓ |
| Compatible with Statistics Layer | ✓ |
| Compatible with Upgrade Foundation | ✓ |
| Local-first: Trackora functional without MongoDB | ✓ |
| Offline-first: MongoDB unavailable → fallback works | ✓ |
| Roadmap covers v2.0.x | ✓ |
| Roadmap covers v2.x | ✓ |
| Roadmap covers v3.0 | ✓ |
| Roadmap covers v4.0 | ✓ |
| All findings classified APPROVED/NEEDS REVISION/REJECTED | ✓ |
| Collection review complete (15 collections) | ✓ |
| Risk review complete (19 risks) | ✓ |

## Appendix B: Architecture Rule Compliance Matrix

| Rule | Source | Status | Evidence |
|------|--------|--------|----------|
| No SQL in UI | `AGENTS.md` | **Compliant** | MongoDB is analytics layer, not UI |
| No business logic in widgets | `AGENTS.md` | **Compliant** | All analytics logic in service/aggregation layer |
| No dependencies without approval | `AGENTS.md` | **Pending** | pymongo/dnspython approval required for Phase A |
| Write tests | `AGENTS.md` | **Architecture ready** | Test strategy defined in Phase 4 |
| Use type hints | `AGENTS.md` | **Not applicable** | Architecture phase — no Python code |
| Follow architecture.md | `AGENTS.md` | **Compliant** | Seven-layer architecture preserved |
| SQLite + MongoDB parallel (v3.0) | Upgrade Foundation Spec | **Architecture ready** | Phase 6 roadmap schedules analytics for v2.x, insights for v3.0 |
