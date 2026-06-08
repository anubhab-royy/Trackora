# ui/widgets/stat_card.py
"""
StatCard widget.

Displays a single statistic: a large value and a descriptive label.
Receives only plain Python values (str). No business logic. No database access.
"""

import logging
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)


class StatCard(QFrame):
    """
    A styled card widget that displays a statistic value and label.

    Args:
        label:   Short description of the statistic (e.g. "Total Playtime").
        value:   Pre-formatted value string (e.g. "142h 30m").
        icon:    Optional Unicode/emoji icon character (e.g. "🎮").
        parent:  Optional parent widget.
    """

    def __init__(
        self,
        label: str,
        value: str,
        icon: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._label_text = label
        self._value_text = value
        self._icon_text = icon
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, value: str) -> None:
        """Update the displayed value string."""
        self._value_text = value
        self._value_label.setText(value)

    def set_label(self, label: str) -> None:
        """Update the displayed label string."""
        self._label_text = label
        self._label_label.setText(label.upper())

    def set_icon(self, icon: str) -> None:
        """Update the displayed icon character."""
        self._icon_text = icon
        self._icon_label.setText(icon)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("StatCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(110)
        self.setMinimumWidth(160)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(18, 14, 18, 14)
        outer_layout.setSpacing(6)

        # Top row: icon + label
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self._icon_label = QLabel(self._icon_text)
        self._icon_label.setObjectName("StatCardIcon")
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self._icon_label)

        self._label_label = QLabel(self._label_text.upper())
        self._label_label.setObjectName("StatCardLabel")
        self._label_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self._label_label)
        top_row.addStretch()

        outer_layout.addLayout(top_row)

        # Value
        self._value_label = QLabel(self._value_text)
        self._value_label.setObjectName("StatCardValue")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        value_font = QFont()
        value_font.setPointSize(20)
        value_font.setWeight(QFont.Weight.Bold)
        self._value_label.setFont(value_font)

        outer_layout.addWidget(self._value_label)
        outer_layout.addStretch()

        logger.debug("StatCard created: label=%s", self._label_text)