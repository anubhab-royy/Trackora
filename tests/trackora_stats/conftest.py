"""
Shared fixtures for statistics tests.

Uses an in-memory SQLite database so tests are fully isolated and fast.
Repositories are constructed exactly as they would be in production —
the statistics layer never touches the database directly.
"""

import sqlite3
from datetime import datetime, timedelta, date
from typing import Generator

import pytest

from database.database_manager import DatabaseManager
from database.repositories.games_repository import GamesRepository
from database.repositories.sessions_repository import SessionsRepository
from trackora_stats.playtime_calculator import PlaytimeCalculator
from trackora_stats.statistics_service import StatisticsService
from trackora_stats.trend_analyzer import TrendAnalyzer


# ---------------------------------------------------------------------------
# Minimal in-memory schema (mirrors database_schema.md exactly)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS games (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL,
    process_name       TEXT    NOT NULL,
    executable_path    TEXT    NOT NULL DEFAULT '',
    icon_path          TEXT             DEFAULT NULL,
    is_enabled         INTEGER NOT NULL DEFAULT 1,
    platform           TEXT             DEFAULT NULL,
    platform_id        TEXT             DEFAULT NULL,
    is_auto_discovered INTEGER NOT NULL DEFAULT 0,
    first_played       DATETIME         DEFAULT NULL,
    last_played        DATETIME         DEFAULT NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id          INTEGER NOT NULL REFERENCES games(id),
    start_time       DATETIME NOT NULL,
    end_time         DATETIME NOT NULL,
    duration_seconds INTEGER  NOT NULL DEFAULT 0,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS active_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    process_id  INTEGER NOT NULL,
    start_time  DATETIME NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

"""


@pytest.fixture
def db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Provide a fresh in-memory SQLite connection per test."""
    conn = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def games_repo(db_connection: sqlite3.Connection) -> GamesRepository:
    return GamesRepository(db_connection)


@pytest.fixture
def sessions_repo(db_connection: sqlite3.Connection) -> SessionsRepository:
    return SessionsRepository(db_connection)


@pytest.fixture
def calculator(
    sessions_repo: SessionsRepository,
    games_repo: GamesRepository,
) -> PlaytimeCalculator:
    return PlaytimeCalculator(
        sessions_repository=sessions_repo,
        games_repository=games_repo,
    )


@pytest.fixture
def trend_analyzer(calculator: PlaytimeCalculator) -> TrendAnalyzer:
    return TrendAnalyzer(calculator=calculator)


@pytest.fixture
def statistics_service(
    sessions_repo: SessionsRepository,
    games_repo: GamesRepository,
) -> StatisticsService:
    return StatisticsService(
        sessions_repository=sessions_repo,
        games_repository=games_repo,
    )


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def insert_game(conn: sqlite3.Connection, name: str = "TestGame") -> int:
    """Insert a minimal game row and return its id."""
    cursor = conn.execute(
        "INSERT INTO games (name, process_name, executable_path) VALUES (?, ?, ?)",
        (name, f"{name.lower()}.exe", f"C:\\Games\\{name}\\{name}.exe"),
    )
    conn.commit()
    return cursor.lastrowid


def insert_session(
    conn: sqlite3.Connection,
    game_id: int,
    start_time: datetime,
    duration_seconds: int,
) -> int:
    """Insert a completed session row and return its id."""
    end_time = start_time + timedelta(seconds=duration_seconds)
    cursor = conn.execute(
        """
        INSERT INTO sessions (game_id, start_time, end_time, duration_seconds)
        VALUES (?, ?, ?, ?)
        """,
        (
            game_id,
            start_time.isoformat(),
            end_time.isoformat(),
            duration_seconds,
        ),
    )
    conn.commit()
    return cursor.lastrowid