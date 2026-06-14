"""Tests for correct environment-specific path resolution.

Verifies that trackora.core.paths resolves paths correctly for
each runtime environment.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def env_cleanup():
    """Save and restore APP_ENV for each test."""
    saved = os.environ.get("APP_ENV")
    yield
    if saved is not None:
        os.environ["APP_ENV"] = saved
    else:
        os.environ.pop("APP_ENV", None)


@pytest.fixture
def appdata_cleanup():
    """Save and restore APPDATA for each test."""
    saved = os.environ.get("APPDATA")
    yield
    if saved is not None:
        os.environ["APPDATA"] = saved
    else:
        os.environ.pop("APPDATA", None)


class TestEnvironmentSelection:
    def test_default_is_production(self):
        saved = os.environ.pop("APP_ENV", None)
        try:
            import importlib
            import trackora.core.environment as env_mod
            importlib.reload(env_mod)
            assert env_mod.CURRENT_ENVIRONMENT == env_mod.Environment.PRODUCTION
        finally:
            if saved is not None:
                os.environ["APP_ENV"] = saved

    def test_development_environment(self, env_cleanup):
        os.environ["APP_ENV"] = "development"
        import importlib
        import trackora.core.environment as env_mod
        importlib.reload(env_mod)
        assert env_mod.CURRENT_ENVIRONMENT == env_mod.Environment.DEVELOPMENT

    def test_invalid_fallback_to_production(self, env_cleanup):
        os.environ["APP_ENV"] = "invalid_value"
        import importlib
        import trackora.core.environment as env_mod
        importlib.reload(env_mod)
        assert env_mod.CURRENT_ENVIRONMENT == env_mod.Environment.PRODUCTION


class TestPathResolution:
    """Verify that BASE_DIR resolves to the correct path per environment."""

    @staticmethod
    def _reload_paths():
        import importlib
        import trackora.core.environment as env_mod
        import trackora.core.paths as paths_mod
        importlib.reload(env_mod)
        importlib.reload(paths_mod)
        return paths_mod

    def test_production_uses_trackora(self, appdata_cleanup, env_cleanup):
        os.environ["APP_ENV"] = "production"
        os.environ["APPDATA"] = "C:\\Test\\Roaming"
        paths_mod = self._reload_paths()
        assert "Trackora" in str(paths_mod.BASE_DIR)
        assert "Trackora-Dev" not in str(paths_mod.BASE_DIR)

    def test_development_uses_trackora_dev(self, appdata_cleanup, env_cleanup):
        os.environ["APP_ENV"] = "development"
        os.environ["APPDATA"] = "C:\\Test\\Roaming"
        paths_mod = self._reload_paths()
        assert "Trackora-Dev" in str(paths_mod.BASE_DIR)

    def test_path_constants_use_base_dir(self, appdata_cleanup, env_cleanup):
        os.environ["APP_ENV"] = "development"
        os.environ["APPDATA"] = "C:\\Test\\Roaming"
        paths_mod = self._reload_paths()
        base = paths_mod.BASE_DIR
        assert paths_mod.DATABASE_PATH == base / "trackora.db"
        assert paths_mod.LOGS_DIR == base / "logs"
        assert paths_mod.CRASH_DIR == base / "crash_reports"
        assert paths_mod.CACHE_DIR == base / "cache"
        assert paths_mod.CONFIG_DIR == base / "config"
        assert paths_mod.SCREENSHOTS_DIR == base / "screenshots"
        assert paths_mod.BACKUPS_DIR == base / "backups"
        assert paths_mod.EXPORTS_DIR == base / "exports"
        assert paths_mod.IMPORTS_DIR == base / "imports"


class TestBuildInfo:
    def test_build_channel_matches_environment(self, env_cleanup):
        os.environ["APP_ENV"] = "development"
        import importlib
        import trackora.core.environment as env_mod
        importlib.reload(env_mod)
        import trackora.core.build_info as bi_mod
        importlib.reload(bi_mod)
        assert bi_mod.BUILD_CHANNEL == "development"

    def test_build_version_from_trackora(self):
        from trackora import __version__
        from trackora.core.build_info import BUILD_VERSION
        assert BUILD_VERSION == __version__
