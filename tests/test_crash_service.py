"""Tests for CrashService and StartupStateManager."""

import json
from pathlib import Path

import pytest

from services.crash.crash_service import (
    CrashResult,
    CrashService,
    StartupState,
    StartupStateManager,
)
from services.crash.diagnostic_service import DiagnosticService


# ======================================================================
# StartupStateManager
# ======================================================================


class TestStartupStateManagerInit:
    def test_creates_storage_dir(self, tmp_path):
        storage = tmp_path / "trackora_state"
        mgr = StartupStateManager(storage_dir=storage)
        assert storage.is_dir()

    def test_state_path(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        assert mgr.state_path == tmp_path / "startup_state.json"


class TestStartupStateManagerMarkAndRead:
    def test_first_read_returns_none(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        assert mgr.read_state() is None

    def test_mark_running_then_read(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.mark_running()
        assert mgr.read_state() == StartupState.RUNNING

    def test_mark_closed_then_read(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.mark_running()
        mgr.mark_closed_cleanly()
        assert mgr.read_state() == StartupState.CLOSED_CLEANLY

    def test_file_contains_json(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.mark_running()
        data = json.loads(mgr.state_path.read_text(encoding="utf-8"))
        assert data["status"] == "running"
        assert "last_updated" in data


class TestStartupStateManagerDetectCrash:
    def test_no_file_is_not_crash(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        assert mgr.detect_crash() is False

    def test_running_is_crash(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.mark_running()
        assert mgr.detect_crash() is True

    def test_cleanly_closed_is_not_crash(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.mark_running()
        mgr.mark_closed_cleanly()
        assert mgr.detect_crash() is False


class TestStartupStateManagerAtomicWrite:
    def test_atomic_write_leaves_no_tmp(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.mark_running()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_mark_running_creates_state_file(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.mark_running()
        assert mgr.state_path.is_file()


class TestStartupStateManagerCorruptedFile:
    def test_corrupted_json_returns_none(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.state_path.write_text("not json", encoding="utf-8")
        assert mgr.read_state() is None

    def test_corrupted_json_detect_returns_false(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.state_path.write_text("not json", encoding="utf-8")
        assert mgr.detect_crash() is False

    def test_empty_file_returns_none(self, tmp_path):
        mgr = StartupStateManager(storage_dir=tmp_path)
        mgr.state_path.write_text("", encoding="utf-8")
        assert mgr.read_state() is None


# ======================================================================
# CrashService
# ======================================================================


class TestCrashServiceLifecycle:
    def test_no_crash_on_first_launch(self, tmp_path):
        storage = tmp_path / "state"
        reports_dir = tmp_path / "reports"
        diag = DiagnosticService(log_dir=tmp_path)
        state_mgr = StartupStateManager(storage_dir=storage)
        svc = CrashService(
            diagnostic_service=diag,
            state_manager=state_mgr,
            crash_report_dir=reports_dir,
        )
        # Simulate first-ever launch: no state file exists, so
        # check_for_crash (reads previous state) must return False
        # before mark_startup overwrites it.
        result = svc.check_for_crash()
        assert result.has_crashed is False
        assert result.report is None

    def test_detects_crash_after_unclean_exit(self, tmp_path):
        storage = tmp_path / "state"
        reports_dir = tmp_path / "reports"
        diag = DiagnosticService(log_dir=tmp_path)
        state_mgr = StartupStateManager(storage_dir=storage)
        svc = CrashService(
            diagnostic_service=diag,
            state_manager=state_mgr,
            crash_report_dir=reports_dir,
        )
        # Simulate unclean shutdown: mark running but never mark clean
        svc.mark_startup()

        # Second service instance detects the crash
        diag2 = DiagnosticService(log_dir=tmp_path)
        svc2 = CrashService(
            diagnostic_service=diag2,
            state_manager=state_mgr,
            crash_report_dir=reports_dir,
        )
        result = svc2.check_for_crash()
        assert result.has_crashed is True
        assert result.report is not None
        assert result.report_path is not None
        assert result.report_path.is_file()
        assert result.report.crash_type == "unexpected_shutdown"

    def test_clean_shutdown_no_crash(self, tmp_path):
        storage = tmp_path / "state"
        reports_dir = tmp_path / "reports"
        diag = DiagnosticService(log_dir=tmp_path)
        state_mgr = StartupStateManager(storage_dir=storage)
        svc = CrashService(
            diagnostic_service=diag,
            state_manager=state_mgr,
            crash_report_dir=reports_dir,
        )
        # Normal lifecycle: check (no prior state), mark, then clean shutdown
        svc.check_for_crash()
        svc.mark_startup()
        svc.mark_clean_shutdown()

        # Second instance
        diag2 = DiagnosticService(log_dir=tmp_path)
        svc2 = CrashService(
            diagnostic_service=diag2,
            state_manager=state_mgr,
            crash_report_dir=reports_dir,
        )
        result = svc2.check_for_crash()
        assert result.has_crashed is False

    def test_check_for_crash_includes_active_sessions(self, tmp_path):
        storage = tmp_path / "state"
        reports_dir = tmp_path / "reports"
        diag = DiagnosticService(log_dir=tmp_path)
        state_mgr = StartupStateManager(storage_dir=storage)
        svc = CrashService(
            diagnostic_service=diag,
            state_manager=state_mgr,
            crash_report_dir=reports_dir,
        )
        svc.mark_startup()

        diag2 = DiagnosticService(log_dir=tmp_path)
        svc2 = CrashService(
            diagnostic_service=diag2,
            state_manager=state_mgr,
            crash_report_dir=reports_dir,
        )
        result = svc2.check_for_crash(
            active_sessions=[{"game_id": 1, "game_name": "GameA"}],
            tracked_games=3,
            was_tracking=True,
        )
        assert result.has_crashed is True
        assert result.report is not None
        assert result.report.active_sessions[0]["game_name"] == "GameA"
        assert result.report.tracked_games == 3
        assert result.report.was_tracking is True

    def test_mark_clean_shutdown_does_not_raise(self, tmp_path):
        diag = DiagnosticService(log_dir=tmp_path)
        svc = CrashService(
            diagnostic_service=diag,
            state_manager=StartupStateManager(storage_dir=tmp_path / "state"),
            crash_report_dir=tmp_path / "reports",
        )
        svc.mark_clean_shutdown()

    def test_properties(self, tmp_path):
        diag = DiagnosticService(log_dir=tmp_path)
        reports_dir = tmp_path / "crash_reports"
        svc = CrashService(
            diagnostic_service=diag,
            crash_report_dir=reports_dir,
        )
        assert svc.crash_report_dir == reports_dir
        assert isinstance(svc.state_manager, StartupStateManager)


class TestCrashResultDataclass:
    def test_defaults(self):
        r = CrashResult(has_crashed=False)
        assert r.has_crashed is False
        assert r.report is None
        assert r.report_path is None

    def test_with_report(self, tmp_path):
        from services.crash.diagnostic_service import CrashReport

        report = CrashReport(
            report_id="cr1",
            timestamp="now",
            app_version="1.0",
            os_version="Win",
            os_platform="Windows",
            active_sessions=[],
            tracked_games=0,
            stack_trace=None,
            recent_log_entries=[],
            crash_type="unexpected_shutdown",
            was_tracking=False,
        )
        r = CrashResult(has_crashed=True, report=report, report_path=tmp_path / "report.json")
        assert r.has_crashed is True
        assert r.report is report
        assert r.report_path == tmp_path / "report.json"
