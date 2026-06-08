"""
GamesView — Phase 5
Main widget for the Games Management screen.

Displays:
  - Table of tracked games (name, process, path, enabled)
  - Toolbar: Add, Edit, Delete, Enable/Disable buttons

Emits signals that the GamesController listens to.
No SQL. No business logic.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from database.models import Game
from ui.games.game_table_model import GameTableModel

logger = logging.getLogger(__name__)


class GamesView(QWidget):
    """
    Widget that renders the Games Management screen.

    Signals:
        add_requested         — user clicked Add Game
        edit_requested(Game)  — user clicked Edit on a selected game
        delete_requested(Game)— user clicked Delete on a selected game
        toggle_enabled_requested(Game) — user clicked Enable/Disable
    """

    add_requested = pyqtSignal()
    edit_requested = pyqtSignal(object)          # Game
    delete_requested = pyqtSignal(object)         # Game
    toggle_enabled_requested = pyqtSignal(object) # Game

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = GameTableModel()
        self._setup_ui()
        self._connect_internal_signals()
        self._update_button_states()

    # ------------------------------------------------------------------
    # Public API (called by controller)
    # ------------------------------------------------------------------

    def set_games(self, games: list[Game]) -> None:
        """Populate the table with a new list of games."""
        self._model.refresh(games)
        self._update_button_states()

    def show_error(self, title: str, message: str) -> None:
        """Display an error dialog."""
        QMessageBox.critical(self, title, message)

    def show_info(self, title: str, message: str) -> None:
        """Display an informational dialog."""
        QMessageBox.information(self, title, message)

    # ------------------------------------------------------------------
    # Private — UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("GamesView")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(12)

        # --- Header ---
        header_layout = QHBoxLayout()

        heading = QLabel("Game Management")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(heading)

        header_layout.addStretch()

        # Add Game button
        self._add_btn = QPushButton("+ Add Game")
        self._add_btn.setFixedHeight(32)
        self._add_btn.setToolTip("Add a new game to track")
        self._add_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "border-radius: 4px; padding: 0 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #106ebe; }"
            "QPushButton:pressed { background-color: #005a9e; }"
        )
        header_layout.addWidget(self._add_btn)

        root_layout.addLayout(header_layout)

        # --- Sub-toolbar (contextual actions) ---
        sub_toolbar = QHBoxLayout()
        sub_toolbar.setSpacing(8)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedHeight(28)
        self._edit_btn.setToolTip("Edit selected game")
        self._edit_btn.setEnabled(False)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedHeight(28)
        self._delete_btn.setToolTip("Delete selected game")
        self._delete_btn.setEnabled(False)
        self._delete_btn.setStyleSheet(
            "QPushButton:enabled { color: #F44336; }"
        )

        self._toggle_btn = QPushButton("Disable Tracking")
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.setToolTip("Enable or disable tracking for selected game")
        self._toggle_btn.setEnabled(False)

        sub_toolbar.addWidget(self._edit_btn)
        sub_toolbar.addWidget(self._delete_btn)
        sub_toolbar.addWidget(self._toggle_btn)
        sub_toolbar.addStretch()

        # Game count label
        self._count_label = QLabel("No games")
        self._count_label.setStyleSheet("color: #888888; font-size: 12px;")
        sub_toolbar.addWidget(self._count_label)

        root_layout.addLayout(sub_toolbar)

        # --- Table ---
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSortingEnabled(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setWordWrap(False)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)          # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # Process
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)          # Path
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Tracking

        self._table.setMinimumHeight(300)
        root_layout.addWidget(self._table)

        # --- Empty state label (shown when no games) ---
        self._empty_label = QLabel(
            "No games added yet.\n\nClick \"+ Add Game\" to start tracking a game."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888888; font-size: 13px;")
        self._empty_label.hide()
        root_layout.addWidget(self._empty_label)

    def _connect_internal_signals(self) -> None:
        """Wire internal widget signals to view methods."""
        self._add_btn.clicked.connect(self.add_requested.emit)
        self._edit_btn.clicked.connect(self._emit_edit)
        self._delete_btn.clicked.connect(self._emit_delete)
        self._toggle_btn.clicked.connect(self._emit_toggle)

        selection_model = self._table.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_changed)

        # Double-click opens edit dialog
        self._table.doubleClicked.connect(self._emit_edit)

    # ------------------------------------------------------------------
    # Private — internal logic
    # ------------------------------------------------------------------

    def _selected_game(self) -> Optional[Game]:
        """Return the currently selected Game, or None."""
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self._model.game_at(indexes[0].row())

    def _update_button_states(self) -> None:
        """Enable/disable contextual buttons based on selection."""
        game = self._selected_game()
        has_selection = game is not None

        self._edit_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)
        self._toggle_btn.setEnabled(has_selection)

        if game is not None:
            self._toggle_btn.setText(
                "Disable Tracking" if game.is_enabled else "Enable Tracking"
            )

        # Update count label
        count = self._model.rowCount()
        if count == 0:
            self._count_label.setText("No games")
            self._table.hide()
            self._empty_label.show()
        elif count == 1:
            self._count_label.setText("1 game")
            self._table.show()
            self._empty_label.hide()
        else:
            self._count_label.setText(f"{count} games")
            self._table.show()
            self._empty_label.hide()

    def _on_selection_changed(self) -> None:
        self._update_button_states()

    def _emit_edit(self) -> None:
        game = self._selected_game()
        if game is not None:
            self.edit_requested.emit(game)

    def _emit_delete(self) -> None:
        game = self._selected_game()
        if game is not None:
            self.delete_requested.emit(game)

    def _emit_toggle(self) -> None:
        game = self._selected_game()
        if game is not None:
            self.toggle_enabled_requested.emit(game)