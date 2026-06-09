"""
SettingsController.

Wires SettingsView user actions to settings services.
No SQL. No business logic.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from database.repositories.settings_repository import SettingsRepository
from services.export_service import ExportService
from services.startup_service import StartupService
from ui.settings.settings_view import SettingsView
from ui.themes.theme_manager import Theme, ThemeManager

logger = logging.getLogger(__name__)

_SETTINGS_THEME = "dark_mode"
_SETTINGS_STARTUP = "start_with_windows"


class SettingsController:
    """
    Controller for the Settings screen.

    Connects:
        SettingsView signals -> service calls -> SettingsView refresh
    """

    def __init__(
        self,
        view: SettingsView,
        settings_repo: SettingsRepository,
        theme_manager: ThemeManager,
        export_service: ExportService,
        parent_widget: QWidget,
    ) -> None:
        self._view = view
        self._settings_repo = settings_repo
        self._theme_manager = theme_manager
        self._export_service = export_service
        self._parent_widget = parent_widget
        self._connect_signals()
        self._load_settings()

    def _connect_signals(self) -> None:
        self._view.theme_toggled.connect(self._on_theme_toggled)
        self._view.startup_toggled.connect(self._on_startup_toggled)
        self._view.export_csv_requested.connect(self._on_export_csv)
        self._view.export_json_requested.connect(self._on_export_json)

    def _load_settings(self) -> None:
        is_dark = self._settings_repo.get_bool(_SETTINGS_THEME, default=True)
        with_startup = self._settings_repo.get_bool(_SETTINGS_STARTUP, default=False)
        self._view.set_dark_mode(is_dark)
        self._view.set_start_with_windows(with_startup)

    def _on_theme_toggled(self, dark_mode: bool) -> None:
        self._settings_repo.set_bool(_SETTINGS_THEME, dark_mode)
        theme = Theme.DARK if dark_mode else Theme.LIGHT
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            self._theme_manager.apply_theme(app, theme)

    def _on_startup_toggled(self, enabled: bool) -> None:
        self._settings_repo.set_bool(_SETTINGS_STARTUP, enabled)
        if enabled:
            StartupService.register()
        else:
            StartupService.unregister()

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._parent_widget,
            "Export Sessions to CSV",
            str(Path.home() / "sessions.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        ok = self._export_service.export_csv(Path(path))
        if ok:
            QMessageBox.information(
                self._parent_widget, "Export", f"Sessions exported to:\n{path}"
            )
        else:
            QMessageBox.warning(
                self._parent_widget, "Export", "Export failed. See logs for details."
            )

    def _on_export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._parent_widget,
            "Backup to JSON",
            str(Path.home() / "gametracker_backup.json"),
            "JSON Files (*.json)",
        )
        if not path:
            return
        ok = self._export_service.export_backup(Path(path))
        if ok:
            QMessageBox.information(
                self._parent_widget, "Backup", f"Backup saved to:\n{path}"
            )
        else:
            QMessageBox.warning(
                self._parent_widget, "Backup", "Backup failed. See logs for details."
            )
