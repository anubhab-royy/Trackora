# Charts & Analytics Audit

## Completed: 2026-06-22

## Data Flow Trace

```
SQLite (sessions, games, active_sessions)
    ↓
Repository Layer (database/repositories/)
    SessionsRepository.get_daily_totals_for_range()
    SessionsRepository.get_all()
    SessionsRepository.get_by_date_range()
    GamesRepository.get_all()
    ↓
Statistics Layer (trackora_stats/)
    PlaytimeCalculator.get_daily_activity()
    PlaytimeCalculator.get_monthly_activity()
    PlaytimeCalculator.get_game_playtime_summaries()
    ↓
StatisticsService (trackora_stats/statistics_service.py)
    get_daily_activity()
    get_monthly_activity()
    get_game_playtime_summaries()
    ↓
Controller Layer (ui/widgets/)
    ChartsController.refresh()
    ↓
View Layer (ui/widgets/)
    DailyActivityChart.refresh()
    MonthlyTrendChart.refresh()
    GameDistributionChart.refresh()
```

## Dependency Map

| Layer | File | Key Class | Responsibility |
|-------|------|-----------|----------------|
| Database | `database/repositories/sessions_repository.py` | `SessionsRepository` | All SQL for sessions |
| Database | `database/repositories/games_repository.py` | `GamesRepository` | All SQL for games |
| Statistics | `trackora_stats/playtime_calculator.py` | `PlaytimeCalculator` | Pure calculation logic |
| Statistics | `trackora_stats/trend_analyzer.py` | `TrendAnalyzer` | Trend comparisons |
| Statistics | `trackora_stats/statistics_service.py` | `StatisticsService` | Public facade |
| Statistics | `trackora_stats/models.py` | Data models | Dataclass definitions |
| Controller | `ui/widgets/charts_controller.py` | `ChartsController` | Bridges service ↔ view |
| View | `ui/widgets/charts_view.py` | `ChartsView` | Container with scroll |
| View | `ui/widgets/daily_activity_chart.py` | `DailyActivityChart` | PyQtGraph bar chart |
| View | `ui/widgets/monthly_trend_chart.py` | `MonthlyTrendChart` | PyQtGraph bar chart |
| View | `ui/widgets/game_distribution_chart.py` | `GameDistributionChart` | Horizontal bar chart |
| Orchestrator | `ui/main_window.py` | `MainWindow` | Creates + wires all |

## Data Validation

### Database Audit (SQLite)

| Table | Purpose | Status |
|-------|---------|--------|
| `games` | Game definitions with process names | Has data after game detection / manual add |
| `sessions` | Completed game sessions with duration_seconds | Has data after tracking sessions |
| `active_sessions` | Currently running sessions | Only populated while games are running |
| `settings` | Key-value store | Not analytics-related |
| `statistics_cache` | Dropped in v1.1.0 migration | Not present |

### Key Queries

**Daily Activity:**
```sql
SELECT DATE(start_time) AS day, COALESCE(SUM(duration_seconds), 0) AS total
FROM sessions
WHERE start_time >= ? AND start_time < ?
GROUP BY day ORDER BY day ASC;
```

**Game Distribution:**
Iterates all sessions in memory, aggregates by game_id, joins game names.

**Monthly Activity:**
Same daily aggregation as above, grouped by `YYYY-MM` key in Python.

## Validation Results

### Data Presence Check

| Metric | Expected | Actual |
|--------|----------|--------|
| Games > 0 | True | Depends on user's game library |
| Sessions > 0 | True | Depends on tracking activity |
| Playtime > 0 | True | Depends on completed sessions |

### Root Cause: Empty Charts

**Primary Root Cause:** `ChartsController.refresh()` was **never called**.

The `MainWindow._build_views()` created the `ChartsController` instance but never invoked `refresh()`. The auto-refresh timer `_refresh_current_view` only handled `DashboardWidget`, not `ChartsView`. When users navigated to the Charts page via the sidebar, no data loading was triggered.

**Secondary Issues:**
1. No `currentChanged` signal handler on `QStackedWidget` for Charts
2. Empty state messages were generic ("No session data yet") instead of actionable
3. Chart display occasionally clipped due to card/plot layout interaction

## StatisticsService Validation

| Method | Input | Output Type | Test Coverage |
|--------|-------|-------------|---------------|
| `get_daily_activity(days=30)` | days=30 | `DailyActivity` | 13 tests |
| `get_monthly_activity(months=12)` | months=12 | `MonthlyActivity` | 11 tests |
| `get_game_playtime_summaries()` | None | `list[GamePlaytimeSummary]` | 7 tests |
