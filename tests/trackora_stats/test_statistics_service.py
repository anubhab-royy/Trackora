"""
Integration tests for StatisticsService.

Verifies that the public API facade correctly delegates to calculator
and trend analyzer, and that all acceptance criteria methods are reachable.
"""

from datetime import datetime, date

import pytest

from trackora_stats.statistics_service import StatisticsService
from tests.trackora_stats.conftest import insert_game, insert_session


class TestStatisticsServiceLifetime:

    def test_get_lifetime_stats_empty(
        self, statistics_service: StatisticsService
    ) -> None:
        stats = statistics_service.get_lifetime_stats()
        assert stats.total_seconds == 0
        assert stats.total_sessions == 0

    def test_get_lifetime_stats_with_sessions(
        self,
        db_connection,
        statistics_service: StatisticsService,
    ) -> None:
        gid = insert_game(db_connection, "MyGame")
        insert_session(db_connection, gid, datetime(2024, 6, 1, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 6, 2, 10, 0, 0), 7200)

        stats = statistics_service.get_lifetime_stats()
        assert stats.total_seconds == 10800
        assert stats.total_sessions == 2
        assert stats.most_played_game_name == "MyGame"


class TestStatisticsServiceDaily:

    def test_get_daily_stats(
        self,
        db_connection,
        statistics_service: StatisticsService,
    ) -> None:
        gid = insert_game(db_connection)
        target = date(2024, 7, 4)
        insert_session(db_connection, gid, datetime(2024, 7, 4, 12, 0, 0), 1800)

        stats = statistics_service.get_daily_stats(target_date=target)
        assert stats.total_seconds == 1800
        assert stats.total_sessions == 1

    def test_get_daily_stats_defaults_today(
        self, statistics_service: StatisticsService
    ) -> None:
        stats = statistics_service.get_daily_stats()
        assert stats.date == date.today()


class TestStatisticsServiceWeekly:

    def test_get_weekly_stats(
        self,
        db_connection,
        statistics_service: StatisticsService,
    ) -> None:
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 4, 1, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 4, 5, 10, 0, 0), 1800)

        stats = statistics_service.get_weekly_stats(target_date=date(2024, 4, 3))
        assert stats.total_seconds == 5400
        assert stats.week_start == date(2024, 4, 1)

    def test_get_weekly_stats_defaults_current_week(
        self, statistics_service: StatisticsService
    ) -> None:
        stats = statistics_service.get_weekly_stats()
        assert stats.week_start.weekday() == 0


class TestStatisticsServiceMonthly:

    def test_get_monthly_stats(
        self,
        db_connection,
        statistics_service: StatisticsService,
    ) -> None:
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 8, 10, 10, 0, 0), 7200)
        insert_session(db_connection, gid, datetime(2024, 8, 20, 10, 0, 0), 3600)

        stats = statistics_service.get_monthly_stats(year=2024, month=8)
        assert stats.total_seconds == 10800
        assert stats.year == 2024
        assert stats.month == 8

    def test_get_monthly_stats_defaults_current_month(
        self, statistics_service: StatisticsService
    ) -> None:
        today = date.today()
        stats = statistics_service.get_monthly_stats()
        assert stats.year == today.year
        assert stats.month == today.month


class TestStatisticsServiceMostPlayed:

    def test_get_most_played_game_none_when_empty(
        self, statistics_service: StatisticsService
    ) -> None:
        assert statistics_service.get_most_played_game() is None

    def test_get_most_played_game_returns_correct_game(
        self,
        db_connection,
        statistics_service: StatisticsService,
    ) -> None:
        gid_a = insert_game(db_connection, "Casual")
        gid_b = insert_game(db_connection, "Favourite")

        start = datetime(2024, 1, 1, 10, 0, 0)
        insert_session(db_connection, gid_a, start, 1800)
        insert_session(db_connection, gid_b, start, 9000)

        result = statistics_service.get_most_played_game()
        assert result is not None
        assert result.game_name == "Favourite"
        assert result.total_seconds == 9000


class TestStatisticsServiceTrends:

    def test_get_weekly_trend_returns_trend_data(
        self, statistics_service: StatisticsService
    ) -> None:
        trend = statistics_service.get_weekly_trend(
            reference_date=date(2024, 4, 3)
        )
        assert hasattr(trend, "current_period_seconds")
        assert hasattr(trend, "change_percent")

    def test_get_monthly_trend_returns_trend_data(
        self, statistics_service: StatisticsService
    ) -> None:
        trend = statistics_service.get_monthly_trend(year=2024, month=4)
        assert hasattr(trend, "is_increase")

    def test_get_daily_trend_returns_trend_data(
        self, statistics_service: StatisticsService
    ) -> None:
        trend = statistics_service.get_daily_trend(
            reference_date=date(2024, 4, 3)
        )
        assert hasattr(trend, "previous_period_seconds")

    def test_weekly_trend_with_data(
        self,
        db_connection,
        statistics_service: StatisticsService,
    ) -> None:
        gid = insert_game(db_connection)
        # Previous week
        insert_session(db_connection, gid, datetime(2024, 4, 2, 10, 0, 0), 3600)
        # Current week
        insert_session(db_connection, gid, datetime(2024, 4, 9, 10, 0, 0), 7200)

        trend = statistics_service.get_weekly_trend(
            reference_date=date(2024, 4, 9)
        )
        assert trend.current_period_seconds == 7200
        assert trend.previous_period_seconds == 3600
        assert trend.is_increase is True
        assert trend.change_percent == pytest.approx(100.0)


class TestStatisticsServiceGameSummaries:

    def test_empty_returns_empty_list(
        self, statistics_service: StatisticsService
    ) -> None:
        assert statistics_service.get_game_playtime_summaries() == []

    def test_sorted_descending(
        self,
        db_connection,
        statistics_service: StatisticsService,
    ) -> None:
        gid_a = insert_game(db_connection, "Short")
        gid_b = insert_game(db_connection, "Long")

        start = datetime(2024, 2, 1, 10, 0, 0)
        insert_session(db_connection, gid_a, start, 900)
        insert_session(db_connection, gid_b, start, 5400)

        summaries = statistics_service.get_game_playtime_summaries()
        assert summaries[0].game_name == "Long"
        assert summaries[1].game_name == "Short"