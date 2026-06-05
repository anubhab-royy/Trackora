# 27 tests: validation, factories

"""
Tests for GameTracker dataclass models.

Covers:
    - Successful construction
    - Validation (ValueError on bad input)
    - Helper methods / factories
"""

from __future__ import annotations

from datetime import datetime

import pytest

from database.models.game import Game
from database.models.session import Session
from database.models.active_session import ActiveSession
from database.models.setting import Setting


class TestGameModel:
    def test_basic_construction(self):
        game = Game(
            name="Elden Ring",
            process_name="eldenring.exe",
            executable_path="C:\\Games\\eldenring.exe",
        )
        assert game.name == "Elden Ring"
        assert game.process_name == "eldenring.exe"
        assert game.is_enabled is True
        assert game.id is None

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            Game(name="", process_name="game.exe", executable_path="C:\\game.exe")

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            Game(name="   ", process_name="game.exe", executable_path="C:\\game.exe")

    def test_empty_process_name_raises(self):
        with pytest.raises(ValueError, match="process_name"):
            Game(name="Game", process_name="", executable_path="C:\\game.exe")

    def test_empty_executable_path_raises(self):
        with pytest.raises(ValueError, match="executable_path"):
            Game(name="Game", process_name="game.exe", executable_path="")

    def test_optional_fields_default(self):
        game = Game(name="Game", process_name="g.exe", executable_path="C:\\g.exe")
        assert game.icon_path == ""
        assert game.first_played is None
        assert game.last_played is None

    def test_is_enabled_defaults_true(self):
        game = Game(name="Game", process_name="g.exe", executable_path="C:\\g.exe")
        assert game.is_enabled is True

    def test_created_at_auto_set(self):
        before = datetime.utcnow()
        game = Game(name="Game", process_name="g.exe", executable_path="C:\\g.exe")
        after = datetime.utcnow()
        assert before <= game.created_at <= after


class TestSessionModel:
    def _make_session(self, duration: int = 3600) -> Session:
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 11, 0, 0)
        return Session(
            game_id=1,
            start_time=start,
            end_time=end,
            duration_seconds=duration,
        )

    def test_basic_construction(self):
        s = self._make_session()
        assert s.game_id == 1
        assert s.duration_seconds == 3600
        assert s.id is None

    def test_invalid_game_id_raises(self):
        with pytest.raises(ValueError, match="game_id"):
            Session(
                game_id=0,
                start_time=datetime(2024, 1, 1),
                end_time=datetime(2024, 1, 1, 1),
                duration_seconds=3600,
            )

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="end_time"):
            Session(
                game_id=1,
                start_time=datetime(2024, 1, 1, 12),
                end_time=datetime(2024, 1, 1, 11),
                duration_seconds=0,
            )

    def test_negative_duration_raises(self):
        with pytest.raises(ValueError, match="duration_seconds"):
            Session(
                game_id=1,
                start_time=datetime(2024, 1, 1, 10),
                end_time=datetime(2024, 1, 1, 11),
                duration_seconds=-1,
            )

    def test_from_start_and_end_factory(self):
        start = datetime(2024, 6, 1, 14, 0, 0)
        end = datetime(2024, 6, 1, 15, 30, 0)
        s = Session.from_start_and_end(game_id=5, start_time=start, end_time=end)
        assert s.duration_seconds == 5400  # 90 minutes
        assert s.game_id == 5

    def test_factory_same_time_gives_zero_duration(self):
        t = datetime(2024, 6, 1, 10, 0, 0)
        s = Session.from_start_and_end(game_id=1, start_time=t, end_time=t)
        assert s.duration_seconds == 0


class TestActiveSessionModel:
    def test_basic_construction(self):
        a = ActiveSession(
            game_id=1,
            process_id=12345,
            start_time=datetime(2024, 6, 1, 10, 0),
        )
        assert a.game_id == 1
        assert a.process_id == 12345
        assert a.id is None

    def test_invalid_game_id_raises(self):
        with pytest.raises(ValueError, match="game_id"):
            ActiveSession(game_id=0, process_id=999, start_time=datetime.utcnow())

    def test_invalid_process_id_raises(self):
        with pytest.raises(ValueError, match="process_id"):
            ActiveSession(game_id=1, process_id=-1, start_time=datetime.utcnow())

    def test_created_at_auto_set(self):
        before = datetime.utcnow()
        a = ActiveSession(game_id=1, process_id=100, start_time=datetime.utcnow())
        after = datetime.utcnow()
        assert before <= a.created_at <= after


class TestSettingModel:
    def test_basic_construction(self):
        s = Setting(key="dark_mode", value="true")
        assert s.key == "dark_mode"
        assert s.value == "true"

    def test_empty_key_raises(self):
        with pytest.raises(ValueError, match="key"):
            Setting(key="", value="true")

    def test_whitespace_key_raises(self):
        with pytest.raises(ValueError, match="key"):
            Setting(key="   ", value="false")

    def test_as_bool_true(self):
        assert Setting(key="k", value="true").as_bool() is True
        assert Setting(key="k", value="True").as_bool() is True
        assert Setting(key="k", value="1").as_bool() is True
        assert Setting(key="k", value="yes").as_bool() is True

    def test_as_bool_false(self):
        assert Setting(key="k", value="false").as_bool() is False
        assert Setting(key="k", value="0").as_bool() is False
        assert Setting(key="k", value="no").as_bool() is False

    def test_as_int(self):
        assert Setting(key="k", value="42").as_int() == 42

    def test_as_float(self):
        assert Setting(key="k", value="3.14").as_float() == pytest.approx(3.14)

    def test_from_bool_factory_true(self):
        s = Setting.from_bool("dark_mode", True)
        assert s.value == "true"
        assert s.as_bool() is True

    def test_from_bool_factory_false(self):
        s = Setting.from_bool("dark_mode", False)
        assert s.value == "false"
        assert s.as_bool() is False