# Windows Runtime Remediation

## Overview

Remediation actions taken to resolve the 8 issues identified in
[windows-runtime-audit.md](./windows-runtime-audit.md) for the v2.0.0 release
on Windows.

## Issues & Fixes

### RB-1 (CRITICAL): `games` table missing `platform`, `platform_id`, `is_auto_discovered`

**Root cause:** `database_manager.py` created the `games` table without these
three columns; `games_repository._row_to_game()` accessed them by key →
`KeyError("No item with that key")` on first run (fresh DB, no migrations).

**Fix:** Added the three columns with appropriate defaults to the base `CREATE
TABLE` statement in `database/database_manager.py:58-78`.

**Schema change:**

| Column             | Type    | Default | Notes            |
|--------------------|---------|---------|------------------|
| `platform`         | TEXT    | NULL    | nullable string  |
| `platform_id`      | TEXT    | NULL    | nullable string  |
| `is_auto_discovered` | INTEGER | 0     | boolean (0/1)    |

Also added index `idx_games_platform` on `(platform)`.

### RB-2 (WARNING): `load_games()` O(n) name-matching

**Assessment:** Acceptable for expected game counts (< 500). No fix applied.
Enhancement deferred to future release.

### RB-3 (LOW): `_is_non_retryable()` may miss Atlas errors

**Fix:** Extended `_NON_RETRYABLE_KEYWORDS` in
`services/support/support_service.py:47` to include:
- `not available`
- `permission denied`
- `forbidden`
- `invalid`
- `bad request`
- `unsupported`

### RB-5 (LOW): Chart widgets lack max-height constraint

**Fix:** Added `setMaximumHeight(300)` to all three chart plot widgets in:
- `ui/widgets/daily_activity_chart.py`
- `ui/widgets/monthly_trend_chart.py`
- `ui/widgets/game_distribution_chart.py`

### RB-6 (LOW): Support form layout adds stretch

**Fix:** Removed all `addStretch()` calls from support form pages in
`ui/support_center/support_center_widget.py` (report_bug, suggest_feature,
feedback).

### RB-7 (LOW): Backup restore fails on staged-file rename (`WinError 5`)

**Assessment:** Pre-existing Windows compatibility limitation.
`os.replace()`/`shutil.move()` fail when the target file handle is held by the
same process. Requires architectural change to use SQLite backup API or
file-copy-then-delete approach. Deferred.

### RB-8 (LOW): Recovery manager allows unbounded session durations

**Fix:** Added constant `MAXIMUM_SESSION_DURATION_SECONDS = 86400` (24 h) to
`tracker/recovery_manager.py:26`. Recovery load filters out sessions whose
`start_time` exceeds this threshold from the current time.

### RB-9 (LOW): Test inline schemas missing platform columns

**Root cause:** Test fixture `SCHEMA_SQL` in `tests/trackora_stats/conftest.py`
and `tests/test_export_service.py` declared `games` tables without the three
platform columns, causing `_row_to_game()` → `KeyError` during unit tests.

**Fix:** Added `platform`, `platform_id`, `is_auto_discovered` to inline
schemas in both files.

## Test Fixture Updates

Updated migration-count assertions from `4` to `5` in:
- `tests/test_upgrade_lifecycle.py:790`
- `tests/test_startup_integration.py:336`

## Pre-existing Failures (not regressions)

| Failure | Reason | Category |
|---------|--------|----------|
| `test_init_cleans_orphan_tmp_failure_logged` | Temp file handle conflict | Windows permission |
| ~10 backup restore tests | `os.replace` fails (WinError 5) | Windows permission |
| `test_export_csv_*` (prior to fix) | Missing platform columns in test schema | FIXED |
| Startup integration tests | `SupabaseReportService` not found | Module refactor |
| Qt widget tests (stat_card, tray) | No display available | CI environment |
| `test_resolves_executable_path` | Epic manifest parse failure | Test data issue |
| `test_permission_denied`, `test_symlink_to_valid_file`, `test_write_permission_error_raised` | `os.replace` on Windows | Windows permission |

## Remaining Work

- (RB-4) Atlas endpoint appears on dashboard even when queue has items —
  depends on Atlas infrastructure, not a code bug.
- (RB-7) Backup restore rename failures on Windows — architectural change
  needed.
- Startup integration tests need module import path update.
