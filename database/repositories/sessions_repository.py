# All SQL for `sessions` + stats queries

"""
SessionsRepository for Trackora.

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
from datetime import UTC, datetime, date, timedelta

from database.models import Session, SessionView

logger = logging.getLogger(__name__)


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        game_id=row["game_id"],
        start_time=datetime.fromisoformat(row["start_time"]),
        end_time=datetime.fromisoformat(row["end_time"]),
        duration_seconds=row["duration_seconds"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_session_view(row: sqlite3.Row) -> SessionView:
    return SessionView(
        id=row["id"],
        game_id=row["game_id"],
        game_name=row["game_name"],
        start_time=datetime.fromisoformat(row["start_time"]),
        end_time=datetime.fromisoformat(row["end_time"]),
        duration_seconds=row["duration_seconds"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _dt_str(dt: datetime) -> str:
    return dt.isoformat()


class SessionsRepository:

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(self, session: Session) -> Session:
        now = datetime.now(UTC).replace(tzinfo=None)
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
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE id = ?;", (session_id,))
        row = cursor.fetchone()
        return _row_to_session(row) if row else None

    def get_all_for_game(self, game_id: int) -> list[Session]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE game_id = ? ORDER BY start_time DESC;",
            (game_id,),
        )
        return [_row_to_session(r) for r in cursor.fetchall()]

    def get_by_date_range(
        self, start_date: date, end_date: date
    ) -> list[Session]:
        start = datetime.combine(start_date, datetime.min.time()).isoformat()
        end = datetime.combine(
            end_date + timedelta(days=1), datetime.min.time()
        ).isoformat()
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE start_time >= ? AND start_time < ? ORDER BY start_time ASC;",
            (start, end),
        )
        return [_row_to_session(r) for r in cursor.fetchall()]

    def get_all(self, limit: int | None = None) -> list[Session]:
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
    # Query — search / filter / sort / paginate (Phase 7)
    # ------------------------------------------------------------------

    def query_sessions(
        self,
        *,
        search_text: str = "",
        game_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        min_duration: int | None = None,
        max_duration: int | None = None,
        sort_by: str = "start_time",
        sort_order: str = "DESC",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[SessionView]]:
        """
        Query sessions with full search, filter, sort, and pagination.

        Returns:
            (total_count, list of SessionView) — total_count is the number of
            matching rows *before* LIMIT/OFFSET is applied.

        Accepted sort_by values: start_time, end_time, duration_seconds, game_name.
        sort_order: ASC or DESC (case-insensitive).
        """
        allowed_sort = {"start_time", "end_time", "duration_seconds", "game_name"}
        if sort_by not in allowed_sort:
            sort_by = "start_time"

        sort_dir = "ASC" if sort_order.upper() == "ASC" else "DESC"

        where_clauses: list[str] = []
        params: list[object] = []

        if search_text:
            where_clauses.append("g.name LIKE ?")
            params.append(f"%{search_text}%")

        if game_id is not None:
            where_clauses.append("s.game_id = ?")
            params.append(game_id)

        if date_from is not None:
            where_clauses.append("s.start_time >= ?")
            params.append(datetime.combine(date_from, datetime.min.time()).isoformat())

        if date_to is not None:
            end_dt = datetime.combine(
                date_to + timedelta(days=1), datetime.min.time()
            )
            where_clauses.append("s.start_time < ?")
            params.append(end_dt.isoformat())

        if min_duration is not None:
            where_clauses.append("s.duration_seconds >= ?")
            params.append(min_duration)

        if max_duration is not None:
            where_clauses.append("s.duration_seconds <= ?")
            params.append(max_duration)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        sort_expr = "g.name" if sort_by == "game_name" else f"s.{sort_by}"

        count_sql = (
            f"SELECT COUNT(*) FROM sessions s "
            f"JOIN games g ON s.game_id = g.id WHERE {where_sql};"
        )

        data_sql = (
            f"SELECT s.*, g.name AS game_name "
            f"FROM sessions s "
            f"JOIN games g ON s.game_id = g.id "
            f"WHERE {where_sql} "
            f"ORDER BY {sort_expr} {sort_dir} "
            f"LIMIT ? OFFSET ?;"
        )

        cursor = self._conn.cursor()
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0]

        cursor.execute(data_sql, params + [limit, offset])
        results = [_row_to_session_view(r) for r in cursor.fetchall()]

        return total, results

    # ------------------------------------------------------------------
    # Read — statistics (AC-004 through AC-007)
    # ------------------------------------------------------------------

    def get_total_seconds_for_game(self, game_id: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM sessions WHERE game_id = ?;",
            (game_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_lifetime_total_seconds(self) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(duration_seconds), 0) FROM sessions;")
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_total_seconds_for_date(self, target_date: date) -> int:
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
        from calendar import monthrange

        _, last_day = monthrange(year, month)
        start = datetime(year, month, 1).isoformat()
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

        current = start_date
        while current <= end_date:
            result.setdefault(current, 0)
            current += timedelta(days=1)

        return dict(sorted(result.items()))

    def get_most_played_game_id(self) -> int | None:
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
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions ORDER BY duration_seconds DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        return _row_to_session(row) if row else None

    def get_session_count_for_game(self, game_id: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sessions WHERE game_id = ?;", (game_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def count(self) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions;")
        row = cursor.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, session_id: int) -> None:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = ?;", (session_id,))
        self._conn.commit()
        logger.info("Session deleted: id=%s", session_id)

    def delete_all_for_game(self, game_id: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE game_id = ?;", (game_id,))
        self._conn.commit()
        deleted = cursor.rowcount
        logger.info("Deleted %s sessions for game_id=%s", deleted, game_id)
        return deleted
