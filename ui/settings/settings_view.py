"""
SettingsView.

Settings screen with theme toggle, startup toggle, and export actions.
No SQL. No business logic.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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
    auto_check_toggled = pyqtSignal(bool)
    export_csv_requested = pyqtSignal()
    export_json_requested = pyqtSignal()
    restore_requested = pyqtSignal()
    check_updates_requested = pyqtSignal()
    view_release_notes_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def set_dark_mode(self, enabled: bool) -> None:
        self._theme_check.setChecked(enabled)

    def set_start_with_windows(self, enabled: bool) -> None:
        self._startup_check.setChecked(enabled)

    def set_auto_check(self, enabled: bool) -> None:
        """Set the 'Automatically check for updates' checkbox state."""
        self._auto_check_checkbox.setChecked(enabled)

    def set_latest_version(self, version: str) -> None:
        """Update the 'Latest Version:' label (T-202)."""
        self._latest_version_label.setText(version)

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
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        group_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setSpacing(8)

        # ── Info rows (QFormLayout — labels on left, values on right) ──
        info_form = QFormLayout()
        info_form.setContentsMargins(0, 0, 0, 0)
        info_form.setSpacing(6)
        root.addLayout(info_form)

        channel_label = QLabel({
            "production": "Production",
            "development": "Development",
        }.get(BUILD_CHANNEL, BUILD_CHANNEL))
        channel_label.setTextInteractionFlags(channel_label.textInteractionFlags())
        info_form.addRow("Build Channel:", channel_label)

        version_label = QLabel(BUILD_VERSION)
        version_label.setTextInteractionFlags(version_label.textInteractionFlags())
        info_form.addRow("Version:", version_label)

        # T-202: Latest Version row — populated after background check
        self._latest_version_label = QLabel("—")
        self._latest_version_label.setObjectName("LatestVersionLabel")
        self._latest_version_label.setTextInteractionFlags(
            self._latest_version_label.textInteractionFlags()
        )
        info_form.addRow("Latest Version:", self._latest_version_label)

        data_label = QLabel(str(BASE_DIR))
        data_label.setWordWrap(True)
        data_label.setTextInteractionFlags(data_label.textInteractionFlags())
        info_form.addRow("Data Directory:", data_label)

        # ── Update controls (decoupled from QFormLayout field column) ──
        self._auto_check_checkbox = QCheckBox("Automatically check for updates")
        self._auto_check_checkbox.setObjectName("AutoCheckCheckbox")
        self._auto_check_checkbox.setChecked(True)
        self._auto_check_checkbox.toggled.connect(self.auto_check_toggled.emit)
        root.addWidget(self._auto_check_checkbox)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()
        self._check_updates_btn = QPushButton("Check for Updates")
        self._check_updates_btn.setObjectName("CheckUpdatesButton")
        self._check_updates_btn.setFixedWidth(180)
        self._check_updates_btn.clicked.connect(self.check_updates_requested.emit)
        btn_row.addWidget(self._check_updates_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── Status rows (QFormLayout) ──
        status_form = QFormLayout()
        status_form.setContentsMargins(0, 0, 0, 0)
        status_form.setSpacing(6)
        root.addLayout(status_form)

        self._last_checked_label = QLabel("")
        self._last_checked_label.setTextInteractionFlags(
            self._last_checked_label.textInteractionFlags()
        )
        status_form.addRow("Last checked:", self._last_checked_label)

        self._update_status_label = QLabel("")
        self._update_status_label.setWordWrap(True)
        status_form.addRow("", self._update_status_label)

        self._view_notes_btn = QPushButton("View Release Notes")
        self._view_notes_btn.setObjectName("SecondaryButton")
        self._view_notes_btn.setFixedWidth(180)
        self._view_notes_btn.clicked.connect(self.view_release_notes_requested.emit)
        self._view_notes_btn.hide()
        status_form.addRow("", self._view_notes_btn)

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

        restore_btn = QPushButton("Restore from Backup...")
        restore_btn.setObjectName("SecondaryButton")
        restore_btn.clicked.connect(self.restore_requested.emit)
        layout.addWidget(restore_btn)

        return group
