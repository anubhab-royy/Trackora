# Windows Runtime Audit Report — Trackora v2.0.0

**Date:** 2026-06-21  
**Audit Scope:** Full runtime investigation across all major subsystems  
**Methodology:** Source code audit + startup log analysis + data flow trace  

---

## Executive Summary

Trackora v2.0.0 has **one release-blocking defect** (Critical severity) and **one High severity defect**, both caused by a single root cause: the `games` table schema omits columns that the code assumes exist on **fresh database creation**. Four of eight investigated issues trace back to this bug.

The Support Center and Atlas pipeline are **functionally correct** — the queue fallback works as designed. The missing `.env` file is an environment configuration gap, not a code defect.

**Go / No-Go: NOT READY** — the critical schema bug must be fixed before release.

---

## Issue Inventory

| # | Title | Severity | Root Cause | Release-Blocking |
|---|-------|----------|------------|-----------------|
| 1 | Dashboard Runtime Failure | **CRITICAL** | Missing DB columns in base schema | YES |
| 2 | Session Integrity (132h session) | **MEDIUM** | Expected recovery behavior; discovery scope issue | NO |
| 3 | Support Center Queueing | **MEDIUM** | Missing `.env` file (environment, not code) | NO |
| 4 | Atlas Validation | **MEDIUM** | Missing `.env` file (environment, not code) | NO |
| 5 | Chart Data Empty | **HIGH** | Same root cause as Issue 1 | YES (blocking for charts feature) |
| 6 | Chart Layout Oversized | **LOW** | No maximum height constraint on plot widgets | NO |
| 7 | Support Center Whitespace | **LOW** | `addStretch()` at bottom of each form | NO |
| 8 | Windows Runtime | **LOW** | `.env` detection path correct; no Windows-specific bugs | NO |

---

## Issue 1 — Dashboard Runtime Failure (CRITICAL)

### Evidence

From `startup.log`:
```
2026-06-21 06:44:22 [ERROR] ui.dashboard.dashboard_controller |
  Failed to load dashboard data: No item with that key
2026-06-21 06:44:22 [ERROR] services.game_service |
  Failed to retrieve games: No item with that key
2026-06-21 06:44:22 [ERROR] services.session_history_service |
  Failed to load games for history filter: No item with that key
```

The error repeats every 5 seconds for the dashboard (auto-refresh timer).

### Root Cause

**The `_row_to_game()` function in `games_repository.py:28-30` accesses columns that do not exist in the base schema.**

```python
# games_repository.py:26-31
def _row_to_game(row: sqlite3.Row) -> Game:
    platform = row["platform"] if row["platform"] is not None else ""
    platform_id = row["platform_id"] if row["platform_id"] is not None else ""
    is_auto_discovered = bool(row["is_auto_discovered"]) ...
```

These three columns (`platform`, `platform_id`, `is_auto_discovered`) are added by migration `v2_0_0_add_discovery_columns.py` via `ALTER TABLE`. However, the base schema in `database_manager.py:161-174` does **not** include them:

```sql
CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    process_name     TEXT    NOT NULL,
    executable_path  TEXT    NOT NULL,
    icon_path        TEXT    NOT NULL DEFAULT '',
    is_enabled       INTEGER NOT NULL DEFAULT 1,
    first_played     DATETIME,
    last_played      DATETIME,
    created_at       DATETIME NOT NULL,
    updated_at       DATETIME NOT NULL
);
```

On **first run** (`__main__.py:121-123`), the code sets the schema version but **does not apply migrations**:

```python
if compat.status == "first_run":
    schema_version_manager.write(app_version)
    # ⚠ No migrations applied!
```

When `_row_to_game()` tries `row["platform"]`, Python's `sqlite3.Row.__getitem__` raises `KeyError("No item with that key")`.

### Affected Files

| File | Line(s) | Issue |
|------|---------|-------|
| `database/database_manager.py` | 161-174 | Missing `platform`, `platform_id`, `is_auto_discovered` in base schema |
| `database/repositories/games_repository.py` | 28-30 | Accesses columns absent from base schema |
| `trackora/__main__.py` | 121-123 | First-run path skips migrations |
| `ui/dashboard/dashboard_controller.py` | 114-124 | Catches exception, shows "Error loading data" |
| `services/game_service.py` | 73-76 | Catches exception, returns empty list |
| `services/session_history_service.py` | 128-132 | Catches exception, returns empty list |

### Downstream Impact

