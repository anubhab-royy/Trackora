from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(scope="module")
def main_window(qapp):
    from ui.main_window import MainWindow
    mw = MainWindow(
        game_service=MagicMock(),
        session_history_service=MagicMock(),
        statistics_service=MagicMock(),
        export_service=MagicMock(),
        theme_manager=MagicMock(),
        settings_repo=MagicMock(),
        active_sessions_repo=MagicMock(),
        games_repo=MagicMock(),
    )
    yield mw


class TestNavigationMapping:
    def test_content_has_correct_number_of_pages(self, main_window):
        assert main_window._content.count() == 6

    def test_nav_index_0_is_dashboard(self, main_window):
        from ui.dashboard.dashboard_widget import DashboardWidget
        assert isinstance(main_window._content.widget(0), DashboardWidget)

    def test_nav_index_1_is_games(self, main_window):
        from ui.games.games_view import GamesView
        assert isinstance(main_window._content.widget(1), GamesView)

    def test_nav_index_2_is_history(self, main_window):
        from ui.history.history_view import HistoryView
        assert isinstance(main_window._content.widget(2), HistoryView)

    def test_nav_index_3_is_charts(self, main_window):
        from ui.widgets.charts_view import ChartsView
        assert isinstance(main_window._content.widget(3), ChartsView)

    def test_nav_index_4_is_settings(self, main_window):
        from ui.settings.settings_view import SettingsView
        assert isinstance(main_window._content.widget(4), SettingsView)

    def test_nav_index_5_is_support_center(self, main_window):
        from ui.support_center.support_center_widget import SupportCenterWidget
        assert isinstance(main_window._content.widget(5), SupportCenterWidget)

    def test_set_current_row_shows_correct_page(self, main_window):
        from ui.dashboard.dashboard_widget import DashboardWidget
        from ui.games.games_view import GamesView
        from ui.history.history_view import HistoryView
        from ui.widgets.charts_view import ChartsView
        from ui.settings.settings_view import SettingsView
        from ui.support_center.support_center_widget import SupportCenterWidget

        expected_types = [
            DashboardWidget,
            GamesView,
            HistoryView,
            ChartsView,
            SettingsView,
            SupportCenterWidget,
        ]
        for idx, expected in enumerate(expected_types):
            main_window._nav.setCurrentRow(idx)
            assert isinstance(main_window._content.currentWidget(), expected), (
                f"Nav index {idx} should show {expected.__name__}"
            )

    def test_switch_to_dashboard(self, main_window):
        from ui.dashboard.dashboard_widget import DashboardWidget
        main_window.switch_to("Dashboard")
        assert isinstance(main_window._content.currentWidget(), DashboardWidget)

    def test_switch_to_support_center(self, main_window):
        from ui.support_center.support_center_widget import SupportCenterWidget
        main_window.switch_to("Support Center")
        assert isinstance(main_window._content.currentWidget(), SupportCenterWidget)


class TestUpdateBannerIsolation:
    def test_update_banner_not_in_stacked_widget(self, main_window):
        for i in range(main_window._content.count()):
            assert not isinstance(main_window._content.widget(i), main_window._update_banner.__class__), (
                f"UpdateBanner should not be at stacked widget index {i}"
            )

    def test_update_banner_is_hidden_after_construction(self, main_window):
        assert main_window._update_banner.isHidden() is True

    def test_update_banner_signals_connected(self, main_window):
        assert main_window._update_banner.receivers(
            main_window._update_banner.ignored
        ) > 0
        assert main_window._update_banner.receivers(
            main_window._update_banner.view_notes_requested
        ) > 0


class TestNavItemsCount:
    def test_nav_items_match_content_pages(self, main_window):
        from ui.main_window import _NAV_ITEMS
        assert main_window._content.count() == len(_NAV_ITEMS)

    def test_nav_list_has_same_count_as_content(self, main_window):
        assert main_window._nav.count() == main_window._content.count()
