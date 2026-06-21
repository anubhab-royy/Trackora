"""
GameDistributionChart — Phase 8
Horizontal bar chart showing total playtime per game.

Uses PyQtGraph. Reads data from StatisticsService.
No SQL. No business logic.
"""

from __future__ import annotations

import logging
from typing import Optional

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget, QLabel

from trackora_stats.models import GamePlaytimeSummary

logger = logging.getLogger(__name__)

_COLORS = ["#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#74c7ec",
           "#cba6f7", "#94e2d5", "#fab387", "#b4befe", "#f5c2e7"]
_COLOR_BG = "#1e1e2e"
_COLOR_TEXT = "#cdd6f4"
_COLOR_GRID = "#313244"
_COLOR_AXIS = "#a6adc8"


class GameDistributionChart(QWidget):
    """
    Horizontal bar chart of total playtime per game, sorted descending.

    Args:
        parent: Optional parent widget.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, summaries: list[GamePlaytimeSummary]) -> None:
        """Update the chart with fresh data."""
        self._plot.clear()

        if not summaries:
            self._no_data_label.show()
            self._plot.hide()
            return

        self._no_data_label.hide()
        self._plot.show()

        n = len(summaries)
        y = list(range(n))
        hours = [s.total_seconds / 3600 for s in summaries]

        max_h = max(1, max(hours))

        for i, (summary, h) in enumerate(zip(summaries, hours)):
            color = _COLORS[i % len(_COLORS)]
            bar = pg.BarGraphItem(
                x=[0],
                height=[h],
                width=0.7,
                y0=[i - 0.3],
                brush=color,
                pen=color,
            )
            self._plot.addItem(bar)

        self._plot.setXRange(0, max_h * 1.2)
        self._plot.setYRange(-0.5, n - 0.5)

        # Y-axis: game names
        tick_labels = [(i, s.game_name) for i, s in enumerate(summaries)]
        self._plot.getAxis("left").setTicks([tick_labels])

        self._title_label.setText(
            f"Game Distribution ({n} game{'s' if n != 1 else ''})"
        )

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._title_label = QLabel("Game Distribution")
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
        self._plot.setMaximumHeight(300)
        self._plot.showGrid(x=True, y=False, alpha=0.3)
        self._plot.getAxis("bottom").setLabel("Hours", color=_COLOR_AXIS)
        self._plot.getAxis("left").setLabel("", color=_COLOR_AXIS)
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
