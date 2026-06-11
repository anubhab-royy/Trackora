"""
Tests for TrendAnalyzer.

Validates trend calculations: weekly change %, monthly change %,
playtime comparisons. Covers the release checklist item
"Trend calculations verified".
"""

from datetime import datetime, date, timedelta
from typing import Optional

import pytest

from trackora_stats.trend_analyzer import TrendAnalyzer
from tests.trackora_stats.conftest import insert_game, insert_session


# ===========================================================================
# Internal _compute_trend helper
# ===========================================================================


class TestComputeTrend:

    def test_increase(self, trend_analyzer: TrendAnalyzer) -> None:
        trend = trend_analyzer._compute_trend(
            current_seconds=7200,
            previous_seconds=3600,
        )
        assert trend.is_increase is True
        assert trend.is_neutral is False
        assert trend.change_seconds == 3600
        assert trend.change_percent == pytest.approx(100.0)

    def test_decrease(self, trend_analyzer: TrendAnalyzer) -> None:
        trend = trend_analyzer._compute_trend(
            current_seconds=1800,
            previous_seconds=3600,
        )
        assert trend.is_increase is False
        assert trend.change_percent == pytest.approx(-50.0)

    def test_neutral(self, trend_analyzer: TrendAnalyzer) -> None:
        trend = trend_analyzer._compute_trend(
            current_seconds=3600,
            previous_seconds=3600,
        )
        assert trend.is_neutral is True
        assert trend.change_percent == pytest.approx(0.0)
        assert trend.change_seconds == 0

    def test_previous_zero_gives_none_percent(
        self, trend_analyzer: TrendAnalyzer
    ) -> None:
        """When previous period is zero, change_percent is None (undefined)."""
        trend = trend_analyzer._compute_trend(
            current_seconds=3600,
            previous_seconds=0,
        )
        assert trend.change_percent is None
        assert trend.is_increase is True

    def test_both_zero_is_neutral(self, trend_analyzer: TrendAnalyzer) -> None:
        trend = trend_analyzer._compute_trend(
            current_seconds=0,
            previous_seconds=0,
        )
        assert trend.change_percent is None
        assert trend.is_neutral is True
        assert trend.is_increase is False


# ===========================================================================
# Weekly trend
# ===========================================================================


