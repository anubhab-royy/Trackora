# tests/test_stat_card.py
"""
Tests for StatCard and GameCard widgets.
Uses pytest-qt / QApplication fixture for headless testing.
"""

import pytest

# Guard: skip entire module if PyQt6 is not installed or display unavailable.
pytest.importorskip("PyQt6")


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class TestStatCard:
    def test_stat_card_creates_without_error(self, qapp):
        from ui.widgets.stat_card import StatCard
        card = StatCard(label="Total Playtime", value="10h 0m", icon="⏱")
        assert card is not None

    def test_stat_card_default_value_displayed(self, qapp):
        from ui.widgets.stat_card import StatCard
        card = StatCard(label="Today", value="30m")
        assert card._value_label.text() == "30m"

    def test_stat_card_set_value_updates_label(self, qapp):
        from ui.widgets.stat_card import StatCard
        card = StatCard(label="Today", value="0m")
        card.set_value("5h 10m")
        assert card._value_label.text() == "5h 10m"

    def test_stat_card_set_label_updates_text(self, qapp):
        from ui.widgets.stat_card import StatCard
        card = StatCard(label="Old Label", value="0m")
        card.set_label("New Label")
        assert "NEW LABEL" in card._label_label.text()

    def test_stat_card_set_icon_updates_icon(self, qapp):
        from ui.widgets.stat_card import StatCard
        card = StatCard(label="Week", value="0m", icon="📅")
        card.set_icon("🗓")
        assert card._icon_label.text() == "🗓"

    def test_stat_card_object_name_is_set(self, qapp):
        from ui.widgets.stat_card import StatCard
        card = StatCard(label="Month", value="0m")
        assert card.objectName() == "StatCard"


class TestGameCard:
    def test_game_card_creates_without_error(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Half-Life 2", total_hours="50h 0m")
        assert card is not None

    def test_game_card_name_displayed(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Doom Eternal", total_hours="20h 0m")
        assert card._name_label.text() == "Doom Eternal"

    def test_game_card_hours_displayed(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Witcher 3", total_hours="200h 0m")
        assert card._hours_label.text() == "200h 0m"

    def test_game_card_set_name_updates(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Old Game", total_hours="1h 0m")
        card.set_game_name("New Game")
        assert card._name_label.text() == "New Game"

    def test_game_card_set_hours_updates(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Game", total_hours="0m")
        card.set_total_hours("99h 59m")
        assert card._hours_label.text() == "99h 59m"

    def test_game_card_badge_text_displayed(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Game", total_hours="0m", badge_text="Most Played")
        assert card._badge_label.text() == "Most Played"

    def test_game_card_object_name_set(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Game", total_hours="0m")
        assert card.objectName() == "GameCard"

    def test_game_card_empty_icon_path_shows_placeholder(self, qapp):
        from ui.widgets.game_card import GameCard
        card = GameCard(game_name="Game", total_hours="0m", icon_path="")
        # Placeholder emoji should be set
        assert card._icon_label.text() == "🎮"