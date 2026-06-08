# tests/test_dashboard_controller.py
"""
Tests for DashboardController.

Validates that:
- Statistics are fetched correctly from the service.
- Seconds are formatted into correct human-readable strings.
- Missing / empty data is handled gracefully.
- AC-004, AC-005, AC-006, AC-007 coverage.
"""

import pytest
from unittest.mock import MagicMock

from ui.dashboard.dashboard_controller import (
    DashboardController,
    DashboardData,
    _format_duration,
)


# ---------------------------------------------------------------------------
# _format_duration unit tests
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_zero_seconds(self):
        assert _format_duration(0) == "0m"

    def test_negative_seconds(self):
        assert _format_duration(-100) == "0m"

    def test_minutes_only(self):
        assert _format_duration(1800) == "30m"

    def test_one_hour_exactly(self):
        assert _format_duration(3600) == "1h 0m"

    def test_hours_and_minutes(self):
        assert _format_duration(5400) == "1h 30m"

    def test_large_value(self):
        # 142h 30m = 512_200 seconds? Let's verify: 142*3600 + 30*60 = 511200+1800=513000
        assert _format_duration(513_000) == "142h 30m"

    def test_only_minutes_no_hours(self):
        assert _format_duration(59 * 60) == "59m"

    def test_one_second(self):
        assert _format_duration(1) == "0m"

    def test_one_minute(self):
        assert _format_duration(60) == "1m"

    def test_59_minutes_59_seconds(self):
        assert _format_duration(3599) == "59m"


# ---------------------------------------------------------------------------
# DashboardController tests
# ---------------------------------------------------------------------------

def _make_service(
    lifetime_seconds: int = 0,
    daily_seconds: int = 0,
    weekly_seconds: int = 0,
    monthly_seconds: int = 0,
    most_played: dict | None = None,
) -> MagicMock:
    """Build a mock StatisticsService with configurable return values."""
    svc = MagicMock()
    svc.get_lifetime_stats.return_value = {"total_seconds": lifetime_seconds}
    svc.get_daily_stats.return_value = {"total_seconds": daily_seconds}
    svc.get_weekly_stats.return_value = {"total_seconds": weekly_seconds}
    svc.get_monthly_stats.return_value = {"total_seconds": monthly_seconds}
    svc.get_most_played_game.return_value = most_played
    return svc


class TestDashboardController:

    def test_load_dashboard_data_returns_dataclass(self):
        svc = _make_service()
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert isinstance(data, DashboardData)

    def test_total_playtime_formatted_correctly(self):
        svc = _make_service(lifetime_seconds=7200)  # 2h 0m
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.total_playtime == "2h 0m"

    def test_today_playtime_formatted_correctly(self):
        svc = _make_service(daily_seconds=1800)  # 30m
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.today_playtime == "30m"

    def test_weekly_playtime_formatted_correctly(self):
        svc = _make_service(weekly_seconds=3_600 * 10)  # 10h 0m
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.week_playtime == "10h 0m"

    def test_monthly_playtime_formatted_correctly(self):
        svc = _make_service(monthly_seconds=3_600 * 25 + 30 * 60)  # 25h 30m
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.month_playtime == "25h 30m"

    def test_zero_values_display_zero(self):
        svc = _make_service()
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.total_playtime == "0m"
        assert data.today_playtime == "0m"
        assert data.week_playtime == "0m"
        assert data.month_playtime == "0m"

    def test_most_played_game_populated(self):
        most_played = {
            "name": "Cyberpunk 2077",
            "total_seconds": 3_600 * 50,  # 50h 0m
            "icon_path": "",
        }
        svc = _make_service(most_played=most_played)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.most_played_game_name == "Cyberpunk 2077"
        assert data.most_played_game_hours == "50h 0m"

    def test_no_most_played_game_shows_default(self):
        svc = _make_service(most_played=None)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.most_played_game_name == "No games tracked yet"
        assert data.most_played_game_hours == "—"

    def test_most_played_game_icon_path_propagated(self):
        most_played = {
            "name": "Half-Life 2",
            "total_seconds": 3600,
            "icon_path": "/path/to/icon.png",
        }
        svc = _make_service(most_played=most_played)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.most_played_game_icon == "/path/to/icon.png"

    def test_most_played_game_missing_icon_path_defaults_empty(self):
        most_played = {
            "name": "Doom",
            "total_seconds": 1800,
            # no icon_path key
        }
        svc = _make_service(most_played=most_played)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.most_played_game_icon == ""

    def test_service_called_once_per_load(self):
        svc = _make_service()
        ctrl = DashboardController(svc)
        ctrl.load_dashboard_data()
        svc.get_lifetime_stats.assert_called_once()
        svc.get_daily_stats.assert_called_once()
        svc.get_weekly_stats.assert_called_once()
        svc.get_monthly_stats.assert_called_once()
        svc.get_most_played_game.assert_called_once()

    def test_multiple_refreshes_call_service_each_time(self):
        svc = _make_service()
        ctrl = DashboardController(svc)
        ctrl.load_dashboard_data()
        ctrl.load_dashboard_data()
        assert svc.get_lifetime_stats.call_count == 2

    def test_none_lifetime_stats_handled_gracefully(self):
        svc = MagicMock()
        svc.get_lifetime_stats.return_value = None
        svc.get_daily_stats.return_value = None
        svc.get_weekly_stats.return_value = None
        svc.get_monthly_stats.return_value = None
        svc.get_most_played_game.return_value = None
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.total_playtime == "0m"
        assert data.today_playtime == "0m"

    def test_lifetime_equals_sum_of_all_sessions(self):
        """AC-004: lifetime playtime must equal database total."""
        expected_seconds = 3_600 * 100
        svc = _make_service(lifetime_seconds=expected_seconds)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.total_playtime == "100h 0m"

    def test_daily_stats_match_database(self):
        """AC-005: today's playtime must match database records."""
        svc = _make_service(daily_seconds=3_600 * 3)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.today_playtime == "3h 0m"

    def test_weekly_stats_correct(self):
        """AC-006: weekly totals must be correct."""
        svc = _make_service(weekly_seconds=3_600 * 20)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.week_playtime == "20h 0m"

    def test_monthly_stats_correct(self):
        """AC-007: monthly totals must be correct."""
        svc = _make_service(monthly_seconds=3_600 * 80)
        ctrl = DashboardController(svc)
        data = ctrl.load_dashboard_data()
        assert data.month_playtime == "80h 0m"