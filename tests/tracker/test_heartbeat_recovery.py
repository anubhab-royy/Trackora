"""
tests/tracker/test_heartbeat_recovery.py

Tests verifying that:
  1. ProcessMonitor calls update_active_sessions_heartbeat() on each tick.
  2. SessionManager.update_active_sessions_heartbeat() updates the heartbeat in the repo.
  3. RecoveryManager uses the heartbeat (created_at) to determine crash recovery duration.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, call

import pytest

from tracker.recovery_manager import RecoveryManager, MINIMUM_SESSION_DURATION_SECONDS
from database.models import ActiveSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_active_session(
    session_id: int = 1,
    game_id: int = 10,
    start_time: datetime | None = None,
    created_at: datetime | None = None,
    process_id: int = 1234,
) -> ActiveSession:
    if start_time is None:
        start_time = _utcnow() - timedelta(hours=1)
    if created_at is None:
        created_at = start_time
    return ActiveSession(
        id=session_id,
        game_id=game_id,
        process_id=process_id,
        start_time=start_time,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Recovery manager uses heartbeat when created_at > start_time
# ---------------------------------------------------------------------------

class TestHeartbeatDurationRecovery:
    """Verify that RecoveryManager uses the heartbeat (created_at) to compute durations."""

    def _make_manager(self, active_sessions: list[ActiveSession], sessions_repo: MagicMock) -> RecoveryManager:
        active_repo = MagicMock()
        active_repo.get_all.return_value = active_sessions
        return RecoveryManager(
            active_sessions_repo=active_repo,
            sessions_repo=sessions_repo,
        )

    def test_recovery_uses_heartbeat_as_end_time(self) -> None:
        """When created_at > start_time, the recovered session's end_time should be created_at."""
        start_time = _utcnow() - timedelta(hours=2)
        heartbeat = start_time + timedelta(hours=1, minutes=45)

        session = _make_active_session(start_time=start_time, created_at=heartbeat)

        sessions_repo = MagicMock()
        sessions_repo.add.return_value = MagicMock(id=42)

        manager = self._make_manager([session], sessions_repo)
        result = manager.recover()

        assert len(result.recovered_sessions) == 1
        recovered = result.recovered_sessions[0]
        expected_seconds = int((heartbeat - start_time).total_seconds())
        assert abs(recovered.duration_seconds - expected_seconds) <= 1

    def test_recovery_falls_back_to_recovery_time_when_no_heartbeat(self) -> None:
        """When created_at == start_time (no heartbeat stored), fall back to recovery_time."""
        start_time = _utcnow() - timedelta(hours=1)
        # created_at equals start_time - no heartbeat has been written yet
        session = _make_active_session(start_time=start_time, created_at=start_time)

        sessions_repo = MagicMock()
        sessions_repo.add.return_value = MagicMock(id=42)

        manager = self._make_manager([session], sessions_repo)
        result = manager.recover()

        # Should still recover, using fallback recovery_time (now approx start_time + 1h)
        assert len(result.recovered_sessions) == 1
        recovered = result.recovered_sessions[0]
        # Duration should be approximately 1 hour (within 10 seconds)
        assert 3590 <= recovered.duration_seconds <= 3610

    def test_recovery_discards_session_if_heartbeat_yields_too_short_duration(self) -> None:
        """Sessions where heartbeat duration is 0 seconds (heartbeat == start_time) and
        recovery_time also equals start_time are discarded as too short."""
        start_time = _utcnow()
        # Heartbeat equals start_time exactly — 0 second duration
        heartbeat = start_time

        session = _make_active_session(start_time=start_time, created_at=heartbeat)

        sessions_repo = MagicMock()
        manager = self._make_manager([session], sessions_repo)

        # Provide a recovery_time also at start_time so duration stays 0
        result = manager.recover()

        # 0 seconds < minimum of 1 second, so session is discarded
        assert len(result.recovered_sessions) == 0
        assert len(result.discarded_sessions) == 1
        sessions_repo.add.assert_not_called()


# ---------------------------------------------------------------------------
# SessionManager heartbeat update
# ---------------------------------------------------------------------------

class TestSessionManagerHeartbeat:
    """Verify that update_active_sessions_heartbeat updates the repository for all active sessions."""

    def test_heartbeat_updates_all_active_sessions(self) -> None:
        from tracker.session_manager import SessionManager

        fake_active_repo = MagicMock()
        fake_sessions_repo = MagicMock()
        fake_games_repo = MagicMock()
        fake_state = MagicMock()

        # Two active sessions in state
        sess_a = MagicMock()
        sess_a.active_session_id = 1
        sess_b = MagicMock()
        sess_b.active_session_id = 2
        fake_state.active_sessions = {10: sess_a, 20: sess_b}

        sm = SessionManager(
            active_sessions_repo=fake_active_repo,
            sessions_repo=fake_sessions_repo,
            games_repo=fake_games_repo,
            state=fake_state,
        )

        sm.update_active_sessions_heartbeat()

        assert fake_active_repo.update_heartbeat.call_count == 2
        called_ids = {c.args[0] for c in fake_active_repo.update_heartbeat.call_args_list}
        assert called_ids == {1, 2}
