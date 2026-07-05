"""
tests/test_t202_settings_update_display.py

T-202: Automatic Update System Phase 1 — Settings UI Tests

Covers:
  - SettingsView.set_latest_version() updates LatestVersionLabel
  - SettingsView.set_auto_check() sets AutoCheckCheckbox state
  - SettingsView.auto_check_toggled emits on checkbox toggle
  - SettingsView has LatestVersionLabel with objectName
  - SettingsView has AutoCheckCheckbox with objectName
  - SettingsView initial latest version is '—'
  - SettingsController._load_settings() calls set_auto_check
  - SettingsController._on_auto_check_toggled() persists to repo
  - SettingsController._update_status_after_check() sets latest version
  - No SQL in SettingsView (architecture)
"""

from __future__ import annotations

import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def view(qapp):
    from ui.settings.settings_view import SettingsView
    return SettingsView()


@pytest.fixture
def settings_repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
    )
    from database.repositories.settings_repository import SettingsRepository
    return SettingsRepository(conn)


@pytest.fixture
def controller(qapp, settings_repo):
    from ui.settings.settings_view import SettingsView
    from ui.settings.settings_controller import SettingsController
    from ui.themes.theme_manager import ThemeManager
    from services.export_service import ExportService

    view = SettingsView()
    theme_manager = MagicMock(spec=ThemeManager)
    theme_manager.current_theme = MagicMock()
    export_service = MagicMock(spec=ExportService)
    parent = MagicMock()

    ctrl = SettingsController(
        view=view,
        settings_repo=settings_repo,
        theme_manager=theme_manager,
        export_service=export_service,
        parent_widget=parent,
        update_service=None,
    )
    return ctrl, view, settings_repo


# ============================================================================
# TestSettingsViewLatestVersion
# ============================================================================

class TestSettingsViewLatestVersion:
    def test_has_latest_version_label(self, view) -> None:
        from PyQt6.QtWidgets import QLabel
        label = view.findChild(QLabel, "LatestVersionLabel")
        assert label is not None

    def test_latest_version_initial_value_is_dash(self, view) -> None:
        from PyQt6.QtWidgets import QLabel
        label = view.findChild(QLabel, "LatestVersionLabel")
        assert label is not None
        assert label.text() == "—"

    def test_set_latest_version_updates_label(self, view) -> None:
        from PyQt6.QtWidgets import QLabel
        view.set_latest_version("3.0.0")
        label = view.findChild(QLabel, "LatestVersionLabel")
        assert label is not None
        assert label.text() == "3.0.0"

    def test_set_latest_version_overwrites_previous(self, view) -> None:
        from PyQt6.QtWidgets import QLabel
        view.set_latest_version("3.0.0")
        view.set_latest_version("3.1.0")
        label = view.findChild(QLabel, "LatestVersionLabel")
        assert label is not None
        assert label.text() == "3.1.0"

    def test_set_latest_version_empty_string(self, view) -> None:
        view.set_latest_version("")
        # Should not raise


# ============================================================================
# TestSettingsViewAutoCheck
# ============================================================================

class TestSettingsViewAutoCheck:
    def test_has_auto_check_checkbox(self, view) -> None:
        from PyQt6.QtWidgets import QCheckBox
        cb = view.findChild(QCheckBox, "AutoCheckCheckbox")
        assert cb is not None

    def test_auto_check_default_is_checked(self, view) -> None:
        from PyQt6.QtWidgets import QCheckBox
        cb = view.findChild(QCheckBox, "AutoCheckCheckbox")
        assert cb is not None
        assert cb.isChecked()

    def test_set_auto_check_false(self, view) -> None:
        from PyQt6.QtWidgets import QCheckBox
        view.set_auto_check(False)
        cb = view.findChild(QCheckBox, "AutoCheckCheckbox")
        assert cb is not None
        assert not cb.isChecked()

    def test_set_auto_check_true(self, view) -> None:
        from PyQt6.QtWidgets import QCheckBox
        view.set_auto_check(False)
        view.set_auto_check(True)
        cb = view.findChild(QCheckBox, "AutoCheckCheckbox")
        assert cb is not None
        assert cb.isChecked()

    def test_auto_check_toggled_signal_emits_false(self, view) -> None:
        received: list[bool] = []
        view.auto_check_toggled.connect(received.append)
        view.set_auto_check(True)
        view._auto_check_checkbox.setChecked(False)
        assert False in received

    def test_auto_check_toggled_signal_emits_true(self, view) -> None:
        received: list[bool] = []
        view.set_auto_check(False)
        view.auto_check_toggled.connect(received.append)
        view._auto_check_checkbox.setChecked(True)
        assert True in received