- **Dashboard**: Shows "Error loading data" — completely broken
- **Games page**: Cannot list or manage games — broken
- **History filter dropdown**: Cannot load game list — broken
- **Charts**: Game distribution chart fails (see Issue 5)
- **Session recovery recovery**: Only `active_sessions_repo` is used, so recovery works
- **Session history table**: Uses `query_sessions()` with JOIN on `games` — the JOIN query succeeds because `sessions.*, g.name AS game_name` doesn't select the missing columns. But the session data display might work independently.

### Fix

**Option A (Recommended):** Add the three columns to the base schema in `database_manager.py`:
```sql
platform         TEXT    DEFAULT NULL,
platform_id      TEXT    DEFAULT NULL,
is_auto_discovered INTEGER DEFAULT 0,
```
This makes fresh databases self-contained without requiring migration.

**Option B:** Apply migrations on first run by removing the `first_run` shortcut in `__main__.py`.

### Fix Effort: 15 minutes

---

## Issue 2 — Session Integrity (MEDIUM)

### Evidence

Reported: GHelper session showing 132h 25m.

### Analysis

The `RecoveryManager.recover()` (`tracker/recovery_manager.py:93-147`) reads orphaned `active_sessions` rows and calculates `duration = recovery_time - start_time`. If Trackora crashes and the computer remains on for 132 hours before Trackora is restarted, the recovery produces a 132-hour session.

**This is not a code bug** — the recovery mechanism correctly reconstructs what it can from available data. It has no way to know that the user wasn't playing for 132 hours.

The actual issue is that GHelper (a laptop utility process, likely ASUS) was added as a tracked game. This is either:
1. A manual user addition
2. An auto-discovery false positive

### Data Integrity Assessment

- The session data is internally consistent
- Total playtime statistics are inflated by the 132h outlier
- No corruption exists
- The recovery mechanism is working as designed

### Remediation

1. Add a maximum session duration threshold to `RecoveryManager` (e.g., 24 hours = 86400 seconds)
2. Add a manual "delete session" UI action to History page (already exists via context menu)
3. Review discovery detectors for false positives (GHelper process name matching)

### Severity: MEDIUM — data quality issue, not a defect

---

## Issue 3 — Support Center Queueing (MEDIUM)

### Evidence

```
2026-06-21 06:44:19 [WARNING] trackora.core.env | No .env file found
2026-06-21 06:44:19 [WARNING] __main__ | MongoDB reporting: not available
2026-06-21 06:44:22 [WARNING] services.support.report_queue_service |
  Queued report submission failed, keeping: 4e2d15a8-...json
2026-06-21 06:44:22 [WARNING] services.support.report_queue_service |
  Queued report submission failed, keeping: 94ed51c7-...json
```

### Analysis

The pipeline works correctly:

1. `load_env_file()` (`env.py:47-96`) searches for `.env` in CWD and project root — finds neither
2. `MongoConnection.__init__()` reads `MONGODB_URI` from env — gets empty string
3. `health_check()` returns `False` because URI is empty
4. `MongoReportService._insert()` checks `is_available` — returns `SubmitResult(success=False, error_message="MongoDB not available.")`
5. `SupportService._try_github_submit()` catches the failure
6. `_is_retryable("MongoDB not available.")` — the string does NOT match `_NON_RETRYABLE_KEYWORDS` (`["not configured", "authentication failed", "not found", "check your"]`), so it IS considered retryable
7. `_try_queue_report()` saves to `pending_reports/` — success
8. On restart, `MainWindow._process_report_queue()` triggers retry — fails again because Atlas still unavailable
9. Reports remain in queue for next startup

The user sees **"Report saved locally and will be sent automatically."** which is the correct message per `SupportCenterController._show_submit_result()` (line 153-156). This is the expected fallback behavior.

### Issue

The `_NON_RETRYABLE_KEYWORDS` list does NOT include any variants of "not available" or "MongoDB". The `_is_retryable()` function classifies "MongoDB not available" as retryable, which causes repeated queue processing failures. The queue will never drain until Atlas is configured.

### Fix

Add "not available" to `_NON_RETRYABLE_KEYWORDS` in `support_service.py:62-67` so that when MongoDB is genuinely unavailable (not just a transient network error), the queue correctly marks failures as non-retryable instead of trying forever.

### Fix Effort: 5 minutes

---

## Issue 4 — Atlas Validation (MEDIUM)

### Analysis

Without a `.env` file containing:
```
MONGODB_URI=mongodb+srv://user:pass@trackora-support.xxxxx.mongodb.net/
MONGODB_DATABASE=trackora_support
```

