"""
DashboardController.

Bridges the StatisticsService (business layer) and the DashboardWidget (view).
Contains zero SQL. Contains zero PyQt6 widgets.
Formats raw seconds into human-readable strings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from services.formatting import format_duration
from statistics.statistics_service import StatisticsService

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


class DashboardController:
    """
    Retrieves statistics and formats them for display.

    Args:
        statistics_service: An instance of StatisticsService (from statistics/).
    """

    def __init__(self, statistics_service: StatisticsService) -> None:
        self._service = statistics_service
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
                game_name = most_played.name
                game_seconds = most_played.total_seconds
                game_hours = format_duration(game_seconds)
                game_icon = most_played.icon_path

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
