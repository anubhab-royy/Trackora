# ui/dashboard/dashboard_widget.py
"""
DashboardWidget.

The main dashboard view. Composed entirely of StatCard and GameCard widgets.
Receives a DashboardController via constructor (dependency injection).
No SQL. No business logic. No direct repository access.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QFrame,
    QPushButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ui.widgets.stat_card import StatCard
from ui.widgets.game_card import GameCard
from ui.dashboard.dashboard_controller import DashboardController, DashboardData

logger = logging.getLogger(__name__)

# Refresh dashboard every 60 seconds
_REFRESH_INTERVAL_MS: int = 60_000


class DashboardWidget(QWidget):
    """
    Main dashboard screen widget.

    Displays:
    - Total Playtime
    - Today's Playtime
    - This Week's Playtime
    - This Month's Playtime
    - Most Played Game card

    Args:
        controller: DashboardController instance.
        parent:     Optional parent widget.
    """

    def __init__(
        self,
        controller: DashboardController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._setup_ui()
        self._setup_refresh_timer()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload all statistics from the controller and update the UI."""
        logger.debug("DashboardWidget: refreshing data.")
        data: DashboardData = self._controller.load_dashboard_data()
        self._apply_data(data)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("ContentArea")

        # Outer layout
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Scroll area so dashboard works on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("DashboardScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        # Container inside scroll
        container = QWidget()
        container.setObjectName("DashboardContainer")
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(20)

        # --- Header row ---
        header_row = QHBoxLayout()
        header_row.setSpacing(0)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setWeight(QFont.Weight.Bold)
        title.setFont(title_font)
        header_row.addWidget(title)
        header_row.addStretch()

        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.setObjectName("RefreshButton")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)

        layout.addLayout(header_row)

        # --- Section: Playtime Overview ---
        layout.addWidget(self._make_section_label("Playtime Overview"))
        layout.addLayout(self._build_stat_cards_row())

        # --- Divider ---
        layout.addWidget(self._make_divider())

        # --- Section: Most Played Game ---
        layout.addWidget(self._make_section_label("Most Played Game"))
        layout.addWidget(self._build_game_card_section())

        layout.addStretch()

    def _build_stat_cards_row(self) -> QHBoxLayout:
        """Construct the row of four StatCard widgets."""
        row = QHBoxLayout()
        row.setSpacing(14)

        self._card_total = StatCard(
            label="Total Playtime",
            value="—",
            icon="⏱",
        )
        self._card_today = StatCard(
            label="Today",
            value="—",
            icon="📅",
        )
        self._card_week = StatCard(
            label="This Week",
            value="—",
            icon="📆",
        )
        self._card_month = StatCard(
            label="This Month",
            value="—",
            icon="🗓",
        )

        for card in (
            self._card_total,
            self._card_today,
            self._card_week,
            self._card_month,
        ):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(card)

        return row

    def _build_game_card_section(self) -> QWidget:
        """Build the most-played game card."""
        wrapper = QWidget()
        wrapper.setObjectName("GameCardWrapper")
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        self._game_card = GameCard(
            game_name="No games tracked yet",
            total_hours="—",
            icon_path="",
            badge_text="Most Played",
        )
        self._game_card.setMaximumWidth(480)
        wrapper_layout.addWidget(self._game_card)
        wrapper_layout.addStretch()

        return wrapper

    # ------------------------------------------------------------------
    # Data Binding
    # ------------------------------------------------------------------

    def _apply_data(self, data: DashboardData) -> None:
        """Update all widgets with fresh data."""
        self._card_total.set_value(data.total_playtime)
        self._card_today.set_value(data.today_playtime)
        self._card_week.set_value(data.week_playtime)
        self._card_month.set_value(data.month_playtime)
        self._game_card.set_game_name(data.most_played_game_name)
        self._game_card.set_total_hours(data.most_played_game_hours)
        self._game_card.set_icon(data.most_played_game_icon)
        logger.debug("DashboardWidget: UI updated.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_section_label(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("SectionLabel")
        font = QFont()
        font.setPointSize(9)
        font.setWeight(QFont.Weight.DemiBold)
        label.setFont(font)
        return label

    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        return line

    def _setup_refresh_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        logger.debug("DashboardWidget: auto-refresh timer started (%dms).", _REFRESH_INTERVAL_MS)