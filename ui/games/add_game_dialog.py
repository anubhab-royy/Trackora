"""
AddGameDialog — Phase 5
Modal dialog for adding or editing a tracked game.

Fields:
  - Game Name (QLineEdit)
  - Executable Path (QLineEdit + Browse button)

Buttons:
  - Save
  - Cancel

No business logic. No SQL. Accepts and returns pure data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from database.models import Game

logger = logging.getLogger(__name__)


class AddGameDialog(QDialog):
    """
    Modal dialog for adding or editing a game.

    Usage — Add mode:
        dialog = AddGameDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, path = dialog.get_values()

    Usage — Edit mode:
        dialog = AddGameDialog(parent=self, game=existing_game)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, path = dialog.get_values()
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        game: Optional[Game] = None,
    ) -> None:
        super().__init__(parent)
        self._game = game
        self._is_edit = game is not None
        self._setup_ui()
        if self._is_edit:
            self._populate(game)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return the trimmed game name entered by the user."""
        return self._name_edit.text().strip()

    def get_executable_path(self) -> str:
        """Return the trimmed executable path entered by the user."""
        return self._path_edit.text().strip()

    # ------------------------------------------------------------------
    # Private — setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        title = "Edit Game" if self._is_edit else "Add Game"
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(16)
        root_layout.setContentsMargins(20, 20, 20, 20)

        # --- Heading ---
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 15px; font-weight: bold;")
        root_layout.addWidget(heading)

        # --- Form ---
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(10)

        # Game Name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Counter-Strike 2")
        self._name_edit.setMaxLength(128)
        form_layout.addRow("Game Name:", self._name_edit)

        # Executable Path + Browse button
        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("/path/to/game/executable")
        self._path_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._on_browse)

        path_layout.addWidget(self._path_edit)
        path_layout.addWidget(browse_btn)

        form_layout.addRow("Executable:", path_widget)

        root_layout.addLayout(form_layout)

        # --- Help text ---
        help_label = QLabel(
            "The process name will be detected automatically from the executable."
        )
        help_label.setStyleSheet("color: #888888; font-size: 11px;")
        help_label.setWordWrap(True)
        root_layout.addWidget(help_label)

        root_layout.addStretch()

        # --- Buttons ---
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        root_layout.addWidget(button_box)

    def _populate(self, game: Game) -> None:
        """Pre-fill fields when editing an existing game."""
        self._name_edit.setText(game.name)
        self._path_edit.setText(game.executable_path)

    # ------------------------------------------------------------------
    # Private — slots
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        """Open file browser and populate the path field."""
        start_dir = ""
        current_path = self._path_edit.text().strip()
        if current_path:
            parent = Path(current_path).parent
            if parent.exists():
                start_dir = str(parent)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Game Executable",
            start_dir,
            "All Files (*)",
        )
        if file_path:
            self._path_edit.setText(file_path)
            # Auto-populate name if empty
            if not self._name_edit.text().strip():
                stem = Path(file_path).stem.replace("_", " ").replace("-", " ").title()
                self._name_edit.setText(stem)

    def _on_save(self) -> None:
        """Validate locally before accepting the dialog."""
        name = self._name_edit.text().strip()
        path = self._path_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Game name cannot be empty.")
            self._name_edit.setFocus()
            return

        if not path:
            QMessageBox.warning(
                self, "Validation Error", "Please select an executable file."
            )
            self._path_edit.setFocus()
            return

        if not Path(path).is_file():
            QMessageBox.warning(
                self,
                "Validation Error",
                f"The file was not found:\n{path}\n\nPlease select a valid executable.",
            )
            self._path_edit.setFocus()
            return

        self.accept()