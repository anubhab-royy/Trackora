"""
Tests for ExportService — Phase 9.

Covers:
  - CSV export: file creation, format, empty data, repo error
  - JSON backup: file creation, structure, empty data, repo error
  - Uses in-memory SQLite (real repos) for data-fidelity tests
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from database.repositories.games_repository import GamesRepository
from database.repositories.sessions_repository import SessionsRepository
from database.repositories.settings_repository import SettingsRepository
from services.export_service import ExportService

# ---------------------------------------------------------------------------
# In-memory schema (mirrors production schema from database_schema.md)
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

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def db_connection() -> Generator[sqlite3.Connection, None, None]:
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
def sessions_repo(
    db_connection: sqlite3.Connection,
) -> SessionsRepository:
    return SessionsRepository(db_connection)


@pytest.fixture
def settings_repo(
    db_connection: sqlite3.Connection,
) -> SettingsRepository:
    return SettingsRepository(db_connection)


@pytest.fixture
def service(
    sessions_repo: SessionsRepository,
    games_repo: GamesRepository,
    settings_repo: SettingsRepository,
) -> ExportService:
    return ExportService(
        sessions_repository=sessions_repo,
        games_repository=games_repo,
        settings_repository=settings_repo,
    )


def _insert_game(
    conn: sqlite3.Connection, name: str = "TestGame"
) -> int:
    cursor = conn.execute(
        "INSERT INTO games (name, process_name, executable_path) VALUES (?, ?, ?)",
        (name, f"{name.lower()}.exe", f"/usr/games/{name}"),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_session(
    conn: sqlite3.Connection,
    game_id: int,
    start_time: datetime,
    duration_seconds: int,
) -> int:
    end_time = start_time + timedelta(seconds=duration_seconds)
    cursor = conn.execute(
        "INSERT INTO sessions (game_id, start_time, end_time, duration_seconds) VALUES (?, ?, ?, ?)",
        (game_id, start_time.isoformat(), end_time.isoformat(), duration_seconds),
    )
    conn.commit()
    return cursor.lastrowid


# ===========================================================================
# CSV Export tests
# ===========================================================================


class TestExportServiceCSV:
    def test_export_csv_creates_file(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        gid = _insert_game(db_connection, "Witcher 3")
        _insert_session(
            db_connection,
            gid,
            datetime(2024, 6, 1, 10, 0),
            7200,  # 2 hours
        )
        out = tmp_path / "sessions.csv"
        result = service.export_csv(str(out))
        assert result is True
        assert out.exists()

    def test_export_csv_format(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        gid = _insert_game(db_connection, "Witcher 3")
        _insert_session(
            db_connection,
            gid,
            datetime(2024, 6, 1, 10, 0),
            7200,
        )
        out = tmp_path / "sessions.csv"
        service.export_csv(str(out))

        with out.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 2  # header + data
        assert rows[0] == [
            "Date",
            "Game",
            "Duration (minutes)",
            "Start Time",
            "End Time",
        ]
        assert rows[1][0] == "2024-06-01"
        assert rows[1][1] == "Witcher 3"
        assert rows[1][3] == "10:00"
        assert rows[1][4] == "12:00"

    def test_export_csv_empty_sessions(
        self,
        service: ExportService,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "sessions.csv"
        result = service.export_csv(str(out))
        assert result is True
        with out.open(encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        # header only
        assert len(rows) == 1
        assert rows[0][0] == "Date"

    def test_export_csv_repo_error(self, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_repo.get_all.side_effect = RuntimeError("DB error")
        svc = ExportService(
            sessions_repository=mock_repo,
            games_repository=MagicMock(),
            settings_repository=MagicMock(),
        )
        out = tmp_path / "fail.csv"
        result = svc.export_csv(str(out))
        assert result is False
        assert not out.exists()

    def test_export_csv_multiple_games(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        gid1 = _insert_game(db_connection, "Witcher 3")
        gid2 = _insert_game(db_connection, "Hades")
        _insert_session(db_connection, gid1, datetime(2024, 6, 1, 10, 0), 3600)
        _insert_session(db_connection, gid2, datetime(2024, 6, 2, 14, 30), 1800)

        out = tmp_path / "sessions.csv"
        service.export_csv(str(out))
        with out.open(encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))

        # get_all() returns sessions ordered by start_time DESC
        assert len(rows) == 3
        assert rows[1][1] == "Hades"   # newer session first
        assert rows[2][1] == "Witcher 3"

    def test_export_csv_path_object(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        gid = _insert_game(db_connection, "Game")
        _insert_session(db_connection, gid, datetime(2024, 6, 1, 10, 0), 600)
        out = tmp_path / "sessions.csv"
        result = service.export_csv(out)  # Path, not str
        assert result is True
        assert out.exists()


# ===========================================================================
# JSON Backup tests
# ===========================================================================


class TestExportServiceJSON:
    def test_export_backup_creates_file(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        gid = _insert_game(db_connection, "Witcher 3")
        _insert_session(db_connection, gid, datetime(2024, 6, 1, 10, 0), 3600)
        out = tmp_path / "backup.json"
        result = service.export_backup(str(out))
        assert result is True
        assert out.exists()

    def test_export_backup_structure(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        gid = _insert_game(db_connection, "Witcher 3")
        _insert_session(db_connection, gid, datetime(2024, 6, 1, 10, 0), 3600)
        out = tmp_path / "backup.json"
        service.export_backup(str(out))

        with out.open(encoding="utf-8") as f:
            data = json.load(f)

        assert "version" in data
        assert "exported_at" in data
        assert "games" in data
        assert "sessions" in data
        assert "settings" in data
        assert data["version"] == "1.0"

    def test_export_backup_game_data(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        gid = _insert_game(db_connection, "Witcher 3")
        _insert_session(db_connection, gid, datetime(2024, 6, 1, 10, 0), 3600)
        out = tmp_path / "backup.json"
        service.export_backup(str(out))

        with out.open(encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["games"]) == 1
        assert data["games"][0]["name"] == "Witcher 3"
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["game_id"] == gid
        assert data["sessions"][0]["duration_seconds"] == 3600

    def test_export_backup_includes_settings(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        db_connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ("theme", "dark"),
        )
        db_connection.commit()

        out = tmp_path / "backup.json"
        service.export_backup(str(out))

        with out.open(encoding="utf-8") as f:
            data = json.load(f)

        settings_map = {s["key"]: s["value"] for s in data["settings"]}
        assert settings_map["theme"] == "dark"

    def test_export_backup_empty_data(
        self,
        service: ExportService,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "backup.json"
        result = service.export_backup(str(out))
        assert result is True

        with out.open(encoding="utf-8") as f:
            data = json.load(f)

        assert data["games"] == []
        assert data["sessions"] == []
        assert data["settings"] == []

    def test_export_backup_repo_error(self, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_repo.get_all.side_effect = RuntimeError("DB error")
        svc = ExportService(
            sessions_repository=mock_repo,
            games_repository=mock_repo,
            settings_repository=mock_repo,
        )
        out = tmp_path / "fail.json"
        result = svc.export_backup(str(out))
        assert result is False
        assert not out.exists()

    def test_export_backup_path_object(
        self,
        service: ExportService,
        db_connection: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        _insert_game(db_connection, "Game")
        out = tmp_path / "backup.json"
        result = service.export_backup(out)  # Path, not str
        assert result is True
        assert out.exists()
