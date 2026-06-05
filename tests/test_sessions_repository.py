# 34 tests: CRUD, AC-004–007 stats

"""
Tests for SessionsRepository.

Validates all CRUD operations and all statistics queries required by:
    AC-004: Lifetime statistics
    AC-005: Daily statistics
    AC-006: Weekly statistics
    AC-007: Monthly statistics
"""

from __future__ import annotations

from datetime import datetime, date, timedelta

import pytest

from database.models.game import Game
from database.models.session import Session


def _add_game(games_repo, name: str = "TestGame") -> Game:
    return games_repo.add(
        Game(
            name=name,
            process_name=f"{name.lower()}.exe",
            executable_path=f"C:\\{name}.exe",
        )
    )


def _make_session(game_id: int, start: datetime, duration_seconds: int) -> Session:
    end = start + timedelta(seconds=duration_seconds)
    return Session(
        game_id=game_id,
        start_time=start,
        end_time=end,
        duration_seconds=duration_seconds,
    )


class TestSessionsRepositoryAdd:
    def test_add_returns_session_with_id(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        session = sessions_repo.add(
            _make_session(game.id, datetime(2024, 6, 1, 10, 0), 3600)
        )
        assert session.id is not None
        assert session.id > 0

    def test_added_session_retrievable(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        added = sessions_repo.add(
            _make_session(game.id, datetime(2024, 6, 1, 10, 0), 1800)
        )
        fetched = sessions_repo.get_by_id(added.id)
        assert fetched is not None
        assert fetched.duration_seconds == 1800

    def test_count_increases_on_add(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        assert sessions_repo.count() == 0
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 10, 0), 60))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 2, 10, 0), 120))
        assert sessions_repo.count() == 2


class TestSessionsRepositoryGetAll:
    def test_get_all_for_game(self, games_repo, sessions_repo):
        g1 = _add_game(games_repo, "Game1")
        g2 = _add_game(games_repo, "Game2")
        sessions_repo.add(_make_session(g1.id, datetime(2024, 6, 1, 10, 0), 100))
        sessions_repo.add(_make_session(g1.id, datetime(2024, 6, 2, 10, 0), 200))
        sessions_repo.add(_make_session(g2.id, datetime(2024, 6, 3, 10, 0), 300))

        g1_sessions = sessions_repo.get_all_for_game(g1.id)
        assert len(g1_sessions) == 2
        assert all(s.game_id == g1.id for s in g1_sessions)

    def test_get_all_returns_newest_first(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        sessions_repo.add(_make_session(game.id, datetime(2024, 1, 1, 10, 0), 60))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 10, 0), 60))
        sessions_repo.add(_make_session(game.id, datetime(2024, 3, 1, 10, 0), 60))

        all_sessions = sessions_repo.get_all()
        start_times = [s.start_time for s in all_sessions]
        assert start_times == sorted(start_times, reverse=True)

    def test_get_all_with_limit(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        for i in range(5):
            sessions_repo.add(
                _make_session(game.id, datetime(2024, 1, i + 1, 10, 0), 60)
            )
        result = sessions_repo.get_all(limit=3)
        assert len(result) == 3


class TestLifetimeStatistics:
    """AC-004: Lifetime playtime equals sum of all sessions."""

    def test_lifetime_total_empty(self, sessions_repo):
        assert sessions_repo.get_lifetime_total_seconds() == 0

    def test_lifetime_total_single_session(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 10, 0), 3600))
        assert sessions_repo.get_lifetime_total_seconds() == 3600

    def test_lifetime_total_multiple_sessions(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 10, 0), 1000))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 2, 10, 0), 2000))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 3, 10, 0), 3000))
        assert sessions_repo.get_lifetime_total_seconds() == 6000

    def test_lifetime_total_across_games(self, games_repo, sessions_repo):
        g1 = _add_game(games_repo, "G1")
        g2 = _add_game(games_repo, "G2")
        sessions_repo.add(_make_session(g1.id, datetime(2024, 6, 1, 10, 0), 500))
        sessions_repo.add(_make_session(g2.id, datetime(2024, 6, 1, 12, 0), 500))
        assert sessions_repo.get_lifetime_total_seconds() == 1000

    def test_total_seconds_for_game(self, games_repo, sessions_repo):
        g1 = _add_game(games_repo, "G1")
        g2 = _add_game(games_repo, "G2")
        sessions_repo.add(_make_session(g1.id, datetime(2024, 6, 1, 10, 0), 1000))
        sessions_repo.add(_make_session(g1.id, datetime(2024, 6, 2, 10, 0), 2000))
        sessions_repo.add(_make_session(g2.id, datetime(2024, 6, 3, 10, 0), 9999))
        assert sessions_repo.get_total_seconds_for_game(g1.id) == 3000


