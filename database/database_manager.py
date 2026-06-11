# Core: opens DB, applies PRAGMAs, creates schema

"""
DatabaseManager for Trackora.

Responsibilities:
    - Open / create the SQLite database file.
    - Enable WAL mode for crash safety (tech_spec.md).
    - Enable foreign key enforcement.
    - Create all tables and indexes on first run.
    - Provide a single shared connection to repositories.
    - Close the connection cleanly on shutdown.

Design notes:
    - All SQL lives in the database layer only (architecture.md rule).
    - Database file path: database/tracker.db  (tech_spec.md)
    - Tables: games, sessions, active_sessions, settings, statistics_cache
    - Indexes defined in database_schema.md are created here.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Default location: <project_root>/database/tracker.db
_DEFAULT_DB_PATH = Path(__file__).parent / "tracker.db"


class DatabaseManager:
    """
    Manages the SQLite connection and schema lifecycle.

    Usage:
        db = DatabaseManager()
        db.initialize()
        conn = db.connection
        # ... pass conn to repositories ...
        db.close()

    Or as a context manager:
        with DatabaseManager() as db:
            conn = db.connection
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        """
        Args:
            db_path: Path to the SQLite file.
                     Defaults to database/tracker.db next to this module.
                     Pass ":memory:" for in-memory databases (useful in tests).
        """
        if db_path is None:
            self._db_path: Path | str = _DEFAULT_DB_PATH
        else:
            self._db_path = db_path

        self._connection: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Open the database, apply PRAGMA settings, and create schema.

        Safe to call multiple times — CREATE TABLE uses IF NOT EXISTS.
        """
        self._open_connection()
        self._apply_pragmas()
        self._create_schema()
        logger.info("DatabaseManager initialized. Path: %s", self._db_path)

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the active connection. Raises RuntimeError if not initialized."""
        if self._connection is None:
            raise RuntimeError(
                "DatabaseManager has not been initialized. Call initialize() first."
            )
        return self._connection

    def close(self) -> None:
        """Commit any pending work and close the connection."""
        if self._connection is not None:
            try:
                self._connection.commit()
                self._connection.close()
                logger.info("DatabaseManager connection closed.")
            except sqlite3.Error as exc:
                logger.error("Error closing database connection: %s", exc)
            finally:
                self._connection = None

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "DatabaseManager":
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        self.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _open_connection(self) -> None:
        """Create the database directory (if needed) and open the connection."""
        if isinstance(self._db_path, Path):
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(
            str(self._db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,
        )
        # Return rows as sqlite3.Row objects so columns are accessible by name.
        self._connection.row_factory = sqlite3.Row

    def _apply_pragmas(self) -> None:
        """
        Configure SQLite for reliability and performance.

        WAL mode:      Better crash safety; allows concurrent readers.
        Foreign keys:  Enforce referential integrity (sessions.game_id → games.id).
        """
        assert self._connection is not None
        cursor = self._connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA foreign_keys = ON;")
        self._connection.commit()
        logger.debug("PRAGMAs applied: WAL mode ON, foreign_keys ON.")

    def _create_schema(self) -> None:
        """Create all tables and indexes defined in database_schema.md."""
        assert self._connection is not None
        cursor = self._connection.cursor()

        # ------------------------------------------------------------------ #
        # Table: games                                                         #
        # ------------------------------------------------------------------ #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    NOT NULL,
                process_name     TEXT    NOT NULL,
                executable_path  TEXT    NOT NULL,
                icon_path        TEXT    NOT NULL DEFAULT '',
                is_enabled       INTEGER NOT NULL DEFAULT 1,
                first_played     DATETIME,
                last_played      DATETIME,
                created_at       DATETIME NOT NULL,
                updated_at       DATETIME NOT NULL
            );
        """)

        # ------------------------------------------------------------------ #
        # Table: sessions                                                       #
        # ------------------------------------------------------------------ #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id          INTEGER  NOT NULL,
                start_time       DATETIME NOT NULL,
                end_time         DATETIME NOT NULL,
                duration_seconds INTEGER  NOT NULL,
                created_at       DATETIME NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games (id)
            );
        """)

        # ------------------------------------------------------------------ #
        # Table: active_sessions  (crash / shutdown recovery)                 #
        # ------------------------------------------------------------------ #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id    INTEGER  NOT NULL,
                process_id INTEGER  NOT NULL,
                start_time DATETIME NOT NULL,
                created_at DATETIME NOT NULL
            );
        """)

        # ------------------------------------------------------------------ #
        # Table: settings                                                       #
        # ------------------------------------------------------------------ #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT     PRIMARY KEY,
                value      TEXT     NOT NULL DEFAULT '',
                updated_at DATETIME NOT NULL
            );
        """)

        # ------------------------------------------------------------------ #
        # Table: statistics_cache  (optional future optimisation)              #
        # ------------------------------------------------------------------ #
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistics_cache (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id       INTEGER NOT NULL,
                period_type   TEXT    NOT NULL,
                period_key    TEXT    NOT NULL,
                value_seconds INTEGER NOT NULL DEFAULT 0
            );
        """)

        # ------------------------------------------------------------------ #
        # Indexes (database_schema.md)                                         #
        # ------------------------------------------------------------------ #
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_process_name
            ON games (process_name);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_game_id
            ON sessions (game_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_start_time
            ON sessions (start_time);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_end_time
            ON sessions (end_time);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_active_sessions_game_id
            ON active_sessions (game_id);
        """)

        self._connection.commit()
        logger.debug("Database schema created / verified successfully.")