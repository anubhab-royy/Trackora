Python 3.13+

Use:
- PyQt6
- SQLite
- psutil
- pytest

Never:
- Put SQL inside UI
- Put business logic inside widgets
- Add dependencies without approval

Always:
- Write tests
- Use type hints
- Follow architecture.md

## Session Summary — Upgrade & Performance Validation

### Done
- Phase 13D: `tests/test_upgrade_validation.py` — 50 tests, all pass.
- Phase 13E: `tests/test_upgrade_backup_restore.py` — 40 tests, all pass.
- Phase 13F: `tests/test_upgrade_recovery.py` — 30 tests, all pass.
- Phase 13I: `tests/test_upgrade_performance.py` — 46 benchmarks (8 domains), all pass. 17 NFR targets met, 28 baselines captured.
- Phase 13G: `tests/test_packaging_validation.py` — 71 tests across 9 packaging domains, all pass. Defensive hidden imports added to `Trackora.spec`.
- Completion reports: `docs/architecture/phase13d-upgrade-validation.md`, `phase13e-backup-restore-validation.md`, `phase13f-recovery-validation.md`, `phase13i-performance-validation.md`, `phase13-packaging-validation.md`.

### Key NFRs Met
| Domain | NFR | Measured | Result |
|--------|-----|----------|--------|
| Dashboard composite load | ≤5000ms | 4.08ms | PASS |
| History default page | ≤300ms | 0.43ms | PASS |
| Charts 30d activity | ≤300ms | 0.28ms | PASS |
| Migration v1→v2 total | ≤10000ms | 9.90ms | PASS |
| Report submission | ≤15000ms | 2.04ms | PASS |

### Next
- Awaiting user direction (Atlas integration, Phase 13G/13H, etc.).