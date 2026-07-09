from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from trackora.core.env import _discover_env_file, load_env_file


class TestDiscoverEnvFile:
    def test_explicit_path_found(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n", encoding="utf-8")
        result = _discover_env_file(env_file)
        assert result == env_file.resolve()

    def test_explicit_path_not_found(self, tmp_path: Path):
        result = _discover_env_file(tmp_path / ".env")
        assert result is None

    def test_none_path_returns_none_when_no_file(self):
        with (
            patch("trackora.core.env.Path.cwd", return_value=Path("/nonexistent")),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            result = _discover_env_file(None)
            assert result is None


class TestLoadEnvFile:
    def test_loads_variables_into_os_environ(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "MONGODB_URI=mongodb+srv://user:pass@cluster.test.mongodb.net\n"
            "MONGODB_DATABASE=trackora_support\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_file)
            assert os.environ["MONGODB_URI"] == "mongodb+srv://user:pass@cluster.test.mongodb.net"
            assert os.environ["MONGODB_DATABASE"] == "trackora_support"

    def test_missing_env_file_does_not_crash(self):
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(Path("/nonexistent/.env"))
            assert "MONGODB_URI" not in os.environ

    def test_skips_comments_and_blank_lines(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\n"
            "\n"
            "  \n"
            "KEY=value\n"
            "# Another comment\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_file)
            assert os.environ["KEY"] == "value"
            assert "MONGODB_URI" not in os.environ

    def test_strips_quotes_from_values(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            'UNQUOTED=hello\n'
            'DOUBLE="world"\n'
            "SINGLE='foo'\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_file)
            assert os.environ["UNQUOTED"] == "hello"
            assert os.environ["DOUBLE"] == "world"
            assert os.environ["SINGLE"] == "foo"

    def test_skips_lines_without_equals_sign(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "JUST_A_KEY\n"
            "KEY=value\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_file)
            assert os.environ["KEY"] == "value"
            assert "JUST_A_KEY" not in os.environ

    def test_does_not_overwrite_existing_env_vars(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "MONGODB_URI=from-dotenv\n"
            "OTHER_VAR=from-dotenv\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"MONGODB_URI": "from-system"}, clear=True):
            load_env_file(env_file)
            assert os.environ["MONGODB_URI"] == "from-system"
            assert os.environ["OTHER_VAR"] == "from-dotenv"

    def test_handles_unreadable_file_gracefully(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.mkdir()
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_file)
            assert "KEY" not in os.environ

    def test_handles_binary_file_gracefully(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_bytes(b"\x00\xff\xfe\xed")
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_file)
            assert "MONGODB_URI" not in os.environ


class TestNoCredentialsInLogs:
    def test_credentials_not_in_log_output(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.INFO)
        env_file = tmp_path / ".env"
        env_file.write_text(
            "MONGODB_URI=mongodb+srv://secretuser:secretpass@cluster.test.mongodb.net\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {}, clear=True):
            load_env_file(env_file)
        for record in caplog.records:
            assert "secretuser" not in record.getMessage()
            assert "secretpass" not in record.getMessage()
            assert "mongodb+srv" not in record.getMessage()

    def test_warning_on_missing_env_file(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        load_env_file(Path("/nonexistent/.env"))
        assert any(
            "No .env file found" in record.getMessage()
            for record in caplog.records
        )


class TestStartupIntegration:
    _PATCHES = [
        "LoggingService", "_acquire_lock", "atexit", "QApplication",
        "ensure_dirs", "DatabaseManager", "SchemaVersionManager",
        "SchemaVersion", "CrashService", "DiagnosticService",
        "GamesRepository", "SessionsRepository", "ActiveSessionsRepository",
        "SettingsRepository", "GameService", "DeleteGameService", "CacheCleanupService", "SessionHistoryService",
        "StatisticsService", "PlaytimeCalculator", "ExportService",
        "MongoReportService", "ReportQueueService",
        "UpdateAnnouncementsService", "SupportService", "TrackingState",
        "SessionManager", "RecoveryManager", "ProcessMonitor",
        "ThemeManager", "MainWindow", "QTimer",
    ]

    def _start_patches(self, entry):
        """Start patches for all imports mocked in startup tests."""
        for name in self._PATCHES:
            kwargs = {"return_value": True} if name == "_acquire_lock" else {}
            p = patch.object(entry, name, **kwargs)
            p.start()
            yield p

    def _stop_patches(self, patches):
        for p in reversed(list(patches)):
            p.stop()

    def test_load_env_file_called_before_mongo_connection(self):
        import trackora.__main__ as entry

        call_order: list[str] = []
        import sys as real_sys
        real_exit = real_sys.exit
        real_sys.exit = lambda *a: None

        def tracking_load():
            call_order.append("load_env_file")

        original_mongo = entry.MongoConnection

        def tracking_mongo(*args, **kwargs):
            call_order.append("MongoConnection")
            return original_mongo(*args, **kwargs)

        patches = list(self._start_patches(entry))
        p_env = patch.object(entry, "load_env_file", side_effect=tracking_load)
        p_mongo = patch.object(entry, "MongoConnection", side_effect=tracking_mongo)
        p_env.start()
        p_mongo.start()
        patches.extend([p_env, p_mongo])

        try:
            entry.main()
        except BaseException:
            pass
        finally:
            real_sys.exit = real_exit
            self._stop_patches(patches)

        assert len(call_order) >= 2, f"Expected >=2 calls, got {call_order}"
        assert call_order[0] == "load_env_file", (
            f"Expected load_env_file first, got {call_order}"
        )
        assert call_order[1] == "MongoConnection", (
            f"Expected MongoConnection second, got {call_order}"
        )

    def test_health_check_called_instead_of_is_available(self):
        import trackora.__main__ as entry

        import sys as real_sys
        real_exit = real_sys.exit
        real_sys.exit = lambda *a: None

        import_paths = list(self._start_patches(entry))
        p_env = patch.object(entry, "load_env_file")
        p_mongo = patch.object(entry, "MongoConnection")
        p_env.start()
        mongo_cls = p_mongo.start()
        import_paths.extend([p_env, p_mongo])
        mongo_instance = mongo_cls.return_value

        try:
            entry.main()
        except BaseException:
            pass
        finally:
            real_sys.exit = real_exit
            self._stop_patches(import_paths)

        mongo_instance.validate_async.assert_called_once()
        mongo_instance.is_available.assert_not_called()


class TestQueueFallback:
    def test_missing_uri_still_allows_queue_path(self, tmp_path: Path):
        """Verify that without MONGODB_URI, submission falls back to queue."""
        from services.support.mongo_connection import MongoConnection
        from services.support.mongo_report_service import MongoReportService

        mongo = MongoConnection()
        assert not mongo.health_check()
        assert not mongo.is_available

        svc = MongoReportService(connection=mongo)
        from services.support.reporting_interface import ReportType, SubmitResult
        result = svc.submit_report(ReportType.BUG, "Test", "Body")
        assert isinstance(result, SubmitResult)
        assert result.success is False
        assert "connection failed" in (result.error_message or "")

class TestAppdataEnvPrioritization:
    def test_prioritizes_appdata_env_over_cwd(self, tmp_path: Path):
        appdata_dir = tmp_path / "appdata"
        appdata_dir.mkdir()
        appdata_env = appdata_dir / ".env"
        appdata_env.write_text("MONGODB_URI=appdata\n", encoding="utf-8")

        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        cwd_env = cwd_dir / ".env"
        cwd_env.write_text("MONGODB_URI=cwd\n", encoding="utf-8")

        def mock_is_file(self_path):
            return self_path == appdata_env or self_path == cwd_env

        with (
            patch("trackora.core.env.Path.cwd", return_value=cwd_dir),
            patch("trackora.core.paths.BASE_DIR", appdata_dir),
            patch("trackora.core.env.Path.is_file", mock_is_file),
        ):
            result = _discover_env_file(None)
            assert result == appdata_env


