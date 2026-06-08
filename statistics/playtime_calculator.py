"""
PlaytimeCalculator: Pure calculation logic for GameTracker statistics.

Responsibilities:
- Lifetime statistics
- Daily statistics
- Weekly statistics
- Monthly statistics

Uses repository layer only. No SQL. No UI.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from database.repositories.sessions_repository import SessionsRepository
from database.repositories.games_repository import GamesRepository
from statistics.models import (
    DailyStats,
    GamePlaytimeSummary,
    LifetimeStats,
    MonthlyStats,
    WeeklyStats,
)

logger = logging.getLogger(__name__)


class PlaytimeCalculator:
    """
    Calculates playtime statistics from session data via repositories.
    All queries go through the repository layer.
    """

    def __init__(
        self,
        sessions_repository: SessionsRepository,
        games_repository: GamesRepository,
    ) -> None:
        self._sessions = sessions_repository
        self._games = games_repository

    # ------------------------------------------------------------------
    # Lifetime
    # ------------------------------------------------------------------

    def get_lifetime_stats(self) -> LifetimeStats:
        """
        Return aggregate statistics across ALL completed sessions.
        Satisfies AC-004.
        """
        logger.info("Calculating lifetime statistics.")

        all_sessions = self._sessions.get_all()

        total_seconds: int = 0
        total_sessions: int = len(all_sessions)
        game_seconds: dict[int, int] = {}
        game_session_counts: dict[int, int] = {}

        longest_session_id: Optional[int] = None
        longest_session_seconds: int = 0
        longest_session_game_id: Optional[int] = None

        first_date: Optional[date] = None
        last_date: Optional[date] = None

        for session in all_sessions:
            duration = session.duration_seconds or 0
            total_seconds += duration

            gid = session.game_id
            game_seconds[gid] = game_seconds.get(gid, 0) + duration
            game_session_counts[gid] = game_session_counts.get(gid, 0) + 1

            if duration > longest_session_seconds:
                longest_session_seconds = duration
                longest_session_id = session.id
                longest_session_game_id = gid

            if session.start_time:
                session_date = (
                    session.start_time.date()
                    if hasattr(session.start_time, "date")
                    else session.start_time
                )
                if first_date is None or session_date < first_date:
                    first_date = session_date
                if last_date is None or session_date > last_date:
                    last_date = session_date

        # Most played game
        most_played_game_id: Optional[int] = None
        most_played_game_seconds: int = 0
        most_played_game_name: Optional[str] = None

        if game_seconds:
            most_played_game_id = max(game_seconds, key=lambda k: game_seconds[k])
            most_played_game_seconds = game_seconds[most_played_game_id]
            game_obj = self._games.get_by_id(most_played_game_id)
            most_played_game_name = game_obj.name if game_obj else None

        # Longest session game name
        longest_session_game_name: Optional[str] = None
        if longest_session_game_id is not None:
            game_obj = self._games.get_by_id(longest_session_game_id)
            longest_session_game_name = game_obj.name if game_obj else None

        return LifetimeStats(
            total_seconds=total_seconds,
            total_sessions=total_sessions,
            total_games_played=len(game_seconds),
            most_played_game_id=most_played_game_id,
            most_played_game_name=most_played_game_name,
            most_played_game_seconds=most_played_game_seconds,
            longest_session_id=longest_session_id,
            longest_session_seconds=longest_session_seconds,
            longest_session_game_name=longest_session_game_name,
            first_session_date=first_date,
            last_session_date=last_date,
        )

    # ------------------------------------------------------------------
    # Daily
    # ------------------------------------------------------------------

    def get_daily_stats(self, target_date: Optional[date] = None) -> DailyStats:
        """
        Return statistics for a given calendar day.
        Defaults to today. Satisfies AC-005.
        """
        if target_date is None:
            target_date = date.today()

        logger.info("Calculating daily statistics for %s.", target_date)

        sessions = self._sessions.get_by_date_range(
            start_date=target_date,
            end_date=target_date,
        )

        total_seconds = 0
        game_breakdown: dict[int, int] = {}

        for session in sessions:
            duration = session.duration_seconds or 0
            total_seconds += duration
            gid = session.game_id
            game_breakdown[gid] = game_breakdown.get(gid, 0) + duration

        return DailyStats(
            date=target_date,
            total_seconds=total_seconds,
            total_sessions=len(sessions),
            game_breakdown=game_breakdown,
        )

    # ------------------------------------------------------------------
    # Weekly
    # ------------------------------------------------------------------

    def get_weekly_stats(
        self,
        target_date: Optional[date] = None,
    ) -> WeeklyStats:
        """
        Return statistics for the ISO week containing target_date.
        Week runs Monday–Sunday. Satisfies AC-006.
        """
        if target_date is None:
            target_date = date.today()

        # ISO: Monday = 0 … Sunday = 6
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)

        logger.info(
            "Calculating weekly statistics for week %s–%s.",
            week_start,
            week_end,
        )

        sessions = self._sessions.get_by_date_range(
            start_date=week_start,
            end_date=week_end,
        )

        total_seconds = 0
        daily_breakdown: dict[date, int] = {}

        for session in sessions:
            duration = session.duration_seconds or 0
            total_seconds += duration

            if session.start_time:
                session_date = (
                    session.start_time.date()
                    if hasattr(session.start_time, "date")
                    else session.start_time
                )
                daily_breakdown[session_date] = (
                    daily_breakdown.get(session_date, 0) + duration
                )

        active_days = len(daily_breakdown)
        average_daily_seconds = (
            total_seconds / active_days if active_days > 0 else 0.0
        )

        iso = target_date.isocalendar()

        return WeeklyStats(
            year=iso[0],
            week_number=iso[1],
            week_start=week_start,
            week_end=week_end,
            total_seconds=total_seconds,
            total_sessions=len(sessions),
            average_daily_seconds=average_daily_seconds,
            daily_breakdown=daily_breakdown,
        )

    # ------------------------------------------------------------------
    # Monthly
    # ------------------------------------------------------------------

    def get_monthly_stats(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> MonthlyStats:
        """
        Return statistics for a given calendar month.
        Defaults to current month. Satisfies AC-007.
        """
        today = date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        month_start = date(year, month, 1)
        # Last day of the month
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        logger.info(
            "Calculating monthly statistics for %d-%02d.", year, month
        )

        sessions = self._sessions.get_by_date_range(
            start_date=month_start,
            end_date=month_end,
        )

        total_seconds = 0
        daily_breakdown: dict[date, int] = {}

        for session in sessions:
            duration = session.duration_seconds or 0
            total_seconds += duration

            if session.start_time:
                session_date = (
                    session.start_time.date()
                    if hasattr(session.start_time, "date")
                    else session.start_time
                )
                daily_breakdown[session_date] = (
                    daily_breakdown.get(session_date, 0) + duration
                )

        active_days = len(daily_breakdown)
        average_daily_seconds = (
            total_seconds / active_days if active_days > 0 else 0.0
        )

        return MonthlyStats(
            year=year,
            month=month,
            total_seconds=total_seconds,
            total_sessions=len(sessions),
            average_daily_seconds=average_daily_seconds,
            daily_breakdown=daily_breakdown,
        )

    # ------------------------------------------------------------------
    # Per-game breakdown helpers
    # ------------------------------------------------------------------

    def get_game_playtime_summaries(self) -> list[GamePlaytimeSummary]:
        """
        Return a list of per-game playtime summaries, sorted by total playtime
        descending.
        """
        all_sessions = self._sessions.get_all()
        all_games = {g.id: g for g in self._games.get_all()}

        game_seconds: dict[int, int] = {}
        game_counts: dict[int, int] = {}

        for session in all_sessions:
            duration = session.duration_seconds or 0
            gid = session.game_id
            game_seconds[gid] = game_seconds.get(gid, 0) + duration
            game_counts[gid] = game_counts.get(gid, 0) + 1

        summaries: list[GamePlaytimeSummary] = []
        for gid, seconds in game_seconds.items():
            game = all_games.get(gid)
            name = game.name if game else f"Unknown ({gid})"
            summaries.append(
                GamePlaytimeSummary(
                    game_id=gid,
                    game_name=name,
                    total_seconds=seconds,
                    session_count=game_counts.get(gid, 0),
                )
            )

        summaries.sort(key=lambda s: s.total_seconds, reverse=True)
        return summaries