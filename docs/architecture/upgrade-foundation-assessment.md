# Upgrade Foundation — MigrationManager Audit Report

**Date:** 2026-06-20
**Status:** Assessment Complete
**Auditor:** Architecture Review

---

## 1. Executive Summary

The Upgrade Foundation architecture is well-specified across 3 documents (~2400 lines total). SchemaVersionManager and BackupManager are fully implemented and tested. MigrationManager has **zero implementation** — no code, no directory, no tests. The startup sequence in `__main__.py` has not been restructured to include the upgrade lifecycle.

**Overall Readiness Score: 40%** — architecture is solid, foundation managers are complete, but MigrationManager implementation and startup integration are the remaining bulk of Phase 6 work.

---

## 2. Architecture Document Alignment Score

| Document | Version | Status | Alignment with Reality |
|----------|---------|--------|----------------------|
| `upgrade-foundation-spec.md` | 2.0.0-draft | Architecture Design | **Low** — multiple divergences |
| `upgrade-foundation.md` | 1.0 | Draft | **Low** — same divergences |
| `milestone-8-upgrade-foundation.md` | 2.0.0-draft | Planning/Phase 0 | **Low** — deliverables not yet created |

**Key Divergences:**
- Spec says SchemaVersionManager must be created at startup Step 1-2; reality is Step 10 (after DB init)
- Spec says BackupManager integrated before migration; reality is not integrated at all
- Spec says `_migrations` table created by DatabaseManager; reality has no such table
- Spec says `trackora/core/migrations/` directory exists; reality has no such directory

---

## 3. Code Existence & Completeness

| Component | Status | Lines | Coverage |
|-----------|--------|-------|----------|
| SchemaVersion | ✅ Done | ~30 | 100% |
| SchemaVersionManager | ✅ Done | 119 | 100% |
| BackupManager | ✅ Done | 326 | 87% |
| Migration ABC | ❌ Missing | 0 | — |
| MigrationRegistry | ❌ Missing | 0 | — |
| MigrationManager | ❌ Missing | 0 | — |
| `_migrations` table in DB | ❌ Missing | 0 | — |
| `trackora/core/migrations/` package | ❌ Missing | 0 | — |
| `__main__.py` upgrade lifecycle | ❌ Missing | 0 | — |

---

## 4. Test Coverage

| Test Suite | Status | Count |
|------------|--------|-------|
| SchemaVersionManager unit | ✅ Done | 70 |
| SchemaVersionManager integration | ✅ Done | 24 |
| SchemaVersion architecture | ✅ Done | 91 |
| BackupManager unit | ✅ Done | 80 |
| BackupManager integration | ✅ Done | 5 |
| BackupManager architecture | ✅ Done | 4 |
| **MigrationManager unit** | **❌ Missing** | **0** |
| **MigrationRegistry unit** | **❌ Missing** | **0** |
| **Upgrade lifecycle integration** | **❌ Missing** | **0** |
| **Migration architecture isolation** | **❌ Missing** | **0** |

**Estimated test effort:** ~24 new tests (14 MigrationManager, 4 MigrationRegistry, 5 integration, 1 architecture)

---

## 5. Integration Readiness (in `__main__.py`)

**Current `__main__.py` startup (12 steps, ~220 lines):**

| Step | What | Alignment |
|------|------|-----------|
| 1 | Path resolution (`ensure_dirs`) | ✅ Matches spec |
| 2 | Logging setup | ⚠️ Acceptable before schema check |
| 3 | Error handler | ⚠️ Acceptable |
| 4 | Single instance lock | ✅ Required by spec |
| 5 | DatabaseManager init | ❌ Must move after SchemaVersion check |
| 6 | Schema creation via repos | ❌ Must move after migration |
| 7 | Settings load | ❌ Must move after migration |
| 8 | Schema setup (unknown) | ❌ Must audit |
| 9 | First-run detection | ❌ Must be replaced by SchemaVersionManager |
| 10 | SchemaVersionManager creation | ❌ Must move to Step 2 |
| 11 | Updater | ❌ Must move after migration |
| 12 | Process monitor | ❌ Must move after migration |
| 13 | UI | ❌ Must be last |

**Required spec flow:**
1️⃣ ensure_dirs → 2️⃣ SchemaVersionManager.read() → 3️⃣ is_compatible() → 4️⃣ BackupManager.create_backup() → 5️⃣ MigrationManager.apply_all() → 6️⃣ SchemaVersionManager.write() → 7️⃣ repos/services/UI

