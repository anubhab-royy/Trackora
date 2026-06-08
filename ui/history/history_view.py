"""
HistoryView — Phase 7
Main widget for the Session History screen.

Displays:
  - Search bar for filtering by game name
  - Filter row: game combo, date range, duration range
  - Sortable table of sessions
  - Pagination controls (prev / next / page info)
  - Summary footer (total sessions, total playtime)

Signals:
  - query_changed — emitted when any search/filter/sort/page input changes
  - sort_changed(sort_by, sort_order)
  - page_changed(page)

No SQL. No business logic. No direct repository access.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from database.models import Game
from database.repositories.sessions_repository import SessionView
from services.session_history_service import format_duration, SessionHistoryResult
from ui.history.history_table_model import HistoryTableModel

logger = logging.getLogger(__name__)


class HistoryView(QWidget):
    """
    Widget that renders the Session History screen.

    Signals:
        query_changed — emitted when the user changes any filter/search/sort/page
    """

    query_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = HistoryTableModel()
        self._setup_ui()
        self._connect_internal_signals()

    # ------------------------------------------------------------------
    # Public API (called by controller)
    # ------------------------------------------------------------------

    def set_sessions(self, result: SessionHistoryResult) -> None:
        """Populate the table and update pagination / footer with query results."""
        self._model.refresh(result.sessions)
        self._update_pagination(result)
        self._update_footer(result)

    def set_games(self, games: list[Game]) -> None:
        """Populate the game filter dropdown."""
        self._game_combo.blockSignals(True)
        self._game_combo.clear()
        self._game_combo.addItem("All Games", None)
        for game in games:
            self._game_combo.addItem(game.name, game.id)
        self._game_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Filter / sort / page getters (called by controller)
    # ------------------------------------------------------------------

    def get_search_text(self) -> str:
        return self._search_edit.text().strip()

    def get_game_id(self) -> int | None:
        data = self._game_combo.currentData()
        return data if data is not None else None

    def get_date_from(self) -> date | None:
        if self._date_from_check.isChecked():
            return self._date_from_edit.date().toPython()
        return None

    def get_date_to(self) -> date | None:
        if self._date_to_check.isChecked():
            return self._date_to_edit.date().toPython()
        return None

    def get_min_duration(self) -> int | None:
        if self._min_dur_check.isChecked():
            return self._min_dur_spin.value()
        return None

    def get_max_duration(self) -> int | None:
        if self._max_dur_check.isChecked():
            return self._max_dur_spin.value()
        return None

    def get_sort_by(self) -> str:
        """Return the sort column identifier based on the current header sort indicator."""
        header = self._table.horizontalHeader()
        for col, sort_col in [(0, "start_time"), (1, "game_name"),
                              (2, "duration_seconds"), (3, "start_time"),
                              (4, "end_time")]:
            if header.sortIndicatorSection() == col:
                return sort_col
        return "start_time"

    def get_sort_order(self) -> str:
        header = self._table.horizontalHeader()
        order = header.sortIndicatorOrder()
        return "ASC" if order == Qt.SortOrder.AscendingOrder else "DESC"

    def get_current_page(self) -> int:
        return self._current_page

    # ------------------------------------------------------------------
    # Private — UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("HistoryView")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(12)

        self._build_header(root_layout)
        self._build_filter_row(root_layout)
        self._build_table(root_layout)
        self._build_pagination(root_layout)

    def _build_header(self, root_layout: QVBoxLayout) -> None:
        header_layout = QHBoxLayout()

        heading = QLabel("Session History")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(heading)

        header_layout.addStretch()

        # Search
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by game name…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setMinimumWidth(220)
        self._search_edit.setFixedHeight(30)
        header_layout.addWidget(self._search_edit)

        root_layout.addLayout(header_layout)

    def _build_filter_row(self, root_layout: QVBoxLayout) -> None:
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        # Game filter
        game_label = QLabel("Game:")
        game_label.setStyleSheet("font-size: 12px;")
        filter_layout.addWidget(game_label)

        self._game_combo = QComboBox()
        self._game_combo.setMinimumWidth(140)
        self._game_combo.setFixedHeight(28)
        filter_layout.addWidget(self._game_combo)

        # Date from
        self._date_from_check = QPushButton("From:")
        self._date_from_check.setCheckable(True)
        self._date_from_check.setChecked(False)
        self._date_from_check.setFixedHeight(28)
        self._date_from_check.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 0 8px; }"
            "QPushButton:checked { font-weight: bold; }"
        )
        filter_layout.addWidget(self._date_from_check)

        self._date_from_edit = QDateEdit()
        self._date_from_edit.setCalendarPopup(True)
        self._date_from_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_from_edit.setDate(self._date_from_edit.date().currentDate())
        self._date_from_edit.setFixedHeight(28)
        self._date_from_edit.setEnabled(False)
        filter_layout.addWidget(self._date_from_edit)

        # Date to
        self._date_to_check = QPushButton("To:")
        self._date_to_check.setCheckable(True)
        self._date_to_check.setChecked(False)
        self._date_to_check.setFixedHeight(28)
        self._date_to_check.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 0 8px; }"
            "QPushButton:checked { font-weight: bold; }"
        )
        filter_layout.addWidget(self._date_to_check)

        self._date_to_edit = QDateEdit()
        self._date_to_edit.setCalendarPopup(True)
        self._date_to_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_to_edit.setDate(self._date_to_edit.date().currentDate())
        self._date_to_edit.setFixedHeight(28)
        self._date_to_edit.setEnabled(False)
        filter_layout.addWidget(self._date_to_edit)

        # Min duration
        self._min_dur_check = QPushButton("Min (min):")
        self._min_dur_check.setCheckable(True)
        self._min_dur_check.setChecked(False)
        self._min_dur_check.setFixedHeight(28)
        self._min_dur_check.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 0 8px; }"
            "QPushButton:checked { font-weight: bold; }"
        )
        filter_layout.addWidget(self._min_dur_check)

        self._min_dur_spin = QSpinBox()
        self._min_dur_spin.setRange(0, 99999)
        self._min_dur_spin.setValue(0)
        self._min_dur_spin.setSuffix(" min")
        self._min_dur_spin.setFixedHeight(28)
        self._min_dur_spin.setFixedWidth(100)
        self._min_dur_spin.setEnabled(False)
        filter_layout.addWidget(self._min_dur_spin)

        # Max duration
        self._max_dur_check = QPushButton("Max (min):")
        self._max_dur_check.setCheckable(True)
        self._max_dur_check.setChecked(False)
        self._max_dur_check.setFixedHeight(28)
        self._max_dur_check.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 0 8px; }"
            "QPushButton:checked { font-weight: bold; }"
        )
        filter_layout.addWidget(self._max_dur_check)

        self._max_dur_spin = QSpinBox()
        self._max_dur_spin.setRange(0, 99999)
        self._max_dur_spin.setValue(0)
        self._max_dur_spin.setSuffix(" min")
        self._max_dur_spin.setFixedHeight(28)
        self._max_dur_spin.setFixedWidth(100)
        self._max_dur_spin.setEnabled(False)
        filter_layout.addWidget(self._max_dur_spin)

        filter_layout.addStretch()

        root_layout.addLayout(filter_layout)

    def _build_table(self, root_layout: QVBoxLayout) -> None:
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
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setWordWrap(False)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # Game
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Duration
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Start
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # End

        # Default sort indicator on Date column descending
        header.setSortIndicator(0, Qt.SortOrder.DescendingOrder)

        self._table.setMinimumHeight(300)
        root_layout.addWidget(self._table)

    def _build_pagination(self, root_layout: QVBoxLayout) -> None:
        pagination_layout = QHBoxLayout()
        pagination_layout.setSpacing(8)

        # Summary footer on the left
        self._footer_label = QLabel("No sessions recorded")
        self._footer_label.setStyleSheet("color: #888888; font-size: 12px;")
        pagination_layout.addWidget(self._footer_label)

        pagination_layout.addStretch()

        # Pagination controls on the right
        self._page_label = QLabel("Page 0 of 0")
        self._page_label.setStyleSheet("font-size: 12px;")
        pagination_layout.addWidget(self._page_label)

        self._prev_btn = QPushButton("< Prev")
        self._prev_btn.setFixedHeight(28)
        self._prev_btn.setEnabled(False)
        pagination_layout.addWidget(self._prev_btn)

        self._next_btn = QPushButton("Next >")
        self._next_btn.setFixedHeight(28)
        self._next_btn.setEnabled(False)
        pagination_layout.addWidget(self._next_btn)

        root_layout.addLayout(pagination_layout)

        # Internal state
        self._current_page: int = 0
        self._total_pages: int = 0

    # ------------------------------------------------------------------
    # Private — signal connections
    # ------------------------------------------------------------------

    def _connect_internal_signals(self) -> None:
        """Wire internal widget signals to emit query_changed."""
        self._search_edit.textChanged.connect(self._emit_query_changed)
        self._game_combo.currentIndexChanged.connect(self._emit_query_changed)
        self._date_from_check.toggled.connect(self._on_date_from_toggle)
        self._date_from_edit.dateChanged.connect(self._emit_query_changed)
        self._date_to_check.toggled.connect(self._on_date_to_toggle)
        self._date_to_edit.dateChanged.connect(self._emit_query_changed)
        self._min_dur_check.toggled.connect(self._on_min_dur_toggle)
        self._min_dur_spin.valueChanged.connect(self._emit_query_changed)
        self._max_dur_check.toggled.connect(self._on_max_dur_toggle)
        self._max_dur_spin.valueChanged.connect(self._emit_query_changed)

        header = self._table.horizontalHeader()
        header.sortIndicatorChanged.connect(self._on_sort_changed)

        self._prev_btn.clicked.connect(self._on_prev_page)
        self._next_btn.clicked.connect(self._on_next_page)

    # ------------------------------------------------------------------
    # Private — slots
    # ------------------------------------------------------------------

    def _emit_query_changed(self) -> None:
        self._current_page = 0
        self.query_changed.emit()

    def _on_date_from_toggle(self, checked: bool) -> None:
        self._date_from_edit.setEnabled(checked)
        self._emit_query_changed()

    def _on_date_to_toggle(self, checked: bool) -> None:
        self._date_to_edit.setEnabled(checked)
        self._emit_query_changed()

    def _on_min_dur_toggle(self, checked: bool) -> None:
        self._min_dur_spin.setEnabled(checked)
        self._emit_query_changed()

    def _on_max_dur_toggle(self, checked: bool) -> None:
        self._max_dur_spin.setEnabled(checked)
        self._emit_query_changed()

    def _on_sort_changed(self, section: int, order: Qt.SortOrder) -> None:
        self._current_page = 0
        self.query_changed.emit()

    def _on_prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self.query_changed.emit()

    def _on_next_page(self) -> None:
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self.query_changed.emit()

    # ------------------------------------------------------------------
    # Private — UI updates
    # ------------------------------------------------------------------

    def _update_pagination(self, result: SessionHistoryResult) -> None:
        self._total_pages = result.total_pages
        self._current_page = result.page

        if result.total_count == 0:
            self._page_label.setText("No results")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
        else:
            start_item = result.page * result.page_size + 1
            end_item = min(
                (result.page + 1) * result.page_size,
                result.total_count,
            )
            self._page_label.setText(
                f"Showing {start_item}–{end_item} of {result.total_count}"
            )
            self._prev_btn.setEnabled(result.page > 0)
            self._next_btn.setEnabled(result.page < result.total_pages - 1)

    def _update_footer(self, result: SessionHistoryResult) -> None:
        if result.total_count == 0:
            self._footer_label.setText("No sessions recorded")
        else:
            total_str = format_duration(result.total_duration_seconds)
            self._footer_label.setText(
                f"{result.total_count} session{'s' if result.total_count != 1 else ''} "
                f"shown — {total_str} total"
            )
