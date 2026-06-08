# ui/widgets/game_card.py
"""
GameCard widget.

Displays the most-played game: icon placeholder, name, and total hours.
Receives only plain Python values. No business logic. No database access.
"""

import logging
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap

logger = logging.getLogger(__name__)

_PLACEHOLDER_ICON_SIZE = 52


class GameCard(QFrame):
    """
    A styled card widget that displays information about a single game.

    Args:
        game_name:      Display name of the game.
        total_hours:    Pre-formatted playtime string (e.g. "142h 30m").
        icon_path:      Optional filesystem path to a game icon image.
        badge_text:     Optional badge text (e.g. "Most Played").
        parent:         Optional parent widget.
    """

    def __init__(
        self,
        game_name: str,
        total_hours: str,
        icon_path: str = "",
        badge_text: str = "Most Played",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._game_name = game_name
        self._total_hours = total_hours
        self._icon_path = icon_path
        self._badge_text = badge_text
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_game_name(self, name: str) -> None:
        """Update the game name label."""
        self._game_name = name
        self._name_label.setText(name)

    def set_total_hours(self, hours_str: str) -> None:
        """Update the total hours label."""
        self._total_hours = hours_str
        self._hours_label.setText(hours_str)

    def set_icon(self, icon_path: str) -> None:
        """Update the game icon from a file path."""
        self._icon_path = icon_path
        self._apply_icon(icon_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("GameCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(90)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(16)

        # Icon
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(_PLACEHOLDER_ICON_SIZE, _PLACEHOLDER_ICON_SIZE)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setObjectName("GameCardIcon")
        self._apply_icon(self._icon_path)
        main_layout.addWidget(self._icon_label)

        # Text block
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.setContentsMargins(0, 0, 0, 0)

        # Badge
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)

        self._badge_label = QLabel(self._badge_text)
        self._badge_label.setObjectName("GameCardBadge")
        self._badge_label.setFixedHeight(20)
        badge_row.addWidget(self._badge_label)
        badge_row.addStretch()
        text_layout.addLayout(badge_row)

        # Game name
        self._name_label = QLabel(self._game_name)
        self._name_label.setObjectName("GameCardName")
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setWeight(QFont.Weight.DemiBold)
        self._name_label.setFont(name_font)
        text_layout.addWidget(self._name_label)

        # Hours
        self._hours_label = QLabel(self._total_hours)
        self._hours_label.setObjectName("GameCardSubtitle")
        text_layout.addWidget(self._hours_label)

        text_layout.addStretch()
        main_layout.addLayout(text_layout)
        main_layout.addStretch()

        logger.debug("GameCard created: game=%s", self._game_name)

    def _apply_icon(self, icon_path: str) -> None:
        """Load icon from path, or display a placeholder emoji."""
        if icon_path:
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                self._icon_label.setPixmap(
                    pixmap.scaled(
                        _PLACEHOLDER_ICON_SIZE,
                        _PLACEHOLDER_ICON_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        # Fallback: text placeholder
        self._icon_label.setText("🎮")
        self._icon_label.setStyleSheet(
            "font-size: 32px; background-color: transparent;"
        )