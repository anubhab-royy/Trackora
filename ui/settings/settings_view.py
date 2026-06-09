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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    """
    Widget that renders the Settings screen.

    Signals:
        theme_toggled(dark_mode: bool)
        startup_toggled(enabled: bool)
        export_csv_requested()
        export_json_requested()
    """

    theme_toggled = pyqtSignal(bool)
    startup_toggled = pyqtSignal(bool)
    export_csv_requested = pyqtSignal()
    export_json_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def set_dark_mode(self, enabled: bool) -> None:
        self._theme_check.setChecked(enabled)

    def set_start_with_windows(self, enabled: bool) -> None:
        self._startup_check.setChecked(enabled)

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
