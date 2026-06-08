"""
HistoryTableModel — Phase 7
QAbstractTableModel that backs the session history QTableView.

No SQL. No business logic. Pure presentation.

Columns:
    0 — Date         (start_time, short date)
    1 — Game         (game_name)
    2 — Duration     (formatted Xh Xm)
    3 — Start Time   (start_time, time only)
    4 — End Time     (end_time, time only)
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

from database.models import SessionView
from services.session_history_service import format_duration

logger = logging.getLogger(__name__)

_COLUMNS = ["Date", "Game", "Duration", "Start Time", "End Time"]
_COL_DATE = 0
_COL_GAME = 1
_COL_DURATION = 2
_COL_START = 3
_COL_END = 4


class HistoryTableModel(QAbstractTableModel):
    """
    Table model for the session history list.

    Columns:
        0 — Date
        1 — Game
        2 — Duration
        3 — Start Time
        4 — End Time
    """

    def __init__(self, sessions: list[SessionView] | None = None) -> None:
        super().__init__()
        self._sessions: list[SessionView] = sessions or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, sessions: list[SessionView]) -> None:
        """Replace the session list and notify the view."""
        self.beginResetModel()
        self._sessions = sessions
        self.endResetModel()

    def session_at(self, row: int) -> SessionView | None:
        """Return the SessionView at a given row index."""
        if 0 <= row < len(self._sessions):
            return self._sessions[row]
        return None

    # ------------------------------------------------------------------
    # QAbstractTableModel overrides
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._sessions)

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

        if row >= len(self._sessions):
            return None

        session = self._sessions[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == _COL_DATE:
                return session.start_time.strftime("%Y-%m-%d")
            if col == _COL_GAME:
                return session.game_name
            if col == _COL_DURATION:
                return format_duration(session.duration_seconds)
            if col == _COL_START:
                return session.start_time.strftime("%H:%M")
            if col == _COL_END:
                return session.end_time.strftime("%H:%M")

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (_COL_DURATION, _COL_START, _COL_END):
                return Qt.AlignmentFlag.AlignCenter

        return None