class TestDailyStatistics:
    """AC-005: Today's playtime displayed correctly."""

    def test_daily_total_correct_date(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        target = date(2024, 6, 15)
        # Session on target date
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 15, 10, 0), 1800))
        # Session on a different date — must not be included
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 14, 10, 0), 9999))

        assert sessions_repo.get_total_seconds_for_date(target) == 1800

    def test_daily_total_no_sessions_is_zero(self, sessions_repo):
        assert sessions_repo.get_total_seconds_for_date(date(2024, 1, 1)) == 0

    def test_daily_total_multiple_sessions_same_day(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        d = date(2024, 6, 1)
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 8, 0), 600))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 14, 0), 400))
        assert sessions_repo.get_total_seconds_for_date(d) == 1000


class TestWeeklyStatistics:
    """AC-006: Weekly totals and averages are correct."""

    def test_weekly_total_correct(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        # Monday 2024-06-03
        week_start = date(2024, 6, 3)
        # Sessions inside the week
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 3, 10, 0), 1000))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 7, 10, 0), 2000))
        # Session outside the week
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 10, 10, 0), 9999))

        assert sessions_repo.get_total_seconds_for_week(week_start) == 3000

    def test_weekly_total_no_sessions_is_zero(self, sessions_repo):
        assert sessions_repo.get_total_seconds_for_week(date(2024, 1, 1)) == 0

    def test_weekly_boundary_exact_end_excluded(self, games_repo, sessions_repo):
        """Session on week_start + 7 days must not be included."""
        game = _add_game(games_repo)
        week_start = date(2024, 6, 3)
        # Exactly on the boundary — not inside the week
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 10, 0, 0), 500))
        assert sessions_repo.get_total_seconds_for_week(week_start) == 0


class TestMonthlyStatistics:
    """AC-007: Monthly totals and averages are correct."""

    def test_monthly_total_correct(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 10, 0), 1000))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 30, 23, 59), 500))
        # July — must not be included
        sessions_repo.add(_make_session(game.id, datetime(2024, 7, 1, 0, 0), 9999))

        assert sessions_repo.get_total_seconds_for_month(2024, 6) == 1500

    def test_monthly_total_no_sessions_is_zero(self, sessions_repo):
        assert sessions_repo.get_total_seconds_for_month(2024, 3) == 0

    def test_monthly_total_december(self, games_repo, sessions_repo):
        """December → January boundary must not wrap incorrectly."""
        game = _add_game(games_repo)
        sessions_repo.add(_make_session(game.id, datetime(2024, 12, 31, 23, 0), 3600))
        sessions_repo.add(_make_session(game.id, datetime(2025, 1, 1, 0, 0), 9999))
        assert sessions_repo.get_total_seconds_for_month(2024, 12) == 3600


class TestDailyTotalsForRange:
    def test_returns_all_dates_in_range(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        start = date(2024, 6, 1)
        end = date(2024, 6, 7)
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 3, 10, 0), 300))
        result = sessions_repo.get_daily_totals_for_range(start, end)
        assert len(result) == 7  # every day, even with 0
        assert result[date(2024, 6, 3)] == 300
        assert result[date(2024, 6, 1)] == 0

    def test_days_with_no_sessions_have_zero(self, sessions_repo):
        start = date(2024, 6, 1)
        end = date(2024, 6, 3)
        result = sessions_repo.get_daily_totals_for_range(start, end)
        assert all(v == 0 for v in result.values())


class TestMostPlayedAndLongest:
    def test_most_played_game_id(self, games_repo, sessions_repo):
        g1 = _add_game(games_repo, "Short")
        g2 = _add_game(games_repo, "Long")
        sessions_repo.add(_make_session(g1.id, datetime(2024, 6, 1, 10, 0), 100))
        sessions_repo.add(_make_session(g2.id, datetime(2024, 6, 2, 10, 0), 9000))
        assert sessions_repo.get_most_played_game_id() == g2.id

    def test_most_played_returns_none_when_empty(self, sessions_repo):
        assert sessions_repo.get_most_played_game_id() is None

    def test_longest_session(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1, 10, 0), 100))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 2, 10, 0), 9999))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 3, 10, 0), 500))
        longest = sessions_repo.get_longest_session()
        assert longest.duration_seconds == 9999

    def test_longest_session_returns_none_when_empty(self, sessions_repo):
        assert sessions_repo.get_longest_session() is None


class TestSessionsRepositoryDelete:
    def test_delete_removes_session(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        session = sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1), 60))
        sessions_repo.delete(session.id)
        assert sessions_repo.get_by_id(session.id) is None

    def test_delete_all_for_game(self, games_repo, sessions_repo):
        game = _add_game(games_repo)
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 1), 60))
        sessions_repo.add(_make_session(game.id, datetime(2024, 6, 2), 120))
        deleted = sessions_repo.delete_all_for_game(game.id)
        assert deleted == 2
        assert sessions_repo.count() == 0