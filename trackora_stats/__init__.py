"""
Statistics package for Trackora.
Provides lifetime, daily, weekly, monthly statistics and trend analysis.
"""

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
from .statistics_service import StatisticsService
from .trend_analyzer import TrendAnalyzer

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
