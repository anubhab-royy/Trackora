"""
tracker/session_manager.py

Handles the full lifecycle of a gaming session:
  - Creating an active_session record when a game starts
  - Closing it when the game stops
  - Writing the completed session to the sessions table
  - Updating games.last_played / games.first_played

SessionManager accepts repository *interfaces* (duck-typed) so it can be
tested with lightweight fakes without a real database.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol

from database.models import ActiveSession as DbActiveSession, Session
from tracker.tracking_state import ActiveSession, TrackingState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository protocols (structural sub-typing — matches real repo interfaces)
# ---------------------------------------------------------------------------

class ActiveSessionsRepositoryProtocol(Protocol):
    def start_session(self, active_session: DbActiveSession) -> DbActiveSession:
        """Insert a new active_session row; return it with id populated."""
        ...

    def end_session(self, active_session_id: int) -> None:
        """Remove the active_session row by PK."""
        ...

    def get_all(self) -> list[DbActiveSession]:
        """Return all rows from active_sessions."""
        ...


class SessionsRepositoryProtocol(Protocol):
    def add(self, session: Session) -> Session:
        """Insert a completed session row; return it with id populated."""
        ...


class GamesRepositoryProtocol(Protocol):
    def update_last_played(self, game_id: int, played_at: datetime) -> None:
        """Update games.last_played (and first_played if null)."""
        ...


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class SessionManager:
    """
    Orchestrates session creation and completion.

    Dependencies are injected so they can be replaced with fakes in tests.
    """

    def __init__(
        self,
        state: TrackingState,
        active_sessions_repo: ActiveSessionsRepositoryProtocol,
        sessions_repo: SessionsRepositoryProtocol,
        games_repo: GamesRepositoryProtocol,
    ) -> None:
        self._state = state
        self._active_sessions_repo = active_sessions_repo
        self._sessions_repo = sessions_repo
        self._games_repo = games_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(self, game_id: int, process_id: int) -> ActiveSession | None:
        """
        Called when a tracked game's process is detected as newly running.

        Persists an active_session row, updates in-memory state, and returns
        the new ActiveSession.  Returns None if a session is already open for
        this game (safety guard).
        """
        if self._state.is_game_active(game_id):
            logger.warning("start_session called but game_id=%d is already active — ignoring", game_id)
            return None

        game = self._state.tracked_games.get(game_id)
        if game is None:
            logger.error("start_session: game_id=%d not found in tracked_games", game_id)
            return None

        start_time = datetime.now()

        try:
            db_session = DbActiveSession(
                game_id=game_id,
                process_id=process_id,
                start_time=start_time,
            )
            saved = self._active_sessions_repo.start_session(db_session)
        except Exception:
            logger.exception("Failed to persist active_session for game_id=%d", game_id)
            return None

        session = ActiveSession(
            active_session_id=saved.id,
            game_id=game_id,
            game_name=game.name,
            process_id=process_id,
            start_time=start_time,
        )
        self._state.active_sessions[game_id] = session

        logger.info(
            "Session started: game=%r game_id=%d pid=%d active_session_id=%d",
            game.name, game_id, process_id, saved.id,
        )
        return session

    def end_session(self, game_id: int) -> bool:
        """
        Called when a tracked game's process has disappeared.

        Calculates duration, writes a completed session row, removes the
        active_session row, and updates games.last_played.

        Returns True on success, False if no active session found.
        """
        session = self._state.active_sessions.get(game_id)
        if session is None:
            logger.warning("end_session called but no active session for game_id=%d", game_id)
            return False

        end_time = datetime.now()
        duration_seconds = self._calculate_duration(session.start_time, end_time)

        # Persist the completed session
        try:
            db_session = Session(
                game_id=game_id,
                start_time=session.start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
            )
            saved = self._sessions_repo.add(db_session)
            logger.info(
                "Session saved: game=%r session_id=%d duration=%ds",
                session.game_name, saved.id, duration_seconds,
            )
        except Exception:
            logger.exception("Failed to save completed session for game_id=%d", game_id)
            # Still clean up in-memory state even if DB write fails
            self._cleanup_active_session(session)
            return False

        # Remove the active_session row (crash-recovery record no longer needed)
        try:
            self._active_sessions_repo.end_session(session.active_session_id)
        except Exception:
            logger.exception(
                "Failed to end active_session id=%d — may cause duplicate on next restart",
                session.active_session_id,
            )

        # Update games.last_played
        try:
            self._games_repo.update_last_played(game_id=game_id, timestamp=end_time)
        except Exception:
            logger.exception("Failed to update last_played for game_id=%d", game_id)

        self._cleanup_active_session(session)
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cleanup_active_session(self, session: ActiveSession) -> None:
        """Remove session from in-memory state."""
        self._state.active_sessions.pop(session.game_id, None)

    @staticmethod
    def _calculate_duration(start_time: datetime, end_time: datetime) -> int:
        """Return non-negative integer seconds between two datetimes."""
        delta = end_time - start_time
        seconds = int(delta.total_seconds())
        return max(0, seconds)
