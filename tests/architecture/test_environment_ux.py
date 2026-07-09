"""Tests for environment-aware UX features.

Verifies:
1. Window titles include [DEV] for development environment
2. Build info is accessible from trackora.core.build_info
3. Single-instance lock names include the environment name
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def env_cleanup():
    saved = os.environ.get("APP_ENV")
    yield
    if saved is not None:
        os.environ["APP_ENV"] = saved
    else:
        os.environ.pop("APP_ENV", None)


class TestWindowTitle:
    """MainWindow._window_title() returns environment-aware title."""

    @staticmethod
    def _reload():
        import importlib
        import trackora.core.environment as env_mod
        import trackora.core.build_info as bi_mod
        import ui.main_window as mw_mod
        importlib.reload(env_mod)
        importlib.reload(bi_mod)
        importlib.reload(mw_mod)
        return mw_mod

    def test_production_title(self, env_cleanup):
        os.environ["APP_ENV"] = "production"
        mw = self._reload()
        assert mw.MainWindow._window_title() == "Trackora"

    def test_development_title(self, env_cleanup):
        os.environ["APP_ENV"] = "development"
        mw = self._reload()
        assert mw.MainWindow._window_title() == "Trackora [DEV]"

class TestBuildInfo:
    """Build info reflects environment."""

    def test_build_channel_production(self, env_cleanup):
        os.environ["APP_ENV"] = "production"
        import importlib
        import trackora.core.environment as env_mod
        import trackora.core.build_info as bi_mod
        importlib.reload(env_mod)
        importlib.reload(bi_mod)
        assert bi_mod.BUILD_CHANNEL == "production"

    def test_build_channel_development(self, env_cleanup):
        os.environ["APP_ENV"] = "development"
        import importlib
        import trackora.core.environment as env_mod
        import trackora.core.build_info as bi_mod
        importlib.reload(env_mod)
        importlib.reload(bi_mod)
        assert bi_mod.BUILD_CHANNEL == "development"

    def test_build_version_matches(self):
        from trackora import __version__
        from trackora.core.build_info import BUILD_VERSION
        assert BUILD_VERSION == __version__


class TestSingleInstanceLock:
    """Single-instance lock uses environment-specific names."""

    @staticmethod
    def _reload_si():
        import importlib
        import trackora.core.environment as env_mod
        import trackora.core.single_instance as si_mod
        importlib.reload(env_mod)
        importlib.reload(si_mod)
        return si_mod

    def test_lock_name_uses_environment(self, env_cleanup):
        os.environ["APP_ENV"] = "development"
        si_mod = self._reload_si()
        assert "Trackora-development" in str(si_mod._LOCK_NAME)
        assert si_mod._LOCK_NAME == "Trackora-development"

    def test_acquire_release_cycle(self, env_cleanup):
        os.environ["APP_ENV"] = "development"
        si_mod = self._reload_si()
        acquired = si_mod.acquire()
        assert acquired is True
        si_mod.release()
        lock_file = si_mod._LOCK_FILE
        if lock_file.exists():
            lock_file.unlink(missing_ok=True)

    def test_double_acquisition_fails(self, env_cleanup):
        os.environ["APP_ENV"] = "development"
        si_mod = self._reload_si()
        acquired1 = si_mod.acquire()
        assert acquired1 is True
        try:
            acquired2 = si_mod.acquire()
            assert acquired2 is False
        finally:
            si_mod.release()
            lock_file = si_mod._LOCK_FILE
            if lock_file.exists():
                lock_file.unlink(missing_ok=True)

    def test_different_environments_can_coexist(self, env_cleanup):
        """Verify two different environments produce different lock names."""
        os.environ["APP_ENV"] = "production"
        si_mod = self._reload_si()
        prod_name = si_mod._LOCK_NAME
        prod_file = si_mod._LOCK_FILE
        os.environ["APP_ENV"] = "development"
        si_mod = self._reload_si()
        dev_name = si_mod._LOCK_NAME
        dev_file = si_mod._LOCK_FILE
        assert prod_name != dev_name
        assert prod_file != dev_file

    def test_activate_existing_instance_posix(self, env_cleanup):
        import os
        from unittest.mock import patch
        si_mod = self._reload_si()
        with patch("os.name", "posix"):
            res = si_mod.activate_existing_instance()
            assert res is False

    @pytest.mark.skipif(os.name != "nt", reason="Windows specific test")
    def test_activate_existing_instance_windows_finds_window(self, env_cleanup):
        from unittest.mock import MagicMock, patch
        si_mod = self._reload_si()
        
        mock_user32 = MagicMock()
        mock_user32.FindWindowW.return_value = 12345
        mock_user32.IsIconic.return_value = True
        mock_user32.ShowWindow.return_value = True
        mock_user32.SetForegroundWindow.return_value = True
        mock_user32.AllowSetForegroundWindow.return_value = True
        
        with patch("ctypes.WinDLL", return_value=mock_user32):
            res = si_mod.activate_existing_instance()
            assert res is True
            mock_user32.ShowWindow.assert_called_once_with(12345, 9)
            mock_user32.SetForegroundWindow.assert_called_once_with(12345)
            mock_user32.AllowSetForegroundWindow.assert_called_once_with(0xFFFFFFFF)

    @pytest.mark.skipif(os.name != "nt", reason="Windows specific test")
    def test_activate_existing_instance_windows_no_window(self, env_cleanup):
        from unittest.mock import MagicMock, patch
        si_mod = self._reload_si()
        
        mock_user32 = MagicMock()
        mock_user32.FindWindowW.return_value = 0
        mock_user32.EnumWindows.return_value = True
        
        with patch("ctypes.WinDLL", return_value=mock_user32):
            res = si_mod.activate_existing_instance()
            assert res is False

