# ui/widgets/__init__.py
"""Reusable UI widgets for GameTracker."""

from ui.widgets.stat_card import StatCard
from ui.widgets.game_card import GameCard
from ui.widgets.daily_activity_chart import DailyActivityChart
from ui.widgets.monthly_trend_chart import MonthlyTrendChart
from ui.widgets.game_distribution_chart import GameDistributionChart
from ui.widgets.charts_view import ChartsView
from ui.widgets.charts_controller import ChartsController

__all__ = [
    "StatCard",
    "GameCard",
    "DailyActivityChart",
    "MonthlyTrendChart",
    "GameDistributionChart",
    "ChartsView",
    "ChartsController",
]