"""
Tests for DeleteGameService — Phase 14
Covers:
  - Deleting games with active sessions.
  - Deleting games with completed sessions.
  - Deleting games with multiple dependent records.
  - Foreign key integrity.
  - Transaction rollback during cleanup errors.
  - Empty cleanup (games without any history).
  - T-222 Statistics cleanup, observer callbacks, and recalculations.
  - T-223 Filesystem cache cleanup, read-only handling, and outside-app safety guards.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from database.models import Game
from database.models import ActiveSession as DbActiveSession
from database.models import Session as DbSession
from database.repositories.games_repository import GamesRepository
from database.repositories.active_sessions_repository import ActiveSessionsRepository
from database.repositories.sessions_repository import SessionsRepository
from services.delete_game_service import DeleteGameService
from services.delete_game_result import DeleteGameResult
from services.cache_cleanup_service import CacheCleanupService
from trackora_stats.statistics_service import StatisticsService
from tracker.tracking_state import TrackingState, TrackedGame, ActiveSession


# ---------------------------------------------------------------------------
# Connection and Cursor Proxies to bypass C-extension read-only limitations
# ---------------------------------------------------------------------------

class CursorProxy:
    def __init__(self, cursor: sqlite3.Cursor, fail_on_delete: bool = False) -> None:
        self._cursor = cursor
        self._fail_on_delete = fail_on_delete

    def execute(self, sql: str, *args: tuple) -> sqlite3.Cursor:
        if self._fail_on_delete and "DELETE FROM games" in sql:
            raise sqlite3.DatabaseError("Disk full or simulated failure")
        return self._cursor.execute(sql, *args)

    def fetchone(self) -> sqlite3.Row | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[sqlite3.Row]:
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid


class ConnectionProxy:
    def __init__(
        self,
        conn: sqlite3.Connection,
        fail_on_delete: bool = False,
        fail_on_execute: bool = False,
    ) -> None:
        self._conn = conn
        self._fail_on_delete = fail_on_delete
        self._fail_on_execute = fail_on_execute
        self.executed_commands: list[str] = []

    def cursor(self, *args: tuple, **kwargs: dict) -> CursorProxy:
        return CursorProxy(self._conn.cursor(*args, **kwargs), fail_on_delete=self._fail_on_delete)

    def execute(self, sql: str, *args: tuple) -> sqlite3.Cursor:
        self.executed_commands.append(sql)
        if self._fail_on_execute:
            raise RuntimeError("Unexpected crash")
        return self._conn.execute(sql, *args)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()


# ---------------------------------------------------------------------------
# Dummy DatabaseManager for injection
# ---------------------------------------------------------------------------

class DummyDatabaseManager:
    def __init__(self, conn: sqlite3.Connection, lock: Optional[threading.Lock] = None) -> None:
        self.connection = conn
        self.lock = lock or threading.Lock()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_conn() -> sqlite3.Connection:
    """Provides an in-memory SQLite database with schema required for tests."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("""
        CREATE TABLE games (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT    NOT NULL,
            process_name       TEXT    NOT NULL,
            executable_path    TEXT    NOT NULL,
            icon_path          TEXT    NOT NULL DEFAULT '',
            is_enabled         INTEGER NOT NULL DEFAULT 1,
            platform           TEXT    DEFAULT NULL,
            platform_id        TEXT    DEFAULT NULL,
            is_auto_discovered INTEGER NOT NULL DEFAULT 0,
            first_played       DATETIME,
            last_played        DATETIME,
            created_at         DATETIME NOT NULL,
            updated_at         DATETIME NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE active_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id    INTEGER  NOT NULL,
            process_id INTEGER  NOT NULL,
            start_time DATETIME NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games (id)
        );
    """)
    cursor.execute("""
        CREATE TABLE sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id          INTEGER  NOT NULL,
            start_time       DATETIME NOT NULL,
            end_time         DATETIME NOT NULL,
            duration_seconds INTEGER  NOT NULL,
            created_at       DATETIME NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games (id)
        );
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def games_repo(db_conn: sqlite3.Connection) -> GamesRepository:
    return GamesRepository(db_conn)


@pytest.fixture()
def active_sessions_repo(db_conn: sqlite3.Connection) -> ActiveSessionsRepository:
    return ActiveSessionsRepository(db_conn)


