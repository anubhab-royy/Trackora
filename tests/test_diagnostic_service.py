"""Tests for DiagnosticService and CrashReport."""

import json
import platform
from pathlib import Path

import pytest

from services.crash.diagnostic_service import CrashReport, DiagnosticService
from trackora import __version__


class TestCrashReportDataclass:
    def test_minimal_report(self):
        report = CrashReport(
            report_id="abc-123",
            timestamp="2026-06-12T00:00:00",
            app_version="1.0.0",
            os_version="Windows-10",
            os_platform="Windows",
            active_sessions=[],
            tracked_games=0,
            stack_trace=None,
            recent_log_entries=[],
            crash_type="unexpected_shutdown",
            was_tracking=False,
        )
        assert report.report_id == "abc-123"
        assert report.crash_type == "unexpected_shutdown"
        assert report.was_tracking is False

    def test_full_report(self):
        report = CrashReport(
            report_id="xyz-789",
            timestamp="2026-06-12T01:02:03Z",
            app_version="1.1.0",
            os_version="Linux-5.15",
            os_platform="Linux",
            active_sessions=[{"game_id": 1, "game_name": "TestGame"}],
            tracked_games=5,
            stack_trace="Traceback (most recent call last):\n  ...",
            recent_log_entries=["line1", "line2"],
            crash_type="unhandled_exception",
            was_tracking=True,
        )
        assert report.active_sessions[0]["game_name"] == "TestGame"
        assert report.stack_trace is not None
        assert "Traceback" in report.stack_trace


class TestDiagnosticServiceCollect:
    def test_collect_defaults_not_none(self):
        svc = DiagnosticService(log_dir=Path("."))
        report = svc.collect_report()
        assert report.report_id is not None
        assert len(report.report_id) > 0
        assert report.timestamp is not None
        assert report.app_version == __version__
        assert report.os_version == platform.platform()
        assert report.os_platform == platform.system()
        assert report.active_sessions == []
        assert report.tracked_games == 0
        assert report.stack_trace is None
        assert report.crash_type == "unexpected_shutdown"
        assert report.was_tracking is False

    def test_collect_with_active_sessions(self):
        svc = DiagnosticService(log_dir=Path("."))
        sessions = [{"game_id": 1, "game_name": "GameA", "process_id": 1234}]
        report = svc.collect_report(
            crash_type="unhandled_exception",
            stack_trace="Traceback: error",
            active_sessions=sessions,
            tracked_games=10,
            was_tracking=True,
        )
        assert report.crash_type == "unhandled_exception"
        assert report.stack_trace == "Traceback: error"
        assert report.active_sessions == sessions
        assert report.tracked_games == 10
        assert report.was_tracking is True

    def test_collect_reads_log_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "trackora.log"
        log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        svc = DiagnosticService(log_dir=log_dir, log_lines=10)
        report = svc.collect_report()
        assert len(report.recent_log_entries) == 3
        assert "line1" in report.recent_log_entries

    def test_collect_log_lines_limit(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "trackora.log"
        log_file.write_text("\n".join(f"line{i}" for i in range(100)), encoding="utf-8")

        svc = DiagnosticService(log_dir=log_dir, log_lines=5)
        report = svc.collect_report()
        assert len(report.recent_log_entries) == 5
        assert report.recent_log_entries[-1] == "line99"

    def test_missing_log_file_returns_empty_list(self, tmp_path):
        log_dir = tmp_path / "nonexistent"
        svc = DiagnosticService(log_dir=log_dir)
        report = svc.collect_report()
        assert report.recent_log_entries == []


class TestDiagnosticServiceSaveAndSerialize:
    def test_serialize_roundtrip(self):
        report = CrashReport(
            report_id="r1",
            timestamp="2026-01-01T00:00:00",
            app_version="1.0.0",
            os_version="Win",
            os_platform="Windows",
            active_sessions=[],
            tracked_games=0,
            stack_trace=None,
            recent_log_entries=[],
            crash_type="unexpected_shutdown",
            was_tracking=False,
        )
        data = DiagnosticService.serialize(report)
        assert data["report_id"] == "r1"
        assert data["crash_type"] == "unexpected_shutdown"

        restored = DiagnosticService.deserialize(data)
        assert restored.report_id == "r1"
        assert restored.stack_trace is None
        assert restored.crash_type == "unexpected_shutdown"

    def test_save_report_creates_file(self, tmp_path):
        svc = DiagnosticService(log_dir=Path("."))
        report = svc.collect_report()
        storage_dir = tmp_path / "crash_reports"
        report_path = svc.save_report(report, storage_dir)
        assert report_path.is_file()
        assert report_path.suffix == ".json"
        assert report.report_id in report_path.name

    def test_save_report_json_content(self, tmp_path):
        svc = DiagnosticService(log_dir=Path("."))
        report = svc.collect_report(crash_type="unhandled_exception")
        storage_dir = tmp_path / "reports"
        report_path = svc.save_report(report, storage_dir)

        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["report_id"] == report.report_id
        assert data["crash_type"] == "unhandled_exception"
        assert data["app_version"] == __version__

    def test_save_uses_atomic_write(self, tmp_path):
        svc = DiagnosticService(log_dir=Path("."))
        report = svc.collect_report()
        storage_dir = tmp_path / "atomic_test"
        report_path = svc.save_report(report, storage_dir)

        # No .tmp files should remain
        tmp_files = list(storage_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestDefaultLogDir:
    def test_returns_path_object(self):
        d = DiagnosticService._default_log_dir()
        assert isinstance(d, Path)
        assert "Trackora" in d.parts

    def test_contains_logs(self):
        d = DiagnosticService._default_log_dir()
        assert "logs" in d.parts


class TestGetAppVersion:
    def test_returns_version_string(self):
        assert isinstance(DiagnosticService._get_app_version(), str)
        assert len(DiagnosticService._get_app_version()) > 0

    def test_matches_trackora_version(self):
        assert DiagnosticService._get_app_version() == __version__


class TestGetOsVersion:
    def test_returns_non_empty_string(self):
        v = DiagnosticService._get_os_version()
        assert isinstance(v, str)
        assert len(v) > 0


class TestGetOsPlatform:
    def test_returns_platform_name(self):
        p = DiagnosticService._get_os_platform()
        assert p in ("Windows", "Linux", "Darwin", "Java")
