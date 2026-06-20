# UI Navigation Repair — Implementation Checkpoints

## Checkpoint 1: `_setup_ui` restructured
- [x] `QWidget` content frame created with `QVBoxLayout`
- [x] `UpdateBanner` created as child of content frame (not `QStackedWidget`)
- [x] Banner connections wired (`ignored`, `view_notes_requested`)
- [x] Banner hidden by default
- [x] Banner added to top of content layout
- [x] `QStackedWidget` added second (with stretch=1)
- [x] Content frame added to root layout instead of raw `QStackedWidget`

## Checkpoint 2: `_build_views` cleaned
- [x] `UpdateBanner` creation removed from `_build_views`
- [x] `insertWidget(0, self._update_banner)` removed
- [x] No remnant of banner in the stacked widget

## Checkpoint 3: Navigation mapping restored
- [x] `_content` has exactly 6 children (Dash, Games, History, Charts, Settings, Support)
- [x] Nav index 0 → DashboardWidget
- [x] Nav index 1 → GamesView
- [x] Nav index 2 → HistoryView
- [x] Nav index 3 → ChartsView
- [x] Nav index 4 → SettingsView
- [x] Nav index 5 → SupportCenterWidget
- [x] `switch_to("Support Center")` lands on Support Center

## Checkpoint 4: UpdateBanner functional
- [x] UpdateBanner is not a page in stacked widget
- [x] UpdateBanner appears at top of content area when shown
- [x] UpdateBanner.ignored still fires
- [x] UpdateBanner.view_notes_requested still fires

## Checkpoint 5: `_perform_startup_update_check` still works
- [x] `self._update_banner.show(...)` displays the banner
- [x] No regression in update check logic

## Checkpoint 6: Tests pass
- [x] New `test_mainwindow_navigation.py` — 15 tests pass
- [x] All existing support center controller tests pass (14 tests)
- [x] All existing support service tests pass (34 tests)
- [x] No regression in related tests

## Checkpoint 7: Visual validation
- [ ] Each nav item shows correct page when clicked
- [ ] Support Center loads its sub-pages
- [ ] Update banner appears at top (triggered or manual)