@pytest.fixture()
def sessions_repo(db_conn: sqlite3.Connection) -> SessionsRepository:
    return SessionsRepository(db_conn)


@pytest.fixture()
def tracking_state() -> TrackingState:
    return TrackingState()


@pytest.fixture()
def statistics_service(
    sessions_repo: SessionsRepository,
    games_repo: GamesRepository,
) -> StatisticsService:
    return StatisticsService(sessions_repo, games_repo)


@pytest.fixture()
def cache_cleanup_service(tmp_path: Path) -> CacheCleanupService:
    cache_dir = tmp_path / "cache"
    base_dir = tmp_path
    cache_dir.mkdir(exist_ok=True)
    return CacheCleanupService(cache_dir=cache_dir, base_dir=base_dir)


@pytest.fixture()
def delete_service(
    games_repo: GamesRepository,
    active_sessions_repo: ActiveSessionsRepository,
    sessions_repo: SessionsRepository,
    db_conn: sqlite3.Connection,
    tracking_state: TrackingState,
    statistics_service: StatisticsService,
    cache_cleanup_service: CacheCleanupService,
) -> DeleteGameService:
    db_mgr = DummyDatabaseManager(db_conn)
    return DeleteGameService(
        games_repo=games_repo,
        active_sessions_repo=active_sessions_repo,
        sessions_repo=sessions_repo,
        db_manager=db_mgr,  # type: ignore
        tracking_state=tracking_state,
        statistics_service=statistics_service,
        cache_cleanup_service=cache_cleanup_service,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _add_test_game(repo: GamesRepository, name: str = "Hades", icon_path: str = "") -> Game:
    game = Game(
        name=name,
        process_name="hades.exe",
        executable_path=r"C:\Games\hades.exe",
        icon_path=icon_path,
        is_enabled=True,
    )
    return repo.add(game)


# ===========================================================================
# Tests
# ===========================================================================

class TestDeleteGameService:

    def test_valid_deletion_workflow_empty_history(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        tracking_state: TrackingState,
    ) -> None:
        """Verifies full valid deletion workflow for a game with no history."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        # Add to tracking state
        tracked = TrackedGame(
            game_id=game.id,
            name=game.name,
            process_name=game.process_name,
            is_enabled=True,
        )
        tracking_state.add_tracked_game(tracked)
        assert game.id in tracking_state.tracked_games

        result = delete_service.delete_game(game_id=game.id)

        assert result.success is True
        assert result.game_id == game.id
        assert result.game_name == "Hades"
        assert result.error_message is None
        assert result.duration_ms > 0.0
        assert "deleted successfully" in result.message

        # Assert removed from DB
        assert games_repo.get_by_id(game.id) is None

        # Assert removed from tracking state
        assert game.id not in tracking_state.tracked_games

        # Assert lock is released (we can acquire it)
        assert delete_service._deletion_lock.acquire(blocking=False)
        delete_service._deletion_lock.release()

    def test_delete_game_with_active_sessions(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        active_sessions_repo: ActiveSessionsRepository,
        db_conn: sqlite3.Connection,
    ) -> None:
        """Verifies deletion cleans up active sessions cleanly when they are not currently running."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        # Add active session in DB (e.g. from an old orphaned state, but not actively tracked in memory)
        active_session = active_sessions_repo.start_session(
            DbActiveSession(
                game_id=game.id,
                process_id=9876,
                start_time=datetime.now(),
            )
        )
        assert active_session.id is not None
        assert active_sessions_repo.has_active_session(game.id) is True

        result = delete_service.delete_game(game_id=game.id)

        assert result.success is True
        assert games_repo.get_by_id(game.id) is None
        assert active_sessions_repo.has_active_session(game.id) is False

    def test_delete_game_with_completed_sessions(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        sessions_repo: SessionsRepository,
    ) -> None:
        """Verifies deletion cleans up completed session history associated with the game."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        # Add completed sessions
        session1 = sessions_repo.add(
            DbSession(
                game_id=game.id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=300,
            )
        )
        session2 = sessions_repo.add(
            DbSession(
                game_id=game.id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=600,
            )
        )
        assert len(sessions_repo.get_all_for_game(game.id)) == 2

        result = delete_service.delete_game(game_id=game.id)

        assert result.success is True
        assert games_repo.get_by_id(game.id) is None
        assert len(sessions_repo.get_all_for_game(game.id)) == 0

    def test_delete_game_with_multiple_dependent_records(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        sessions_repo: SessionsRepository,
        active_sessions_repo: ActiveSessionsRepository,
    ) -> None:
        """Verifies deletion cleans up both active and completed sessions in one go."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        active_sessions_repo.start_session(
            DbActiveSession(
                game_id=game.id,
                process_id=5555,
                start_time=datetime.now(),
            )
        )
        sessions_repo.add(
            DbSession(
                game_id=game.id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=1200,
            )
        )

        assert active_sessions_repo.has_active_session(game.id) is True
        assert len(sessions_repo.get_all_for_game(game.id)) == 1

        result = delete_service.delete_game(game_id=game.id)

        assert result.success is True
        assert games_repo.get_by_id(game.id) is None
        assert active_sessions_repo.has_active_session(game.id) is False
        assert len(sessions_repo.get_all_for_game(game.id)) == 0

    def test_foreign_key_integrity_order(
        self,
        games_repo: GamesRepository,
        sessions_repo: SessionsRepository,
        db_conn: sqlite3.Connection,
    ) -> None:
        """Verifies that direct game deletion raises IntegrityError due to foreign keys."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        sessions_repo.add(
            DbSession(
                game_id=game.id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=150,
            )
        )

        # Deleting the game directly from DB without deleting the session first must raise an IntegrityError
        # because foreign key constraints are active.
        with pytest.raises(sqlite3.IntegrityError):
            cursor = db_conn.cursor()
            cursor.execute("DELETE FROM games WHERE id = ?;", (game.id,))
            db_conn.commit()

    def test_invalid_game_id(self, delete_service: DeleteGameService) -> None:
        """Verifies rejection of invalid game IDs (e.g. non-integer, <= 0)."""
        # Test negative ID
        result = delete_service.delete_game(-5)
        assert result.success is False
        assert "Invalid Game ID" in result.error_message

        # Test non-integer ID
        result = delete_service.delete_game("not-an-int")  # type: ignore
        assert result.success is False
        assert "Invalid Game ID" in result.error_message

    def test_game_not_found(self, delete_service: DeleteGameService) -> None:
        """Verifies failure when attempting to delete a nonexistent game."""
        result = delete_service.delete_game(9999)
        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_game_currently_active_check(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        tracking_state: TrackingState,
    ) -> None:
        """Verifies validation blocks deletion if game is currently active in memory."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        # Start active session in tracking state (live tracking)
        tracking_state.active_sessions[game.id] = ActiveSession(
            active_session_id=1,
            game_id=game.id,
            game_name=game.name,
            process_id=1234,
            start_time=datetime.now(),
        )

        result = delete_service.delete_game(game.id)

        assert result.success is False
        assert "currently active/running" in result.error_message
        assert games_repo.get_by_id(game.id) is not None

    def test_double_deletion_prevention(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
    ) -> None:
        """Verifies double-click or parallel delete requests are blocked."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        # Manually hold the deletion lock to simulate a deletion already running
        delete_service._deletion_lock.acquire()

        result = delete_service.delete_game(game.id)

        assert result.success is False
        assert "already in progress" in result.error_message

        # Release lock and ensure game was not deleted
        delete_service._deletion_lock.release()
        assert games_repo.get_by_id(game.id) is not None

    def test_transaction_rollback_during_cleanup_error(
        self,
        games_repo: GamesRepository,
        sessions_repo: SessionsRepository,
        active_sessions_repo: ActiveSessionsRepository,
        db_conn: sqlite3.Connection,
        tracking_state: TrackingState,
    ) -> None:
        """Verifies database transaction rolls back if deletion fails mid-way."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        active_sessions_repo.start_session(
            DbActiveSession(
                game_id=game.id,
                process_id=5555,
                start_time=datetime.now(),
            )
        )
        sessions_repo.add(
            DbSession(
                game_id=game.id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=1200,
            )
        )

        # Setup Connection Proxy configured to raise error on DELETE execution from games table
        proxy_conn = ConnectionProxy(db_conn, fail_on_delete=True)
        db_mgr = DummyDatabaseManager(proxy_conn)  # type: ignore

        proxy_games_repo = GamesRepository(proxy_conn)  # type: ignore
        proxy_sessions_repo = SessionsRepository(proxy_conn)  # type: ignore
        proxy_active_sessions_repo = ActiveSessionsRepository(proxy_conn)  # type: ignore

        service = DeleteGameService(
            games_repo=proxy_games_repo,
            active_sessions_repo=proxy_active_sessions_repo,
            sessions_repo=proxy_sessions_repo,
            db_manager=db_mgr,  # type: ignore
            tracking_state=tracking_state,
        )

        result = service.delete_game(game.id)

        assert result.success is False
        assert "Database transaction failed" in result.error_message

        # Verify rollback: game is still in the DB, and dependent records remain
        assert games_repo.get_by_id(game.id) is not None
        assert active_sessions_repo.has_active_session(game.id) is True
        assert len(sessions_repo.get_all_for_game(game.id)) == 1

        # Verify the lock is released
        assert service._deletion_lock.acquire(blocking=False)
        service._deletion_lock.release()

    def test_lock_release_on_unexpected_exception(
        self,
        games_repo: GamesRepository,
        active_sessions_repo: ActiveSessionsRepository,
        sessions_repo: SessionsRepository,
        db_conn: sqlite3.Connection,
        tracking_state: TrackingState,
    ) -> None:
        """Verifies that the deletion lock is safely released even if an unexpected exception occurs."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        # Setup Connection Proxy configured to raise error on execute (e.g. at BEGIN)
        proxy_conn = ConnectionProxy(db_conn, fail_on_execute=True)
        db_mgr = DummyDatabaseManager(proxy_conn)  # type: ignore

        service = DeleteGameService(
            games_repo=games_repo,
            active_sessions_repo=active_sessions_repo,
            sessions_repo=sessions_repo,
            db_manager=db_mgr,  # type: ignore
            tracking_state=tracking_state,
        )

        result = service.delete_game(game.id)

        assert result.success is False
        assert "Unexpected crash" in result.error_message

        # Verify lock is released
        assert service._deletion_lock.acquire(blocking=False)
        service._deletion_lock.release()

    def test_service_architecture_constraints(
        self,
        games_repo: GamesRepository,
        active_sessions_repo: ActiveSessionsRepository,
        sessions_repo: SessionsRepository,
        db_conn: sqlite3.Connection,
        tracking_state: TrackingState,
    ) -> None:
        """Verifies architecture: service layer manages transaction boundaries."""
        game = _add_test_game(games_repo)
        assert game.id is not None

        proxy_conn = ConnectionProxy(db_conn)
        db_mgr = DummyDatabaseManager(proxy_conn)  # type: ignore

        service = DeleteGameService(
            games_repo=games_repo,
            active_sessions_repo=active_sessions_repo,
            sessions_repo=sessions_repo,
            db_manager=db_mgr,  # type: ignore
            tracking_state=tracking_state,
        )

        result = service.delete_game(game.id)
        assert result.success is True

        # Check transaction commands were invoked on connection
        assert "BEGIN;" in proxy_conn.executed_commands
        assert "COMMIT;" in proxy_conn.executed_commands

    def test_statistics_cleanup_and_observer_callback(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        sessions_repo: SessionsRepository,
        statistics_service: StatisticsService,
    ) -> None:
        """Verifies that statistics recalculations and registered callbacks are executed upon deletion."""
        game_deleted = _add_test_game(games_repo, name="Deleted Game")
        game_kept = _add_test_game(games_repo, name="Kept Game")
        assert game_deleted.id is not None
        assert game_kept.id is not None

        sessions_repo.add(
            DbSession(
                game_id=game_deleted.id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=3600,
            )
        )
        sessions_repo.add(
            DbSession(
                game_id=game_kept.id,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=1800,
            )
        )

        pre_lifetime = statistics_service.get_lifetime_stats()
        assert pre_lifetime.total_seconds == 5400
        assert pre_lifetime.total_games_played == 2
        assert pre_lifetime.most_played_game_name == "Deleted Game"

        callback_invoked = False

        def on_stats_refresh() -> None:
            nonlocal callback_invoked
            callback_invoked = True

        statistics_service.register_refresh_callback(on_stats_refresh)

        result = delete_service.delete_game(game_deleted.id)
        assert result.success is True
        assert callback_invoked is True

        post_lifetime = statistics_service.get_lifetime_stats()
        assert post_lifetime.total_seconds == 1800
        assert post_lifetime.total_games_played == 1
        assert post_lifetime.most_played_game_name == "Kept Game"

        summaries = statistics_service.get_game_playtime_summaries()
        assert len(summaries) == 1
        assert summaries[0].game_name == "Kept Game"

    def test_cache_cleanup_files_removed_and_missing_ignored(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        cache_cleanup_service: CacheCleanupService,
    ) -> None:
        """Verifies game-specific cache files and local icons are successfully deleted, and missing ones ignored."""
        # Create a mock icon path inside base app directory
        base = cache_cleanup_service._base_dir
        icon_path = base / "cached_icon_1.png"
        icon_path.write_text("dummy icon bytes")

        # Create a game-specific prefix file in cache directory
        cache = cache_cleanup_service._cache_dir
        cache_file = cache / "game_1_metadata.json"
        cache_file.write_text("dummy cache content")

        # Another file for a different game (should NOT be deleted)
        other_file = cache / "game_999_metadata.json"
        other_file.write_text("keep this")

        # Create game model pointing to the icon_path
        game = _add_test_game(games_repo, name="Hades", icon_path=str(icon_path))
        assert game.id is not None

        # Execute Deletion
        result = delete_service.delete_game(game.id)
        assert result.success is True

        # Assert files are deleted
        assert not icon_path.exists()
        assert not cache_file.exists()
        assert other_file.exists()  # Kept!

        # Delete again (or trigger cleanup with missing files) -> must ignore missing files gracefully
        cache_cleanup_service.cleanup_game_artifacts(game.id, "Hades", str(icon_path))

    def test_cache_cleanup_read_only_files(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        cache_cleanup_service: CacheCleanupService,
    ) -> None:
        """Verifies that the cleanup service handles read-only files by updating permissions first."""
        base = cache_cleanup_service._base_dir
        icon_path = base / "read_only_icon.png"
        icon_path.write_text("dummy bytes")

        # Set read-only permissions (0o444)
        os.chmod(icon_path, 0o444)

        game = _add_test_game(games_repo, name="Hades", icon_path=str(icon_path))
        assert game.id is not None

        result = delete_service.delete_game(game.id)
        assert result.success is True
        assert not icon_path.exists()

    def test_cache_cleanup_safety_check_guards_outside_files(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        cache_cleanup_service: CacheCleanupService,
        tmp_path: Path,
    ) -> None:
        """Verifies that the cleanup safety checks guard against deleting original/outside assets (like system executables)."""
        # Create an "executable" file outside the application base directory (APPDATA simulation)
        outside_dir = tmp_path.parent / "outside_dir"
        outside_dir.mkdir(exist_ok=True)
        exe_file = outside_dir / "game_exec.exe"
        exe_file.write_text("game binary")

        game = _add_test_game(games_repo, name="Hades", icon_path=str(exe_file))
        assert game.id is not None

        result = delete_service.delete_game(game.id)
        assert result.success is True

        # SAFETY VERIFICATION: The file outside BASE_DIR must NOT be deleted!
        assert exe_file.exists()
        assert exe_file.read_text() == "game binary"

    def test_cache_cleanup_partial_failure_continues(
        self,
        delete_service: DeleteGameService,
        games_repo: GamesRepository,
        cache_cleanup_service: CacheCleanupService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verifies that filesystem cleanup is best-effort and continues even if a partial deletion failure occurs."""
        base = cache_cleanup_service._base_dir
        icon_path = base / "good_icon.png"
        icon_path.write_text("dummy")

        bad_path = base / "bad_icon.png"
        bad_path.write_text("dummy")

        # Monkeypatch Path.unlink to simulate a PermissionError on bad_path, but pass otherwise
        original_unlink = Path.unlink

        def mock_unlink(self: Path, *args: tuple, **kwargs: dict) -> None:
            if self.name == "bad_icon.png":
                raise PermissionError("Access denied")
            original_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", mock_unlink)

        game = _add_test_game(games_repo, name="Hades", icon_path=str(bad_path))
        assert game.id is not None

        # Trigger cleanup directly for bad_path (simulated error) and good_path
        cache_cleanup_service.cleanup_game_artifacts(game.id, "Hades", str(bad_path))
        assert bad_path.exists()  # Failed to delete, but shouldn't raise unhandled crash

        # Clean up good path to confirm scanner loop continues
        cache_cleanup_service.cleanup_game_artifacts(game.id, "Hades", str(icon_path))
        assert not icon_path.exists()
