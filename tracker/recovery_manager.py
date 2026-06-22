"""
Recovery Manager - Phase 3
Handles crash recovery and shutdown recovery by restoring active sessions.

Architecture: Tracking Layer
Uses: ActiveSessionsRepository, SessionsRepository
No direct database access - all persistence through repositories.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from database.repositories.active_sessions_repository import ActiveSessionsRepository
from database.repositories.sessions_repository import SessionsRepository
from database.models import ActiveSession, Session

logger = logging.getLogger(__name__)

# Minimum session duration in seconds to be considered valid for recovery.
# Sessions shorter than this are likely noise from crashes at startup.
MINIMUM_SESSION_DURATION_SECONDS: int = 1

# Maximum session duration in seconds for recovered sessions.
# Sessions longer than this are likely artifacts of a long gap between
# crash and recovery (e.g. computer left on for days after Trackora crash).
MAXIMUM_SESSION_DURATION_SECONDS: int = 86400  # 24 hours


@dataclass
class RecoveredSession:
    """
    Represents a session that was successfully recovered after a crash or shutdown.
    Returned by RecoveryManager to allow the SessionManager to resume state.
    """
    active_session_id: int
    game_id: int
    start_time: datetime
    duration_seconds: int
    saved_session_id: Optional[int]
    was_saved: bool
    discard_reason: Optional[str] = None


@dataclass
class RecoveryResult:
    """
    Summary of the full recovery operation.
    """
    recovered_sessions: list[RecoveredSession] = field(default_factory=list)
    discarded_count: int = 0
    error_count: int = 0

    @property
    def total_found(self) -> int:
        return len(self.recovered_sessions) + self.discarded_count + self.error_count

    @property
    def recovery_needed(self) -> bool:
        return self.total_found > 0


class RecoveryManager:
    """
    Recovers active sessions after an application crash or unexpected shutdown.

    Strategy (from architecture.md):
        Application Crash
            ↓
        Read active_sessions
            ↓
        Restore tracking state
            ↓
        Continue monitoring

    This class is part of the Tracking Layer.
    It uses repositories exclusively — no raw SQL, no direct DB access.

    Usage:
        recovery_manager = RecoveryManager(
            active_sessions_repo=active_sessions_repo,
            sessions_repo=sessions_repo
        )
        result = recovery_manager.recover()
    """

    def __init__(
        self,
        active_sessions_repo: ActiveSessionsRepository,
        sessions_repo: SessionsRepository,
    ) -> None:
        self._active_sessions_repo = active_sessions_repo
        self._sessions_repo = sessions_repo

    def recover(self) -> RecoveryResult:
        """
        Main recovery entry point. Called once at application startup.

        Reads all records from active_sessions, saves each as a completed
        session in the sessions table, then clears the active_sessions table.

        Returns:
            RecoveryResult with details of what was recovered, discarded, or errored.
        """
        logger.info("RecoveryManager: Starting session recovery scan.")

        result = RecoveryResult()

        try:
            orphaned: list[ActiveSession] = (
                self._active_sessions_repo.get_all()
            )
        except Exception as exc:
            logger.error(
                "RecoveryManager: Failed to read active_sessions table. "
                "Recovery aborted. Error: %s",
                exc,
                exc_info=True,
            )
            result.error_count += 1
            return result

        if not orphaned:
            logger.info(
                "RecoveryManager: No orphaned sessions found. "
                "Clean startup confirmed."
            )
            return result

        logger.warning(
            "RecoveryManager: Found %d orphaned active session(s). "
            "Application likely did not shut down cleanly.",
            len(orphaned),
        )

        recovery_time: datetime = datetime.now(tz=timezone.utc)

        for active_session in orphaned:
            recovered = self._recover_single_session(active_session, recovery_time)

            if recovered.was_saved:
                result.recovered_sessions.append(recovered)
            elif recovered.discard_reason is not None:
                result.discarded_count += 1
            else:
                result.error_count += 1

        self._log_recovery_summary(result)
        return result

    def _recover_single_session(
        self,
        active_session: ActiveSession,
        recovery_time: datetime,
    ) -> RecoveredSession:
        """
        Recovers a single orphaned active session.

        Steps:
        1. Calculate duration from start_time to recovery_time
        2. Validate minimum duration
        3. Save to sessions table
        4. Remove from active_sessions table

        Args:
            active_session: The orphaned ActiveSession record.
            recovery_time: The timestamp to use as the session end time.

        Returns:
            RecoveredSession describing the outcome.
        """
        logger.info(
            "RecoveryManager: Processing orphaned session id=%d "
            "game_id=%d start_time=%s",
            active_session.id,
            active_session.game_id,
            active_session.start_time,
        )

        # Ensure start_time is timezone-aware for safe arithmetic
        start_time = self._ensure_utc(active_session.start_time)

        # Calculate duration
        duration_seconds = self._calculate_duration(start_time, recovery_time)

        # Discard sessions that are too short to be meaningful
        if duration_seconds < MINIMUM_SESSION_DURATION_SECONDS:
            logger.warning(
                "RecoveryManager: Discarding session id=%d — "
                "duration %d second(s) is below minimum threshold of %d.",
                active_session.id,
                duration_seconds,
                MINIMUM_SESSION_DURATION_SECONDS,
            )
            self._safe_delete_active_session(active_session.id)
            return RecoveredSession(
                active_session_id=active_session.id,
                game_id=active_session.game_id,
                start_time=start_time,
                duration_seconds=duration_seconds,
                saved_session_id=None,
                was_saved=False,
                discard_reason=(
                    f"Duration {duration_seconds}s below minimum "
                    f"{MINIMUM_SESSION_DURATION_SECONDS}s"
                ),
            )

        # Discard sessions that are too long (likely recovery artifact)
        if duration_seconds > MAXIMUM_SESSION_DURATION_SECONDS:
            logger.warning(
                "RecoveryManager: Discarding session id=%d — "
                "duration %d second(s) exceeds maximum threshold of %d.",
                active_session.id,
                duration_seconds,
                MAXIMUM_SESSION_DURATION_SECONDS,
            )
            self._safe_delete_active_session(active_session.id)
            return RecoveredSession(
                active_session_id=active_session.id,
                game_id=active_session.game_id,
                start_time=start_time,
                duration_seconds=duration_seconds,
                saved_session_id=None,
                was_saved=False,
                discard_reason=(
                    f"Duration {duration_seconds}s exceeds maximum "
                    f"{MAXIMUM_SESSION_DURATION_SECONDS}s"
                ),
            )

        # Save the session to the sessions table
        saved_session_id = self._save_recovered_session(
            game_id=active_session.game_id,
            start_time=start_time,
            end_time=recovery_time,
            duration_seconds=duration_seconds,
        )

        if saved_session_id is None:
            # Save failed — error already logged in _save_recovered_session
            return RecoveredSession(
                active_session_id=active_session.id,
                game_id=active_session.game_id,
                start_time=start_time,
                duration_seconds=duration_seconds,
                saved_session_id=None,
                was_saved=False,
                discard_reason=None,  # None here means error, not deliberate discard
            )

        # Remove from active_sessions now that it is safely stored
        self._safe_delete_active_session(active_session.id)

        logger.info(
            "RecoveryManager: Recovered session id=%d → "
            "saved as session id=%d (game_id=%d, duration=%ds)",
            active_session.id,
            saved_session_id,
            active_session.game_id,
            duration_seconds,
        )

        return RecoveredSession(
            active_session_id=active_session.id,
            game_id=active_session.game_id,
            start_time=start_time,
            duration_seconds=duration_seconds,
            saved_session_id=saved_session_id,
            was_saved=True,
        )

    def _calculate_duration(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """
        Calculate session duration in whole seconds.

        Args:
            start_time: Session start (UTC-aware).
            end_time: Session end (UTC-aware).

        Returns:
            Duration in seconds, minimum 0.
        """
        delta = end_time - start_time
        seconds = int(delta.total_seconds())
        return max(0, seconds)

    def _save_recovered_session(
        self,
        game_id: int,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: int,
    ) -> Optional[int]:
        """
        Persists the recovered session to the sessions table.

        Returns:
            The new session's id on success, None on failure.
        """
        try:
            session = Session(
                id=None,
                game_id=game_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                created_at=datetime.now(tz=timezone.utc),
            )
            saved = self._sessions_repo.add(session)
            return saved.id
        except Exception as exc:
            logger.error(
                "RecoveryManager: Failed to save recovered session "
                "for game_id=%d. Error: %s",
                game_id,
                exc,
                exc_info=True,
            )
            return None

    def _safe_delete_active_session(self, active_session_id: int) -> None:
        """
        Deletes an active_session record. Errors are logged but do not propagate.

        Args:
            active_session_id: The id of the active_session to remove.
        """
        try:
            self._active_sessions_repo.end_session(active_session_id)
        except Exception as exc:
            logger.error(
                "RecoveryManager: Failed to delete active_session id=%d. "
                "Error: %s",
                active_session_id,
                exc,
                exc_info=True,
            )

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """
        Ensures a datetime is UTC-aware.
        If naive, assumes it was stored as UTC (SQLite behaviour).

        Args:
            dt: datetime that may or may not be timezone-aware.

        Returns:
            UTC-aware datetime.
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz=timezone.utc)

    def _log_recovery_summary(self, result: RecoveryResult) -> None:
        """Logs a human-readable summary after recovery completes."""
        logger.info(
            "RecoveryManager: Recovery complete. "
            "Found=%d | Recovered=%d | Discarded=%d | Errors=%d",
            result.total_found,
            len(result.recovered_sessions),
            result.discarded_count,
            result.error_count,
        )
        if result.error_count > 0:
            logger.warning(
                "RecoveryManager: %d session(s) could not be recovered "
                "due to errors. Check logs above for details.",
                result.error_count,
            )