class TestWeeklyTrend:

    def test_weekly_trend_increase(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        """Current week has more playtime → is_increase is True."""
        gid = insert_game(db_connection)

        # Previous week: Mon 2024-04-01 – Sun 2024-04-07
        insert_session(db_connection, gid, datetime(2024, 4, 2, 10, 0, 0), 3600)

        # Current week: Mon 2024-04-08 – Sun 2024-04-14
        insert_session(db_connection, gid, datetime(2024, 4, 8, 10, 0, 0), 7200)
        insert_session(db_connection, gid, datetime(2024, 4, 10, 10, 0, 0), 3600)

        trend = trend_analyzer.get_weekly_trend(reference_date=date(2024, 4, 9))
        assert trend.current_period_seconds == 10800
        assert trend.previous_period_seconds == 3600
        assert trend.is_increase is True

    def test_weekly_trend_decrease(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        gid = insert_game(db_connection)

        # Previous week
        insert_session(db_connection, gid, datetime(2024, 4, 2, 10, 0, 0), 9000)
        # Current week
        insert_session(db_connection, gid, datetime(2024, 4, 8, 10, 0, 0), 1800)

        trend = trend_analyzer.get_weekly_trend(reference_date=date(2024, 4, 8))
        assert trend.is_increase is False
        assert trend.change_seconds < 0

    def test_weekly_trend_both_empty(self, trend_analyzer: TrendAnalyzer) -> None:
        """Both periods empty → neutral, percent is None."""
        trend = trend_analyzer.get_weekly_trend(reference_date=date(2024, 4, 1))
        assert trend.is_neutral is True
        assert trend.change_percent is None

    def test_weekly_trend_previous_week_boundaries(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        """Sessions exactly on the boundary of previous week are included."""
        gid = insert_game(db_connection)

        # Sunday of previous week (2024-04-07)
        insert_session(db_connection, gid, datetime(2024, 4, 7, 23, 59, 0), 60)

        # Monday of current week (2024-04-08)
        insert_session(db_connection, gid, datetime(2024, 4, 8, 0, 1, 0), 60)

        trend = trend_analyzer.get_weekly_trend(reference_date=date(2024, 4, 8))
        assert trend.previous_period_seconds == 60
        assert trend.current_period_seconds == 60


# ===========================================================================
# Monthly trend
# ===========================================================================


class TestMonthlyTrend:

    def test_monthly_trend_increase(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        """Current month more play → is_increase."""
        gid = insert_game(db_connection)

        insert_session(db_connection, gid, datetime(2024, 3, 15, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 4, 5, 10, 0, 0), 7200)

        trend = trend_analyzer.get_monthly_trend(year=2024, month=4)
        assert trend.current_period_seconds == 7200
        assert trend.previous_period_seconds == 3600
        assert trend.is_increase is True
        assert trend.change_percent == pytest.approx(100.0)

    def test_monthly_trend_january_wraps_to_december(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        """January's previous month is December of the prior year."""
        gid = insert_game(db_connection)

        insert_session(db_connection, gid, datetime(2023, 12, 20, 10, 0, 0), 1800)
        insert_session(db_connection, gid, datetime(2024, 1, 10, 10, 0, 0), 3600)

        trend = trend_analyzer.get_monthly_trend(year=2024, month=1)
        assert trend.previous_period_seconds == 1800
        assert trend.current_period_seconds == 3600

    def test_monthly_trend_both_empty(self, trend_analyzer: TrendAnalyzer) -> None:
        trend = trend_analyzer.get_monthly_trend(year=2024, month=6)
        assert trend.is_neutral is True

    def test_monthly_trend_decrease(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        gid = insert_game(db_connection)

        insert_session(db_connection, gid, datetime(2024, 2, 10, 10, 0, 0), 9000)
        insert_session(db_connection, gid, datetime(2024, 3, 5, 10, 0, 0), 1800)

        trend = trend_analyzer.get_monthly_trend(year=2024, month=3)
        assert trend.is_increase is False
        assert trend.change_seconds == 1800 - 9000


# ===========================================================================
# Daily trend
# ===========================================================================


class TestDailyTrend:

    def test_daily_trend_increase(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 5, 9, 10, 0, 0), 1800)   # yesterday
        insert_session(db_connection, gid, datetime(2024, 5, 10, 10, 0, 0), 3600)  # today

        trend = trend_analyzer.get_daily_trend(reference_date=date(2024, 5, 10))
        assert trend.is_increase is True
        assert trend.current_period_seconds == 3600
        assert trend.previous_period_seconds == 1800

    def test_daily_trend_no_previous(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 5, 10, 10, 0, 0), 3600)

        trend = trend_analyzer.get_daily_trend(reference_date=date(2024, 5, 10))
        assert trend.previous_period_seconds == 0
        assert trend.change_percent is None
        assert trend.is_increase is True


# ===========================================================================
# compare_weeks / compare_months
# ===========================================================================


class TestArbitraryComparisons:

    def test_compare_weeks(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 4, 1, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 4, 8, 10, 0, 0), 7200)

        trend = trend_analyzer.compare_weeks(
            week_a_date=date(2024, 4, 8),
            week_b_date=date(2024, 4, 1),
        )
        assert trend.current_period_seconds == 7200
        assert trend.previous_period_seconds == 3600

    def test_compare_months(
        self,
        db_connection,
        trend_analyzer: TrendAnalyzer,
    ) -> None:
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 1, 10, 10, 0, 0), 9000)
        insert_session(db_connection, gid, datetime(2024, 2, 10, 10, 0, 0), 3600)

        trend = trend_analyzer.compare_months(2024, 1, 2024, 2)
        assert trend.current_period_seconds == 9000
        assert trend.previous_period_seconds == 3600
        assert trend.is_increase is True