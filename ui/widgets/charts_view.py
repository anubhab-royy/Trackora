"""
ChartsView — Phase 8
Container widget that holds all three chart widgets.

Provides a scrollable layout with a refresh-all button.
No SQL. No business logic. No direct repository access.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.daily_activity_chart import DailyActivityChart
from ui.widgets.monthly_trend_chart import MonthlyTrendChart
from ui.widgets.game_distribution_chart import GameDistributionChart

logger = logging.getLogger(__name__)


class ChartsView(QWidget):
    """
    Container that arranges the three chart widgets in a scrollable view.

    Public API (called by controller):
        daily_chart   -> DailyActivityChart
        monthly_chart -> MonthlyTrendChart
        distribution_chart -> GameDistributionChart
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChartsView")
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public access to chart sub-widgets
    # ------------------------------------------------------------------

    @property
    def daily_chart(self) -> DailyActivityChart:
        return self._daily_chart

    @property
    def monthly_chart(self) -> MonthlyTrendChart:
        return self._monthly_chart

    @property
    def distribution_chart(self) -> GameDistributionChart:
        return self._distribution_chart

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("ChartsScroll")
        outer_layout.addWidget(scroll)

        container = QWidget()
        container.setObjectName("ChartsContainer")
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(20)

        # --- Header ---
        header_layout = QHBoxLayout()
        title = QLabel("Charts")
        title.setObjectName("PageTitle")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # --- Daily activity chart ---
        daily_card = self._make_chart_card()
        self._daily_chart = DailyActivityChart()
        daily_card_layout = daily_card.layout()
        assert daily_card_layout is not None
        daily_card_layout.addWidget(self._daily_chart)
        layout.addWidget(daily_card)

        # --- Monthly trend chart ---
        monthly_card = self._make_chart_card()
        self._monthly_chart = MonthlyTrendChart()
        monthly_card_layout = monthly_card.layout()
        assert monthly_card_layout is not None
        monthly_card_layout.addWidget(self._monthly_chart)
        layout.addWidget(monthly_card)

        # --- Game distribution chart ---
        dist_card = self._make_chart_card()
        self._distribution_chart = GameDistributionChart()
        dist_card_layout = dist_card.layout()
        assert dist_card_layout is not None
        dist_card_layout.addWidget(self._distribution_chart)
        layout.addWidget(dist_card)

        layout.addStretch()

    @staticmethod
    def _make_chart_card() -> QFrame:
        """Create a styled card frame for a chart."""
        card = QFrame()
        card.setObjectName("ChartCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "#ChartCard { background-color: #2d2d44; border: 1px solid #3d3d5c;"
            " border-radius: 10px; padding: 12px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(0)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return card
