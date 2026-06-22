"""
Tests for tracker/recovery_manager.py

Covers:
- AC-008: Crash Recovery
- Clean startup (no orphans)
- Single session recovery
- Multiple session recovery
- Short session discard
- Repository failure handling
- Duration calculation correctness
- UTC-naive datetime handling
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
from typing import Optional

from database.models import ActiveSession, Session
from tracker.recovery_manager import (
    RecoveryManager,
    RecoveryResult,
    RecoveredSession,
    MINIMUM_SESSION_DURATION_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def make_active_session(
    id: int = 1,
    game_id: int = 10,
    start_time: Optional[datetime] = None,
    process_id: int = 1234,
) -> ActiveSession:
    """Factory for ActiveSession test instances."""
    if start_time is None:
        start_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    return ActiveSession(
        id=id,
        game_id=game_id,
        process_id=process_id,
        start_time=start_time,
        created_at=start_time,
    )


def make_repos(
    active_sessions: Optional[list[ActiveSession]] = None,
    add_returns_id: int = 99,
) -> tuple[MagicMock, MagicMock]:
    """
    Returns (active_sessions_repo_mock, sessions_repo_mock).
    active_sessions_repo.get_all() returns `active_sessions`.
    sessions_repo.add().id returns `add_returns_id`.
    """
    active_repo = MagicMock()
    active_repo.get_all.return_value = active_sessions or []

    sessions_repo = MagicMock()
    sessions_repo.add.return_value.id = add_returns_id

    return active_repo, sessions_repo


# ---------------------------------------------------------------------------
# Clean startup — no orphans
# ---------------------------------------------------------------------------

class TestCleanStartup:
    def test_no_orphans_returns_empty_result(self):
        active_repo, sessions_repo = make_repos(active_sessions=[])
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert isinstance(result, RecoveryResult)
        assert result.total_found == 0
        assert result.recovery_needed is False
        assert result.recovered_sessions == []
        assert result.discarded_count == 0
        assert result.error_count == 0

    def test_no_orphans_does_not_touch_sessions_repo(self):
        active_repo, sessions_repo = make_repos(active_sessions=[])
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        sessions_repo.add.assert_not_called()

    def test_no_orphans_does_not_delete_anything(self):
        active_repo, sessions_repo = make_repos(active_sessions=[])
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        active_repo.end_session.assert_not_called()


# ---------------------------------------------------------------------------
# Single session recovery — AC-008
# ---------------------------------------------------------------------------

class TestSingleSessionRecovery:
    def test_recover_single_session_is_saved(self):
        """AC-008: Active session recovered, no session data lost."""
        start = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        orphan = make_active_session(id=1, game_id=5, start_time=start)
        active_repo, sessions_repo = make_repos(
            active_sessions=[orphan],
            add_returns_id=42,
        )
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert result.recovery_needed is True
        assert len(result.recovered_sessions) == 1

        recovered = result.recovered_sessions[0]
        assert recovered.game_id == 5
        assert recovered.active_session_id == 1
        assert recovered.was_saved is True
        assert recovered.saved_session_id == 42
        assert recovered.discard_reason is None

    def test_recover_single_session_duration_is_reasonable(self):
        """AC-008: Recovered session duration reasonable."""
        start = datetime.now(tz=timezone.utc) - timedelta(minutes=45)
        orphan = make_active_session(id=1, game_id=5, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        recovered = result.recovered_sessions[0]
        # Duration should be approximately 45 minutes
        assert 2600 <= recovered.duration_seconds <= 2800

    def test_recover_single_session_deletes_from_active_sessions(self):
        """After recovery, the active_session record must be removed."""
        orphan = make_active_session(id=7)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        active_repo.end_session.assert_called_once_with(7)

    def test_recover_single_session_correct_game_id_saved(self):
        orphan = make_active_session(id=1, game_id=999)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        created_session: Session = sessions_repo.add.call_args[0][0]
        assert created_session.game_id == 999

    def test_recover_single_session_start_time_preserved(self):
        start = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        orphan = make_active_session(id=1, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        created_session: Session = sessions_repo.add.call_args[0][0]
        assert created_session.start_time == start

    def test_recover_single_session_duration_stored_correctly(self):
        start = datetime.now(tz=timezone.utc) - timedelta(seconds=3600)
        orphan = make_active_session(id=1, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        created_session: Session = sessions_repo.add.call_args[0][0]
        # Duration should be approximately 3600 seconds
        assert abs(created_session.duration_seconds - 3600) < 5


# ---------------------------------------------------------------------------
# Multiple sessions recovery
# ---------------------------------------------------------------------------

class TestMultipleSessionsRecovery:
    def test_recover_multiple_sessions_all_saved(self):
        now = datetime.now(tz=timezone.utc)
        orphans = [
            make_active_session(id=1, game_id=10, start_time=now - timedelta(hours=2)),
            make_active_session(id=2, game_id=20, start_time=now - timedelta(hours=1)),
            make_active_session(id=3, game_id=30, start_time=now - timedelta(minutes=30)),
        ]
        active_repo, sessions_repo = make_repos(active_sessions=orphans)
        sessions_repo.add.side_effect = [MagicMock(id=101), MagicMock(id=102), MagicMock(id=103)]
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert len(result.recovered_sessions) == 3
        assert result.discarded_count == 0
        assert result.error_count == 0

    def test_recover_multiple_sessions_each_deleted(self):
        now = datetime.now(tz=timezone.utc)
        orphans = [
            make_active_session(id=1, start_time=now - timedelta(hours=2)),
            make_active_session(id=2, start_time=now - timedelta(hours=1)),
        ]
        active_repo, sessions_repo = make_repos(active_sessions=orphans)
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        assert active_repo.end_session.call_count == 2
        active_repo.end_session.assert_any_call(1)
        active_repo.end_session.assert_any_call(2)

    def test_recover_multiple_sessions_correct_total_found(self):
        now = datetime.now(tz=timezone.utc)
        orphans = [
            make_active_session(id=i, start_time=now - timedelta(hours=i))
            for i in range(1, 6)
        ]
        active_repo, sessions_repo = make_repos(active_sessions=orphans)
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert result.total_found == 5


# ---------------------------------------------------------------------------
# Short session discard
# ---------------------------------------------------------------------------

class TestShortSessionDiscard:
    def test_session_below_minimum_duration_is_discarded(self):
        """Sessions under MINIMUM_SESSION_DURATION_SECONDS must be discarded."""
        start = datetime.now(tz=timezone.utc) - timedelta(
            milliseconds=500  # well below 1 second minimum
        )
        orphan = make_active_session(id=1, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert result.discarded_count == 1
        assert len(result.recovered_sessions) == 0
        sessions_repo.add.assert_not_called()

    def test_discarded_session_still_deleted_from_active_sessions(self):
        """Even discarded sessions must be cleaned from active_sessions."""
        start = datetime.now(tz=timezone.utc)  # 0 seconds ago
        orphan = make_active_session(id=5, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        manager.recover()

        active_repo.end_session.assert_called_once_with(5)

    def test_session_exactly_at_minimum_duration_is_saved(self):
        """Session at exactly MINIMUM_SESSION_DURATION_SECONDS must be saved."""
        start = datetime.now(tz=timezone.utc) - timedelta(
            seconds=MINIMUM_SESSION_DURATION_SECONDS
        )
        orphan = make_active_session(id=1, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert len(result.recovered_sessions) == 1
        assert result.discarded_count == 0

    def test_mixed_valid_and_short_sessions(self):
        """Some sessions discarded, others recovered correctly."""
        now = datetime.now(tz=timezone.utc)
        orphans = [
            make_active_session(id=1, start_time=now - timedelta(hours=1)),   # valid
            make_active_session(id=2, start_time=now),                         # too short
            make_active_session(id=3, start_time=now - timedelta(minutes=30)), # valid
        ]
        active_repo, sessions_repo = make_repos(active_sessions=orphans)
        sessions_repo.add.side_effect = [MagicMock(id=10), MagicMock(id=11)]
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert len(result.recovered_sessions) == 2
        assert result.discarded_count == 1
        assert sessions_repo.add.call_count == 2


# ---------------------------------------------------------------------------
# Repository failure handling
# ---------------------------------------------------------------------------

class TestRepositoryFailures:
    def test_get_all_failure_returns_error_result(self):
        """If active_sessions cannot be read, error is counted and recovery aborts."""
        active_repo = MagicMock()
        active_repo.get_all.side_effect = Exception("DB connection failed")
        sessions_repo = MagicMock()

        manager = RecoveryManager(active_repo, sessions_repo)
        result = manager.recover()

        assert result.error_count == 1
        assert result.total_found == 1
        assert len(result.recovered_sessions) == 0
        sessions_repo.add.assert_not_called()

    def test_session_save_failure_counts_as_error(self):
        """If saving a session fails, it counts as an error not a discard."""
        orphan = make_active_session(
            id=1,
            start_time=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        sessions_repo.add.side_effect = Exception("Write failed")

        manager = RecoveryManager(active_repo, sessions_repo)
        result = manager.recover()

        assert result.error_count == 1
        assert len(result.recovered_sessions) == 0

    def test_delete_failure_does_not_propagate(self):
        """Delete failure is logged but does not crash recovery or raise."""
        orphan = make_active_session(
            id=1,
            start_time=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        active_repo.end_session.side_effect = Exception("Delete failed")

        manager = RecoveryManager(active_repo, sessions_repo)

        # Must not raise
        result = manager.recover()

        # Session was still saved despite delete failure
        assert sessions_repo.add.call_count == 1

    def test_partial_failure_continues_other_sessions(self):
        """If one session fails, recovery continues for remaining sessions."""
        now = datetime.now(tz=timezone.utc)
        orphans = [
            make_active_session(id=1, game_id=10, start_time=now - timedelta(hours=2)),
            make_active_session(id=2, game_id=20, start_time=now - timedelta(hours=1)),
            make_active_session(id=3, game_id=30, start_time=now - timedelta(minutes=30)),
        ]
        active_repo, sessions_repo = make_repos(active_sessions=orphans)
        # Second create() call fails
        sessions_repo.add.side_effect = [MagicMock(id=100), Exception("Write error"), MagicMock(id=102)]

        manager = RecoveryManager(active_repo, sessions_repo)
        result = manager.recover()

        assert len(result.recovered_sessions) == 2
        assert result.error_count == 1
        assert result.total_found == 3


# ---------------------------------------------------------------------------
# Duration calculation
# ---------------------------------------------------------------------------

class TestDurationCalculation:
    def test_duration_calculation_exact_one_hour(self):
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        orphan = make_active_session(id=1, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        with patch(
            "tracker.recovery_manager.datetime",
            wraps=datetime,
        ) as mock_dt:
            mock_dt.now.return_value = end
            result = manager.recover()

        recovered = result.recovered_sessions[0]
        assert recovered.duration_seconds == 3600

    def test_duration_never_negative(self):
        """Even if clocks are skewed, duration must be >= 0."""
        # start_time is in the future (edge case)
        start = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        orphan = make_active_session(id=1, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        # Session will be discarded as duration < MINIMUM, but must not be negative
        assert result.discarded_count == 1 or result.error_count == 1

    def test_duration_calculation_exact_30_minutes(self):
        start = datetime(2024, 3, 15, 14, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
        orphan = make_active_session(id=1, start_time=start)
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        with patch("tracker.recovery_manager.datetime", wraps=datetime) as mock_dt:
            mock_dt.now.return_value = end
            result = manager.recover()

        recovered = result.recovered_sessions[0]
        assert recovered.duration_seconds == 1800


# ---------------------------------------------------------------------------
# UTC-naive datetime handling
# ---------------------------------------------------------------------------

class TestNaiveDatetimeHandling:
    def test_naive_start_time_is_handled(self):
        """SQLite may return naive datetimes; recovery must handle them gracefully."""
        # Naive datetime (no tzinfo) — simulates SQLite storage behaviour
        naive_start = datetime(2024, 5, 1, 12, 0, 0)  # no tzinfo
        orphan = ActiveSession(
            id=1,
            game_id=10,
            process_id=999,
            start_time=naive_start,
            created_at=naive_start,
        )
        active_repo, sessions_repo = make_repos(active_sessions=[orphan])
        manager = RecoveryManager(active_repo, sessions_repo)

        # Should not raise TypeError on naive vs aware comparison
        result = manager.recover()

        # If duration > MINIMUM, it should be recovered
        assert result.error_count == 0

    def test_naive_start_treated_as_utc(self):
        """Naive datetime assumed to be UTC — matches SQLite storage convention."""
        naive_start = datetime(2024, 5, 1, 12, 0, 0)  # no tzinfo
        aware_equivalent = datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc)

        manager = RecoveryManager.__new__(RecoveryManager)
        result = RecoveryManager._ensure_utc(naive_start)

        assert result.tzinfo is not None
        assert result == aware_equivalent


# ---------------------------------------------------------------------------
# RecoveryResult properties
# ---------------------------------------------------------------------------

class TestRecoveryResultProperties:
    def test_recovery_needed_false_when_empty(self):
        result = RecoveryResult()
        assert result.recovery_needed is False

    def test_recovery_needed_true_with_recovered(self):
        result = RecoveryResult()
        result.recovered_sessions.append(
            RecoveredSession(
                active_session_id=1,
                game_id=1,
                start_time=datetime.now(tz=timezone.utc),
                duration_seconds=100,
                saved_session_id=1,
                was_saved=True,
            )
        )
        assert result.recovery_needed is True

    def test_recovery_needed_true_with_errors(self):
        result = RecoveryResult()
        result.error_count = 1
        assert result.recovery_needed is True

    def test_recovery_needed_true_with_discards(self):
        result = RecoveryResult()
        result.discarded_count = 2
        assert result.recovery_needed is True

    def test_total_found_sums_all_categories(self):
        result = RecoveryResult()
        result.recovered_sessions = [MagicMock(), MagicMock()]
        result.discarded_count = 3
        result.error_count = 1
        assert result.total_found == 6


# ---------------------------------------------------------------------------
# Integration-style: full recovery scenario
# ---------------------------------------------------------------------------

class TestFullRecoveryScenario:
    def test_crash_recovery_scenario_ac008(self):
        """
        AC-008: Trackora terminates unexpectedly.
        When application restarts:
        - Active session recovered
        - No session data lost
        - Recovered session duration reasonable
        """
        crash_time = datetime.now(tz=timezone.utc) - timedelta(hours=3)
        game_session = make_active_session(
            id=1,
            game_id=42,
            start_time=crash_time,
            process_id=5678,
        )

        active_repo, sessions_repo = make_repos(
            active_sessions=[game_session],
            add_returns_id=200,
        )
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        # Session was recovered
        assert result.recovery_needed is True
        assert len(result.recovered_sessions) == 1
        assert result.error_count == 0

        recovered = result.recovered_sessions[0]
        assert recovered.game_id == 42
        assert recovered.was_saved is True
        assert recovered.saved_session_id == 200

        # Duration is approximately 3 hours (reasonable)
        assert 10600 <= recovered.duration_seconds <= 11000

        # Active session was cleaned up
        active_repo.end_session.assert_called_once_with(1)

        # Session was stored with correct data
        saved: Session = sessions_repo.add.call_args[0][0]
        assert saved.game_id == 42
        assert saved.duration_seconds == recovered.duration_seconds
        assert saved.start_time == crash_time

    def test_shutdown_recovery_scenario(self):
        """
        Shutdown recovery: multiple games were running when Windows shut down.
        All sessions should be preserved.
        """
        now = datetime.now(tz=timezone.utc)
        sessions = [
            make_active_session(id=1, game_id=1, start_time=now - timedelta(hours=2)),
            make_active_session(id=2, game_id=2, start_time=now - timedelta(hours=1)),
        ]
        active_repo, sessions_repo = make_repos(active_sessions=sessions)
        sessions_repo.add.side_effect = [MagicMock(id=301), MagicMock(id=302)]
        manager = RecoveryManager(active_repo, sessions_repo)

        result = manager.recover()

        assert len(result.recovered_sessions) == 2
        assert result.discarded_count == 0
        assert result.error_count == 0

        ids = {r.saved_session_id for r in result.recovered_sessions}
        assert ids == {301, 302}