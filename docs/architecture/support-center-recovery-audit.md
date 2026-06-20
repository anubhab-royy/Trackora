# Support Center Recovery Audit

## Purpose

Verify whether the Support Center (`SupportCenterWidget` + `SupportCenterController`) is correctly wired and merely inaccessible due to the navigation index shift, or whether it has independent bugs.

## Page Registration (main_window.py:253)

| Component | Stack Index | Nav Index | Status |
|-----------|-------------|-----------|--------|
| SupportCenterWidget | 6 (after banner insertion) | 5 | **MISMATCH** — nav 5 shows Settings (index 5) instead |

**Conclusion:** Registration is correct in intent but ineffective due to the off-by-one shift. Fixing the UpdateBanner layout will restore navigation to index 5 → SupportCenterWidget.

## Controller Wiring (main_window.py:248-253)

```python
self._support_view = SupportCenterWidget(self)
self._support_ctrl = SupportCenterController(
    view=self._support_view,
    support_service=self._support_service,
)
self._content.addWidget(self._support_view)
```

- Controller receives the view and service.
- `__init__` calls `_connect_signals()` which wires all 3 view signals.
- `__init__` calls `_load_upcoming_updates()` for initial data.
- **Status: PASS** — no wiring defects.

## Signal Connections (controller:43-46)

| Signal | Connected Slot | Status |
|--------|---------------|--------|
| `navigation_requested(str)` | `_on_page_changed` | PASS |
| `submit_requested(str)` | `_on_submit` | PASS |
| `refresh_requested()` | `_on_refresh` | PASS |

All signals have 1 emitter and 1 receiver. **Status: PASS.**

## Widget Internal Structure

- `SupportCenterWidget` has its own internal `QStackedWidget` with 4 pages:
  - Index 0: Report Bug form
  - Index 1: Suggest Feature form
  - Index 2: General Feedback form
  - Index 3: Upcoming Updates (with Refresh button)
- Navigation bar with 4 buttons switches between these pages.
- **Status: PASS** — internal structure is sound.

## Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_support_center_controller.py` | 14 | 100% of controller methods exercised |
| `tests/test_support_service.py` | 21 | All submission/queue/announcement paths |
| `tests/test_support_center_widget.py` | **0** | **MISSING** — no widget-level tests |

## Minor Findings (non-blocking)

| Finding | Severity | Location |
|---------|----------|----------|
| `set_upcoming_updates()` is dead code (never called) | LOW | widget:64-100 |
| `controller.navigate_to()` has no external caller | LOW | controller:186-193 |
| No widget-level tests | MEDIUM | `test_support_center_widget.py` |

## Recovery Plan

The Support Center will be fully accessible and functional **immediately** after the navigation fix. No Support Center code changes are required. The widget-level test gap is tracked as optional follow-up.