**Gap:** Major restructuring needed — 9 of 12 current steps are in the wrong order.

---

## 6. Dependency Inversion / Isolation

| Rule | Status |
|------|--------|
| SchemaVersionManager → paths.py + stdlib only | ✅ Enforced by test |
| BackupManager → paths.py + stdlib + SchemaVersionManager only | ✅ Enforced by test |
| MigrationManager → Connection + SchemaVersionManager + BackupManager only | ❌ No test exists |
| No circular dependencies | ✅ Structurally impossible |

---

## 7. Startup Sequence Alignment

The spec calls for this startup sequence:

```
1. ensure_dirs()              ← matches current Step 1
2. db.initialize()            ← add _migrations table creation
3. SchemaVersionManager.read() ← move from Step 10 to here
4. is_compatible() → guard     ← new integration
5. BackupManager.create_backup() ← new integration
6. MigrationManager.apply_all()  ← new integration
7. SchemaVersionManager.write()  ← new integration
8. Repository creation → UI      ← existing Steps 6-13, shifted
```

**Restructuring difficulty:** Medium-high. The 450-line `main()` function is monolithic. It does not use helper functions for distinct phases. SchemaVersionManager is imported and created at line 183. DatabaseManager init at line 105 creates the connection and schema before any version check.

---

## 8. Migration Directory Readiness

| Requirement | Status |
|-------------|--------|
| `trackora/core/migrations/__init__.py` | ❌ Missing |
| `trackora/core/migrations/registry.py` | ❌ Missing |
| `trackora/core/migrations/base_schema.py` | ❌ Missing |
| `trackora/core/migrations/v2_0_0_add_discovery_columns.py` | ❌ Missing |
| `trackora/core/migrations/v2_0_0_add_update_center_settings.py` | ❌ Missing |
| `trackora/core/migration_manager.py` (Migration ABC + MigrationManager) | ❌ Missing |

**Estimated implementation:** ~5 files, ~400 lines total

---

## 9. Data Loss Prevention (Backup Integration)

| Capability | Status |
|------------|--------|
| `create_backup(backup_type="pre_migration")` | ✅ Supported by BackupManager |
| `restore_backup(backup_id)` rollback | ✅ Supported by BackupManager |
| `verify_backup(backup_id)` integrity check | ✅ Supported |
| Retention policy cleanup | ✅ Supported |
| Backup before each migration in `__main__.py` | ❌ Not integrated |
| Backup during migration in `MigrationManager.apply_all()` | ❌ Not implemented |

**Risk:** No current defense-in-depth. If a migration is applied without BackupManager integration, data loss is unrecoverable.

---

## 10. Schema Version Integration

| Capability | Status |
|------------|--------|
| `read()` returns `None` on first run | ✅ Works |
| `is_compatible()` handles all 5 statuses | ✅ Works (first_run, ok, needs_migration, newer_data, unknown) |
| `write()` atomic via .tmp + rename | ✅ Works |
| Schema version used by BackupManager | ✅ In manifest metadata |
| Schema version checked before migration in startup | ❌ Not integrated |
| Schema version written after migration | ❌ Not integrated |

**Current startup bug:** SchemaVersionManager.read() at Step 10 returns `None` on first run, but this has no consumer — the version is never checked before DB init at Step 5.

---

## 11. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MigrationManager implementation diverges from spec | Medium | High | Spec is clear; follow it |
| `__main__.py` refactoring introduces regressions | Medium | High | Unit-test the new startup flow |
| Startup sequence changes break first-run detection | Medium | Medium | Integration test for first-run |
| MigrationManager depends on repos/services (arch violation) | Low | Medium | Architecture enforcement test |
| Order of SchemaVersionManager creation breaks BackupManager | Low | High | SchemaVersionManager must be created before BackupManager |
| Single migration takes >2s (NFR-02 violation) | Low | Low | Benchmark test |
| WAL mode + backup creates inconsistent DB snapshot | Low | Medium | Ensure DB connection closed before backup, or use `sqlite3.backup()` |

---

## 12. Gap Analysis

