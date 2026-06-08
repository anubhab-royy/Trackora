# ui/themes/theme_manager.py
"""
Theme manager for GameTracker.

Provides dark and light theme stylesheets.
No business logic. No database access.
Theme selection is controlled by the caller (reads from StatisticsService/SettingsRepository
via the controller, not directly here).
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"


# ---------------------------------------------------------------------------
# Colour palette constants
# ---------------------------------------------------------------------------

_DARK_PALETTE: dict[str, str] = {
    "bg_primary": "#1e1e2e",
    "bg_secondary": "#2a2a3e",
    "bg_card": "#2d2d44",
    "bg_card_hover": "#35354f",
    "border": "#3d3d5c",
    "text_primary": "#cdd6f4",
    "text_secondary": "#a6adc8",
    "text_muted": "#6c7086",
    "accent": "#89b4fa",
    "accent_hover": "#74c7ec",
    "success": "#a6e3a1",
    "warning": "#f9e2af",
    "error": "#f38ba8",
    "sidebar_bg": "#181825",
    "sidebar_text": "#cdd6f4",
    "sidebar_selected": "#313244",
    "sidebar_selected_text": "#89b4fa",
    "sidebar_hover": "#262637",
    "scrollbar_bg": "#2a2a3e",
    "scrollbar_handle": "#45475a",
}

_LIGHT_PALETTE: dict[str, str] = {
    "bg_primary": "#eff1f5",
    "bg_secondary": "#e6e9ef",
    "bg_card": "#ffffff",
    "bg_card_hover": "#f5f5f5",
    "border": "#ccd0da",
    "text_primary": "#4c4f69",
    "text_secondary": "#5c5f77",
    "text_muted": "#9ca0b0",
    "accent": "#1e66f5",
    "accent_hover": "#209fb5",
    "success": "#40a02b",
    "warning": "#df8e1d",
    "error": "#d20f39",
    "sidebar_bg": "#dce0e8",
    "sidebar_text": "#4c4f69",
    "sidebar_selected": "#bcc0cc",
    "sidebar_selected_text": "#1e66f5",
    "sidebar_hover": "#ccd0da",
    "scrollbar_bg": "#e6e9ef",
    "scrollbar_handle": "#bcc0cc",
}


def _build_stylesheet(p: dict[str, str]) -> str:
    """Build a complete Qt stylesheet from a palette dictionary."""
    return f"""
/* ======================================================
   GameTracker Theme Stylesheet
   ====================================================== */

QWidget {{
    background-color: {p['bg_primary']};
    color: {p['text_primary']};
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}}

QMainWindow {{
    background-color: {p['bg_primary']};
}}

/* ------ Sidebar / Navigation ------ */

#Sidebar {{
    background-color: {p['sidebar_bg']};
    border-right: 1px solid {p['border']};
}}

#NavButton {{
    background-color: transparent;
    color: {p['sidebar_text']};
    text-align: left;
    padding: 10px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    border: none;
}}

#NavButton:hover {{
    background-color: {p['sidebar_hover']};
    color: {p['sidebar_text']};
}}

#NavButton[selected="true"] {{
    background-color: {p['sidebar_selected']};
    color: {p['sidebar_selected_text']};
    font-weight: 600;
}}

#AppTitle {{
    color: {p['accent']};
    font-size: 18px;
    font-weight: 700;
    padding: 20px 16px 8px 16px;
}}

/* ------ Content Area ------ */

#ContentArea {{
    background-color: {p['bg_primary']};
}}

#PageTitle {{
    color: {p['text_primary']};
    font-size: 22px;
    font-weight: 700;
    padding: 0px 0px 4px 0px;
}}

#SectionLabel {{
    color: {p['text_secondary']};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 8px 0px 4px 0px;
}}

/* ------ Stat Card ------ */

#StatCard {{
    background-color: {p['bg_card']};
    border: 1px solid {p['border']};
    border-radius: 10px;
    padding: 16px;
}}

