# Game Consolidation — Validation Report

## Date
2026-06-21

## Before Merge State

| Metric | Value |
|--------|-------|
| Total games | 5 |
| Total sessions | 11 |
| Total playtime | 74529 seconds |
| Statistics cache rows | 0 |
| Active sessions | 1 (game_id=2, Valorant legacy) |

### Games Before
| ID | Name | Platform | Sessions | Total (s) |
|----|------|----------|----------|-----------|
| 1 | eFootball | NULL | 8 | 64621 |
| 2 | Valorant | NULL | 3 | 9908 |
| 10 | eFootball™ | steam | 0 | 0 |
| 11 | Wallpaper Engine | steam | 0 | 0 |
| 12 | Valorant | riot | 0 | 0 |

## After Merge State

| Metric | Value | Delta |
|--------|-------|-------|
| Total games | 4 | -1 ✅ |
| Total sessions | 11 | 0 ✅ |
| Total playtime | 74529 seconds | 0 ✅ |
| Statistics cache rows | 0 | 0 ✅ |
| Active sessions | 1 (game_id=2) | unchanged ✅ |

### Games After
| ID | Name | Platform | Sessions | Total (s) |
|----|------|----------|----------|-----------|
| 2 | Valorant | NULL | 3 | 9908 |
| 10 | eFootball™ | steam | 8 | 64621 |
| 11 | Wallpaper Engine | steam | 0 | 0 |
| 12 | Valorant | riot | 0 | 0 |

## Validation Checks

| # | Check | Expected | Actual | Result |
|---|-------|----------|--------|--------|
| 1 | Game count decreased by 1 | 4 | 4 | ✅ |
| 2 | Legacy ID=1 removed | Gone | Gone | ✅ |
| 3 | Surviving ID=10 present | Present | Present | ✅ |
| 4 | Total session count unchanged | 11 | 11 | ✅ |
| 5 | Total playtime unchanged | 74529s | 74529s | ✅ |
| 6 | Surviving process_name = eFootball.exe | `eFootball.exe` | `eFootball.exe` | ✅ |
| 7 | first_played preserved | `2026-06-10T11:05:26` | `2026-06-10T11:05:26` | ✅ |
| 8 | last_played preserved | `2026-06-13T17:20:38` | `2026-06-13T17:20:38` | ✅ |
| 9 | Sessions on surviving = legacy sessions | 8 sessions, 64621s | 8 sessions, 64621s | ✅ |
| 10 | No eFootball duplicates remain | 0 | 0 | ✅ |

## Test Suite
All **40 game_service tests pass** — including the newly updated `import_discovered_games` tests that validate:
- Normalized name match updates legacy records
- Existing duplicate checks preserved
- No regressions in add/edit/delete/enable flows

Full suite: **2013 passed**, 11 pre-existing failures (unrelated), 44 pre-existing errors (Qt environment on non-GUI test runner).

## Remaining Items

| Item | Status | Action |
|------|--------|--------|
| Valorant (ID=2→12) merge | **MANUAL REVIEW** | Investigate 3 sessions (9908s) — real playtime or Trackora uptime? |
| Valorant active session (ID=15) | **MANUAL REVIEW** | PID 2924 — process may not exist; consider cleanup |
| Future scan protection | **DEPLOYED** | Normalized name matching in `import_discovered_games()` |
| Statistics cache | **N/A** | Table exists but empty; no migration needed |
