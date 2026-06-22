"""
UpdateBanner — Phase 10

Non-intrusive banner widget displayed at the top of MainWindow
when a newer version of Trackora is available.

Signals:
    ignored(version: str) — emitted when user dismisses the banner
    view_notes_requested() — emitted when user clicks "View Release Notes"
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class UpdateBanner(QFrame):
    """
    Non-intrusive update notification banner.

    Args:
        parent: Optional parent widget.
    """

    ignored = pyqtSignal(str)
    view_notes_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("UpdateBanner")
        self._version = ""
        self._setup_ui()
        self.hide()

    def show(self, version: str, release_notes: str = "") -> None:
        """Show the banner for the given version."""
        self._version = version
        self._label.setText(f"Trackora {version} is available!")
        super().show()

    def dismiss(self) -> None:
        """Dismiss the banner and emit the ignored signal."""
        self.ignored.emit(self._version)
        self.hide()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self._label = QLabel()
        self._label.setObjectName("BannerLabel")
        layout.addWidget(self._label, stretch=1)

        self._view_notes_btn = QPushButton("View Release Notes")
        self._view_notes_btn.setObjectName("ViewNotesButton")
        self._view_notes_btn.clicked.connect(self.view_notes_requested.emit)
        layout.addWidget(self._view_notes_btn)

        dismiss_btn = QPushButton("✕")
        dismiss_btn.setObjectName("DismissButton")
        dismiss_btn.setFixedSize(24, 24)
        dismiss_btn.clicked.connect(self.dismiss)
        layout.addWidget(dismiss_btn)
