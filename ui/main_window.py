"""
MainWindow — Phase 12
Application-level window that assembles all UI views into a single
QMainWindow with sidebar navigation.

Architecture:
  - Creates views and controllers, wires them together.
  - Hosts them in a QStackedWidget switched by the sidebar.
  - Integrates TrayService for minimize-to-tray.
  - Provides theme toggle and export actions.
  - Processes offline report queue on startup.
  - Detects unexpected shutdowns and prompts user.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QAction, QKeySequence

from database.repositories import (
    ActiveSessionsRepository,
    GamesRepository,
    SettingsRepository,
)
from services.crash.crash_service import CrashService
from services.crash.diagnostic_service import DiagnosticService
from services.export_service import ExportService
from services.game_service import GameService
from services.session_history_service import SessionHistoryService
from services.support.github_issue_service import GitHubIssueService
from services.support.report_queue_service import ReportQueueService
from services.support.reporting_interface import AbstractReportService
from services.support.support_service import SupportService
from services.tray_service import TrayService
from services.update_announcements_service import UpdateAnnouncementsService
from services.update_center_service import UpdateCenterService
from tracker.tracking_state import TrackingState
from trackora.core.build_info import BUILD_CHANNEL
from trackora.core.environment import Environment
from trackora_stats.statistics_service import StatisticsService
from ui.crash_dialog import CrashDialog
from ui.dashboard.dashboard_controller import DashboardController
from ui.dashboard.dashboard_widget import DashboardWidget
from ui.games.games_controller import GamesController
from ui.games.games_view import GamesView
from ui.history.history_controller import HistoryController
from ui.history.history_view import HistoryView
from ui.settings.settings_controller import SettingsController
from ui.settings.settings_view import SettingsView
from ui.support_center.support_center_controller import SupportCenterController
from ui.support_center.support_center_widget import SupportCenterWidget
from ui.dialogs.update_dialog import UpdateDialog
from ui.themes.theme_manager import Theme, ThemeManager
from ui.widgets.charts_controller import ChartsController
from ui.widgets.charts_view import ChartsView
from ui.widgets.update_banner import UpdateBanner

logger = logging.getLogger(__name__)

_NAV_ITEMS = ["Dashboard", "Games", "History", "Charts", "Settings", "Support Center"]


class MainWindow(QMainWindow):
    """
    Main application window with sidebar navigation.

    Owns all views and controllers.  Exposes methods
    for tray service and menu actions.
    """

    def __init__(
        self,
        game_service: GameService,
        session_history_service: SessionHistoryService,
        statistics_service: StatisticsService,
        export_service: ExportService,
        theme_manager: ThemeManager,
        settings_repo: SettingsRepository,
        active_sessions_repo: ActiveSessionsRepository,
        games_repo: GamesRepository,
        support_service: SupportService | None = None,
        tracking_state: TrackingState | None = None,
        report_service: AbstractReportService | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._game_service = game_service
        self._session_history_service = session_history_service
        self._statistics_service = statistics_service
        self._export_service = export_service
        self._theme_manager = theme_manager
        self._settings_repo = settings_repo
        self._active_repo = active_sessions_repo
        self._games_repo = games_repo
        self._tracking_state = tracking_state

        self._diagnostic_service = DiagnosticService()
        self._crash_service = CrashService(self._diagnostic_service)
        self._report_service: AbstractReportService = (
            report_service or GitHubIssueService(self._settings_repo)
        )
        self._queue_service = ReportQueueService()
        self._announcements_service = UpdateAnnouncementsService(
            remote_url=self._get_announcements_url(),
        )
        self._support_service = support_service or SupportService(
            github_service=self._report_service,
            queue_service=self._queue_service,
            announcements_service=self._announcements_service,
        )

        self._check_for_crashes()
        self._crash_service.mark_startup()

        self._process_report_queue()

        self.setWindowTitle(self._window_title())
        self.setMinimumSize(1000, 650)
        self.resize(1200, 750)

        self._setup_ui()
        self._build_views()
        self._connect_nav()
        self._create_menu_actions()
        self._setup_tray()
        self._setup_auto_refresh()

        # Non-blocking startup update check
        QTimer.singleShot(5000, self._perform_startup_update_check)

        # Ensure clean shutdown even on OS shutdown
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._on_about_to_quit)

        logger.info("MainWindow initialised.")

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        suffix = {
            Environment.DEVELOPMENT: " [DEV]",
        }.get(BUILD_CHANNEL, "")
        title = QLabel(f"Trackora{suffix}")
        title.setObjectName("AppTitle")
        sidebar_layout.addWidget(title)

        self._nav = QListWidget()
        self._nav.setObjectName("NavList")
        for name in _NAV_ITEMS:
            self._nav.addItem(QListWidgetItem(name))

        sidebar_layout.addWidget(self._nav, stretch=1)

        content_frame = QWidget()
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._update_banner = UpdateBanner(content_frame)
        self._update_banner.hide()
        self._update_banner.ignored.connect(self._on_update_banner_ignored)
        self._update_banner.view_notes_requested.connect(self._on_show_release_notes)

        content_layout.addWidget(self._update_banner)

        self._content = QStackedWidget()
        self._content.setObjectName("ContentArea")
        content_layout.addWidget(self._content, stretch=1)

        root.addWidget(sidebar)
        root.addWidget(content_frame, stretch=1)

    def _build_views(self) -> None:
        self._dash_ctrl = DashboardController(
            self._statistics_service, self._active_repo, self._games_repo
        )
        self._dash_view = DashboardWidget(self._dash_ctrl, self)
        self._content.addWidget(self._dash_view)

        # Discovery orchestrator for "Scan For Games"
        from tracker.discovery.orchestrator import DiscoveryOrchestrator
        discovery_orchestrator = DiscoveryOrchestrator(
            exists_by_executable_path=self._games_repo.get_by_executable_path,
            exists_by_platform_id=self._games_repo.exists_by_platform_id,
        )

        self._games_view = GamesView(self)
        self._games_ctrl = GamesController(
            self._games_view, self._game_service, discovery_orchestrator
        )
        self._content.addWidget(self._games_view)

        self._hist_view = HistoryView(self)
        self._hist_ctrl = HistoryController(
            self._hist_view, self._session_history_service
        )
        self._content.addWidget(self._hist_view)

        self._charts_view = ChartsView(self)
        self._charts_ctrl = ChartsController(
            self._charts_view, self._statistics_service
        )
        self._content.addWidget(self._charts_view)

        self._update_service = UpdateCenterService(
            settings_repo=self._settings_repo,
            repo="anomalyco/trackora",
        )

        self._settings_view = SettingsView(self)
        self._settings_ctrl = SettingsController(
            view=self._settings_view,
            settings_repo=self._settings_repo,
            theme_manager=self._theme_manager,
            export_service=self._export_service,
            parent_widget=self,
            update_service=self._update_service,
        )
        self._content.addWidget(self._settings_view)

        self._support_view = SupportCenterWidget(self)
        self._support_ctrl = SupportCenterController(
            view=self._support_view,
            support_service=self._support_service,
        )
        self._content.addWidget(self._support_view)

    def _connect_nav(self) -> None:
        self._nav.currentRowChanged.connect(self._content.setCurrentIndex)
        self._nav.setCurrentRow(0)

    def _create_menu_actions(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        csv_action = QAction("Export CSV...", self)
        csv_action.setShortcut(QKeySequence("Ctrl+E"))
        csv_action.triggered.connect(self.export_csv)
        file_menu.addAction(csv_action)

        json_action = QAction("Backup JSON...", self)
        json_action.setShortcut(QKeySequence("Ctrl+B"))
        json_action.triggered.connect(self.export_json)
        file_menu.addAction(json_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self._quit_app)
        file_menu.addAction(quit_action)

        view_menu = menu.addMenu("&View")

        theme_action = QAction("Toggle Theme", self)
        theme_action.setShortcut(QKeySequence("Ctrl+T"))
        theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(theme_action)

    def _setup_tray(self) -> None:
        self._tray = TrayService(self, self)
        self._tray.show_requested.connect(self._show_from_tray)
        self._tray.dashboard_requested.connect(lambda: (self.switch_to("Dashboard"), self._show_from_tray()))
        self._tray.history_requested.connect(lambda: (self.switch_to("History"), self._show_from_tray()))
        self._tray.check_updates_requested.connect(self._on_check_updates_from_tray)
        self._tray.quit_requested.connect(self._quit_app)
        self._tray.show()

    def _setup_auto_refresh(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_current_view)
        self._refresh_timer.start(5000)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def closeEvent(self, event):  # type: ignore[override]
        event.ignore()
        self.hide()

    def _show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_about_to_quit(self) -> None:
        """Ensure clean shutdown is marked.

        Handles OS shutdown (WM_ENDSESSION) and any path where
        app.quit() is called without going through _quit_app.
        """
        self._crash_service.mark_clean_shutdown()

    def _quit_app(self) -> None:
        self._crash_service.mark_clean_shutdown()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _perform_startup_update_check(self) -> None:
        """Check for updates at startup, non-blocking."""
        if not self._settings_repo.get_bool("update_auto_check_enabled", default=True):
            return
        try:
            result = self._update_service.check_for_updates()
            if result.update_available and self._update_service.is_update_available():
                assert result.release is not None
                self._update_banner.show(
                    result.release.version, result.release.body
                )
                self._tray.show_notification(
                    "Trackora Update",
                    f"Trackora {result.release.version} is ready to download",
                )
        except Exception as exc:
            logger.warning("Startup update check failed: %s", exc)

    def _on_update_banner_ignored(self, version: str) -> None:
        self._update_service.ignore_version(version)

    def _on_check_updates_from_tray(self) -> None:
        result = self._update_service.check_for_updates()
        UpdateDialog(result, parent=self).exec()

    def _on_show_release_notes(self) -> None:
        result = self._update_service.get_cached_result()
        if result and result.release:
            UpdateDialog(result, parent=self).exec()

    def _refresh_current_view(self) -> None:
        widget = self._content.currentWidget()
        if isinstance(widget, DashboardWidget):
            widget.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def switch_to(self, page: str) -> None:
        try:
            idx = _NAV_ITEMS.index(page)
            self._nav.setCurrentRow(idx)
        except ValueError:
            logger.warning("Unknown page: %s", page)

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Sessions to CSV",
            str(Path.home() / "sessions.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        ok = self._export_service.export_csv(Path(path))
        if ok:
            QMessageBox.information(
                self, "Export", f"Sessions exported to:\n{path}"
            )
        else:
            QMessageBox.warning(
                self, "Export", "Export failed. See logs for details."
            )

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup to JSON",
            str(Path.home() / "trackora_backup.json"),
            "JSON Files (*.json)",
        )
        if not path:
            return
        ok = self._export_service.export_backup(Path(path))
        if ok:
            QMessageBox.information(
                self, "Backup", f"Backup saved to:\n{path}"
            )
        else:
            QMessageBox.warning(
                self, "Backup", "Backup failed. See logs for details."
            )

    def toggle_theme(self) -> None:
        current = self._theme_manager.current_theme
        new_theme = Theme.LIGHT if current == Theme.DARK else Theme.DARK
        app = QApplication.instance()
        if app is not None:
            self._theme_manager.apply_theme(app, new_theme)

    # ------------------------------------------------------------------
    # Queue processing
    # ------------------------------------------------------------------

    def _process_report_queue(self) -> None:
        """Scan and submit any pending offline reports."""
        pending = self._queue_service.count_pending()
        if pending == 0:
            return
        logger.info("Found %d pending report(s), processing queue...", pending)
        try:
            result = self._support_service.process_queue()
            if result and result.succeeded:
                logger.info(
                    "Queue processing complete: %d submitted, %d failed.",
                    result.succeeded,
                    result.failed,
                )
        except Exception as exc:
            logger.error("Queue processing error: %s", exc)

    # ------------------------------------------------------------------
    # Crash detection
    # ------------------------------------------------------------------

    def _check_for_crashes(self) -> None:
        """Check if the previous session crashed and prompt the user."""
        try:
            active: list[dict[str, Any]] = []
            tracked = 0
            was_tracking = False
            if self._tracking_state is not None:
                for session in self._tracking_state.active_sessions.values():
                    active.append({
                        "game_id": session.game_id,
                        "game_name": session.game_name,
                        "process_id": session.process_id,
                    })
                tracked = len(self._tracking_state.tracked_games)
                was_tracking = self._tracking_state.is_running

            result = self._crash_service.check_for_crash(
                active_sessions=active,
                tracked_games=tracked,
                was_tracking=was_tracking,
            )
            if not result.has_crashed:
                return

            dialog = CrashDialog(
                report=result.report,
                report_path=result.report_path,
                github_service=self._report_service,
                queue_service=self._queue_service,
                parent=self,
            )
            dialog.exec()
        except Exception as exc:
            logger.error("Crash check failed: %s", exc)

    # ------------------------------------------------------------------
    # Announcements URL
    # ------------------------------------------------------------------

    @staticmethod
    def _window_title() -> str:
        suffix = {
            Environment.DEVELOPMENT: " [DEV]",
        }.get(BUILD_CHANNEL, "")
        return f"Trackora{suffix}"

    @staticmethod
    def _get_announcements_url() -> str:
        """Return the remote URL for update announcements.

        The URL and JSON format are configured separately from the
        codebase.  This method exists so it can be overridden or
        replaced with a user-configurable setting in the future.
        """
        return (
            "https://raw.githubusercontent.com/"
            "anomalco/trackora-announcements/main/announcements.json"
        )
