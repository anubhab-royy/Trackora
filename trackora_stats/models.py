"""
Dataclasses representing statistics results for Trackora.
All durations are stored in seconds unless otherwise noted.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class LifetimeStats:
    """Aggregate statistics across all recorded sessions."""
    total_seconds: int
    total_sessions: int
    total_games_played: int
    most_played_game_id: Optional[int]
    most_played_game_name: Optional[str]
    most_played_game_seconds: int
    longest_session_id: Optional[int]
    longest_session_seconds: int
    longest_session_game_name: Optional[str]
    first_session_date: Optional[date]
    last_session_date: Optional[date]


@dataclass
class DailyStats:
    """Statistics for a single calendar day."""
    date: date
    total_seconds: int
    total_sessions: int
    game_breakdown: dict[int, int] = field(default_factory=dict)
    """game_id -> seconds played on that day."""


@dataclass
class WeeklyStats:
    """Statistics for an ISO calendar week (Monday–Sunday)."""
    year: int
    week_number: int
    week_start: date
    week_end: date
    total_seconds: int
    total_sessions: int
    average_daily_seconds: float
    """Average playtime per active day (days with at least one session)."""
    daily_breakdown: dict[date, int] = field(default_factory=dict)
    """date -> seconds played on that day."""


@dataclass
class MonthlyStats:
    """Statistics for a calendar month."""
    year: int
    month: int
    total_seconds: int
    total_sessions: int
    average_daily_seconds: float
    """Average playtime per active day (days with at least one session)."""
    daily_breakdown: dict[date, int] = field(default_factory=dict)
    """date -> seconds played on that day."""


@dataclass
class TrendData:
    """Trend comparison between two periods."""
    current_period_seconds: int
    previous_period_seconds: int
    change_seconds: int
    change_percent: Optional[float]
    """None when previous period had zero playtime (undefined percentage)."""
    is_increase: bool
    is_neutral: bool


@dataclass
class GamePlaytimeSummary:
    """Per-game playtime summary used in breakdowns."""
    game_id: int
    game_name: str
    total_seconds: int
    session_count: int


@dataclass
class DailyActivity:
    """Daily activity data for charting (last N days)."""
    dates: list[date]
    values: list[int]
    """Seconds per day."""
    max_value: int


@dataclass
class MonthlyActivity:
    """Monthly activity data for charting (last N months)."""
    labels: list[str]
    """YYYY-MM format labels."""
    values: list[int]
    """Seconds per month."""
    max_value: int