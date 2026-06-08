# tests/test_theme_manager.py
"""
Tests for ThemeManager.
"""

import pytest
from ui.themes.theme_manager import ThemeManager, Theme, _DARK_PALETTE, _LIGHT_PALETTE


class TestThemeManager:
    def test_default_theme_is_dark(self):
        mgr = ThemeManager()
        assert mgr.current_theme == Theme.DARK

    def test_get_stylesheet_dark_returns_string(self):
        mgr = ThemeManager()
        sheet = mgr.get_stylesheet(Theme.DARK)
        assert isinstance(sheet, str)
        assert len(sheet) > 100

    def test_get_stylesheet_light_returns_string(self):
        mgr = ThemeManager()
        sheet = mgr.get_stylesheet(Theme.LIGHT)
        assert isinstance(sheet, str)
        assert len(sheet) > 100

    def test_dark_and_light_stylesheets_differ(self):
        mgr = ThemeManager()
        dark = mgr.get_stylesheet(Theme.DARK)
        light = mgr.get_stylesheet(Theme.LIGHT)
        assert dark != light

    def test_dark_stylesheet_contains_dark_primary_bg(self):
        mgr = ThemeManager()
        sheet = mgr.get_stylesheet(Theme.DARK)
        assert _DARK_PALETTE["bg_primary"] in sheet

    def test_light_stylesheet_contains_light_primary_bg(self):
        mgr = ThemeManager()
        sheet = mgr.get_stylesheet(Theme.LIGHT)
        assert _LIGHT_PALETTE["bg_primary"] in sheet

    def test_get_palette_color_dark(self):
        mgr = ThemeManager()
        color = mgr.get_palette_color(Theme.DARK, "accent")
        assert color == _DARK_PALETTE["accent"]

    def test_get_palette_color_light(self):
        mgr = ThemeManager()
        color = mgr.get_palette_color(Theme.LIGHT, "accent")
        assert color == _LIGHT_PALETTE["accent"]

    def test_get_palette_color_invalid_key_raises(self):
        mgr = ThemeManager()
        with pytest.raises(KeyError):
            mgr.get_palette_color(Theme.DARK, "nonexistent_key")

    def test_theme_enum_values(self):
        assert Theme.DARK.value == "dark"
        assert Theme.LIGHT.value == "light"

    def test_apply_theme_requires_qapplication(self):
        mgr = ThemeManager()
        with pytest.raises(TypeError):
            mgr.apply_theme("not_a_qapp", Theme.DARK)

    def test_dark_palette_has_required_keys(self):
        required = {
            "bg_primary", "bg_card", "text_primary", "text_muted",
            "accent", "border", "sidebar_bg",
        }
        for key in required:
            assert key in _DARK_PALETTE, f"Missing key in DARK palette: {key}"

    def test_light_palette_has_required_keys(self):
        required = {
            "bg_primary", "bg_card", "text_primary", "text_muted",
            "accent", "border", "sidebar_bg",
        }
        for key in required:
            assert key in _LIGHT_PALETTE, f"Missing key in LIGHT palette: {key}"

    def test_stylesheet_contains_stat_card_selector(self):
        mgr = ThemeManager()
        sheet = mgr.get_stylesheet(Theme.DARK)
        assert "#StatCard" in sheet

    def test_stylesheet_contains_game_card_selector(self):
        mgr = ThemeManager()
        sheet = mgr.get_stylesheet(Theme.DARK)
        assert "#GameCard" in sheet

    def test_stylesheet_contains_nav_button_selector(self):
        mgr = ThemeManager()
        sheet = mgr.get_stylesheet(Theme.DARK)
        assert "#NavButton" in sheet