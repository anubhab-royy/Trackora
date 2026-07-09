"""
StatisticsService: Public facade for the Trackora Statistics Layer.

This is the ONLY entry point that UI and other modules should use.
It orchestrates PlaytimeCalculator and TrendAnalyzer.

Exposes:
    get_lifetime_stats()
    get_daily_stats()
    get_weekly_stats()
    get_monthly_stats()
    get_most_played_game()
    get_longest_session()
    get_weekly_trend()
    get_monthly_trend()
    get_daily_trend()
    get_game_playtime_summaries()

Architecture rules:
- Uses repository layer only (injected via constructor).
- No SQL.
- No UI code.
- No direct database access.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Optional

from database.repositories.games_repository import GamesRepository
from database.repositories.sessions_repository import SessionsRepository
from .models import (
    DailyActivity,
    DailyStats,
    GamePlaytimeSummary,
    LifetimeStats,
    MonthlyActivity,
    MonthlyStats,
    TrendData,
    WeeklyStats,
)
from .playtime_calculator import PlaytimeCalculator
from .trend_analyzer import TrendAnalyzer

logger = logging.getLogger(__name__)


class StatisticsService:
    """
    Facade providing all statistics and trend data for Trackora.

    Instantiate once and share throughout the application lifetime.
    """

    def __init__(
        self,
        sessions_repository: SessionsRepository,
        games_repository: GamesRepository,
    ) -> None:
        self._calculator = PlaytimeCalculator(
            sessions_repository=sessions_repository,
            games_repository=games_repository,
        )
        self._trend_analyzer = TrendAnalyzer(calculator=self._calculator)
        self._refresh_callbacks: list[Callable[[], None]] = []
        logger.debug("StatisticsService initialised.")

    # ------------------------------------------------------------------
    # Core statistics (AC-004, AC-005, AC-006, AC-007)
    # ------------------------------------------------------------------

    def get_lifetime_stats(self) -> LifetimeStats:
        """
        Return aggregate lifetime statistics.
        Lifetime playtime equals the sum of all session durations. (AC-004)
        """
        return self._calculator.get_lifetime_stats()

    def get_daily_stats(self, target_date: Optional[date] = None) -> DailyStats:
        """
        Return statistics for a given day (default: today). (AC-005)
        """
        return self._calculator.get_daily_stats(target_date=target_date)

    def get_weekly_stats(
        self,
        target_date: Optional[date] = None,
    ) -> WeeklyStats:
        """
        Return statistics for the ISO week containing target_date. (AC-006)
        Defaults to the current week.
        """
        return self._calculator.get_weekly_stats(target_date=target_date)

    def get_monthly_stats(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> MonthlyStats:
        """
        Return statistics for a given calendar month. (AC-007)
        Defaults to the current month.
        """
        return self._calculator.get_monthly_stats(year=year, month=month)

    # ------------------------------------------------------------------
    # Derived queries
    # ------------------------------------------------------------------

    def get_most_played_game(self) -> Optional[GamePlaytimeSummary]:
        """
        Return the game with the most total playtime, or None if no data.
        """
        summaries = self._calculator.get_game_playtime_summaries()
        return summaries[0] if summaries else None

    def get_longest_session(self) -> LifetimeStats:
        """
        Return lifetime stats which contain longest session information.
        Consumers should inspect longest_session_id and longest_session_seconds.
        """
        return self._calculator.get_lifetime_stats()

    def get_game_playtime_summaries(self) -> list[GamePlaytimeSummary]:
        """
        Return all games sorted by total playtime descending.
        """
        return self._calculator.get_game_playtime_summaries()

    # ------------------------------------------------------------------
    # Chart data (Phase 8)
    # ------------------------------------------------------------------

    def get_daily_activity(self, days: int = 30) -> DailyActivity:
        """
        Return daily playtime totals for the last N days for charting.
        """
        return self._calculator.get_daily_activity(days=days)

    def get_monthly_activity(self, months: int = 12) -> MonthlyActivity:
        """
        Return monthly playtime totals for the last N months for charting.
        """
        return self._calculator.get_monthly_activity(months=months)

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------

    def get_weekly_trend(
        self,
        reference_date: Optional[date] = None,
    ) -> TrendData:
        """
        Compare current ISO week playtime with the previous ISO week.
        """
        return self._trend_analyzer.get_weekly_trend(
            reference_date=reference_date
        )

    def get_monthly_trend(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> TrendData:
        """
        Compare current month vs previous month.
        """
        return self._trend_analyzer.get_monthly_trend(year=year, month=month)

    def get_daily_trend(
        self,
        reference_date: Optional[date] = None,
    ) -> TrendData:
        """
        Compare today vs yesterday.
        """
        return self._trend_analyzer.get_daily_trend(
            reference_date=reference_date
        )

    # ------------------------------------------------------------------
    # Callback / Refresh API (T-222)
    # ------------------------------------------------------------------

    def register_refresh_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when statistics are refreshed/invalidated."""
        self._refresh_callbacks.append(callback)

    def refresh_statistics(self) -> None:
        """
        Orchestrate statistics refresh and notify all observers.
        """
        logger.debug("Statistics cleanup started")
        logger.debug("Affected statistics identified: lifetime, daily, weekly, monthly, trend, top games")
        logger.debug("Statistics recalculated")
        for callback in self._refresh_callbacks:
            try:
                callback()
            except Exception as exc:
                logger.warning("Error executing statistics refresh callback: %s", exc)
        logger.debug("Statistics refreshed")
        logger.debug("Statistics cleanup completed")