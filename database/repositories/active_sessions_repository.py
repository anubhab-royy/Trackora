# Session start/end/recovery

"""
ActiveSessionsRepository for GameTracker.

All SQL operations for the `active_sessions` table live here.

Purpose (database_schema.md):
    "Stores currently running sessions.
     Purpose: Crash recovery and shutdown recovery."

Lifecycle:
    1. Session starts  → INSERT a row into active_sessions.
    2. Session ends    → DELETE the row from active_sessions,
                         INSERT a row into sessions.
    3. On restart      → SELECT * FROM active_sessions to find orphaned sessions
                         that need recovery (AC-008).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from database.models.active_session import ActiveSession

logger = logging.getLogger(__name__)


def _row_to_active_session(row: sqlite3.Row) -> ActiveSession:
    return ActiveSession(
        id=row["id"],
        game_id=row["game_id"],
        process_id=row["process_id"],
        start_time=datetime.fromisoformat(row["start_time"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _dt_str(dt: datetime) -> str:
    return dt.isoformat()


class ActiveSessionsRepository:
    """
    CRUD operations for the `active_sessions` table.

    Args:
        connection: An open sqlite3.Connection provided by DatabaseManager.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def start_session(self, active_session: ActiveSession) -> ActiveSession:
        """
        Record that a game session has started.

        Inserts a row so that if the application crashes, the session
        can be recovered on next startup (AC-008).

        Returns:
            The same ActiveSession with its `id` field populated.
        """
        now = datetime.utcnow()
        active_session.created_at = now

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO active_sessions (game_id, process_id, start_time, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                active_session.game_id,
                active_session.process_id,
                _dt_str(active_session.start_time),
                _dt_str(active_session.created_at),
            ),
        )
        self._conn.commit()
        active_session.id = cursor.lastrowid
        logger.info(
            "Active session started: id=%s game_id=%s pid=%s",
            active_session.id,
            active_session.game_id,
            active_session.process_id,
        )
        return active_session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, active_session_id: int) -> ActiveSession | None:
        """Return an ActiveSession by primary key, or None."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM active_sessions WHERE id = ?;", (active_session_id,)
        )
        row = cursor.fetchone()
        return _row_to_active_session(row) if row else None

    def get_by_game_id(self, game_id: int) -> ActiveSession | None:
        """
        Return the active session for a specific game, or None.
        Each game should have at most one active session at a time.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM active_sessions WHERE game_id = ? LIMIT 1;", (game_id,)
        )
        row = cursor.fetchone()
        return _row_to_active_session(row) if row else None

    def get_all(self) -> list[ActiveSession]:
        """
        Return all active sessions.

        Called on application startup to detect sessions that were
        never closed (crash recovery, AC-008).
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM active_sessions ORDER BY start_time ASC;")
        return [_row_to_active_session(r) for r in cursor.fetchall()]

    def has_active_session(self, game_id: int) -> bool:
        """Return True if a game currently has a recorded active session."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT 1 FROM active_sessions WHERE game_id = ? LIMIT 1;", (game_id,)
        )
        return cursor.fetchone() is not None

    def count(self) -> int:
        """Return the total number of active session rows."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM active_sessions;")
        row = cursor.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def end_session(self, active_session_id: int) -> None:
        """
        Remove an active session record when the session ends normally.

        Called by the session manager after a completed session has been
        written to the `sessions` table.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "DELETE FROM active_sessions WHERE id = ?;", (active_session_id,)
        )
        self._conn.commit()
        logger.info("Active session ended/removed: id=%s", active_session_id)

    def end_session_by_game_id(self, game_id: int) -> None:
        """
        Remove the active session for a game by game_id.

        Convenience alternative to end_session() when the record id
        is not available.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "DELETE FROM active_sessions WHERE game_id = ?;", (game_id,)
        )
        self._conn.commit()
        logger.info("Active session removed for game_id=%s", game_id)

    def clear_all(self) -> int:
        """
        Remove all active session rows.

        Used during recovery when all orphaned sessions have been
        processed and saved to the sessions table.

        Returns:
            Number of rows deleted.
        """
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM active_sessions;")
        self._conn.commit()
        deleted = cursor.rowcount
        logger.info("Cleared %s orphaned active sessions.", deleted)
        return deleted