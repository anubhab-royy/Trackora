# GameTracker Integration Audit

**Date:** 2026-06-09  
**Auditor:** Automated codebase analysis  
**Scope:** All 81 Python source files across database/, tracker/, statistics/, services/, ui/, tests/

---

## Summary

| Severity | Count |
|----------|-------|
| **CRASH BUGS** (will fail at runtime) | 7 |
| **Architecture violations** | 6 files |
| **Duplicated logic** | 1 instance |
| **Missing exports** | 3 packages |
| **Untested source files** | ~52 files |
| **Test/production interface mismatch** | 4 test files |

---

## 1. CRASH BUGS — Non-existent method calls

### 1.1 `services/game_service.py` — calls `get_by_executable_path` (does not exist)

**Files:** `services/game_service.py:111`, `services/game_service.py:167`  
**Root cause:** Calls `self._repo.get_by_executable_path(executable_path)` but `GamesRepository` only has `exists_by_executable_path(executable_path) -> bool`. The latter returns a `bool`, not a `Game` object, so even if the method name were corrected, the return type is wrong.

```python
# game_service.py:111 — CRASH: no such method
existing = self._repo.get_by_executable_path(executable_path)
if existing is not None:    # also wrong: bool is never None

# game_service.py:167 — same crash
duplicate = self._repo.get_by_executable_path(executable_path)
if duplicate is not None and duplicate.id != request.game_id:
```

**Why tests pass:** The test mocks are `MagicMock` instances, which auto-create any missing attribute on first access. The test sets `mock_repo.get_by_executable_path.return_value = None` without the method ever existing on the real class.

**Fix:** Replace with a new `get_by_executable_path(executable_path: str) -> Game | None` method in `GamesRepository`, and rewrite the service to use it.

---

### 1.2 `tracker/session_manager.py` — calls `create()` and `delete()` on repos (do not exist)

**Files:** `tracker/session_manager.py:110`, `tracker/session_manager.py:153`, `tracker/session_manager.py:171`  
**Root cause:** SessionManager expects its repos to have `create()` and `delete()` methods, but the real repositories use different names:

| SessionManager calls | Real ActiveSessionsRepository has | Real SessionsRepository has |
|---------------------|----------------------------------|----------------------------|
| `_active_sessions_repo.create(game_id=..., process_id=..., start_time=...)` | `start_session(active_session: ActiveSession) -> ActiveSession` | — |
| `_active_sessions_repo.delete(active_session_id)` | `end_session(active_session_id) -> None` | — |
| `_sessions_repo.create(game_id=..., start_time=..., end_time=..., duration_seconds=...)` | — | `add(session: Session) -> Session` |

**Why tests pass:** The test uses `FakeActiveSessionsRepo` and `FakeSessionsRepo` which DO have `create()` and `delete()`. The fakes' interface matches the SessionManager's expectations, but the real production repos have a different interface. This is a **test/production interface divergence**.

**Fix:** Either rename the real repo methods to `create()`/`delete()` or add protocol adapters. Prefer: rename real repos to match.

---

### 1.3 `tracker/recovery_manager.py` — calls `create()` on sessions_repo (does not exist)

**File:** `tracker/recovery_manager.py:289`  
**Root cause:** Calls `self._sessions_repo.create(session)` but `SessionsRepository` has `add()`, not `create()`.

```python
session_id: int = self._sessions_repo.create(session)  # CRASH
```

**Fix:** Change to `self._sessions_repo.add(session)` and handle the return type (it returns `Session`, not `int`).

---

## 2. CRASH BUG — Dataclass treated as dict

### 2.1 `ui/dashboard/dashboard_controller.py` — calls `.get()` on dataclass objects

**File:** `ui/dashboard/dashboard_controller.py:73-86`  
**Root cause:** The `StatisticsService` methods return dataclass instances (`LifetimeStats`, `DailyStats`, `WeeklyStats`, `MonthlyStats`, `GamePlaytimeSummary`), but the controller calls `.get()` as if they were dicts:

```python
# These return dataclasses, not dicts:
lifetime = self._service.get_lifetime_stats()    # -> LifetimeStats
daily = self._service.get_daily_stats()          # -> DailyStats
# etc.

# dashboard_controller.py:73-76 — CRASH: AttributeError on .get()
total_seconds = lifetime.get("total_seconds", 0)   # LifetimeStats has .total_seconds, not .get()
today_seconds = daily.get("total_seconds", 0)
```

Affected lines: 73, 74, 75, 76, 83, 84, 86.

**Why tests pass:** The test helper `_make_service()` (`test_dashboard_controller.py:63-77`) returns dicts like `{"total_seconds": 7200}` from the mock, not actual dataclass instances. The test thus uses dict access patterns, but production code would receive dataclasses.

**Fix:** Change all `.get("key", default)` calls to attribute access with `getattr(..., default)` or handle `None`:

```python
total_seconds = lifetime.total_seconds if lifetime else 0
today_seconds = daily.total_seconds if daily else 0
most_played_name = most_played.name if most_played else "No games tracked yet"
```

---

## 3. Architecture Violations — UI imports from database layer

### 3.1 UI files importing `database.models`

PLAN.md says: *"UI must never directly access SQLite"* and *"No business logic inside widgets."*  
architecture.md says no direct DB access from widgets.

The following UI files import from `database.models` (dataclass definitions that mirror the DB schema):

| File | Import | Severity |
|------|--------|----------|
| `ui/games/games_view.py:32` | `from database.models import Game` | Moderate |
| `ui/games/games_controller.py:21` | `from database.models import Game` | Moderate |
| `ui/games/add_game_dialog.py:38` | `from database.models import Game` | Moderate |
| `ui/games/game_table_model.py:16` | `from database.models import Game` | Moderate |
| `ui/history/history_view.py:43` | `from database.models import Game` | Moderate |
| `ui/history/history_table_model.py:22` | `from database.repositories.sessions_repository import SessionView` | **High** — imports from repository layer |

The `Game` dataclass is a simple data container with validation — importing it into UI is *acceptable* in practice (many clean-architecture projects share model DTOs). However, `SessionView` is defined inside the repository layer and should not be imported by the UI.

**Fix:** Move `SessionView` to `database/models/session_view.py` so it lives in `database.models` rather than `database.repositories`, then update imports. Or accept the `Game` model imports as a tolerable code-sharing convenience (preferred for V1.0 scope).

---

## 4. Duplicated Logic

### 4.1 Two copies of seconds-to-duration formatting

| Location | Function | Behavior |
|----------|----------|----------|
| `ui/dashboard/dashboard_controller.py:28` | `_format_duration(seconds)` | `0 → "0m"`, `3600 → "1h 0m"` |
| `services/session_history_service.py:58` | `format_duration(seconds)` | `0 → "0m"`, `3600 → "1h 0m"` |

The two functions are nearly identical. The dashboard version is private; the history version is public.

**Fix:** Move to a shared location (e.g., `services/formatting.py`) and have both call sites import from there.

---

## 5. Missing Package Exports

### 5.1 `statistics/__init__.py` — empty

Currently only has a docstring. Does not export `StatisticsService`, `PlaytimeCalculator`, `TrendAnalyzer`, or the models. Compare with `services/__init__.py` which properly re-exports all public classes.

### 5.2 `services/__init__.py` — incomplete

Exports `ExportService`, `LoggingService`, `StartupService`, `TrayService` but omits `GameService` and `SessionHistoryService`. All UI controllers import these two by full path rather than from the package init.

### 5.3 `tracker/__init__.py` — limited exports

Exports `RecoveryManager`, `RecoveryResult`, `RecoveredSession` but omits `ProcessMonitor`, `SessionManager`, `TrackingState`, `TrackedGame`, `ActiveSession`.

### 5.4 Missing `ui/settings/` directory

The architecture references `ui/settings/` but it does not exist. No Settings UI module has been created.

---

## 6. Additional Issues

### 6.1 `ui/dashboard/dashboard_controller.py:55` — weak type hint

```python
def __init__(self, statistics_service: object) -> None:
```

