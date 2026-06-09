"""
SessionHistoryService — Phase 7
Mediates between the UI history layer and SessionsRepository.

No SQL. No UI. Pure service logic.

Provides:
  - Paginated session queries with search, filter, and sort
  - Game list for filter dropdown
  - Duration formatting
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from database.models import Game
from database.repositories.games_repository import GamesRepository
from database.repositories.sessions_repository import (
    SessionView,
    SessionsRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionHistoryQuery:
    """Data transfer object for a session history query."""

    search_text: str = ""
    game_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_duration_minutes: int | None = None
    max_duration_minutes: int | None = None
    sort_by: str = "start_time"
    sort_order: str = "DESC"
    page: int = 0
    page_size: int = 50


@dataclass
class SessionHistoryResult:
    """Result returned from a session history query."""

    sessions: list[SessionView] = field(default_factory=list)
    total_count: int = 0
    page: int = 0
    page_size: int = 50
    total_pages: int = 0
    total_duration_seconds: int = 0


class SessionHistoryService:
    """
    Service for session history queries.

    Args:
        sessions_repository: Injected SessionsRepository instance.
        games_repository:    Injected GamesRepository instance.
    """

    def __init__(
        self,
        sessions_repository: SessionsRepository,
        games_repository: GamesRepository,
    ) -> None:
        self._sessions_repo = sessions_repository
        self._games_repo = games_repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, query: SessionHistoryQuery) -> SessionHistoryResult:
        """
        Execute a paginated, filtered, sorted session query.

        Returns a SessionHistoryResult with the matching sessions,
        total count, pagination info, and total duration.
        """
        try:
            min_seconds: int | None = None
            if query.min_duration_minutes is not None:
                min_seconds = query.min_duration_minutes * 60

            max_seconds: int | None = None
            if query.max_duration_minutes is not None:
                max_seconds = query.max_duration_minutes * 60

            total_count, session_views = self._sessions_repo.query_sessions(
                search_text=query.search_text,
                game_id=query.game_id,
                date_from=query.date_from,
                date_to=query.date_to,
                min_duration=min_seconds,
                max_duration=max_seconds,
                sort_by=query.sort_by,
                sort_order=query.sort_order,
                limit=query.page_size,
                offset=query.page * query.page_size,
            )

            total_duration = sum(s.duration_seconds for s in session_views)
            total_pages = max(0, (total_count - 1) // query.page_size) + 1 if total_count > 0 else 0

            return SessionHistoryResult(
                sessions=session_views,
                total_count=total_count,
                page=query.page,
                page_size=query.page_size,
                total_pages=total_pages,
                total_duration_seconds=total_duration,
            )
        except Exception as exc:
            logger.error("Session history query failed: %s", exc)
            return SessionHistoryResult(
                page=query.page,
                page_size=query.page_size,
            )

    def get_games(self) -> list[Game]:
        """Return all games (for the filter dropdown)."""
        try:
            return self._games_repo.get_all()
        except Exception as exc:
            logger.error("Failed to load games for history filter: %s", exc)
            return []

    def get_all_sessions_total_duration(self) -> int:
        """Return the total duration of all sessions (for footer summary)."""
        try:
            return self._sessions_repo.get_lifetime_total_seconds()
        except Exception as exc:
            logger.error("Failed to get total duration: %s", exc)
            return 0
