"""
TrendAnalyzer: Computes trend comparisons between time periods.

Provides:
- Weekly change % (current week vs previous week)
- Monthly change % (current month vs previous month)
- Arbitrary period playtime comparisons

Uses PlaytimeCalculator only. No direct repository access.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from statistics.models import TrendData
from statistics.playtime_calculator import PlaytimeCalculator

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """
    Analyzes trends by comparing playtime across adjacent periods.
    Depends on PlaytimeCalculator for raw statistics.
    """

    def __init__(self, calculator: PlaytimeCalculator) -> None:
        self._calculator = calculator

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_trend(
        current_seconds: int,
        previous_seconds: int,
    ) -> TrendData:
        """Build a TrendData from two raw second values."""
        change_seconds = current_seconds - previous_seconds

        if previous_seconds == 0:
            change_percent: Optional[float] = None
            is_neutral = current_seconds == 0
            is_increase = current_seconds > 0
        else:
            change_percent = (change_seconds / previous_seconds) * 100.0
            is_neutral = change_seconds == 0
            is_increase = change_seconds > 0

        return TrendData(
            current_period_seconds=current_seconds,
            previous_period_seconds=previous_seconds,
            change_seconds=change_seconds,
            change_percent=change_percent,
            is_increase=is_increase,
            is_neutral=is_neutral,
        )

    # ------------------------------------------------------------------
    # Weekly trend
    # ------------------------------------------------------------------

    def get_weekly_trend(
        self,
        reference_date: Optional[date] = None,
    ) -> TrendData:
        """
        Compare current ISO week playtime with the previous ISO week.

        Args:
            reference_date: Any date inside the "current" week.
                            Defaults to today.

        Returns:
            TrendData comparing this week vs last week.
        """
        if reference_date is None:
            reference_date = date.today()

        # Current week
        current_stats = self._calculator.get_weekly_stats(
            target_date=reference_date
        )

        # Previous week — go back 7 days from the start of this week
        previous_reference = current_stats.week_start - timedelta(days=1)
        previous_stats = self._calculator.get_weekly_stats(
            target_date=previous_reference
        )

        logger.info(
            "Weekly trend: current=%ds, previous=%ds.",
            current_stats.total_seconds,
            previous_stats.total_seconds,
        )

        return self._compute_trend(
            current_seconds=current_stats.total_seconds,
            previous_seconds=previous_stats.total_seconds,
        )

    # ------------------------------------------------------------------
    # Monthly trend
    # ------------------------------------------------------------------

    def get_monthly_trend(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> TrendData:
        """
        Compare a given calendar month playtime with the previous month.

        Args:
            year: The year of the "current" month. Defaults to today's year.
            month: The "current" month (1–12). Defaults to today's month.

        Returns:
            TrendData comparing this month vs last month.
        """
        today = date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        current_stats = self._calculator.get_monthly_stats(year=year, month=month)

        # Previous month
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        previous_stats = self._calculator.get_monthly_stats(
            year=prev_year, month=prev_month
        )

        logger.info(
            "Monthly trend: current=%ds, previous=%ds.",
            current_stats.total_seconds,
            previous_stats.total_seconds,
        )

        return self._compute_trend(
            current_seconds=current_stats.total_seconds,
            previous_seconds=previous_stats.total_seconds,
        )

    # ------------------------------------------------------------------
    # Daily trend
    # ------------------------------------------------------------------

    def get_daily_trend(
        self,
        reference_date: Optional[date] = None,
    ) -> TrendData:
        """
        Compare today's playtime with yesterday's playtime.

        Args:
            reference_date: The "current" day. Defaults to today.

        Returns:
            TrendData comparing today vs yesterday.
        """
        if reference_date is None:
            reference_date = date.today()

        current_stats = self._calculator.get_daily_stats(target_date=reference_date)
        previous_stats = self._calculator.get_daily_stats(
            target_date=reference_date - timedelta(days=1)
        )

        logger.info(
            "Daily trend: current=%ds, previous=%ds.",
            current_stats.total_seconds,
            previous_stats.total_seconds,
        )

        return self._compute_trend(
            current_seconds=current_stats.total_seconds,
            previous_seconds=previous_stats.total_seconds,
        )

    # ------------------------------------------------------------------
    # Arbitrary period comparison
    # ------------------------------------------------------------------

    def compare_weeks(
        self,
        week_a_date: date,
        week_b_date: date,
    ) -> TrendData:
        """
        Compare the total playtime of two arbitrary ISO weeks.

        Args:
            week_a_date: Any date in the "current" (reference) week.
            week_b_date: Any date in the "comparison" week.

        Returns:
            TrendData where current = week_a and previous = week_b.
        """
        stats_a = self._calculator.get_weekly_stats(target_date=week_a_date)
        stats_b = self._calculator.get_weekly_stats(target_date=week_b_date)
        return self._compute_trend(
            current_seconds=stats_a.total_seconds,
            previous_seconds=stats_b.total_seconds,
        )

    def compare_months(
        self,
        year_a: int,
        month_a: int,
        year_b: int,
        month_b: int,
    ) -> TrendData:
        """
        Compare the total playtime of two arbitrary calendar months.

        Returns:
            TrendData where current = (year_a, month_a) and previous = (year_b, month_b).
        """
        stats_a = self._calculator.get_monthly_stats(year=year_a, month=month_a)
        stats_b = self._calculator.get_monthly_stats(year=year_b, month=month_b)
        return self._compute_trend(
            current_seconds=stats_a.total_seconds,
            previous_seconds=stats_b.total_seconds,
        )