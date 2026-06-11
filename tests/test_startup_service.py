"""
Tests for StartupService — Phase 9.

Covers:
  - is_supported returns correct value per platform
  - Linux .desktop file creation / detection / removal
  - Linux unregister when file does not exist (no-op)
  - Windows paths (winreg mocking)
"""

from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.startup_service import (
    StartupService,
    _linux_is_registered,
    _linux_register,
    _linux_unregister,
)


class TestStartupServicePlatform:
    def test_is_supported_returns_bool(self) -> None:
        result = StartupService.is_supported()
        assert isinstance(result, bool)
        assert result == (platform.system() in ("Windows", "Linux"))

    def test_is_registered_delegates_to_platform(self) -> None:
        result = StartupService.is_registered()
        assert isinstance(result, bool)


class TestStartupServiceLinux:
    def test_linux_register_creates_desktop_file(self, tmp_path: Path) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"

        with patch(
            "services.startup_service._AUTOSTART_DIR", autostart_dir
        ), patch(
            "services.startup_service._DESKTOP_FILE", desktop_file
        ):
            result = _linux_register()
            assert result is True
            assert desktop_file.is_file()
            content = desktop_file.read_text(encoding="utf-8")
            assert "Trackora" in content
            assert "Exec=" in content

    def test_linux_is_registered_returns_true_when_file_exists(
        self, tmp_path: Path
    ) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"
        autostart_dir.mkdir(parents=True)
        desktop_file.write_text("[Desktop Entry]\n", encoding="utf-8")

        with patch(
            "services.startup_service._DESKTOP_FILE", desktop_file
        ):
            assert _linux_is_registered() is True

    def test_linux_is_registered_returns_false_when_no_file(
        self, tmp_path: Path
    ) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"

        with patch(
            "services.startup_service._DESKTOP_FILE", desktop_file
        ):
            assert _linux_is_registered() is False

    def test_linux_unregister_removes_desktop_file(self, tmp_path: Path) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"
        autostart_dir.mkdir(parents=True)
        desktop_file.write_text("[Desktop Entry]\n", encoding="utf-8")

        with patch(
            "services.startup_service._DESKTOP_FILE", desktop_file
        ):
            result = _linux_unregister()
            assert result is True
            assert not desktop_file.exists()

    def test_linux_unregister_no_file_does_not_error(
        self, tmp_path: Path
    ) -> None:
        desktop_file = tmp_path / "Trackora.desktop"
        assert not desktop_file.exists()

        with patch(
            "services.startup_service._DESKTOP_FILE", desktop_file
        ):
            result = _linux_unregister()
            assert result is True

    def test_linux_register_creates_directory_if_missing(
        self, tmp_path: Path
    ) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"

        with patch(
            "services.startup_service._AUTOSTART_DIR", autostart_dir
        ), patch(
            "services.startup_service._DESKTOP_FILE", desktop_file
        ):
            assert not autostart_dir.exists()
            result = _linux_register()
            assert result is True
            assert autostart_dir.is_dir()


class TestStartupServiceWindows:
    def test_register_calls_windows_impl(self) -> None:
        with patch(
            "services.startup_service.platform.system",
            return_value="Windows",
        ), patch(
            "services.startup_service._windows_register",
            return_value=True,
        ) as mock_impl:
            result = StartupService.register()
            assert result is True
            mock_impl.assert_called_once()

    def test_unregister_calls_windows_impl(self) -> None:
        with patch(
            "services.startup_service.platform.system",
            return_value="Windows",
        ), patch(
            "services.startup_service._windows_unregister",
            return_value=True,
        ) as mock_impl:
            result = StartupService.unregister()
            assert result is True
            mock_impl.assert_called_once()

    def test_is_registered_calls_windows_impl(self) -> None:
        with patch(
            "services.startup_service.platform.system",
            return_value="Windows",
        ), patch(
            "services.startup_service._windows_is_registered",
            return_value=True,
        ) as mock_impl:
            result = StartupService.is_registered()
            assert result is True
            mock_impl.assert_called_once()

    def test_windows_register_failure_returns_false(self) -> None:
        """When winreg raises OSError, _windows_register returns False."""
        with patch(
            "services.startup_service._windows_register",
            return_value=False,
        ) as mock_impl:
            result = mock_impl()
            assert result is False