Atlas collections (`bug_reports`, `feature_requests`, `feedback`, `crash_reports`) contain zero documents. This is an environment configuration gap, not a code defect.

Pending reports exist at: `%APPDATA%\Trackora-Dev\pending_reports\`

### Fix

Create `.env` file in project root with valid Atlas credentials.

---

## Issue 5 — Chart Data Empty (HIGH)

### Evidence

Charts appear empty on all three chart widgets.

### Analysis

The `ChartsController.refresh()` (`charts_controller.py:44-61`) calls three methods in a single `try/except`:

```python
try:
    daily = self._service.get_daily_activity(days=30)       # sessions only — likely succeeds
    self._view.daily_chart.refresh(daily)                    # renders daily chart
    monthly = self._service.get_monthly_activity(months=12)  # sessions only — likely succeeds
    self._view.monthly_chart.refresh(monthly)                # renders monthly chart
    summaries = self._service.get_game_playtime_summaries()  # calls games_repo.get_all() → FAILS
    self._view.distribution_chart.refresh(summaries)
except Exception as exc:
    logger.error("Failed to refresh charts: %s", exc)       # ← ALL charts appear empty
```

Even though daily and monthly chart queries may succeed (they use the `sessions` table only), the third call to `get_game_playtime_summaries()` fails with the same `KeyError("No item with that key")` because it calls `GamesRepository.get_all()` → `_row_to_game()` → accesses missing columns. The `except` clause catches this and **all three charts** show nothing.

### Root cause

Same as Issue 1 — missing columns in `games` table base schema.

### Fix

Same as Issue 1 — add missing columns to base schema.

### Fix Effort: Included in Issue 1 fix

---

## Issue 6 — Chart Layout Oversized (LOW)

### Evidence

Chart panels are excessively large with wasted space.

### Analysis

Each chart widget (`daily_activity_chart.py:104`, `monthly_trend_chart.py:104`, `game_distribution_chart.py:108`) uses:

```python
self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
self._plot.setMinimumHeight(220)
```

The plot widgets have **`Expanding` vertical policy** with **no maximum height** constraint. The containing card (`charts_view.py:135`) uses:

```python
card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
```

The card is `Fixed` vertically, meaning its height is determined by its content's preferred size. With `Expanding` vertical policy, `PlotWidget` tends to report a large preferred height. Combined with `setMinimumHeight(220)`, the plot can grow significantly when the window is resized.

The problematic behavior:
1. Each chart has **no `setMaximumHeight()`**
2. The `Expanding` + `Expanding` policy chain means plots take as much space as available
3. Only 3 charts stack vertically, creating a very tall scroll area
4. No responsive breakpoints or adaptive sizing

### Recommendation

Add `setMaximumHeight(300)` or similar upper bound to each chart plot widget:

```python
self._plot.setMinimumHeight(220)
self._plot.setMaximumHeight(300)
```

Alternatively, use `Preferred` vertical policy instead of `Expanding`.

### Fix Effort: 15 minutes

---

## Issue 7 — Support Center Layout (LOW)

### Evidence

Excessive whitespace at the bottom of each form page; submit button position is not anchored to form content.

### Analysis

Each form page in `support_center_widget.py` ends with:

```python
layout.addStretch()     # ← pushes all content up, creates whitespace
```

The `addStretch()` creates a flexible spacer that absorbs all remaining vertical space. In a scroll area, this forces all form content to the top and leaves the bottom half (or more) empty.

Additionally:
- The submit button is placed above the stretch, before the whitespace
- The "Upcoming Updates" page has a similar stretch
- The `setFixedHeight()` on text fields (80px, 100px, 120px for `QPlainTextEdit`) is moderate

### Recommendation

Remove `addStretch()` from each form page. The `QScrollArea` already handles overflow — forms should use their natural height.

### Fix Effort: 10 minutes

---

## Issue 8 — Windows Runtime Audit (LOW)

### Analysis

Windows-specific concerns checked:

| Concern | Status | Evidence |
|---------|--------|----------|
| `.env` file loading | WORKS | `env.py` uses `Path.cwd() / ".env"` and project root — both valid on Windows |
| `APPDATA` path resolution | WORKS | `paths.py:31-34` reads `os.environ["APPDATA"]` — correct for Windows |
| `AppData\Roaming\Trackora-Dev` | WORKS | Created correctly by `ensure_dirs()` |
| Single instance lock | WORKS | `CreateMutexW` via ctypes — correct for Windows |
| SQLite WAL mode | WORKS | No platform-specific issues |
| Process monitoring (psutil) | WORKS | Cross-platform |
| PyQt6 rendering | WORKS | No Windows-specific rendering issues detected |

No Windows-specific code defects found. The `.env` absence is the only environmental gap.

---

## Root Cause Analysis Summary

```
Missing columns in base schema (database_manager.py)
    ↓
