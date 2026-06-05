# All SQL for `sessions` + stats queries

"""
SessionsRepository for GameTracker.

All SQL operations for the `sessions` table live here.
Supports the full statistics requirements from acceptance_criteria.md:
    AC-004  Lifetime statistics
    AC-005  Daily statistics
    AC-006  Weekly statistics
    AC-007  Monthly statistics
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, date, timedelta

from database.models.session import Session

logger = logging.getLogger(__name__)


def _row_to_session(row: sqlite3.Row) -> Session:
    """Convert a sqlite3.Row from the sessions table into a Session dataclass."""
    return Session(
        id=row["id"],
        game_id=row["game_id"],
        start_time=datetime.fromisoformat(row["start_time"]),
        end_time=datetime.fromisoformat(row["end_time"]),
        duration_seconds=row["duration_seconds"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _dt_str(dt: datetime) -> str:
    return dt.isoformat()


class SessionsRepository:
    """
    CRUD and query operations for the `sessions` table.

    Args:
        connection: An open sqlite3.Connection provided by DatabaseManager.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(self, session: Session) -> Session:
        """
        Insert a completed session row.

        Returns:
            The same Session with its `id` field populated.
        """
        now = datetime.utcnow()
        session.created_at = now

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions
                (game_id, start_time, end_time, duration_seconds, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session.game_id,
                _dt_str(session.start_time),
                _dt_str(session.end_time),
                session.duration_seconds,
                _dt_str(session.created_at),
            ),
        )
        self._conn.commit()
        session.id = cursor.lastrowid
        logger.info(
            "Session saved: id=%s game_id=%s duration=%ss",
            session.id,
            session.game_id,
            session.duration_seconds,
        )
        return session

    # ------------------------------------------------------------------
    # Read — individual
    # ------------------------------------------------------------------

    def get_by_id(self, session_id: int) -> Session | None:
        """Return the Session with the given primary key, or None."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE id = ?;", (session_id,))
        row = cursor.fetchone()
        return _row_to_session(row) if row else None

    def get_all_for_game(self, game_id: int) -> list[Session]:
        """Return all sessions for a game, newest first."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE game_id = ? ORDER BY start_time DESC;",
            (game_id,),
        )
        return [_row_to_session(r) for r in cursor.fetchall()]

    def get_all(self, limit: int | None = None) -> list[Session]:
        """Return all sessions ordered by start_time descending."""
        cursor = self._conn.cursor()
        if limit is not None:
            cursor.execute(
                "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?;",
                (limit,),
            )
        else:
            cursor.execute("SELECT * FROM sessions ORDER BY start_time DESC;")
        return [_row_to_session(r) for r in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Read — statistics (AC-004 through AC-007)
    # ------------------------------------------------------------------

    def get_total_seconds_for_game(self, game_id: int) -> int:
        """Return the lifetime total duration in seconds for a single game."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM sessions WHERE game_id = ?;",
            (game_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_lifetime_total_seconds(self) -> int:
        """
        Return the sum of duration_seconds across all sessions.
        AC-004: Lifetime playtime equals sum of all sessions.
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(duration_seconds), 0) FROM sessions;")
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_total_seconds_for_date(self, target_date: date) -> int:
        """
        Return total playtime in seconds for a specific calendar date.
        AC-005: Today's playtime.
        """
        day_start = datetime.combine(target_date, datetime.min.time()).isoformat()
        day_end = datetime.combine(
            target_date + timedelta(days=1), datetime.min.time()
        ).isoformat()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0)
            FROM sessions
            WHERE start_time >= ? AND start_time < ?;
            """,
            (day_start, day_end),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_total_seconds_for_week(self, week_start: date) -> int:
        """
        Return total playtime in seconds for the 7-day week starting on week_start.
        AC-006: Weekly totals.
        """
        start = datetime.combine(week_start, datetime.min.time()).isoformat()
        end = datetime.combine(
            week_start + timedelta(days=7), datetime.min.time()
        ).isoformat()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0)
            FROM sessions
            WHERE start_time >= ? AND start_time < ?;
            """,
            (start, end),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_total_seconds_for_month(self, year: int, month: int) -> int:
        """
        Return total playtime in seconds for a calendar month.
        AC-007: Monthly totals.
        """
        from calendar import monthrange

        _, last_day = monthrange(year, month)
        start = datetime(year, month, 1).isoformat()
        # End = first moment of the next month
        if month == 12:
            end = datetime(year + 1, 1, 1).isoformat()
        else:
            end = datetime(year, month + 1, 1).isoformat()

        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0)
            FROM sessions
            WHERE start_time >= ? AND start_time < ?;
            """,
            (start, end),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_daily_totals_for_range(
        self, start_date: date, end_date: date
    ) -> dict[date, int]:
        """
        Return a mapping of {date: total_seconds} for every day in [start_date, end_date].
        Days with no sessions appear with value 0.
        Used to populate daily activity charts.
        """
        start = datetime.combine(start_date, datetime.min.time()).isoformat()
        end = datetime.combine(
            end_date + timedelta(days=1), datetime.min.time()
        ).isoformat()

        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT DATE(start_time) AS day, COALESCE(SUM(duration_seconds), 0) AS total
            FROM sessions
            WHERE start_time >= ? AND start_time < ?
            GROUP BY day
            ORDER BY day ASC;
            """,
            (start, end),
        )
        result: dict[date, int] = {}
        for row in cursor.fetchall():
            result[date.fromisoformat(row["day"])] = row["total"]

        # Fill in days with no sessions
        current = start_date
        while current <= end_date:
            result.setdefault(current, 0)
            current += timedelta(days=1)

        return dict(sorted(result.items()))

    def get_most_played_game_id(self) -> int | None:
        """
        Return the game_id of the game with the highest total playtime, or None.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT game_id
            FROM sessions
            GROUP BY game_id
            ORDER BY SUM(duration_seconds) DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        return row["game_id"] if row else None

    def get_longest_session(self) -> Session | None:
        """Return the single longest session ever recorded, or None."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions ORDER BY duration_seconds DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        return _row_to_session(row) if row else None

    def get_session_count_for_game(self, game_id: int) -> int:
        """Return the number of sessions recorded for a specific game."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sessions WHERE game_id = ?;", (game_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def count(self) -> int:
        """Return the total number of session rows."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions;")
        row = cursor.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, session_id: int) -> None:
        """Delete a session by its primary key."""
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = ?;", (session_id,))
        self._conn.commit()
        logger.info("Session deleted: id=%s", session_id)

    def delete_all_for_game(self, game_id: int) -> int:
        """Delete all sessions for a game. Returns number of rows deleted."""
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE game_id = ?;", (game_id,))
        self._conn.commit()
        deleted = cursor.rowcount
        logger.info("Deleted %s sessions for game_id=%s", deleted, game_id)
        return deleted