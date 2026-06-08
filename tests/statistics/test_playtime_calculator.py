"""
Tests for PlaytimeCalculator.

Validates AC-004 (Lifetime), AC-005 (Daily), AC-006 (Weekly), AC-007 (Monthly).
Every assertion maps directly to an acceptance criterion.
"""

from datetime import datetime, date, timedelta

import pytest

from statistics.playtime_calculator import PlaytimeCalculator
from tests.statistics.conftest import insert_game, insert_session


# ===========================================================================
# AC-004 — Lifetime Statistics
# ===========================================================================


class TestLifetimeStats:

    def test_empty_database_returns_zeros(self, calculator: PlaytimeCalculator) -> None:
        """No sessions → all lifetime fields are zero/None."""
        stats = calculator.get_lifetime_stats()
        assert stats.total_seconds == 0
        assert stats.total_sessions == 0
        assert stats.total_games_played == 0
        assert stats.most_played_game_id is None
        assert stats.most_played_game_name is None
        assert stats.longest_session_id is None
        assert stats.longest_session_seconds == 0
        assert stats.first_session_date is None
        assert stats.last_session_date is None

    def test_lifetime_total_equals_sum_of_all_sessions(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """AC-004: Lifetime playtime equals sum of all sessions."""
        gid = insert_game(db_connection, "GameA")
        start = datetime(2024, 1, 10, 14, 0, 0)

        durations = [3600, 1800, 7200, 900]
        for d in durations:
            insert_session(db_connection, gid, start, d)
            start += timedelta(days=1)

        expected_total = sum(durations)
        stats = calculator.get_lifetime_stats()

        assert stats.total_seconds == expected_total
        assert stats.total_sessions == len(durations)

    def test_most_played_game_is_correct(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """Most played game is the one with the highest total duration."""
        gid_a = insert_game(db_connection, "ShortGame")
        gid_b = insert_game(db_connection, "LongGame")

        start = datetime(2024, 3, 1, 10, 0, 0)
        insert_session(db_connection, gid_a, start, 3600)          # 1 h
        insert_session(db_connection, gid_b, start, 7200)          # 2 h
        insert_session(db_connection, gid_b, start + timedelta(days=1), 3600)  # +1 h

        stats = calculator.get_lifetime_stats()
        assert stats.most_played_game_id == gid_b
        assert stats.most_played_game_name == "LongGame"
        assert stats.most_played_game_seconds == 10800  # 3 h

    def test_longest_session_is_correct(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """Longest session id and duration are identified correctly."""
        gid = insert_game(db_connection, "ActionGame")
        start = datetime(2024, 4, 5, 20, 0, 0)

        sid_short = insert_session(db_connection, gid, start, 1800)
        sid_long = insert_session(db_connection, gid, start + timedelta(days=1), 9000)

        stats = calculator.get_lifetime_stats()
        assert stats.longest_session_id == sid_long
        assert stats.longest_session_seconds == 9000

    def test_date_range_is_tracked(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """first_session_date and last_session_date are accurate."""
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 1, 5, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 6, 20, 10, 0, 0), 3600)

        stats = calculator.get_lifetime_stats()
        assert stats.first_session_date == date(2024, 1, 5)
        assert stats.last_session_date == date(2024, 6, 20)

    def test_multiple_games_counted(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """total_games_played reflects distinct game IDs with sessions."""
        gid_a = insert_game(db_connection, "Game1")
        gid_b = insert_game(db_connection, "Game2")
        gid_c = insert_game(db_connection, "Game3")

        start = datetime(2024, 2, 1, 8, 0, 0)
        insert_session(db_connection, gid_a, start, 3600)
        insert_session(db_connection, gid_b, start, 3600)
        insert_session(db_connection, gid_c, start, 3600)

        stats = calculator.get_lifetime_stats()
        assert stats.total_games_played == 3


# ===========================================================================
# AC-005 — Daily Statistics
# ===========================================================================


class TestDailyStats:

    def test_empty_day_returns_zeros(self, calculator: PlaytimeCalculator) -> None:
        """A day with no sessions returns all zeros."""
        stats = calculator.get_daily_stats(target_date=date(2024, 3, 15))
        assert stats.total_seconds == 0
        assert stats.total_sessions == 0
        assert stats.game_breakdown == {}
        assert stats.date == date(2024, 3, 15)

    def test_daily_total_matches_database(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """AC-005: Today's playtime displayed correctly, matches database records."""
        gid = insert_game(db_connection)
        target = date(2024, 5, 10)

        insert_session(db_connection, gid, datetime(2024, 5, 10, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 5, 10, 14, 0, 0), 1800)
        # Different day — must NOT be counted
        insert_session(db_connection, gid, datetime(2024, 5, 11, 10, 0, 0), 7200)

        stats = calculator.get_daily_stats(target_date=target)
        assert stats.total_seconds == 5400  # 3600 + 1800
        assert stats.total_sessions == 2

    def test_game_breakdown_is_per_game(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """game_breakdown maps each game to its seconds for the day."""
        gid_a = insert_game(db_connection, "Alpha")
        gid_b = insert_game(db_connection, "Beta")
        target = date(2024, 5, 20)

        insert_session(db_connection, gid_a, datetime(2024, 5, 20, 10, 0, 0), 3600)
        insert_session(db_connection, gid_b, datetime(2024, 5, 20, 12, 0, 0), 1800)

        stats = calculator.get_daily_stats(target_date=target)
        assert stats.game_breakdown[gid_a] == 3600
        assert stats.game_breakdown[gid_b] == 1800

    def test_defaults_to_today(self, calculator: PlaytimeCalculator) -> None:
        """No argument defaults to today without raising."""
        stats = calculator.get_daily_stats()
        assert stats.date == date.today()


# ===========================================================================
# AC-006 — Weekly Statistics
# ===========================================================================


class TestWeeklyStats:

    def test_empty_week_returns_zeros(self, calculator: PlaytimeCalculator) -> None:
        """A week with no sessions returns all zeros."""
        stats = calculator.get_weekly_stats(target_date=date(2024, 1, 15))
        assert stats.total_seconds == 0
        assert stats.total_sessions == 0
        assert stats.average_daily_seconds == 0.0

    def test_weekly_total_is_correct(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """AC-006: Weekly totals are the sum of sessions in that ISO week."""
        gid = insert_game(db_connection)

        # Week containing 2024-04-01 is Mon 2024-04-01 to Sun 2024-04-07
        insert_session(db_connection, gid, datetime(2024, 4, 1, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 4, 3, 12, 0, 0), 1800)
        insert_session(db_connection, gid, datetime(2024, 4, 7, 20, 0, 0), 900)
        # Outside the week
        insert_session(db_connection, gid, datetime(2024, 4, 8, 10, 0, 0), 7200)

        stats = calculator.get_weekly_stats(target_date=date(2024, 4, 3))
        assert stats.total_seconds == 3600 + 1800 + 900
        assert stats.total_sessions == 3

    def test_weekly_average_is_per_active_day(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """Average daily seconds is total divided by days WITH sessions."""
        gid = insert_game(db_connection)

        insert_session(db_connection, gid, datetime(2024, 4, 1, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 4, 3, 10, 0, 0), 3600)

        stats = calculator.get_weekly_stats(target_date=date(2024, 4, 1))
        # 2 active days with 3600 s each = 7200 s total / 2 = 3600 avg
        assert stats.average_daily_seconds == pytest.approx(3600.0)

    def test_week_boundaries_monday_to_sunday(
        self,
        calculator: PlaytimeCalculator,
    ) -> None:
        """Week always starts on Monday and ends on Sunday."""
        # 2024-04-03 is a Wednesday
        stats = calculator.get_weekly_stats(target_date=date(2024, 4, 3))
        assert stats.week_start.weekday() == 0  # Monday
        assert stats.week_end.weekday() == 6    # Sunday
        assert stats.week_end - stats.week_start == timedelta(days=6)

    def test_daily_breakdown_contains_correct_dates(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """daily_breakdown keys are the dates sessions occurred on."""
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 4, 2, 10, 0, 0), 1200)
        insert_session(db_connection, gid, datetime(2024, 4, 4, 10, 0, 0), 600)

        stats = calculator.get_weekly_stats(target_date=date(2024, 4, 2))
        assert date(2024, 4, 2) in stats.daily_breakdown
        assert date(2024, 4, 4) in stats.daily_breakdown
        assert stats.daily_breakdown[date(2024, 4, 2)] == 1200
        assert stats.daily_breakdown[date(2024, 4, 4)] == 600


# ===========================================================================
# AC-007 — Monthly Statistics
# ===========================================================================


class TestMonthlyStats:

    def test_empty_month_returns_zeros(self, calculator: PlaytimeCalculator) -> None:
        """A month with no sessions returns all zeros."""
        stats = calculator.get_monthly_stats(year=2024, month=2)
        assert stats.total_seconds == 0
        assert stats.total_sessions == 0
        assert stats.average_daily_seconds == 0.0

    def test_monthly_total_is_correct(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """AC-007: Monthly totals are the sum of sessions in that calendar month."""
        gid = insert_game(db_connection)

        insert_session(db_connection, gid, datetime(2024, 3, 5, 10, 0, 0), 3600)
        insert_session(db_connection, gid, datetime(2024, 3, 20, 14, 0, 0), 7200)
        # Different month — must NOT be counted
        insert_session(db_connection, gid, datetime(2024, 4, 1, 10, 0, 0), 9000)

        stats = calculator.get_monthly_stats(year=2024, month=3)
        assert stats.total_seconds == 10800  # 3600 + 7200
        assert stats.total_sessions == 2

    def test_monthly_average_is_per_active_day(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """Average daily seconds is total divided by days WITH sessions."""
        gid = insert_game(db_connection)

        insert_session(db_connection, gid, datetime(2024, 3, 1, 10, 0, 0), 1800)
        insert_session(db_connection, gid, datetime(2024, 3, 15, 10, 0, 0), 3600)

        stats = calculator.get_monthly_stats(year=2024, month=3)
        assert stats.average_daily_seconds == pytest.approx(2700.0)  # 5400 / 2

    def test_december_boundary(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """December month-end calculation does not throw (year wrap-around)."""
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 12, 25, 10, 0, 0), 1800)

        stats = calculator.get_monthly_stats(year=2024, month=12)
        assert stats.total_seconds == 1800
        assert stats.year == 2024
        assert stats.month == 12

    def test_defaults_to_current_month(self, calculator: PlaytimeCalculator) -> None:
        """No arguments defaults to current year/month without raising."""
        today = date.today()
        stats = calculator.get_monthly_stats()
        assert stats.year == today.year
        assert stats.month == today.month

    def test_daily_breakdown_sums_correctly(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """Multiple sessions on the same day are summed in daily_breakdown."""
        gid = insert_game(db_connection)
        insert_session(db_connection, gid, datetime(2024, 6, 10, 8, 0, 0), 1800)
        insert_session(db_connection, gid, datetime(2024, 6, 10, 14, 0, 0), 3600)

        stats = calculator.get_monthly_stats(year=2024, month=6)
        assert stats.daily_breakdown[date(2024, 6, 10)] == 5400


# ===========================================================================
# Game playtime summaries
# ===========================================================================


class TestGamePlaytimeSummaries:

    def test_sorted_descending(
        self,
        db_connection,
        calculator: PlaytimeCalculator,
    ) -> None:
        """Summaries are sorted by total_seconds descending."""
        gid_a = insert_game(db_connection, "SmallGame")
        gid_b = insert_game(db_connection, "BigGame")

        start = datetime(2024, 1, 1, 10, 0, 0)
        insert_session(db_connection, gid_a, start, 1800)
        insert_session(db_connection, gid_b, start, 7200)

        summaries = calculator.get_game_playtime_summaries()
        assert summaries[0].game_id == gid_b
        assert summaries[1].game_id == gid_a

    def test_empty_returns_empty_list(self, calculator: PlaytimeCalculator) -> None:
        summaries = calculator.get_game_playtime_summaries()
        assert summaries == []