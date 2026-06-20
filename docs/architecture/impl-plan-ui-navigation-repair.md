# UI Navigation Repair — Implementation Plan

## Overview

Single-file change to `ui/main_window.py` to restructure the content area layout so `UpdateBanner` sits outside the `QStackedWidget`.

## Steps

### 1. Change `_setup_ui` layout (main_window.py:159-192)

Replace:
```python
self._content = QStackedWidget()
root.addWidget(sidebar)
root.addWidget(self._content, stretch=1)
```

With:
```python
self._content = QStackedWidget()
self._content.setObjectName("ContentArea")

content_frame = QWidget()
content_layout = QVBoxLayout(content_frame)
content_layout.setContentsMargins(0, 0, 0, 0)
content_layout.setSpacing(0)

self._update_banner = UpdateBanner(content_frame)
self._update_banner.hide()
self._update_banner.ignored.connect(self._on_update_banner_ignored)
self._update_banner.view_notes_requested.connect(self._on_show_release_notes)

content_layout.addWidget(self._update_banner)
content_layout.addWidget(self._content, stretch=1)

root.addWidget(sidebar)
root.addWidget(content_frame, stretch=1)
```

### 2. Remove banner insertion from `_build_views` (main_window.py:231-235)

Remove:
```python
self._update_banner = UpdateBanner(self._content)
self._update_banner.ignored.connect(self._on_update_banner_ignored)
self._update_banner.view_notes_requested.connect(self._on_show_release_notes)
self._update_banner.hide()
self._content.layout().insertWidget(0, self._update_banner)
```

### 3. Move UpdateBanner import to top of file

Already imported at line 73:
```python
from ui.widgets.update_banner import UpdateBanner
```

No change needed.

### 4. Adjust `_on_show_release_notes` if it accesses `_update_service`

No change needed — `_update_service` is already a member variable.

### 5. Verify `_perform_startup_update_check`

No change needed — it calls `self._update_banner.show(...)` which will now display the banner at the top of the content frame.

## Tests

### New test file: `tests/test_mainwindow_navigation.py`

Test plan:
1. Create `MainWindow` with minimal dependencies (using mocks)
2. Verify `_content` widget at each nav index matches expected type
3. Verify `switch_to("Support Center")` sets correct nav row
4. Verify `UpdateBanner` is a child of the content frame (not QStackedWidget)
5. Verify `UpdateBanner` is hidden after construction

## Risk Mitigation

- **Regression:** All views remain at same indices relative to each other (0-5). Only UpdateBanner is removed from the stack.
- **Banner visibility:** `UpdateBanner.show()` calls `super().show()` which will correctly show the QFrame; no change to banner behavior.
- **Signal wiring:** `ignored` and `view_notes_requested` connections are moved to `_setup_ui` before `_build_views` — they fire identically.
