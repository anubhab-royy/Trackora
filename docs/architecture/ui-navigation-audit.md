# UI Navigation Audit — Root Cause Analysis

## Expected Navigation Order

| Nav Index | Sidebar Item   | QStackedWidget Page       |
|-----------|----------------|---------------------------|
| 0         | Dashboard      | DashboardWidget           |
| 1         | Games          | GamesView                 |
| 2         | History        | HistoryView               |
| 3         | Charts         | ChartsView                |
| 4         | Settings       | SettingsView              |
| 5         | Support Center | SupportCenterWidget       |

## Actual Navigation Order (Broken)

| Nav Index | Sidebar Item   | QStackedWidget Page (actual) | Symptom                     |
|-----------|----------------|------------------------------|-----------------------------|
| 0         | Dashboard      | **UpdateBanner** (hidden)    | Dashboard shows blank/empty |
| 1         | Games          | DashboardWidget              | Dashboard shows when Games clicked |
| 2         | History        | GamesView                    | Games shows when History clicked |
| 3         | Charts         | HistoryView                  | History shows when Charts clicked |
| 4         | Settings       | ChartsView                   | Charts shows when Settings clicked |
| 5         | Support Center | SettingsView                 | Settings shows for Support Center |

**Support Center at index 6 is never reachable** via navigation.

## Root Cause

**File:** `ui/main_window.py:235`

```python
self._content.layout().insertWidget(0, self._update_banner)
```

The `UpdateBanner` is inserted at position 0 of the `QStackedWidget` **after** four pages have already been added (Dashboard, Games, History, Charts). This shifts all existing page indices up by 1:

- Before: `[Dash(0), Games(1), History(2), Charts(3)]`
- After `insertWidget(0, banner)`: `[Banner(0), Dash(1), Games(2), History(3), Charts(4)]`
- Further `addWidget` calls append at 5 (Settings) and 6 (Support Center)

The navigation (`_connect_nav`) connects `nav.currentRowChanged` directly to `content.setCurrentIndex` with **no offset**, causing a one-index-shift for every page after the insertion point.

## Why UpdateBanner Should Not Be in QStackedWidget

`UpdateBanner` is a `QFrame` — a small horizontal bar (~40px tall) showing "Trackora X.Y.Z is available!" with dismiss/view buttons. It is **not a page**. It is a notification bar that should appear **above** the content area, not as a child page of the stacked widget.

## Recent Modifications That Introduced the Bug

The `UpdateBanner` was added as part of **Phase 10 — Update Center** (file header says "Phase 10"). The banner insertion at position 0 was presumably intended to make it render "behind" or "over" the content, but `QStackedWidget` does not overlay — it shows one child at a time. This architectural mismatch is the bug.

The Phase 12 MongoDB changes did not touch navigation code.

## Affected Pages

| Page           | Severity | Impact                              |
|----------------|----------|-------------------------------------|
| Dashboard      | HIGH     | Not displayed (shows hidden banner) |
| Games          | MEDIUM   | Wrong nav highlight (Dashboard)     |
| History        | MEDIUM   | Wrong nav highlight (Games)         |
| Charts         | MEDIUM   | Wrong nav highlight (History)       |
| Settings       | HIGH     | Wrong nav highlight (Charts)        |
| Support Center | CRITICAL | Inaccessible (reachable via index 6 when nav max is 5) |

## Risk Assessment

- **Data loss risk:** None — views are all created and wired; only routing is broken.
- **UI freeze risk:** Low — app starts, views render, only the wrong page shows.
- **Regression risk:** MEDIUM — fixing requires restructuring the layout; existing non-navigation tests should be unaffected.
- **Support Center risk:** HIGH — currently impossible for users to reach.

## Fix Strategy

Restructure `_setup_ui` to place `UpdateBanner` **outside** the `QStackedWidget`:

```
Current:
  QHBoxLayout
  ├── Sidebar
  └── QStackedWidget  ← Banner corrupts indices

Fixed:
  QHBoxLayout
  ├── Sidebar
  └── ContentFrame (QVBoxLayout)
      ├── UpdateBanner  ← above content, hidden by default
      └── QStackedWidget ← clean 0-5 page indices
```

This restores 1:1 mapping between nav items and stacked widget pages with zero shift.