#StatCard:hover {{
    background-color: {p['bg_card_hover']};
    border: 1px solid {p['accent']};
}}

#StatCardValue {{
    color: {p['text_primary']};
    font-size: 28px;
    font-weight: 700;
}}

#StatCardLabel {{
    color: {p['text_muted']};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}

#StatCardIcon {{
    color: {p['accent']};
    font-size: 20px;
}}

/* ------ Game Card ------ */

#GameCard {{
    background-color: {p['bg_card']};
    border: 1px solid {p['border']};
    border-radius: 10px;
    padding: 16px;
}}

#GameCard:hover {{
    background-color: {p['bg_card_hover']};
    border: 1px solid {p['accent']};
}}

#GameCardName {{
    color: {p['text_primary']};
    font-size: 15px;
    font-weight: 600;
}}

#GameCardSubtitle {{
    color: {p['text_muted']};
    font-size: 12px;
}}

#GameCardBadge {{
    background-color: {p['accent']};
    color: {p['bg_primary']};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
}}

/* ------ Scroll Area ------ */

QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background-color: {p['scrollbar_bg']};
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: {p['scrollbar_handle']};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {p['scrollbar_bg']};
    height: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: {p['scrollbar_handle']};
    border-radius: 4px;
    min-width: 20px;
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ------ Buttons ------ */

QPushButton {{
    background-color: {p['accent']};
    color: {p['bg_primary']};
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {p['accent_hover']};
}}

QPushButton:pressed {{
    background-color: {p['border']};
}}

QPushButton#SecondaryButton {{
    background-color: {p['bg_secondary']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
}}

QPushButton#SecondaryButton:hover {{
    background-color: {p['bg_card_hover']};
}}

/* ------ Labels ------ */

QLabel {{
    background-color: transparent;
    color: {p['text_primary']};
}}

/* ------ Separator ------ */

QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {p['border']};
    background-color: {p['border']};
}}

/* ------ Misc ------ */

#EmptyStateLabel {{
    color: {p['text_muted']};
    font-size: 14px;
}}

#RefreshButton {{
    background-color: transparent;
    color: {p['text_secondary']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}}

#RefreshButton:hover {{
    background-color: {p['bg_card_hover']};
    color: {p['text_primary']};
}}
"""


class ThemeManager:
    """
    Manages application theme switching.

    Responsibilities:
    - Build stylesheet for a given theme.
    - Apply theme to a QApplication instance.

    No database access. No business logic.
    """

    def __init__(self) -> None:
        self._current_theme: Theme = Theme.DARK
        logger.info("ThemeManager initialised.")

    @property
    def current_theme(self) -> Theme:
        return self._current_theme

    def get_stylesheet(self, theme: Theme) -> str:
        """Return the complete Qt stylesheet for the given theme."""
        palette = _DARK_PALETTE if theme == Theme.DARK else _LIGHT_PALETTE
        return _build_stylesheet(palette)

    def apply_theme(self, app: object, theme: Theme) -> None:
        """
        Apply theme stylesheet to a QApplication.

        Args:
            app: QApplication instance.
            theme: Theme enum value.
        """
        from PyQt6.QtWidgets import QApplication  # local import avoids top-level Qt dep

        if not isinstance(app, QApplication):
            raise TypeError("app must be a QApplication instance.")

        stylesheet = self.get_stylesheet(theme)
        app.setStyleSheet(stylesheet)
        self._current_theme = theme
        logger.info("Applied theme: %s", theme.value)

    def get_palette_color(self, theme: Theme, key: str) -> str:
        """Return a specific palette colour for the given theme and key."""
        palette = _DARK_PALETTE if theme == Theme.DARK else _LIGHT_PALETTE
        if key not in palette:
            raise KeyError(f"Colour key '{key}' not found in theme palette.")
        return palette[key]