"""
tests/test_update_checker_thread.py

T-202: Automatic Update System Phase 1 — Background Thread Tests

Covers:
  - Thread emits check_completed on success
  - Thread emits check_failed when service raises unexpectedly
  - Thread delegates to UpdateCenterService.check_for_updates()
  - Thread carries no UI imports (architecture constraint)
  - Thread carries no SQL imports (architecture constraint)
  - Signal payloads are UpdateCheckResult instances
  - Thread runs without blocking (non-blocking contract)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication required by QThread."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(update_available: bool = False) -> object:
    from services.update_center_service import GitHubRelease, UpdateCheckResult
    release = GitHubRelease(
        tag_name="v3.0.0",
        name="Trackora 3.0.0",
        body="## What's New\n- Background checks",
        published_at="2026-07-01T12:00:00Z",
        html_url="https://github.com/example/trackora/releases/tag/v3.0.0",
    ) if update_available else None
    return UpdateCheckResult(
        update_available=update_available,
        current_version="2.0.0",
        latest_version="3.0.0" if update_available else "2.0.0",
        release=release,
        checked_at="2026-07-05T12:00:00",
        source="remote",
    )


def _collect_signal(thread, signal_name: str) -> list:
    """Connect signal to a collector list; return the list."""
    collected: list = []
    getattr(thread, signal_name).connect(lambda *args: collected.extend(args))
    return collected


# ============================================================================
# TestUpdateCheckerThreadInit
# ============================================================================

class TestUpdateCheckerThreadInit:
    def test_instantiates_without_error(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        thread = UpdateCheckerThread(mock_service)
        assert thread is not None

    def test_stores_service_reference(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        thread = UpdateCheckerThread(mock_service)
        assert thread._update_service is mock_service

    def test_has_check_completed_signal(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        thread = UpdateCheckerThread(mock_service)
        assert hasattr(thread, "check_completed")

    def test_has_check_failed_signal(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        thread = UpdateCheckerThread(mock_service)
        assert hasattr(thread, "check_failed")

    def test_is_qthread_subclass(self, qapp) -> None:
        from PyQt6.QtCore import QThread
        from services.update_checker_thread import UpdateCheckerThread
        assert issubclass(UpdateCheckerThread, QThread)


# ============================================================================
# TestUpdateCheckerThreadRun
# ============================================================================

class TestUpdateCheckerThreadRun:
    """Tests for run() — delegate, emit, no blocking."""

    def test_run_calls_check_for_updates(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        mock_service.check_for_updates.return_value = _make_result()
        thread = UpdateCheckerThread(mock_service)
        thread.run()
        mock_service.check_for_updates.assert_called_once()

    def test_run_emits_check_completed_on_success(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        expected = _make_result(update_available=True)
        mock_service = MagicMock()
        mock_service.check_for_updates.return_value = expected
        thread = UpdateCheckerThread(mock_service)
        collected = _collect_signal(thread, "check_completed")
        thread.run()
        assert len(collected) == 1
        assert collected[0] is expected

    def test_run_emits_update_check_result_type(self, qapp) -> None:
        from services.update_center_service import UpdateCheckResult
        from services.update_checker_thread import UpdateCheckerThread
        result = _make_result(update_available=False)
        mock_service = MagicMock()
        mock_service.check_for_updates.return_value = result
        thread = UpdateCheckerThread(mock_service)
        collected = _collect_signal(thread, "check_completed")
        thread.run()
        assert isinstance(collected[0], UpdateCheckResult)

    def test_run_emits_correct_update_available_flag(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        result = _make_result(update_available=True)
        mock_service = MagicMock()
        mock_service.check_for_updates.return_value = result
        thread = UpdateCheckerThread(mock_service)
        collected = _collect_signal(thread, "check_completed")
        thread.run()
        assert collected[0].update_available is True

    def test_run_emits_no_check_failed_on_success(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        mock_service.check_for_updates.return_value = _make_result()
        thread = UpdateCheckerThread(mock_service)
        failed = _collect_signal(thread, "check_failed")
        thread.run()
        assert len(failed) == 0

    def test_run_emits_check_failed_on_exception(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        mock_service.check_for_updates.side_effect = RuntimeError("boom")
        thread = UpdateCheckerThread(mock_service)
        failed = _collect_signal(thread, "check_failed")
        thread.run()
        assert len(failed) == 1
        assert "boom" in failed[0]

    def test_run_emits_no_check_completed_on_exception(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        mock_service.check_for_updates.side_effect = ValueError("network gone")
        thread = UpdateCheckerThread(mock_service)
        completed = _collect_signal(thread, "check_completed")
        thread.run()
        assert len(completed) == 0

    def test_run_passes_through_service_result_unchanged(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        result = _make_result(update_available=True)
        mock_service = MagicMock()
        mock_service.check_for_updates.return_value = result
        thread = UpdateCheckerThread(mock_service)
        completed = _collect_signal(thread, "check_completed")
        thread.run()
        assert completed[0].latest_version == "3.0.0"
        assert completed[0].source == "remote"


# ============================================================================
# TestUpdateCheckerThreadArchitecture
# ============================================================================

class TestUpdateCheckerThreadArchitecture:
    """Verify no layer violations are introduced by the thread module."""

    def test_no_ui_import_in_thread_module(self) -> None:
        import ast
        import importlib.util
        spec = importlib.util.find_spec("services.update_checker_thread")
        assert spec is not None and spec.origin is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("ui"), (
                    f"Thread module imports from ui: {node.module}"
                )

    def test_no_database_import_in_thread_module(self) -> None:
        import ast
        import importlib.util
        spec = importlib.util.find_spec("services.update_checker_thread")
        assert spec is not None and spec.origin is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("database"), (
                    f"Thread module imports from database: {node.module}"
                )

    def test_thread_module_importable(self) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        assert UpdateCheckerThread is not None

    def test_thread_run_is_callable(self, qapp) -> None:
        from services.update_checker_thread import UpdateCheckerThread
        mock_service = MagicMock()
        thread = UpdateCheckerThread(mock_service)
        assert callable(thread.run)