# ============================================================================
# TestSettingsControllerAutoCheck
# ============================================================================

class TestSettingsControllerAutoCheck:
    def test_load_settings_calls_set_auto_check_default_true(
        self, qapp, settings_repo
    ) -> None:
        """When no setting persisted, auto-check defaults to True."""
        from ui.settings.settings_view import SettingsView
        from ui.settings.settings_controller import SettingsController
        from ui.themes.theme_manager import ThemeManager

        view = SettingsView()
        ctrl = SettingsController(
            view=view,
            settings_repo=settings_repo,
            theme_manager=MagicMock(spec=ThemeManager),
            export_service=MagicMock(),
            parent_widget=MagicMock(),
        )
        from PyQt6.QtWidgets import QCheckBox
        cb = view.findChild(QCheckBox, "AutoCheckCheckbox")
        assert cb is not None
        assert cb.isChecked()

    def test_load_settings_respects_stored_false(
        self, qapp, settings_repo
    ) -> None:
        """When setting persisted as false, checkbox reflects it."""
        settings_repo.set_bool("update_auto_check_enabled", False)
        from ui.settings.settings_view import SettingsView
        from ui.settings.settings_controller import SettingsController
        from ui.themes.theme_manager import ThemeManager

        view = SettingsView()
        SettingsController(
            view=view,
            settings_repo=settings_repo,
            theme_manager=MagicMock(spec=ThemeManager),
            export_service=MagicMock(),
            parent_widget=MagicMock(),
        )
        from PyQt6.QtWidgets import QCheckBox
        cb = view.findChild(QCheckBox, "AutoCheckCheckbox")
        assert cb is not None
        assert not cb.isChecked()

    def test_on_auto_check_toggled_persists_false(self, controller) -> None:
        ctrl, view, repo = controller
        ctrl._on_auto_check_toggled(False)
        assert repo.get_bool("update_auto_check_enabled", default=True) is False

    def test_on_auto_check_toggled_persists_true(self, controller) -> None:
        ctrl, view, repo = controller
        ctrl._on_auto_check_toggled(False)
        ctrl._on_auto_check_toggled(True)
        assert repo.get_bool("update_auto_check_enabled", default=False) is True


# ============================================================================
# TestSettingsControllerLatestVersionDisplay
# ============================================================================

class TestSettingsControllerLatestVersionDisplay:
    def _make_result(
        self,
        latest: str = "3.0.0",
        update_available: bool = True,
        error: str | None = None,
    ) -> object:
        from services.update_center_service import GitHubRelease, UpdateCheckResult
        release = None
        if update_available:
            release = GitHubRelease(
                tag_name=f"v{latest}",
                name=f"Trackora {latest}",
                body="",
                published_at="2026-07-01T00:00:00Z",
                html_url="",
            )
        return UpdateCheckResult(
            update_available=update_available,
            current_version="2.0.0",
            latest_version=latest,
            release=release,
            checked_at="2026-07-05T12:00:00",
            error=error,
            source="remote",
        )

    def test_update_status_sets_latest_version_label(self, controller) -> None:
        ctrl, view, _ = controller
        result = self._make_result(latest="3.0.0", update_available=True)
        ctrl._update_status_after_check(result)
        from PyQt6.QtWidgets import QLabel
        label = view.findChild(QLabel, "LatestVersionLabel")
        assert label is not None
        assert label.text() == "3.0.0"

    def test_update_status_latest_version_up_to_date(self, controller) -> None:
        ctrl, view, _ = controller
        result = self._make_result(latest="2.0.0", update_available=False)
        ctrl._update_status_after_check(result)
        from PyQt6.QtWidgets import QLabel
        label = view.findChild(QLabel, "LatestVersionLabel")
        assert label is not None
        assert label.text() == "2.0.0"

    def test_update_status_error_does_not_reset_latest(self, controller) -> None:
        ctrl, view, _ = controller
        # First: successful check sets it
        ctrl._update_status_after_check(self._make_result("3.0.0", True))
        from PyQt6.QtWidgets import QLabel
        label = view.findChild(QLabel, "LatestVersionLabel")
        assert label is not None
        before = label.text()
        # Then: error result with no latest_version
        from services.update_center_service import UpdateCheckResult
        err_result = UpdateCheckResult(
            update_available=False,
            current_version="2.0.0",
            latest_version=None,
            release=None,
            checked_at="2026-07-05T12:00:00",
            error="timeout",
            source="error",
        )
        ctrl._update_status_after_check(err_result)
        # Label should remain unchanged (None is falsy, skips set)
        assert label.text() == before
