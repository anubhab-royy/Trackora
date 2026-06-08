"""
Statistics package for GameTracker.
Provides lifetime, daily, weekly, monthly statistics and trend analysis.
"""

from statistics.models import (
    DailyActivity,
    DailyStats,
    GamePlaytimeSummary,
    LifetimeStats,
    MonthlyActivity,
    MonthlyStats,
    TrendData,
    WeeklyStats,
)
from statistics.playtime_calculator import PlaytimeCalculator
from statistics.statistics_service import StatisticsService
from statistics.trend_analyzer import TrendAnalyzer

__all__ = [
    "DailyActivity",
    "DailyStats",
    "GamePlaytimeSummary",
    "LifetimeStats",
    "MonthlyActivity",
    "MonthlyStats",
    "MonthlyStats",
    "PlaytimeCalculator",
    "StatisticsService",
    "TrendAnalyzer",
    "TrendData",
    "WeeklyStats",
]
