# ui/dashboard/dashboard_controller.py
"""
DashboardController.

Bridges the StatisticsService (business layer) and the DashboardWidget (view).
Contains zero SQL. Contains zero PyQt6 widgets.
Formats raw seconds into human-readable strings.
"""

import logging
from dataclasses import dataclass

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


def _format_duration(seconds: int) -> str:
    """
    Convert seconds into a human-readable string.

    Examples:
        0       -> "0m"
        3600    -> "1h 0m"
        5400    -> "1h 30m"
        90061   -> "25h 1m"
    """
    if seconds <= 0:
        return "0m"
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class DashboardController:
    """
    Retrieves statistics and formats them for display.

    Args:
        statistics_service: An instance of StatisticsService (from statistics/).
    """

    def __init__(self, statistics_service: object) -> None:
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

            total_seconds: int = lifetime.get("total_seconds", 0) if lifetime else 0
            today_seconds: int = daily.get("total_seconds", 0) if daily else 0
            week_seconds: int = weekly.get("total_seconds", 0) if weekly else 0
            month_seconds: int = monthly.get("total_seconds", 0) if monthly else 0

            game_name: str = "No games tracked yet"
            game_hours: str = "—"
            game_icon: str = ""

            if most_played:
                game_name = most_played.get("name", "Unknown")
                game_seconds = most_played.get("total_seconds", 0)
                game_hours = _format_duration(game_seconds)
                game_icon = most_played.get("icon_path", "")

            data = DashboardData(
                total_playtime=_format_duration(total_seconds),
                today_playtime=_format_duration(today_seconds),
                week_playtime=_format_duration(week_seconds),
                month_playtime=_format_duration(month_seconds),
                most_played_game_name=game_name,
                most_played_game_hours=game_hours,
                most_played_game_icon=game_icon,
            )

            logger.info(
                "Dashboard data loaded: total=%s today=%s week=%s month=%s",
                data.total_playtime,
                data.today_playtime,
                data.week_playtime,
                data.month_playtime,
            )
            return data

        except Exception as exc:  # pragma: no cover
            logger.error("Failed to load dashboard data: %s", exc)
            return DashboardData(
                total_playtime="—",
                today_playtime="—",
                week_playtime="—",
                month_playtime="—",
                most_played_game_name="Unable to load",
                most_played_game_hours="—",
                most_played_game_icon="",
            )