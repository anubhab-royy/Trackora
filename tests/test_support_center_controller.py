"""Tests for SupportCenterController."""

from unittest.mock import MagicMock, patch

import pytest

from ui.support_center.support_center_controller import SupportCenterController


@pytest.fixture
def mock_view():
    return MagicMock()


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.get_upcoming_updates.return_value = []
    return svc


class TestSupportCenterController:
    def test_controller_initialises(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        assert ctrl is not None

    def test_controller_calls_load_upcoming_updates_on_init(
        self, mock_view, mock_service
    ):
        SupportCenterController(mock_view, mock_service)
        mock_service.get_upcoming_updates.assert_called_once()

    def test_controller_sets_updates_on_view(self, mock_view, mock_service):
        SupportCenterController(mock_view, mock_service)
        mock_view.set_upcoming_updates.assert_called_once_with([])

    def test_navigate_to_calls_view_navigate_to(self, mock_view, mock_service):
        ctrl = SupportCenterController(mock_view, mock_service)
        ctrl.navigate_to("report_bug")
        mock_view.navigate_to.assert_called_once_with("report_bug")

    def test_on_page_changed_updates_page_loads_updates(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_page_changed("upcoming_updates")
        mock_service.get_upcoming_updates.assert_called_once()

    def test_on_page_changed_other_pages_do_not_load_updates(
        self, mock_view, mock_service
    ):
        ctrl = SupportCenterController(mock_view, mock_service)
        mock_service.reset_mock()
        mock_view.reset_mock()
        ctrl._on_page_changed("report_bug")
        mock_service.get_upcoming_updates.assert_not_called()
