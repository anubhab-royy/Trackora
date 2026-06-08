# All SQL for `games` table

"""
GamesRepository for GameTracker.

All SQL operations for the `games` table live here and nowhere else.
The UI layer must never call this repository directly.

Rules from architecture.md / AGENTS.md:
    - No SQL outside repositories.
    - No business logic inside widgets.
    - Use type hints everywhere.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from database.models.game import Game

logger = logging.getLogger(__name__)


def _row_to_game(row: sqlite3.Row) -> Game:
    """Convert a sqlite3.Row from the games table into a Game dataclass."""
    return Game(
        id=row["id"],
        name=row["name"],
        process_name=row["process_name"],
        executable_path=row["executable_path"],
        icon_path=row["icon_path"] or "",
        is_enabled=bool(row["is_enabled"]),
        first_played=_parse_dt(row["first_played"]),
        last_played=_parse_dt(row["last_played"]),
        created_at=_parse_dt(row["created_at"]) or datetime.now(UTC).replace(tzinfo=None),
        updated_at=_parse_dt(row["updated_at"]) or datetime.now(UTC).replace(tzinfo=None),
    )


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-format datetime string from SQLite, or return None."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _dt_str(dt: datetime | None) -> str | None:
    """Serialize a datetime to ISO string, or return None."""
    return dt.isoformat() if dt is not None else None


class GamesRepository:
    """
    CRUD operations for the `games` table.

    Args:
        connection: An open sqlite3.Connection provided by DatabaseManager.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(self, game: Game) -> Game:
        """
        Insert a new game row.

        Returns:
            The same Game with its `id` field populated.

        Raises:
            ValueError: If a game with the same executable_path already exists.
        """
        now = datetime.now(UTC).replace(tzinfo=None)
        game.created_at = now
        game.updated_at = now

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO games
                (name, process_name, executable_path, icon_path,
                 is_enabled, first_played, last_played, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game.name,
                game.process_name,
                game.executable_path,
                game.icon_path,
                1 if game.is_enabled else 0,
                _dt_str(game.first_played),
                _dt_str(game.last_played),
                _dt_str(game.created_at),
                _dt_str(game.updated_at),
            ),
        )
        self._conn.commit()
        game.id = cursor.lastrowid
        logger.info("Game added: id=%s name=%r", game.id, game.name)
        return game

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_id(self, game_id: int) -> Game | None:
        """Return the Game with the given primary key, or None if not found."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM games WHERE id = ?;", (game_id,))
        row = cursor.fetchone()
        return _row_to_game(row) if row else None

    def get_by_process_name(self, process_name: str) -> Game | None:
        """
        Return the enabled Game whose process_name matches (case-insensitive).
        Used by the process monitor to identify running games.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM games WHERE LOWER(process_name) = LOWER(?) AND is_enabled = 1;",
            (process_name,),
        )
        row = cursor.fetchone()
        return _row_to_game(row) if row else None

    def get_all(self) -> list[Game]:
        """Return all games ordered by name."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM games ORDER BY name COLLATE NOCASE ASC;")
        return [_row_to_game(row) for row in cursor.fetchall()]

    def get_all_enabled(self) -> list[Game]:
        """Return only games with is_enabled = 1, ordered by name."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM games WHERE is_enabled = 1 ORDER BY name COLLATE NOCASE ASC;"
        )
        return [_row_to_game(row) for row in cursor.fetchall()]

    def exists_by_executable_path(self, executable_path: str) -> bool:
        """
        Check whether a game with this executable path already exists.
        Used to prevent duplicates (AC-001).
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT 1 FROM games WHERE executable_path = ? LIMIT 1;",
            (executable_path,),
        )
        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, game: Game) -> None:
        """
        Persist changes to an existing game row.

        Raises:
            ValueError: If game.id is None (game has not been persisted yet).
        """
        if game.id is None:
            raise ValueError("Cannot update a Game that has no id.")

        game.updated_at = datetime.now(UTC).replace(tzinfo=None)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE games
            SET name             = ?,
                process_name     = ?,
                executable_path  = ?,
                icon_path        = ?,
                is_enabled       = ?,
                first_played     = ?,
                last_played      = ?,
                updated_at       = ?
            WHERE id = ?;
            """,
            (
                game.name,
                game.process_name,
                game.executable_path,
                game.icon_path,
                1 if game.is_enabled else 0,
                _dt_str(game.first_played),
                _dt_str(game.last_played),
                _dt_str(game.updated_at),
                game.id,
            ),
        )
        self._conn.commit()
        logger.info("Game updated: id=%s name=%r", game.id, game.name)

    def update_last_played(self, game_id: int, timestamp: datetime) -> None:
        """
        Update only first_played (if unset) and last_played for a game.
        Called by the session manager when a session starts/ends.
        """
        cursor = self._conn.cursor()
        # Set first_played only if it has never been set
        cursor.execute(
            """
            UPDATE games
            SET first_played = CASE WHEN first_played IS NULL THEN ? ELSE first_played END,
                last_played  = ?,
                updated_at   = ?
            WHERE id = ?;
            """,
            (
                _dt_str(timestamp),
                _dt_str(timestamp),
                _dt_str(datetime.now(UTC).replace(tzinfo=None)),
                game_id,
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Enable / Disable  (added Phase 5)
    # ------------------------------------------------------------------

    def set_enabled(self, game_id: int, enabled: bool) -> None:
        """
        Set the is_enabled flag for a game.

        Args:
            game_id: Primary key of the game to update.
            enabled: True to enable tracking, False to disable.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE games
            SET is_enabled = ?,
                updated_at = ?
            WHERE id = ?;
            """,
            (
                1 if enabled else 0,
                datetime.now(UTC).replace(tzinfo=None).isoformat(),
                game_id,
            ),
        )
        self._conn.commit()
        logger.info(
            "Game id=%s tracking %s",
            game_id,
            "enabled" if enabled else "disabled",
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, game_id: int) -> None:
        """
        Delete a game by its primary key.

        Note: sessions belonging to this game will remain in the database
        (no CASCADE DELETE) to preserve historical data. The UI layer is
        responsible for prompting the user about this.
        """
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM games WHERE id = ?;", (game_id,))
        self._conn.commit()
        logger.info("Game deleted: id=%s", game_id)

    def count(self) -> int:
        """Return the total number of games in the table."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games;")
        row = cursor.fetchone()
        return row[0] if row else 0