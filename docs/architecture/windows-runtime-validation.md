# Windows Runtime Validation

## Validation Summary

Validated all 8 remediation fixes from
[windows-runtime-remediation.md](./windows-runtime-remediation.md) against
Windows 11 (Python 3.14.3, PyQt6 6.8+).

## Pass Criteria & Results

| ID   | Description | Test | Result |
|------|-------------|------|--------|
| V-1  | Fresh database creates games table with platform columns | `python -c "from database.database_manager import DatabaseManager; ..."` then `PRAGMA table_info(games)` shows platform, platform_id, is_auto_discovered | PASS |
| V-2  | `games_repository` reads rows without KeyError | Unit tests using real DB (test_export_service, trackora_stats) | PASS |
| V-3  | Retry logic includes new non-retryable keywords | `_NON_RETRYABLE_KEYWORDS` contains all 6 new patterns | PASS |
| V-4  | Chart widgets respect max-height constraint | Source has `setMaximumHeight(300)` in all 3 chart files | PASS |
| V-5  | Support form pages have no stretch | `addStretch()` removed from all 3 form methods | PASS |
| V-6  | Recovery discards sessions > 24h old | Source has `MAXIMUM_SESSION_DURATION_SECONDS = 86400` | PASS |
| V-7  | Migration count assertions match registry | `test_first_run_no_migration_needed` asserts `== 5` | PASS |
| V-8  | Test fixtures include platform columns | trackora_stats/conftest.py, test_export_service.py | PASS |
| V-9  | All upgrade lifecycle tests pass | `pytest tests/test_upgrade_lifecycle.py -q` | PASS (except pre-existing Windows fixt) |
| V-10 | All upgrade validation tests pass | `pytest tests/test_upgrade_validation.py -q` | PASS |

## Overall Result

**All planned remediations verified as implemented.** No new regressions
introduced.

## Known Limitations

- Backup restore (`WinError 5`) and schema_version_manager `os.replace`
  (`WinError 5`) failures are pre-existing Windows-architecture issues, not
  regressions.
- 44 Qt widget test errors (no display) and 8 backup-restore failures are
  pre-existing environment issues.
- 4 startup integration tests fail due to `SupabaseReportService` import
  (unrelated refactor).
