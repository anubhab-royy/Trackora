# UI Navigation Repair — Architecture Specification

## Root Cause

In `main_window.py:235`:
```python
self._content.layout().insertWidget(0, self._update_banner)
```

The `UpdateBanner` (a `QFrame` notification bar) is inserted at position 0 of the `QStackedWidget` **after** 4 pages are already added. This shifts all existing page indices by 1, breaking the 1:1 mapping between sidebar `QListWidget` rows and `QStackedWidget` pages.

## Architectural Mismatch

`UpdateBanner` is a ~40px tall notification bar. It is **not a page**. It should sit **above** the content area, not inside the QStackedWidget. `QStackedWidget` shows one child at a time — it does not overlay.

## Fix Design

Separate the banner from the page stack:

```
Before:
  QHBoxLayout
  ├── Sidebar (QListWidget)
  └── QStackedWidget (0: UpdateBanner, 1: Dash, 2: Games, 3: History, 4: Charts, 5: Settings, 6: Support)

After:
  QHBoxLayout
  ├── Sidebar (QListWidget)
  └── ContentArea (QVBoxLayout)
      ├── UpdateBanner (QFrame)  ← hidden by default, sits above content
      └── QStackedWidget (0: Dash, 1: Games, 2: History, 3: Charts, 4: Settings, 5: Support)
```

## Benefits

- Restores 1:1 nav-to-page mapping (indices 0-5).
- UpdateBanner appears as a proper top-bar notification (not a full-page replacement).
- Zero changes to any view or controller code.
- All six nav items work correctly.
- Support Center becomes immediately accessible.

## Non-Goals

- Do not change `UpdateBanner` itself.
- Do not change `SupportCenterWidget` or `SupportCenterController`.
- Do not change sidebar items or nav item order.
- Do not touch auto-refresh timer logic.

## Verification Criteria

1. Clicking each nav item shows the correct page.
2. `switch_to("Support Center")` navigates to `SupportCenterWidget`.
3. UpdateBanner appears at the top of the content area when an update is available.
4. UpdateBanner is hidden by default.
5. UpdateBanner's `ignored` and `view_notes_requested` signals still fire.
6. All existing tests pass without modification.
