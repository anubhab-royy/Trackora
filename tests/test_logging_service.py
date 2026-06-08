"""
Tests for LoggingService — Phase 9.

Covers:
  - setup creates log directory and file
  - setup is idempotent (no duplicate handlers)
  - force=True reconfigures
  - get_log_dir returns expected path
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from services.logging_service import LoggingService


class TestLoggingService:
    def test_setup_creates_log_directory(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        LoggingService.setup(log_dir=log_dir, force=True)
        assert log_dir.is_dir()

    def test_setup_creates_log_file(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        LoggingService.setup(log_dir=log_dir, force=True)
        log_file = log_dir / "game_tracker.log"
        assert log_file.exists()

    def test_setup_idempotent(self, tmp_path: Path) -> None:
        LoggingService.setup(log_dir=tmp_path, force=True)
        root = logging.getLogger()
        handler_count = len(root.handlers)

        # second call without force should not add handlers
        LoggingService.setup(log_dir=tmp_path)
        assert len(root.handlers) == handler_count

    def test_setup_force_replaces_handlers(self, tmp_path: Path) -> None:
        LoggingService.setup(log_dir=tmp_path, force=True)
        root = logging.getLogger()
        handler_count = len(root.handlers)

        LoggingService.setup(log_dir=tmp_path, force=True)
        # handlers are removed and re-added, so count should be the same
        assert len(root.handlers) == handler_count

    def test_get_log_dir_returns_path(self) -> None:
        log_dir = LoggingService.get_log_dir()
        assert isinstance(log_dir, Path)
        assert "logs" in str(log_dir)

    def test_force_reset(self, tmp_path: Path) -> None:
        """With force=True, setup can be called again to re-init."""
        LoggingService.setup(log_dir=tmp_path, force=True)
        root = logging.getLogger()
        original_handlers = list(root.handlers)

        LoggingService.setup(log_dir=tmp_path, force=True)
        # Old handlers should have been removed; new ones added.
        # Count should be same, but objects differ.
        assert len(root.handlers) == len(original_handlers)
        # At least one root handler should exist
        assert len(root.handlers) >= 1

    @pytest.fixture(autouse=True)
    def _cleanup(self) -> None:
        """Reset LoggingService._initialized between tests."""
        LoggingService._initialized = False  # type: ignore[attr-defined]
        yield
        LoggingService._initialized = False
