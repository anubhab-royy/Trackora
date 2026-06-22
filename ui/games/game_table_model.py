"""
GameTableModel — Phase 5
QAbstractTableModel that backs the games QTableView.

No SQL. No business logic. Pure presentation.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor

from database.models import Game

logger = logging.getLogger(__name__)

_COLUMNS = ["Name", "Platform", "Process Name", "Executable Path", "Tracking"]
_COL_NAME = 0
_COL_PLATFORM = 1
_COL_PROCESS = 2
_COL_PATH = 3
_COL_ENABLED = 4


class GameTableModel(QAbstractTableModel):
    """
    Table model for the list of tracked games.

    Columns:
        0 — Name
        1 — Process Name
        2 — Executable Path
        3 — Tracking (Enabled / Disabled)
    """

    def __init__(self, games: list[Game] | None = None) -> None:
        super().__init__()
        self._games: list[Game] = games or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, games: list[Game]) -> None:
        """Replace the game list and notify the view."""
        self.beginResetModel()
        self._games = games
        self.endResetModel()

    def game_at(self, row: int) -> Game | None:
        """Return the Game at a given row index."""
        if 0 <= row < len(self._games):
            return self._games[row]
        return None

    # ------------------------------------------------------------------
    # QAbstractTableModel overrides
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._games)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(_COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                if 0 <= section < len(_COLUMNS):
                    return _COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if row >= len(self._games):
            return None

        game = self._games[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == _COL_NAME:
                return game.name
            if col == _COL_PLATFORM:
                return game.platform.capitalize() if game.platform else "—"
            if col == _COL_PROCESS:
                return game.process_name
            if col == _COL_PATH:
                return game.executable_path
            if col == _COL_ENABLED:
                return "Enabled" if game.is_enabled else "Disabled"

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == _COL_ENABLED:
                if game.is_enabled:
                    return QColor("#4CAF50")   # green
                return QColor("#F44336")        # red

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == _COL_ENABLED:
                return Qt.AlignmentFlag.AlignCenter

        if role == Qt.ItemDataRole.UserRole:
            # Expose the full Game object for internal use
            return game

        return None