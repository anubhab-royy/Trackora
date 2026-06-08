"""
TrayService — Phase 9
System tray icon and context menu for GameTracker.

Provides:
    - Tray icon with application icon
    - Context menu: Show/Hide, Dashboard, History, Quit
    - Minimize-to-tray behavior (connected by the application window)
    - Signals for main window integration

Usage:
    tray = TrayService(parent_window)
    tray.show()
    tray.hide_window_action.setVisible(False)  # after minimizing

Requirements:
    - AC-012: System Tray
        When main window closed, application minimizes to tray.
        Tracking continues in background.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

logger = logging.getLogger(__name__)

_ICON_PATH = Path(__file__).resolve().parent.parent / "ui" / "icons" / "app_icon.png"


class TrayService(QObject):
    """
    System tray icon for GameTracker.

    Signals:
        show_requested      — user clicked "Show" or double-clicked tray icon
        hide_requested      — user clicked "Hide"
        dashboard_requested — user clicked "Dashboard"
        history_requested   — user clicked "History"
        quit_requested      — user clicked "Quit"

    Args:
        parent_window: The main QWidget that should be shown/hidden.
        parent:        Optional QObject parent.
    """

    show_requested = pyqtSignal()
    hide_requested = pyqtSignal()
    dashboard_requested = pyqtSignal()
    history_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(
        self,
        parent_window: QWidget,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._window = parent_window
        self._tray_icon: Optional[QSystemTrayIcon] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Create and display the tray icon with context menu."""
        if self._tray_icon is not None:
            return  # already created

        icon = self._load_icon()

        self._tray_icon = QSystemTrayIcon(icon, self._window)
        self._tray_icon.setToolTip("GameTracker")

        menu = self._build_menu()
        self._tray_icon.setContextMenu(menu)

        self._tray_icon.activated.connect(self._on_activated)
        self._tray_icon.show()

        logger.info("TrayService: icon displayed.")

    def hide(self) -> None:
        """Remove the tray icon."""
        if self._tray_icon is not None:
            self._tray_icon.hide()
            self._tray_icon = None
            logger.info("TrayService: icon hidden.")

    def is_visible(self) -> bool:
        """Return True if the tray icon is currently shown."""
        return self._tray_icon is not None and self._tray_icon.isVisible()

    def show_notification(
        self, title: str, message: str, duration_ms: int = 5000
    ) -> None:
        """
        Show a balloon/notification from the tray icon.

        Args:
            title:      Notification title.
            message:    Notification body text.
            duration_ms: How long to show the notification (platform-dependent).
        """
        if self._tray_icon is not None and self._tray_icon.supportsMessages():
            icon_type = QSystemTrayIcon.MessageIcon.Information
            self._tray_icon.showMessage(
                title, message, icon_type, duration_ms
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_icon(self) -> QIcon:
        """Load the application icon, or return a default pixmap icon."""
        if _ICON_PATH.is_file():
            return QIcon(str(_ICON_PATH))
        # Fallback: create a simple coloured pixmap
        pixmap = QPixmap(64, 64)
        pixmap.fill()
        return QIcon(pixmap)

    def _build_menu(self) -> QMenu:
        """Build the tray context menu."""
        menu = QMenu()

        self.show_action = QAction("Show GameTracker", menu)
        self.show_action.triggered.connect(self.show_requested.emit)
        menu.addAction(self.show_action)

        self.hide_action = QAction("Hide", menu)
        self.hide_action.triggered.connect(self.hide_requested.emit)
        menu.addAction(self.hide_action)

        menu.addSeparator()

        self.dashboard_action = QAction("Dashboard", menu)
        self.dashboard_action.triggered.connect(self.dashboard_requested.emit)
        menu.addAction(self.dashboard_action)

        self.history_action = QAction("History", menu)
        self.history_action.triggered.connect(self.history_requested.emit)
        menu.addAction(self.history_action)

        menu.addSeparator()

        self.quit_action = QAction("Quit", menu)
        self.quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(self.quit_action)

        return menu

    def _on_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        """Handle tray icon activation (click/double-click)."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_requested.emit()
