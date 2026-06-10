"""
DashboardController.

Bridges the StatisticsService (business layer) and the DashboardWidget (view).
Contains zero SQL. Contains zero PyQt6 widgets.
Formats raw seconds into human-readable strings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from database.repositories.active_sessions_repository import ActiveSessionsRepository
from database.repositories.games_repository import GamesRepository
from services.formatting import format_duration
from gametracker_stats.statistics_service import StatisticsService

logger = logging.getLogger(__name__)


@dataclass
class DashboardData:
    """Plain data object passed to the dashboard view."""
    total_playtime: str
    today_playtime: str
    week_playtime: str
    month_playtime: str
    most_played_game_name: str
    most_played_game_hours: str
    most_played_game_icon: str


@dataclass
class ActiveGameInfo:
    """Information about a currently tracked active game session."""
    game_name: str
    game_id: int
    start_time: datetime
    duration_seconds: int


class DashboardController:
    """
    Retrieves statistics and formats them for display.

    Args:
        statistics_service:    An instance of StatisticsService.
        active_sessions_repo:  ActiveSessionsRepository for live session data.
        games_repo:            GamesRepository for game names.
    """

    def __init__(
        self,
        statistics_service: StatisticsService,
        active_sessions_repo: ActiveSessionsRepository,
        games_repo: GamesRepository,
    ) -> None:
        self._service = statistics_service
        self._active_repo = active_sessions_repo
        self._games_repo = games_repo
        logger.info("DashboardController initialised.")

    def load_dashboard_data(self) -> DashboardData:
        """
        Fetch all required statistics and return a DashboardData object.

        Returns:
            DashboardData with pre-formatted strings ready for display.
        """
        try:
            lifetime = self._service.get_lifetime_stats()
            daily = self._service.get_daily_stats()
            weekly = self._service.get_weekly_stats()
            monthly = self._service.get_monthly_stats()
            most_played = self._service.get_most_played_game()

            total_seconds: int = lifetime.total_seconds if lifetime else 0
            today_seconds: int = daily.total_seconds if daily else 0
            week_seconds: int = weekly.total_seconds if weekly else 0
            month_seconds: int = monthly.total_seconds if monthly else 0

            game_name: str = "No games tracked yet"
            game_hours: str = "—"
            game_icon: str = ""

            if most_played:
                game_name = most_played.game_name
                game_seconds = most_played.total_seconds
                game_hours = format_duration(game_seconds)

            data = DashboardData(
                total_playtime=format_duration(total_seconds),
                today_playtime=format_duration(today_seconds),
                week_playtime=format_duration(week_seconds),
                month_playtime=format_duration(month_seconds),
                most_played_game_name=game_name,
                most_played_game_hours=game_hours,
                most_played_game_icon=game_icon,
            )

            logger.debug(
                "Dashboard data loaded: total=%s today=%s week=%s month=%s "
                "most_played=%s",
                data.total_playtime,
                data.today_playtime,
                data.week_playtime,
                data.month_playtime,
                data.most_played_game_name,
            )
            return data

        except Exception as exc:
            logger.error("Failed to load dashboard data: %s", exc)
            return DashboardData(
                total_playtime="—",
                today_playtime="—",
                week_playtime="—",
                month_playtime="—",
                most_played_game_name="Error loading data",
                most_played_game_hours="—",
                most_played_game_icon="",
            )

    def get_active_games(self) -> list[ActiveGameInfo]:
        """Return info for all currently tracked active game sessions."""
        try:
            active = self._active_repo.get_all()
            if not active:
                return []
            now = datetime.now()
            result: list[ActiveGameInfo] = []
            for a in active:
                game = self._games_repo.get_by_id(a.game_id)
                if game is None:
                    continue
                duration = int((now - a.start_time).total_seconds())
                result.append(ActiveGameInfo(
                    game_name=game.name,
                    game_id=a.game_id,
                    start_time=a.start_time,
                    duration_seconds=duration,
                ))
            return result
        except Exception as exc:
            logger.error("Failed to get active games: %s", exc)
            return []
