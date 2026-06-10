"""
ChartsController — Phase 8
Wires ChartsView to StatisticsService for all chart data.

Responsibilities:
- Load daily activity data and push to daily chart
- Load monthly trend data and push to monthly chart
- Load game distribution data and push to distribution chart
- Provide a single refresh() entry point

No SQL. No business logic.
"""

from __future__ import annotations

import logging

from gametracker_stats.statistics_service import StatisticsService
from ui.widgets.charts_view import ChartsView

logger = logging.getLogger(__name__)


class ChartsController:
    """
    Controller for the Charts screen.

    Loads data from StatisticsService and refreshes chart widgets.
    """

    def __init__(
        self,
        view: ChartsView,
        statistics_service: StatisticsService,
    ) -> None:
        self._view = view
        self._service = statistics_service
        logger.info("ChartsController initialised.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload all chart data from the service and update the UI."""
        try:
            # Daily activity
            daily = self._service.get_daily_activity(days=30)
            self._view.daily_chart.refresh(daily)

            # Monthly trend
            monthly = self._service.get_monthly_activity(months=12)
            self._view.monthly_chart.refresh(monthly)

            # Game distribution
            summaries = self._service.get_game_playtime_summaries()
            self._view.distribution_chart.refresh(summaries)

            logger.debug("ChartsController: all charts refreshed.")
        except Exception as exc:
            logger.error("Failed to refresh charts: %s", exc)