This defeats type checking. Should be:

```python
from statistics.statistics_service import StatisticsService

def __init__(self, statistics_service: StatisticsService) -> None:
```

### 6.2 `services/game_service.py:229-231` — platform-specific path handling

```python
import ntpath
return ntpath.basename(executable_path)
```

Uses `ntpath` (Windows-specific) but the app may run on Linux. `ntpath.basename()` happens to work on Linux paths by accident. Should use `os.path.basename()` or `Path(executable_path).name`.

### 6.3 `database/repositories/games_repository.py:31` — fragile bool cast

```python
"is_enabled": bool(row["is_enabled"]),
```

SQLite stores `is_enabled` as `0`/`1`. `bool(0)` is `False`, `bool(1)` is `True`. This works but is fragile — any non-1 truthy value would be misinterpreted. Should use `row["is_enabled"] == 1`.

### 6.4 `tests/conftest.py` — test fakes diverge from real repos

| Fake class | Has method | Real repo method name |
|------------|-----------|----------------------|
| `FakeActiveSessionsRepo` | `create()` | `start_session()` |
| `FakeActiveSessionsRepo` | `delete()` | `end_session()` |
| `FakeSessionsRepo` | `create()` | `add()` |

These fakes are used by `test_session_manager.py` and `test_recovery_manager.py`. Since `SessionManager` calls `create()`/`delete()`, and the fakes support those methods, tests pass — but production code would crash because the real repos don't have these methods.

---

## 7. Missing Tests

### 7.1 Core database layer — zero test coverage

| File | Lines | Risk |
|------|-------|------|
| `database/database_manager.py` | ~200 | **High** — no test at all |
| `database/repositories/games_repository.py` | ~284 | **High** — no dedicated test |
| `database/repositories/sessions_repository.py` | ~399 | **High** — no dedicated test (most complex repo) |
| `database/repositories/active_sessions_repository.py` | ~180 | **High** — no dedicated test |
| `database/repositories/settings_repository.py` | ~143 | **High** — no dedicated test |

### 7.2 Services layer — gaps

| File | Has tests? | Notes |
|------|-----------|-------|
| `services/game_service.py` | `test_game_service.py` | Covers well, but mock interface divergence |
| `services/session_history_service.py` | `test_history_controller.py` covers service indirectly | No dedicated service test |
| `services/export_service.py` | `test_export_service.py` | Good coverage |
| `services/logging_service.py` | `test_logging_service.py` | Good coverage |
| `services/startup_service.py` | `test_startup_service.py` | Good coverage |
| `services/tray_service.py` | `test_tray_service.py` | Good coverage |

### 7.3 UI layer — most files untested

| Directory | Files | With tests |
|-----------|-------|-----------|
| `ui/dashboard/` | 2 files (controller + widget) | Controller only |
| `ui/games/` | 4 files | None |
| `ui/history/` | 3 files | Controller only |
| `ui/widgets/` | 7 files | `test_charts_controller.py`, `test_stat_card.py` |
| `ui/themes/` | 1 file | `test_theme_manager.py` |

---

## 8. Quick-Fix Priority Matrix

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| **P0** | `game_service.py` calls `get_by_executable_path` | Small | CRASH |
| **P0** | `session_manager.py` calls `create()`/`delete()` on repos | Small | CRASH |
| **P0** | `recovery_manager.py` calls `create()` on sessions_repo | Small | CRASH |
| **P0** | `dashboard_controller.py` calls `.get()` on dataclasses | Small | CRASH |
| **P1** | `SessionView` imported from `database.repositories` by UI | Small | Architecture |
| **P1** | `ui/settings/` directory missing | Medium | Missing feature |
| **P2** | `_format_duration` / `format_duration` duplication | Tiny | Maintainability |
| **P2** | Missing package exports | Tiny | Cleanliness |
| **P3** | Weak type hint (`statistics_service: object`) | Tiny | Type safety |
| **P3** | `ntpath` usage in game_service | Tiny | Portability |
| **P3** | Database layer has zero tests | Large | Test coverage |
