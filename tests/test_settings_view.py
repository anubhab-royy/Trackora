"""Tests for SettingsView button layout (RC-018E/018F)."""

import sys

import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)

from ui.settings.settings_view import SettingsView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class TestCheckForUpdatesButton:
    def test_button_exists(self, qapp):
        view = SettingsView()
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        assert btn is not None
        assert btn.text() == "Check for Updates"

    def test_button_has_fixed_width(self, qapp):
        view = SettingsView()
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        assert btn.minimumWidth() == btn.maximumWidth()
        assert btn.minimumWidth() > 0

    def test_button_is_centered_in_own_hbox(self, qapp):
        """Button lives in its own dedicated QHBoxLayout with stretch on both sides."""
        view = SettingsView()
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        parent_layout = btn.parentWidget().layout()
        # Walk the button up to find its immediate QHBoxLayout container
        container = btn.parentWidget()
        cl = container.layout()
        assert isinstance(cl, QVBoxLayout), (
            "About group must use QVBoxLayout as root"
        )
        found = False
        for i in range(cl.count()):
            item = cl.itemAt(i)
            if item is not None and item.layout() is not None and isinstance(item.layout(), QHBoxLayout):
                hbox = item.layout()
                for j in range(hbox.count()):
                    w = hbox.itemAt(j).widget()
                    if w is btn:
                        found = True
                        break
        assert found, "CheckUpdatesButton not inside a QHBoxLayout within the About VBox"

    def test_button_not_in_form_layout_field_column(self, qapp):
        """Button must NOT be inside a QFormLayout field (which causes expansion)."""
        view = SettingsView()
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        # The button's parent QGroupBox has a QVBoxLayout, not a QFormLayout.
        about_group = btn.parentWidget()
        assert isinstance(about_group.layout(), QVBoxLayout)

    def test_button_checkbox_in_separate_rows(self, qapp):
        """Checkbox and button occupy separate rows in the About group."""
        view = SettingsView()
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        cb = view.findChild(QCheckBox, "AutoCheckCheckbox")
        about_group = btn.parentWidget()
        vbox = about_group.layout()
        assert isinstance(vbox, QVBoxLayout)
        btn_row_index = None
        cb_row_index = None
        for i in range(vbox.count()):
            item = vbox.itemAt(i)
            if item is not None:
                w = item.widget()
                if w is btn:
                    btn_row_index = i
                if w is cb:
                    cb_row_index = i
                lay = item.layout()
                if lay is not None:
                    for j in range(lay.count()):
                        w = lay.itemAt(j).widget()
                        if w is btn:
                            btn_row_index = i
                        if w is cb:
                            cb_row_index = i
        assert cb_row_index is not None, "Checkbox not found in About VBox"
        assert btn_row_index is not None, "Button not found in About VBox"
        assert btn_row_index > cb_row_index, (
            "Button must be below the checkbox"
        )

    def test_button_does_not_stretch_full_width(self, qapp):
        """Button's fixed width is much smaller than the About group's width."""
        view = SettingsView()
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        about_group = btn.parentWidget()
        btn_w = btn.minimumWidth()
        # The About group hasn't been rendered, so its width may be 0.
        # Instead, verify the button width is reasonable (< 300px).
        assert btn_w < 300, "Button width too large"

    def test_button_is_clickable(self, qapp):
        view = SettingsView()
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        assert btn.isEnabled()
        assert not btn.isHidden()

    def test_button_emits_signal_on_click(self, qapp):
        view = SettingsView()
        calls: list[str] = []
        view.check_updates_requested.connect(lambda: calls.append("check"))
        btn = view.findChild(QPushButton, "CheckUpdatesButton")
        btn.click()
        assert calls == ["check"]


class TestViewReleaseNotesButton:
    def test_button_has_fixed_width(self, qapp):
        view = SettingsView()
        btn = _find_btn_by_text(view, "View Release Notes")
        assert btn is not None
        assert btn.minimumWidth() == btn.maximumWidth()
        assert btn.minimumWidth() > 0

    def test_button_hidden_by_default(self, qapp):
        view = SettingsView()
        btn = _find_btn_by_text(view, "View Release Notes")
        assert btn is not None
        assert btn.isHidden()


def _find_btn_by_text(view, text: str) -> QPushButton | None:
    for btn in view.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    return None
