"""
SettingsView.

Settings screen with theme toggle, startup toggle, and export actions.
No SQL. No business logic.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from trackora.core.build_info import BUILD_CHANNEL, BUILD_VERSION
from trackora.core.paths import BASE_DIR

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    """
    Widget that renders the Settings screen.

    Signals:
        theme_toggled(dark_mode: bool)
        startup_toggled(enabled: bool)
        export_csv_requested()
        export_json_requested()
        check_updates_requested()
        view_release_notes_requested()
    """

    theme_toggled = pyqtSignal(bool)
    startup_toggled = pyqtSignal(bool)
    export_csv_requested = pyqtSignal()
    export_json_requested = pyqtSignal()
    check_updates_requested = pyqtSignal()
    view_release_notes_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def set_dark_mode(self, enabled: bool) -> None:
        self._theme_check.setChecked(enabled)

    def set_start_with_windows(self, enabled: bool) -> None:
        self._startup_check.setChecked(enabled)

    def set_last_checked(self, iso_timestamp: str) -> None:
        self._last_checked_label.setText(iso_timestamp)

    def set_update_status(self, message: str, is_update_available: bool) -> None:
        self._update_status_label.setText(message)
        self._view_notes_btn.setVisible(is_update_available)

    def _setup_ui(self) -> None:
        self.setObjectName("SettingsView")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        heading = QLabel("Settings")
        heading.setObjectName("PageTitle")
        root_layout.addWidget(heading)

        root_layout.addWidget(self._build_appearance_group())
        root_layout.addWidget(self._build_startup_group())
        root_layout.addWidget(self._build_data_group())
        root_layout.addWidget(self._build_about_group())
        root_layout.addStretch()

    def _build_appearance_group(self) -> QGroupBox:
        group = QGroupBox("Appearance")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._theme_check = QCheckBox("Dark Mode")
        self._theme_check.setChecked(True)
        self._theme_check.toggled.connect(self.theme_toggled.emit)
        layout.addWidget(self._theme_check)

        return group

    def _build_about_group(self) -> QGroupBox:
        group = QGroupBox("About")
        layout = QFormLayout(group)
        layout.setSpacing(8)

        channel_label = QLabel({
            "production": "Production",
            "development": "Development",
        }.get(BUILD_CHANNEL, BUILD_CHANNEL))
        channel_label.setTextInteractionFlags(channel_label.textInteractionFlags())
        layout.addRow("Build Channel:", channel_label)

        version_label = QLabel(BUILD_VERSION)
        version_label.setTextInteractionFlags(version_label.textInteractionFlags())
        layout.addRow("Version:", version_label)

        data_label = QLabel(str(BASE_DIR))
        data_label.setWordWrap(True)
        data_label.setTextInteractionFlags(data_label.textInteractionFlags())
        layout.addRow("Data Directory:", data_label)

        self._check_updates_btn = QPushButton("Check for Updates")
        self._check_updates_btn.setObjectName("CheckUpdatesButton")
        self._check_updates_btn.clicked.connect(self.check_updates_requested.emit)
        layout.addRow("", self._check_updates_btn)

        self._last_checked_label = QLabel("")
        self._last_checked_label.setTextInteractionFlags(
            self._last_checked_label.textInteractionFlags()
        )
        layout.addRow("Last checked:", self._last_checked_label)

        self._update_status_label = QLabel("")
        self._update_status_label.setWordWrap(True)
        layout.addRow("", self._update_status_label)

        self._view_notes_btn = QPushButton("View Release Notes")
        self._view_notes_btn.setObjectName("SecondaryButton")
        self._view_notes_btn.clicked.connect(self.view_release_notes_requested.emit)
        self._view_notes_btn.hide()
        layout.addRow("", self._view_notes_btn)

        return group

    def _build_startup_group(self) -> QGroupBox:
        group = QGroupBox("Startup")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._startup_check = QCheckBox("Start with system")
        self._startup_check.toggled.connect(self.startup_toggled.emit)
        layout.addWidget(self._startup_check)

        return group

    def _build_data_group(self) -> QGroupBox:
        group = QGroupBox("Data")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        csv_btn = QPushButton("Export to CSV...")
        csv_btn.setObjectName("SecondaryButton")
        csv_btn.clicked.connect(self.export_csv_requested.emit)
        layout.addWidget(csv_btn)

        json_btn = QPushButton("Backup to JSON...")
        json_btn.setObjectName("SecondaryButton")
        json_btn.clicked.connect(self.export_json_requested.emit)
        layout.addWidget(json_btn)

        return group