_row_to_game() raises KeyError("No item with that key")
    ↓
GamesRepository.get_all() fails
    ↓
GameService.get_all_games()     → Games page broken          (Issue 1)
StatisticsService.get_most_played_game() → Dashboard broken  (Issue 1)
SessionHistoryService.get_games() → History filter broken    (Issue 1)
PlaytimeCalculator.get_game_playtime_summaries() → Charts     (Issue 5)
```

All four subsystems (Dashboard, Games, History, Charts) fail due to the same root cause.

---

## Release-Blocking Defect List

| # | Defect | File | Fix |
|---|--------|------|-----|
| **RB-1** | `games` base schema missing `platform`, `platform_id`, `is_auto_discovered` columns | `database/database_manager.py:161-174` | Add columns to `CREATE TABLE` |
| **RB-2** | Charts all empty because `get_game_playtime_summaries()` fails via same root cause | `ui/widgets/charts_controller.py:56` | Auto-fixed when RB-1 is fixed |

---

## Non-Blocking Issues (Fix Optional)

| # | Issue | Priority |
|---|-------|----------|
| NB-1 | `_is_retryable()` should exclude "not available" to prevent infinite queue retries | Medium |
| NB-2 | `RecoveryManager` should cap maximum recovered session duration (e.g., 24h) | Low |
| NB-3 | Chart widgets need `setMaximumHeight()` to prevent oversized panels | Low |
| NB-4 | Support Center forms should remove `addStretch()` for natural height | Low |

---

## Ordered Fix Plan

| Order | Fix | Effort | Dependencies |
|-------|-----|--------|-------------|
| 1 | Add missing columns to `database_manager.py` base schema + add `_row_to_game` defensive check | 15 min | None |
| 2 | Verify all subsystems work (Dashboard, Games, History, Charts) | 10 min | Fix 1 |
| 3 | Add "not available" to `_NON_RETRYABLE_KEYWORDS` in `support_service.py` | 5 min | None |
| 4 | (Optional) Add `setMaximumHeight()` to chart plot widgets | 15 min | None |
| 5 | (Optional) Remove `addStretch()` from support center forms | 10 min | None |
| 6 | (Optional) Add max session duration cap in `RecoveryManager` | 15 min | None |

**Total critical effort:** 25 minutes  
**Total optional effort:** 40 minutes  

---

## Go / No-Go Release Recommendation

**RECOMMENDATION: NOT READY**

### Conditions for Release

1. **Required:** Fix RB-1 (missing schema columns)
2. **Required:** Verify Dashboard, Games, History, and Charts all load correctly
3. **Required:** Verify fresh database creation produces correct schema
4. **Required:** Verify migration from v1.1.0 still works (the migration is still needed for existing DBs)
5. **Recommended:** Fix NB-1 (queue retry classification) to prevent infinite retries
6. **Optional:** Fix NB-2 through NB-4 for polish

### Reasoning

The critical defect (RB-1) makes the application unusable on first run — the Dashboard shows "Error loading data", the Games page cannot display games, the History filter cannot load game names, and Charts show empty. These are core user-facing features.

The fix is small (15 minutes) and scoped to a single file (`database_manager.py`), but it is absolutely required before any user can meaningfully use Trackora v2.0.0.

### Verification Commands

```bash
# After fix — create fresh database and verify
Remove-Item -Path "$env:APPDATA\Trackora-Dev\trackora.db" -ErrorAction SilentlyContinue
python -m trackora
# Dashboard should show data, Games should list, Charts should render

# Migration test — create v1.1.0 DB then upgrade
python -c "
import sqlite3
conn = sqlite3.connect('test_v1.db')
conn.execute('''CREATE TABLE games (
    id INTEGER PRIMARY KEY, name TEXT, process_name TEXT,
    executable_path TEXT, icon_path TEXT DEFAULT '',
    is_enabled INTEGER DEFAULT 1,
    first_played DATETIME, last_played DATETIME,
    created_at DATETIME, updated_at DATETIME
)''')
conn.close()
"
# Then run Trackora with this DB to verify migration applies
```
