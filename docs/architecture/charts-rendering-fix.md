# Charts Rendering Fix

## Completed: 2026-06-22

## Root Causes

### 1. Charts Never Received Data (Critical)

**Problem:** `ChartsController.refresh()` was never called during the application lifecycle.

**Evidence:**
- `MainWindow._build_views()` (line 235) created `ChartsController` but never called `.refresh()`
- `MainWindow._refresh_current_view()` only handled `DashboardWidget`, not `ChartsView`
- `MainWindow._connect_nav()` only switched the stacked widget with no refresh trigger
- No signal was connected to `QStackedWidget.currentChanged` for Charts

**Fix:** Three changes to `ui/main_window.py`:
1. Added `_on_page_changed` handler connected to `_content.currentChanged`
2. Added `ChartsView` and `HistoryView` handling in `_refresh_current_view`
3. Import `HistoryView` for type checking

### 2. Empty State Messages Unhelpful

**Problem:** All three chart widgets displayed "No session data yet" — a generic message that doesn't guide users.

**Fix:** Changed to actionable message:
```
No playtime data available yet.
Start tracking games to see analytics.
```

### 3. Chart Sizing Suboptimal

**Problem:** Charts consumed excessive vertical space (min 220px per chart, total ~900px for 3 charts filled most viewports).

**Fix:** Reduced dimensions:
| Chart | Before (min/max) | After (min/max) |
|-------|------------------|------------------|
| Daily Activity | 220 / 300 px | 180 / 280 px |
| Monthly Trend | 220 / 300 px | 180 / 280 px |
| Game Distribution | 220 / 300 px | 180 / 280 px |

Also reduced card padding from `(16, 12, 16, 12)` to `(12, 8, 12, 8)`.

### 4. No Diagnostic Logging

**Problem:** No visibility into what data charts were receiving.

**Fix:** Added structured logging in `ChartsController.refresh()`:
- Daily activity: record count + max hours
- Monthly trend: month count + max hours
- Game distribution: game count + total hours

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `ui/main_window.py` | Added `_on_page_changed`, updated `_refresh_current_view`, added `HistoryView` import | +20 |
| `ui/widgets/charts_controller.py` | Added diagnostic logging with data validation | +12 |
| `ui/widgets/daily_activity_chart.py` | Updated empty state text, reduced min/max height | 2 |
| `ui/widgets/monthly_trend_chart.py` | Updated empty state text, reduced min/max height | 2 |
| `ui/widgets/game_distribution_chart.py` | Updated empty state text, reduced min/max height | 2 |
| `ui/widgets/charts_view.py` | Reduced card padding | 1 |

## Refresh Lifecycle

| Event | Before Fix | After Fix |
|-------|-----------|-----------|
| App startup → Dashboard | Dashboard refreshes (internal timer) | Dashboard refreshes (internal timer) |
| Navigate to Charts | **No refresh — charts empty** | `_on_page_changed` calls `_charts_ctrl.refresh()` |
| 5s auto-refresh timer | Only Dashboard refreshed | Dashboard, Charts, and History all refresh |
| Data change during tracking | Only Dashboard updated | Dashboard updated; Charts update when navigated to |
| App restart | Charts empty until bug fix | Charts load on first navigation |

## Cross-Reference Validation

Data consistency is ensured because all views read from the same `StatisticsService` singleton:

| View | Service Method | Data Source |
|------|---------------|-------------|
| Dashboard total playtime | `get_lifetime_stats()` | `SessionsRepository.get_all()` |
| Dashboard today/week/month | `get_daily_stats()`, `get_weekly_stats()`, `get_monthly_stats()` | `SessionsRepository.get_by_date_range()` |
| Charts daily activity | `get_daily_activity()` | `SessionsRepository.get_daily_totals_for_range()` |
| Charts monthly trend | `get_monthly_activity()` | `SessionsRepository.get_daily_totals_for_range()` (aggregated) |
| Charts game distribution | `get_game_playtime_summaries()` | `SessionsRepository.get_all()` + `GamesRepository.get_all()` |
| History page | `SessionHistoryService.query()` | `SessionsRepository.query_sessions()` |

The same `StatisticsService` instance is injected into both `DashboardController` and `ChartsController` at construction time (`ui/main_window.py:210-238`), guaranteeing data consistency.

## Empty State Handling

When no data exists:
- Charts show the message: "No playtime data available yet. Start tracking games to see analytics."
- Charts do NOT display broken axis labels (0.1, 0.2, etc.)
- The empty state label is centered and styled consistently
- No crashes or blank widgets on empty/corrupted data

## Corrupted/Incomplete Data Safety

All chart `refresh()` methods wrap data access in try/except at the controller level (`charts_controller.py:60`). Individual chart widgets also check for:
- Empty dates/labels lists → show empty state
- Zero max_value → use `max(1, ...)` for axis range
- Missing games → display "Unknown ({id})" fallback
