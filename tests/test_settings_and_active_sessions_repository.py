# 24 tests: settings + recovery

"""
Tests for SettingsRepository and ActiveSessionsRepository.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from database.models.active_session import ActiveSession


# ======================================================================
# SettingsRepository
# ======================================================================

class TestSettingsRepositorySet:
    def test_set_creates_new_setting(self, settings_repo):
        settings_repo.set("dark_mode", "true")
        result = settings_repo.get("dark_mode")
        assert result is not None
        assert result.value == "true"

    def test_set_updates_existing_setting(self, settings_repo):
        settings_repo.set("dark_mode", "true")
        settings_repo.set("dark_mode", "false")
        result = settings_repo.get("dark_mode")
        assert result.value == "false"

    def test_set_returns_setting(self, settings_repo):
        setting = settings_repo.set("key1", "val1")
        assert setting.key == "key1"
        assert setting.value == "val1"

    def test_set_bool_true(self, settings_repo):
        settings_repo.set_bool("dark_mode", True)
        assert settings_repo.get_bool("dark_mode") is True

    def test_set_bool_false(self, settings_repo):
        settings_repo.set_bool("dark_mode", False)
        assert settings_repo.get_bool("dark_mode") is False


class TestSettingsRepositoryGet:
    def test_get_returns_none_for_missing_key(self, settings_repo):
        assert settings_repo.get("nonexistent") is None

    def test_get_value_returns_default_for_missing(self, settings_repo):
        assert settings_repo.get_value("missing", default="fallback") == "fallback"

    def test_get_value_returns_stored_value(self, settings_repo):
        settings_repo.set("theme", "dark")
        assert settings_repo.get_value("theme") == "dark"

    def test_get_bool_returns_default_for_missing(self, settings_repo):
        assert settings_repo.get_bool("nonexistent", default=True) is True
        assert settings_repo.get_bool("nonexistent", default=False) is False

    def test_get_all_returns_all_settings(self, settings_repo):
        settings_repo.set("a", "1")
        settings_repo.set("b", "2")
        settings_repo.set("c", "3")
        all_settings = settings_repo.get_all()
        assert len(all_settings) == 3

    def test_get_all_ordered_by_key(self, settings_repo):
        settings_repo.set("z", "1")
        settings_repo.set("a", "2")
        settings_repo.set("m", "3")
        keys = [s.key for s in settings_repo.get_all()]
        assert keys == sorted(keys)


class TestSettingsRepositoryDefaults:
    def test_set_defaults_inserts_missing_keys(self, settings_repo):
        settings_repo.set_defaults({
            "dark_mode": "false",
            "start_with_windows": "false",
            "minimize_to_tray": "true",
        })
        assert settings_repo.get_value("dark_mode") == "false"
        assert settings_repo.get_value("minimize_to_tray") == "true"

    def test_set_defaults_does_not_overwrite_existing(self, settings_repo):
        settings_repo.set("dark_mode", "true")
        settings_repo.set_defaults({"dark_mode": "false"})
        assert settings_repo.get_value("dark_mode") == "true"  # unchanged


class TestSettingsRepositoryDelete:
    def test_delete_removes_setting(self, settings_repo):
        settings_repo.set("temp_key", "temp_value")
        settings_repo.delete("temp_key")
        assert settings_repo.get("temp_key") is None

    def test_delete_nonexistent_does_not_raise(self, settings_repo):
        settings_repo.delete("does_not_exist")  # must not raise


# ======================================================================
# ActiveSessionsRepository
# ======================================================================

def _make_active_session(game_id: int = 1, process_id: int = 1234) -> ActiveSession:
    return ActiveSession(
        game_id=game_id,
        process_id=process_id,
        start_time=datetime.utcnow(),
    )


class TestActiveSessionsRepositoryStart:
    def test_start_session_returns_with_id(self, active_sessions_repo):
        a = active_sessions_repo.start_session(_make_active_session())
        assert a.id is not None
        assert a.id > 0

    def test_start_session_is_retrievable(self, active_sessions_repo):
        a = active_sessions_repo.start_session(_make_active_session(game_id=5))
        fetched = active_sessions_repo.get_by_id(a.id)
        assert fetched is not None
        assert fetched.game_id == 5

    def test_count_increases(self, active_sessions_repo):
        assert active_sessions_repo.count() == 0
        active_sessions_repo.start_session(_make_active_session(1))
        active_sessions_repo.start_session(_make_active_session(2))
        assert active_sessions_repo.count() == 2


class TestActiveSessionsRepositoryGet:
    def test_get_by_id_returns_none_for_missing(self, active_sessions_repo):
        assert active_sessions_repo.get_by_id(9999) is None

    def test_get_by_game_id_returns_session(self, active_sessions_repo):
        active_sessions_repo.start_session(_make_active_session(game_id=7))
        result = active_sessions_repo.get_by_game_id(7)
        assert result is not None
        assert result.game_id == 7

    def test_get_by_game_id_returns_none_when_missing(self, active_sessions_repo):
        assert active_sessions_repo.get_by_game_id(999) is None

    def test_get_all_returns_all_records(self, active_sessions_repo):
        active_sessions_repo.start_session(_make_active_session(1))
        active_sessions_repo.start_session(_make_active_session(2))
        active_sessions_repo.start_session(_make_active_session(3))
        assert len(active_sessions_repo.get_all()) == 3

    def test_has_active_session_true(self, active_sessions_repo):
        active_sessions_repo.start_session(_make_active_session(game_id=10))
        assert active_sessions_repo.has_active_session(10) is True

    def test_has_active_session_false(self, active_sessions_repo):
        assert active_sessions_repo.has_active_session(99) is False


class TestActiveSessionsRepositoryEnd:
    def test_end_session_removes_record(self, active_sessions_repo):
        a = active_sessions_repo.start_session(_make_active_session())
        active_sessions_repo.end_session(a.id)
        assert active_sessions_repo.get_by_id(a.id) is None

    def test_end_session_by_game_id(self, active_sessions_repo):
        active_sessions_repo.start_session(_make_active_session(game_id=42))
        active_sessions_repo.end_session_by_game_id(42)
        assert active_sessions_repo.has_active_session(42) is False

    def test_clear_all_removes_all(self, active_sessions_repo):
        active_sessions_repo.start_session(_make_active_session(1))
        active_sessions_repo.start_session(_make_active_session(2))
        deleted = active_sessions_repo.clear_all()
        assert deleted == 2
        assert active_sessions_repo.count() == 0

    def test_clear_all_returns_count(self, active_sessions_repo):
        for i in range(1, 4):
            active_sessions_repo.start_session(_make_active_session(i))
        assert active_sessions_repo.clear_all() == 3


# ======================================================================
# AC-008: Crash recovery — active sessions survive restart
# ======================================================================

class TestCrashRecovery:
    """
    AC-008: When GameTracker restarts after a crash, active sessions must
    be present in the database so recovery can proceed.
    """

    def test_active_sessions_persist_for_recovery(self, db_manager):
        """
        Simulate: session starts → app crashes → app restarts.
        The active_sessions table must still contain the orphaned row.
        """
        from database.repositories import ActiveSessionsRepository, GamesRepository
        from database.models.game import Game

        conn = db_manager.connection
        games_repo = GamesRepository(conn)
        active_repo = ActiveSessionsRepository(conn)

        game = games_repo.add(
            Game(name="Elden Ring", process_name="eldenring.exe",
                 executable_path="C:\\eldenring.exe")
        )
        # Simulate session start (would normally be deleted when session ends)
        a = active_repo.start_session(
            ActiveSession(
                game_id=game.id,
                process_id=99999,
                start_time=datetime(2024, 6, 1, 10, 0, 0),
            )
        )

        # "Crash" — the app never calls end_session()
        # On restart, get_all() must surface the orphaned row
        orphans = active_repo.get_all()
        assert len(orphans) == 1
        assert orphans[0].game_id == game.id
        assert orphans[0].process_id == 99999