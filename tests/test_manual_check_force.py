"""
tests/test_manual_check_force.py

Regression tests to verify that:
  - Manual update checks (force=True) bypass the cooldown limit.
  - Automatic checks (force=False or default) respect the cooldown.
  - SettingsController passes force=True when the user checks manually.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.update_center_service import UpdateCenterService, UpdateCheckResult, GitHubRelease
from ui.settings.settings_controller import SettingsController
from ui.settings.settings_view import SettingsView

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def mock_repo() -> MagicMock:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
    )
    from database.repositories.settings_repository import SettingsRepository
    return SettingsRepository(conn)


@pytest.fixture
def service(mock_repo, temp_cache_dir) -> UpdateCenterService:
    return UpdateCenterService(settings_repo=mock_repo, cache_dir=temp_cache_dir)


_SAMPLE_RELEASE = {
    "tag_name": "v3.0.0",
    "name": "Release 3.0.0",
    "body": "changelog description",
    "published_at": "2026-07-01T12:00:00Z",
    "html_url": "https://github.com/anubhab-royy/Trackora/releases/tag/v3.0.0",
    "assets": [],
}


# ============================================================================
# Cooldown Bypass Tests
# ============================================================================

class TestCooldownBypass:
    @patch("services.update_center_service.urlopen")
    def test_default_check_respects_rate_limit(
        self, mock_urlopen: MagicMock, service
    ) -> None:
        """By default, rate limits are respected (returns cached)."""
        # Set cooldown active (last checked 5 mins ago)
        service._settings_repo.set(
            "update_last_checked",
            datetime.now(UTC).replace(tzinfo=None).isoformat()
        )
        service._last_result = UpdateCheckResult(
            update_available=False,
            current_version="2.0.2",
            latest_version="2.0.2",
            release=None,
            checked_at="2026-07-05T12:00:00",
        )

        result = service.check_for_updates()  # default force=False

        mock_urlopen.assert_not_called()
        assert result.previously_checked is True

    @patch("services.update_center_service.urlopen")
    def test_forced_check_bypasses_rate_limit(
        self, mock_urlopen: MagicMock, service
    ) -> None:
        """With force=True, the request is dispatched despite cooldown."""
        # Set cooldown active
        service._settings_repo.set(
            "update_last_checked",
            datetime.now(UTC).replace(tzinfo=None).isoformat()
        )

        # Mock successful fetch response
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(_SAMPLE_RELEASE).encode("utf-8")
        mock_resp.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = service.check_for_updates(force=True)

        mock_urlopen.assert_called_once()
        assert result.previously_checked is False
        assert result.latest_version == "3.0.0"
        assert result.source == "remote"


# ============================================================================
# Controller Manual Integration Tests
# ============================================================================

class TestControllerManualIntegration:
    @patch("ui.settings.settings_controller.UpdateDialog")
    def test_controller_passes_force_to_service(
        self, mock_dialog: MagicMock, qapp, mock_repo
    ) -> None:
        """Manual check action in controller sets force=True."""
        view = SettingsView()
        mock_service = MagicMock(spec=UpdateCenterService)
        # Mock check_for_updates returning a dummy result
        dummy_result = UpdateCheckResult(
            update_available=False,
            current_version="2.0.2",
            latest_version="2.0.2",
            release=None,
            checked_at="2026-07-05T12:00:00",
        )
        mock_service.check_for_updates.return_value = dummy_result

        # Instantiate controller
        ctrl = SettingsController(
            view=view,
            settings_repo=mock_repo,
            theme_manager=MagicMock(),
            export_service=MagicMock(),
            parent_widget=MagicMock(),
            update_service=mock_service,
        )

        # Trigger manual updates
        ctrl._on_check_updates()

        # Assert check_for_updates was called with force=True
        mock_service.check_for_updates.assert_called_once_with(force=True)
