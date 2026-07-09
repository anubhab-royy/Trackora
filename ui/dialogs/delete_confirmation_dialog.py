"""
DeleteConfirmationDialog — Phase 14
Custom confirmation dialog for deleting a game.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class DeleteConfirmationDialog(QDialog):
    """
    Dialog asking the user to confirm game deletion.
    """

    def __init__(self, game_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._game_name = game_name
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Delete Game")
        self.setMinimumSize(440, 260)
        self.resize(440, 260)
        self.setSizeGripEnabled(False)
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title/Heading
        title_label = QLabel(f'Delete "{self._game_name}"?')
        title_label.setObjectName("DialogTitle")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        # Permanent warning text
        warning_label = QLabel("This action cannot be undone.")
        warning_label.setStyleSheet("font-weight: bold; color: #f38ba8;")  # error color match
        layout.addWidget(warning_label)

        # Summary of what will be removed
        summary_text = (
            "The following will be removed:\n"
            "• Game entry\n"
            "• Session history\n"
            "• Statistics and analytics\n"
            "• Local Trackora data related to this game\n\n"
            "Your other games and application settings will remain unaffected."
        )
        summary_label = QLabel(summary_text)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet("font-size: 12px; color: #a6adc8;")  # secondary text color match
        layout.addWidget(summary_label)

        # Add spacing before buttons
        layout.addStretch(1)

        # Button Layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        # Cancel Button (Default)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.setDefault(True)
        self.cancel_btn.clicked.connect(self.reject)

        # Delete Button (Destructive)
        self.delete_btn = QPushButton("Delete Game")
        self.delete_btn.setObjectName("DeleteButton")
        self.delete_btn.clicked.connect(self.accept)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.delete_btn)

        layout.addLayout(btn_layout)

        # Set initial focus to Cancel button to prevent accidental enter-key trigger
        self.cancel_btn.setFocus()
