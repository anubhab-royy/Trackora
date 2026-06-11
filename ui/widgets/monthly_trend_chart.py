"""
MonthlyTrendChart — Phase 8
Bar chart showing monthly playtime for the last N months.

Uses PyQtGraph. Reads data from StatisticsService.
No SQL. No business logic.
"""

from __future__ import annotations

import logging
from typing import Optional

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget, QLabel

from trackora_stats.models import MonthlyActivity

logger = logging.getLogger(__name__)

_COLOR_BAR = "#a6e3a1"
_COLOR_BG = "#1e1e2e"
_COLOR_TEXT = "#cdd6f4"
_COLOR_GRID = "#313244"
_COLOR_AXIS = "#a6adc8"

_MONTHS_DEFAULT = 12


class MonthlyTrendChart(QWidget):
    """
    Bar chart of monthly playtime for the last N months.

    Args:
        parent: Optional parent widget.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, data: MonthlyActivity) -> None:
        """Update the chart with fresh data."""
        self._plot.clear()

        if not data.labels:
            self._no_data_label.show()
            self._plot.hide()
            return

        self._no_data_label.hide()
        self._plot.show()

        x = list(range(len(data.labels)))
        bars = pg.BarGraphItem(
            x=x,
            height=[v / 3600 for v in data.values],
            width=0.7,
            brush=_COLOR_BAR,
            pen=_COLOR_BAR,
        )
        self._plot.addItem(bars)

        # X-axis: show every label as short month name
        tick_labels = []
        for i, label in enumerate(data.labels):
            parts = label.split("-")
            short = _month_abbr(int(parts[1]))
            tick_labels.append((i, f"{short}" if len(data.labels) <= 12 else f"{short} {parts[0]}"))
        self._plot.getAxis("bottom").setTicks([tick_labels])

        # Y-axis range
        max_h = max(1, max(v / 3600 for v in data.values))
        self._plot.setYRange(0, max_h * 1.15)

        # Title
        self._title_label.setText(f"Monthly Trend (Last {len(data.labels)} Months)")

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._title_label = QLabel("Monthly Trend")
        self._title_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {_COLOR_TEXT};"
            " background: transparent;"
        )
        layout.addWidget(self._title_label)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(_COLOR_BG)
        self._plot.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._plot.setMinimumHeight(220)
        self._plot.showGrid(x=False, y=True, alpha=0.3)
        self._plot.getAxis("bottom").setLabel("Month", color=_COLOR_AXIS)
        self._plot.getAxis("left").setLabel("Hours", color=_COLOR_AXIS)
        self._plot.getAxis("bottom").setPen(_COLOR_AXIS)
        self._plot.getAxis("left").setPen(_COLOR_AXIS)
        self._plot.getAxis("bottom").setTextPen(_COLOR_AXIS)
        self._plot.getAxis("left").setTextPen(_COLOR_AXIS)
        self._plot.getViewBox().setMouseEnabled(x=False, y=False)
        self._plot.hideButtons()

        layout.addWidget(self._plot)

        self._no_data_label = QLabel("No session data yet")
        self._no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_label.setStyleSheet(
            f"color: {_COLOR_TEXT}; font-size: 12px; background: transparent;"
        )
        self._no_data_label.hide()
        layout.addWidget(self._no_data_label)


def _month_abbr(month: int) -> str:
    """Return a 3-letter month abbreviation."""
    names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return names[month] if 1 <= month <= 12 else f"Month {month}"