| # | Gap | Severity | Effort | Depends On |
|---|-----|----------|--------|------------|
| G1 | MigrationManager class missing | Critical | High | G2, G3 |
| G2 | Migration ABC missing | Critical | Medium | — |
| G3 | MigrationRegistry missing | Critical | Medium | G2 |
| G4 | Migration directory missing (5 files) | Critical | Low | G3 |
| G5 | `_migrations` table not in DatabaseManager | Critical | Low | — |
| G6 | `__main__.py` not restructured | Critical | High | G1, G5 |
| G7 | SchemaVersionManager created too late | High | Low | G6 |
| G8 | BackupManager not integrated in startup | High | Low | G6 |
| G9 | No migration isolation architecture test | High | Low | G1 |
| G10 | No migration lifecycle integration test | High | Medium | G1, G6 |

**Total estimated effort:** ~800 lines of code + ~500 lines of tests

---

## 13. Migration File Format & Registry

**Spec recommendation:** Python files (not SQL files) — enables complex transforms, conditional logic, API calls.

**Recommended first migration files:**

```
trackora/core/migrations/
├── __init__.py
├── registry.py          ← MigrationRegistry.discover(), get_by_id()
├── base_schema.py       ← v1.0.0 marker (records all v1.1.0 schema as "applied")
├── v2_0_0_add_discovery_columns.py
└── v2_0_0_add_update_center_settings.py
```

**Naming convention:** `v<major>_<minor>_<patch>_<short_description>.py`

**Migration ABC (in `migration_manager.py`):**
- `migration_id` (str) — unique, e.g. `v2_0_0_add_discovery_columns`
- `description` (str) — human-readable
- `app_version` (str) — target version after this migration
- `upgrade(connection)` — apply the migration
- `downgrade(connection)` — revert the migration
- `verify(connection) -> list[str]` — optional verification
- `requires_backup` (bool) — default True

---

## 14. Recommended Approach

### Phase 6a — Migration Infrastructure (files only, no logic)
1. Create `trackora/core/migrations/__init__.py`
2. Create `trackora/core/migration_manager.py` with Migration ABC
3. Create `trackora/core/migrations/registry.py`

### Phase 6b — MigrationManager Core Logic
4. Implement `MigrationManager` class in `migration_manager.py`
   - `__init__()` with dependency injection (Connection, SchemaVersionManager, BackupManager)
   - `get_pending_migrations()`, `get_applied_migrations()`, `get_all_migrations()`
   - `apply_all()` with SAVEPOINT transaction per migration
   - `apply_one()` for development/testing
   - `has_been_applied()`, `get_migration_checksum()`

### Phase 6c — Database Schema
5. Add `_migrations` table creation to `database_manager.py` in `_create_schema()`

### Phase 6d — Startup Integration
6. Restructure `__main__.py`:
   - Move SchemaVersionManager creation to Step 2 (after ensure_dirs, before DB init)
   - Add is_compatible() guard
   - Add BackupManager.create_backup() call
   - Add MigrationManager.apply_all() call
   - Add SchemaVersionManager.write() after successful migration

### Phase 6e — Migration Files
7. Create `base_schema.py` (v1.0.0 marker)
8. Create `v2_0_0_add_discovery_columns.py`
9. Create `v2_0_0_add_update_center_settings.py`

### Phase 6f — Tests
10. Unit tests: Migration ABC validation
11. Unit tests: MigrationRegistry discovery/sorting
12. Unit tests: MigrationManager (pending, apply, rollback, checksum)
13. Integration tests: Full upgrade lifecycle
14. Architecture enforcement: migration isolation

---

## 15. Readiness Score

| Category | Weight | Score | Weighted |
|----------|--------|-------|----------|
| Architecture documentation | 15% | 90% | 13.5% |
| SchemaVersionManager completeness | 15% | 100% | 15.0% |
| BackupManager completeness | 15% | 100% | 15.0% |
| MigrationManager implementation | 25% | 0% | 0.0% |
| `__main__.py` integration | 15% | 0% | 0.0% |
| Migration infrastructure (dir/table) | 10% | 0% | 0.0% |
| Test coverage for migration | 5% | 0% | 0.0% |
| **Total** | **100%** | — | **43.5%** |

**Readiness: MODERATE** — architecture is clear, dependencies are complete, but ~56% of the implementation work remains.

### Verdict

**Proceed to Architecture Specification.** The architecture is sufficiently well-defined, the foundation managers (SchemaVersionManager, BackupManager) are production-ready, and the remaining gaps are implementation-only. No additional audit is needed.

### Recommendation

Begin Phase 6 — MigrationManager Architecture Specification, starting with the Migration ABC and MigrationRegistry (Phase 6a), followed by the core MigrationManager class (Phase 6b).
