"""
Tests for TrayService — Phase 9.

Covers:
  - Construction
  - show / hide / is_visible
  - Signal connections

Qt-based tests require the qapp fixture (session-scoped QApplication).
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class TestTrayService:
    def test_construction(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)
        assert tray._window is window
        assert tray._tray_icon is None

    def test_show_creates_tray_icon(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_instance = MagicMock()
            mock_tray_cls.return_value = mock_instance
            mock_instance.isVisible.return_value = True

            tray.show()
            assert tray._tray_icon is not None
            mock_tray_cls.assert_called_once()
            mock_instance.show.assert_called_once()

    def test_is_visible_returns_false_before_show(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)
        assert tray.is_visible() is False

    def test_is_visible_returns_true_after_show(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_instance = MagicMock()
            mock_instance.isVisible.return_value = True
            mock_tray_cls.return_value = mock_instance

            tray.show()
            assert tray.is_visible() is True

    def test_hide_removes_tray_icon(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_instance = MagicMock()
            mock_tray_cls.return_value = mock_instance

            tray.show()
            assert tray._tray_icon is not None
            tray.hide()
            assert tray._tray_icon is None
            mock_instance.hide.assert_called_once()

    def test_show_is_idempotent(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_tray_cls.return_value = MagicMock()
            tray.show()
            tray.show()  # second call should not create new icon
            assert mock_tray_cls.call_count == 1

    def test_signals_defined(self, qapp) -> None:
        from PyQt6.QtCore import QMetaMethod
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        # Verify signals exist by checking they can be connected
        def dummy() -> None: pass
        tray.show_requested.connect(dummy)
        tray.dashboard_requested.connect(dummy)
        tray.history_requested.connect(dummy)
        tray.quit_requested.connect(dummy)
        # If we get here without error, signals exist

    def test_show_action_triggers_signal(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_tray_cls.return_value = MagicMock()
            tray.show()

            fired = False

            def on_show() -> None:
                nonlocal fired
                fired = True

            tray.show_requested.connect(on_show)
            tray.show_action.trigger()
            assert fired is True

    def test_quit_action_triggers_signal(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_tray_cls.return_value = MagicMock()
            tray.show()

            fired = False

            def on_quit() -> None:
                nonlocal fired
                fired = True

            tray.quit_requested.connect(on_quit)
            tray.quit_action.trigger()
            assert fired is True

    def test_menu_actions_created(self, qapp) -> None:
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_tray_cls.return_value = MagicMock()
            tray.show()

            assert tray.show_action is not None
            assert tray.dashboard_action is not None
            assert tray.history_action is not None
            assert tray.quit_action is not None

    def test_activated_connects_to_tray_icon(self, qapp) -> None:
        """show() connects the activated signal."""
        from PyQt6.QtWidgets import QWidget
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch(
            "services.tray_service.QSystemTrayIcon"
        ) as mock_tray_cls:
            mock_instance = MagicMock()
            mock_tray_cls.return_value = mock_instance
            tray.show()

            mock_instance.activated.connect.assert_called_once_with(
                tray._on_activated
            )

    def test_double_click_calls_show_requested_emit(self, qapp) -> None:
        """_on_activated emits show_requested for DoubleClick."""
        from PyQt6.QtWidgets import QWidget
        from PyQt6.QtWidgets import QSystemTrayIcon
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch.object(tray, "show_requested") as mock_signal:
            reason = QSystemTrayIcon.ActivationReason.DoubleClick
            tray._on_activated(reason)
            mock_signal.emit.assert_called_once()

    def test_other_activation_does_not_emit(self, qapp) -> None:
        """_on_activated does not emit for non-double-click reasons."""
        from PyQt6.QtWidgets import QWidget
        from PyQt6.QtWidgets import QSystemTrayIcon
        from services.tray_service import TrayService

        window = QWidget()
        tray = TrayService(window)

        with patch.object(tray, "show_requested") as mock_signal:
            reason = QSystemTrayIcon.ActivationReason.Trigger
            tray._on_activated(reason)
            mock_signal.emit.assert_not_called()
