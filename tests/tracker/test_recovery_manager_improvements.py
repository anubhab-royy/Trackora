"""
Tests for T-203 Crash Recovery Improvements in tracker/recovery_manager.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

from database.models import ActiveSession, Session
from tracker.recovery_manager import (
    RecoveryManager,
    RecoveryResult,
    RecoveredSession,
)

def make_active_session(
    id: int = 1,
    game_id: int = 10,
    process_id: int = 1234,
    start_time: datetime | None = None,
) -> ActiveSession:
    if start_time is None:
        start_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    return ActiveSession(
        id=id,
        game_id=game_id,
        process_id=process_id,
        start_time=start_time,
        created_at=start_time,
    )

def make_repos(active_sessions: list[ActiveSession] | None = None, add_returns_id: int = 99):
    active_repo = MagicMock()
    active_repo.get_all.return_value = active_sessions or []
    sessions_repo = MagicMock()
    sessions_repo.add.return_value.id = add_returns_id
    return active_repo, sessions_repo

class TestRecoveryManagerImprovements:
    def test_recovered_session_carries_process_id(self):
        active_session = make_active_session(id=1, game_id=10, process_id=5678)
        active_repo, sessions_repo = make_repos(active_sessions=[active_session])
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()
        
        assert len(result.recovered_sessions) == 1
        recovered = result.recovered_sessions[0]
        assert recovered.process_id == 5678
        assert recovered.active_session_id == 1
        assert recovered.game_id == 10

    def test_discarded_sessions_populated_in_result(self):
        # Short session (< 1 second) to trigger discard
        start_time = datetime.now(tz=timezone.utc)
        active_session = make_active_session(id=2, game_id=20, process_id=9999, start_time=start_time)
        active_repo, sessions_repo = make_repos(active_sessions=[active_session])
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert len(result.recovered_sessions) == 0
        assert len(result.discarded_sessions) == 1
        discarded = result.discarded_sessions[0]
        assert discarded.active_session_id == 2
        assert discarded.game_id == 20
        assert discarded.process_id == 9999
        assert discarded.was_saved is False
        assert "below minimum" in discarded.discard_reason

    def test_was_crash_false_logs_info_instead_of_warning(self):
        active_session = make_active_session(id=1, game_id=10, process_id=5678)
        active_repo, sessions_repo = make_repos(active_sessions=[active_session])
        manager = RecoveryManager(active_repo, sessions_repo)

        with patch("tracker.recovery_manager.logger") as mock_logger:
            manager.recover(was_crash=False)
            
            # Should NOT log warning about unclean shutdown
            warning_calls = [c for c in mock_logger.warning.call_args_list if "uncleanly" in str(c)]
            assert len(warning_calls) == 0

            # Should log info about clean shutdown recovery
            info_calls = [c for c in mock_logger.info.call_args_list if "clean shutdown" in str(c)]
            assert len(info_calls) > 0

    def test_was_crash_true_logs_warning_about_unclean_shutdown(self):
        active_session = make_active_session(id=1, game_id=10, process_id=5678)
        active_repo, sessions_repo = make_repos(active_sessions=[active_session])
        manager = RecoveryManager(active_repo, sessions_repo)

        with patch("tracker.recovery_manager.logger") as mock_logger:
            manager.recover(was_crash=True)
            
            # Should log warning about unclean shutdown
            warning_calls = [c for c in mock_logger.warning.call_args_list if "cleanly" in str(c)]
            assert len(warning_calls) > 0
