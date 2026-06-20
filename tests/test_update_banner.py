"""Tests for UpdateBanner."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    """Create a QApplication for the test session."""
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


from ui.widgets.update_banner import UpdateBanner


class TestUpdateBanner:
    def test_hidden_by_default(self, qapp) -> None:
        banner = UpdateBanner()
        assert not banner.isVisible()

    def test_show_makes_visible(self, qapp) -> None:
        banner = UpdateBanner()
        banner.show("2.0.0")
        assert banner.isVisible()

    def test_show_sets_version_text(self, qapp) -> None:
        banner = UpdateBanner()
        banner.show("2.0.0")
        assert "2.0.0" in banner._label.text()

    def test_dismiss_hides(self, qapp) -> None:
        banner = UpdateBanner()
        banner.show("2.0.0")
        banner.dismiss()
        assert not banner.isVisible()

    def test_dismiss_emits_ignored(self, qapp) -> None:
        banner = UpdateBanner()
        banner.show("2.0.0")
        received = []

        def on_ignored(version: str) -> None:
            received.append(version)

        banner.ignored.connect(on_ignored)
        banner.dismiss()
        assert received == ["2.0.0"]

    def test_view_notes_button_emits_signal(self, qapp) -> None:
        banner = UpdateBanner()
        banner.show("2.0.0")
        received = []

        def on_view() -> None:
            received.append(True)

        banner.view_notes_requested.connect(on_view)
        banner._view_notes_btn.click()
        assert received == [True]

    def test_hide_no_signal(self, qapp) -> None:
        banner = UpdateBanner()
        banner.show("2.0.0")
        received = []
        banner.ignored.connect(lambda v: received.append(v))
        banner.hide()
        assert received == []
        assert not banner.isVisible()

    def test_object_name(self, qapp) -> None:
        banner = UpdateBanner()
        assert banner.objectName() == "UpdateBanner"

    def test_dismiss_button_exists(self, qapp) -> None:
        banner = UpdateBanner()
        from PyQt6.QtWidgets import QPushButton
        dismiss_btn = banner.findChild(QPushButton, "DismissButton")
        assert dismiss_btn is not None
