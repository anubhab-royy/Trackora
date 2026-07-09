"""
SettingsController.

Wires SettingsView user actions to settings services.
No SQL. No business logic.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

from database.repositories.settings_repository import SettingsRepository
from services.export_service import ExportService
from services.startup_service import StartupService
from services.update_center_service import UpdateCenterService, UpdateCheckResult
from ui.dialogs.update_dialog import UpdateDialog
from ui.settings.settings_view import SettingsView
from ui.themes.theme_manager import Theme, ThemeManager

logger = logging.getLogger(__name__)

_SETTINGS_THEME = "dark_mode"
_SETTINGS_STARTUP = "start_with_windows"
_SETTINGS_AUTO_CHECK = "update_auto_check_enabled"


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
        update_service: UpdateCenterService | None = None,
    ) -> None:
        self._view = view
        self._settings_repo = settings_repo
        self._theme_manager = theme_manager
        self._export_service = export_service
        self._parent_widget = parent_widget
        self._update_service = update_service
        self._connect_signals()
        self._load_settings()

    def _connect_signals(self) -> None:
        self._view.theme_toggled.connect(self._on_theme_toggled)
        self._view.startup_toggled.connect(self._on_startup_toggled)
        self._view.auto_check_toggled.connect(self._on_auto_check_toggled)
        self._view.export_csv_requested.connect(self._on_export_csv)
        self._view.export_json_requested.connect(self._on_export_json)
        self._view.restore_requested.connect(self._on_restore_backup)
        self._view.check_updates_requested.connect(self._on_check_updates)
        self._view.view_release_notes_requested.connect(self._on_view_release_notes)

    def _load_settings(self) -> None:
        is_dark = self._settings_repo.get_bool(_SETTINGS_THEME, default=True)
        with_startup = self._settings_repo.get_bool(_SETTINGS_STARTUP, default=False)
        auto_check = self._settings_repo.get_bool(_SETTINGS_AUTO_CHECK, default=True)
        self._view.set_dark_mode(is_dark)
        self._view.set_start_with_windows(with_startup)
        self._view.set_auto_check(auto_check)

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

    def _on_auto_check_toggled(self, enabled: bool) -> None:
        """Persist the auto-check-for-updates preference (T-202)."""
        self._settings_repo.set_bool(_SETTINGS_AUTO_CHECK, enabled)

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

    def _on_check_updates(self) -> None:
        if self._update_service is None:
            return
        result = self._update_service.check_for_updates(force=True)
        dialog = UpdateDialog(result, parent=self._parent_widget)
        dialog.exec()
        if dialog.ignored_version:
            self._update_service.ignore_version(dialog.ignored_version)
        self._update_status_after_check(result)

    def _on_view_release_notes(self) -> None:
        if self._update_service is None:
            return
        result = self._update_service.get_cached_result()
        if result and result.release:
            UpdateDialog(result, parent=self._parent_widget).exec()

    def _update_status_after_check(self, result: UpdateCheckResult) -> None:
        self._view.set_last_checked(
            result.checked_at.split(".")[0].replace("T", " ")
        )
        # T-202: populate Latest Version label
        if result.latest_version:
            self._view.set_latest_version(result.latest_version)
        if result.update_available and result.release:
            self._view.set_update_status(
                f"Trackora {result.release.version} available", True
            )
        elif result.error:
            self._view.set_update_status("Check failed. See logs.", False)
        else:
            self._view.set_update_status("Up to date", False)

    def _on_export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self._parent_widget,
            "Backup to JSON",
            str(Path.home() / "trackora_backup.json"),
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

    def _on_restore_backup(self) -> None:
        # 1. Confirmation dialog
        reply = QMessageBox.question(
            self._parent_widget,
            "Restore Backup",
            "Are you sure you want to restore the database from a backup?\n"
            "This will overwrite all current games, sessions, and settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 2. File picker
        path, _ = QFileDialog.getOpenFileName(
            self._parent_widget,
            "Select Backup File",
            "",
            "Backup Files (*.zip *.json)",
        )
        if not path:
            return

        # 3. Call restore service
        restore_service = getattr(self._parent_widget, "_restore_service", None)
        if restore_service is None:
            QMessageBox.warning(
                self._parent_widget, "Restore Backup", "Restore service is not initialized."
            )
            return

        try:
            res = restore_service.restore_from_file(Path(path))
            if res.success:
                QMessageBox.information(
                    self._parent_widget,
                    "Restore Backup",
                    "Database restore completed successfully.\n"
                    "The application will now restart to apply the changes.",
                )
                # Restart the application
                import sys
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)
            else:
                QMessageBox.warning(
                    self._parent_widget,
                    "Restore Backup",
                    f"Restore failed:\n{res.error}",
                )
        except Exception as exc:
            logger.exception("Restore operation failed")
            QMessageBox.warning(
                self._parent_widget,
                "Restore Backup",
                f"An unexpected error occurred during restore:\n{exc}",
            )
