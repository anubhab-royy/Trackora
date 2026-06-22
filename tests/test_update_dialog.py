"""Tests for UpdateDialog."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    """Create a QApplication for the test session."""
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


from services.update_center_service import (
    GitHubRelease,
    UpdateCheckResult,
)
from ui.dialogs.update_dialog import UpdateDialog


_SAMPLE_RELEASE = GitHubRelease(
    tag_name="v2.0.0",
    name="Trackora 2.0.0",
    body="## What's New\n- Feature A\n- Feature B",
    published_at="2026-06-20T12:00:00Z",
    html_url="https://github.com/anomalyco/trackora/releases/tag/v2.0.0",
    prerelease=False,
    download_url="https://example.com/setup.exe",
)


class TestUpdateDialog:
    def test_update_available_shows_title(self, qapp) -> None:
        result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=_SAMPLE_RELEASE,
            checked_at="2026-06-20T12:00:00",
        )
        dialog = UpdateDialog(result)
        assert dialog.windowTitle() == "Update Available"

    def test_release_notes_in_text_browser(self, qapp) -> None:
        result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=_SAMPLE_RELEASE,
            checked_at="2026-06-20T12:00:00",
        )
        dialog = UpdateDialog(result)
        from PyQt6.QtWidgets import QTextBrowser
        browser = dialog.findChild(QTextBrowser)
        assert browser is not None
        assert "Feature A" in browser.toPlainText()

    @patch("PyQt6.QtGui.QDesktopServices.openUrl")
    def test_download_opens_browser(
        self, mock_open_url: MagicMock, qapp
    ) -> None:
        result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=_SAMPLE_RELEASE,
            checked_at="2026-06-20T12:00:00",
        )
        dialog = UpdateDialog(result)
        from PyQt6.QtWidgets import QPushButton
        download_btn = dialog.findChild(QPushButton, "DownloadButton")
        assert download_btn is not None
        download_btn.click()
        mock_open_url.assert_called_once()

    def test_ignore_version_sets_flag(self, qapp) -> None:
        result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=_SAMPLE_RELEASE,
            checked_at="2026-06-20T12:00:00",
        )
        dialog = UpdateDialog(result)
        from PyQt6.QtWidgets import QPushButton
        ignore_btn = dialog.findChild(QPushButton, "IgnoreButton")
        assert ignore_btn is not None
        ignore_btn.click()
        assert dialog.ignored_version == "2.0.0"

    def test_remind_later_keeps_flag_none(self, qapp) -> None:
        result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=_SAMPLE_RELEASE,
            checked_at="2026-06-20T12:00:00",
        )
        dialog = UpdateDialog(result)
        from PyQt6.QtWidgets import QPushButton
        remind_btn = dialog.findChild(QPushButton, "RemindButton")
        assert remind_btn is not None
        remind_btn.click()
        assert dialog.ignored_version is None

    def test_up_to_date_shows_message(self, qapp) -> None:
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version="1.1.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
        )
        dialog = UpdateDialog(result)
        assert dialog.windowTitle() == "Up to Date"

    def test_error_shows_message(self, qapp) -> None:
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version=None,
            release=None,
            checked_at="2026-06-20T12:00:00",
            error="Network error",
            source="error",
        )
        dialog = UpdateDialog(result)
        assert dialog.windowTitle() == "Update Check Failed"

    def test_up_to_date_no_action_buttons(self, qapp) -> None:
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version="1.1.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
        )
        dialog = UpdateDialog(result)
        from PyQt6.QtWidgets import QPushButton
        assert dialog.findChild(QPushButton, "DownloadButton") is None
        assert dialog.findChild(QPushButton, "IgnoreButton") is None
        assert dialog.findChild(QPushButton, "RemindButton") is None
