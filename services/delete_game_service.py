"""
DeleteGameService — Phase 14
Orchestrator for safely deleting games, ensuring transaction integrity,
concurrency control, logging, and tracking state updates.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Optional, TYPE_CHECKING

from services.delete_game_result import DeleteGameResult

if TYPE_CHECKING:
    from database.database_manager import DatabaseManager
    from database.repositories.games_repository import GamesRepository
    from database.repositories.active_sessions_repository import ActiveSessionsRepository
    from database.repositories.sessions_repository import SessionsRepository
    from services.cache_cleanup_service import CacheCleanupService
    from trackora_stats.statistics_service import StatisticsService
    from tracker.tracking_state import TrackingState

logger = logging.getLogger(__name__)


class DeleteGameService:
    """
    Orchestration layer responsible for deleting games safely.

    Provides transaction safety, concurrency lock control, and live state updates.
    """

    def __init__(
        self,
        games_repo: GamesRepository,
        active_sessions_repo: ActiveSessionsRepository,
        sessions_repo: SessionsRepository,
        db_manager: DatabaseManager,
        tracking_state: Optional[TrackingState] = None,
        statistics_service: Optional[StatisticsService] = None,
        cache_cleanup_service: Optional[CacheCleanupService] = None,
    ) -> None:
        self._games_repo = games_repo
        self._active_sessions_repo = active_sessions_repo
        self._sessions_repo = sessions_repo
        self._db_manager = db_manager
        self._tracking_state = tracking_state
        self._statistics_service = statistics_service
        self._cache_cleanup_service = cache_cleanup_service
        self._deletion_lock = threading.Lock()

    def delete_game(self, game_id: int) -> DeleteGameResult:
        """
        Delete a game by primary key and clean up all related database records, statistics, and cache.

        Implements the following workflow:
          1. Log delete request.
          2. Validate game exists and is valid.
          3. Validate game is not actively running.
          4. Acquire deletion lock to prevent concurrent deletions.
          5. Begin database transaction.
          6. Delete dependent records (active sessions, completed sessions).
          7. Delete game metadata record.
          8. Commit transaction.
          9. Remove from tracking state index.
          10. Refresh and recalculate statistics.
          11. Clean up filesystem cache/assets (best-effort).
          12. Log success.
          13. Release lock.
        """
        start_time = time.perf_counter()
        logger.info("Delete requested for game_id=%r", game_id)

        # 1. Validation: Valid ID type and value
        if not isinstance(game_id, int) or game_id <= 0:
            msg = f"Invalid Game ID: {game_id}."
            logger.warning("Validation failed for game_id=%r: %s", game_id, msg)
            return DeleteGameResult(
                success=False,
                game_id=0,
                game_name="",
                error_message=msg,
                duration_ms=0.0,
            )

        # 2. Validation: Game exists (consistent repository state check)
        try:
            game = self._games_repo.get_by_id(game_id)
        except Exception as exc:
            msg = f"Failed to retrieve game details: {exc}"
            logger.warning("Validation failed for game_id=%d: %s", game_id, msg)
            return DeleteGameResult(
                success=False,
                game_id=game_id,
                game_name="",
                error_message=msg,
                duration_ms=0.0,
            )

        if game is None:
            msg = f"Game with ID {game_id} not found."
            logger.warning("Validation failed for game_id=%d: %s", game_id, msg)
            return DeleteGameResult(
                success=False,
                game_id=game_id,
                game_name="",
                error_message=msg,
                duration_ms=0.0,
            )

        game_name = game.name

        # 3. Validation: Game is not actively running (tracked)
        in_memory_active = False
        if self._tracking_state is not None:
            in_memory_active = self._tracking_state.is_game_active(game_id)

        if in_memory_active:
            msg = f"Cannot delete game '{game_name}' because it is currently active/running."
            logger.warning("Validation failed for game_id=%d: %s", game_id, msg)
            return DeleteGameResult(
                success=False,
                game_id=game_id,
                game_name=game_name,
                error_message=msg,
                duration_ms=0.0,
            )

        # 4. Concurrency lock: No deletion already in progress
        acquired = self._deletion_lock.acquire(blocking=False)
        if not acquired:
            msg = "A deletion is already in progress."
            logger.warning("Validation failed for game_id=%d: %s", game_id, msg)
            return DeleteGameResult(
                success=False,
                game_id=game_id,
                game_name=game_name,
                error_message=msg,
                duration_ms=0.0,
            )

        logger.info("Deletion started for game_id=%d", game_id)

        # Use the existing DatabaseManager abstraction to acquire connection and lock
        db_lock_context = self._db_manager.lock
        conn = self._db_manager.connection

        with db_lock_context:
            try:
                # Log cleanup started
                logger.debug("Cleanup started for game_id=%d", game_id)

                # Begin Transaction
                conn.execute("BEGIN;")

                # Delete dependent records (active_sessions)
                active_deleted = self._active_sessions_repo.delete_all_for_game(game_id, commit=False)
                logger.debug("Table cleanup completed for active_sessions. Records removed: %d", active_deleted)

                # Delete dependent records (sessions)
                sessions_deleted = self._sessions_repo.delete_all_for_game(game_id, commit=False)
                logger.debug("Table cleanup completed for sessions. Records removed: %d", sessions_deleted)

                # Delete game metadata (games)
                self._games_repo.delete(game_id, commit=False)
                logger.debug("Table cleanup completed for games. Records removed: 1")

                # Commit Transaction
                conn.execute("COMMIT;")
                logger.debug("Cleanup completed for game_id=%d", game_id)
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK;")
                    logger.info("Rollback executed for game_id=%d due to error: %s", game_id, exc)
                except Exception as rollback_exc:
                    logger.error("Rollback failed for game_id=%d: %s", game_id, rollback_exc)

                self._deletion_lock.release()
                return DeleteGameResult(
                    success=False,
                    game_id=game_id,
                    game_name=game_name,
                    error_message=f"Database transaction failed: {exc}",
                    duration_ms=(time.perf_counter() - start_time) * 1000.0,
                )

        # 8. Remove from tracking state index
        # TODO: Move this mutation logic to a dedicated tracking coordinator when introduced.
        # This is a temporary architectural compromise.
        if self._tracking_state is not None:
            self._tracking_state.remove_tracked_game(game_id)

        # 9. Invalidate and refresh statistics (T-222)
        if self._statistics_service is not None:
            self._statistics_service.refresh_statistics()

        # 10. Clean up filesystem cache artifacts (T-233) (best-effort)
        if self._cache_cleanup_service is not None:
            try:
                self._cache_cleanup_service.cleanup_game_artifacts(
                    game_id=game_id,
                    game_name=game_name,
                    icon_path=game.icon_path if game else "",
                )
            except Exception as exc:
                logger.error("Failed to perform cache cleanup for game_id=%d: %s", game_id, exc)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info("Deletion completed for game_id=%d (%s)", game_id, game_name)

        # 11. Release lock
        self._deletion_lock.release()

        return DeleteGameResult(
            success=True,
            game_id=game_id,
            game_name=game_name,
            duration_ms=duration_ms,
        )
