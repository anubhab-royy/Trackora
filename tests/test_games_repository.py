# 22 tests: CRUD, AC-001 dedup

"""
Tests for GamesRepository.

Validates all CRUD operations and the duplicate-prevention logic
required by AC-001.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from database.models.game import Game


def _make_game(
    name: str = "Elden Ring",
    process_name: str = "eldenring.exe",
    executable_path: str = "C:\\Games\\eldenring.exe",
) -> Game:
    return Game(name=name, process_name=process_name, executable_path=executable_path)


class TestGamesRepositoryAdd:
    def test_add_returns_game_with_id(self, games_repo):
        game = games_repo.add(_make_game())
        assert game.id is not None
        assert game.id > 0

    def test_added_game_retrievable(self, games_repo):
        added = games_repo.add(_make_game())
        fetched = games_repo.get_by_id(added.id)
        assert fetched is not None
        assert fetched.name == "Elden Ring"

    def test_created_at_is_set(self, games_repo):
        before = datetime.utcnow()
        game = games_repo.add(_make_game())
        after = datetime.utcnow()
        assert before <= game.created_at <= after

    def test_updated_at_is_set(self, games_repo):
        before = datetime.utcnow()
        game = games_repo.add(_make_game())
        after = datetime.utcnow()
        assert before <= game.updated_at <= after

    def test_count_increases(self, games_repo):
        assert games_repo.count() == 0
        games_repo.add(_make_game("Game1", "g1.exe", "C:\\g1.exe"))
        games_repo.add(_make_game("Game2", "g2.exe", "C:\\g2.exe"))
        assert games_repo.count() == 2


class TestGamesRepositoryGet:
    def test_get_by_id_returns_correct_game(self, games_repo):
        g1 = games_repo.add(_make_game("Alpha", "a.exe", "C:\\a.exe"))
        g2 = games_repo.add(_make_game("Beta", "b.exe", "C:\\b.exe"))
        assert games_repo.get_by_id(g1.id).name == "Alpha"
        assert games_repo.get_by_id(g2.id).name == "Beta"

    def test_get_by_id_returns_none_for_missing(self, games_repo):
        assert games_repo.get_by_id(9999) is None

    def test_get_all_returns_all_games(self, games_repo):
        games_repo.add(_make_game("Alpha", "a.exe", "C:\\a.exe"))
        games_repo.add(_make_game("Beta", "b.exe", "C:\\b.exe"))
        games_repo.add(_make_game("Gamma", "c.exe", "C:\\c.exe"))
        all_games = games_repo.get_all()
        assert len(all_games) == 3

    def test_get_all_ordered_by_name(self, games_repo):
        games_repo.add(_make_game("Zelda", "z.exe", "C:\\z.exe"))
        games_repo.add(_make_game("Alpha", "a.exe", "C:\\a.exe"))
        games_repo.add(_make_game("Minecraft", "m.exe", "C:\\m.exe"))
        names = [g.name for g in games_repo.get_all()]
        assert names == sorted(names, key=str.lower)

    def test_get_all_enabled_excludes_disabled(self, games_repo):
        enabled = _make_game("Enabled", "e.exe", "C:\\e.exe")
        enabled.is_enabled = True
        disabled = _make_game("Disabled", "d.exe", "C:\\d.exe")
        disabled.is_enabled = False
        games_repo.add(enabled)
        games_repo.add(disabled)

        result = games_repo.get_all_enabled()
        names = [g.name for g in result]
        assert "Enabled" in names
        assert "Disabled" not in names

    def test_get_by_process_name_case_insensitive(self, games_repo):
        games_repo.add(_make_game("Elden Ring", "eldenring.exe", "C:\\elden.exe"))
        found = games_repo.get_by_process_name("ELDENRING.EXE")
        assert found is not None
        assert found.name == "Elden Ring"

    def test_get_by_process_name_returns_none_if_disabled(self, games_repo):
        g = _make_game("Disabled Game", "disabled.exe", "C:\\disabled.exe")
        g.is_enabled = False
        games_repo.add(g)
        assert games_repo.get_by_process_name("disabled.exe") is None

    def test_get_by_process_name_returns_none_when_missing(self, games_repo):
        assert games_repo.get_by_process_name("notexist.exe") is None


class TestGamesRepositoryDuplicatePrevention:
    """AC-001: No duplicate game is created."""

    def test_exists_by_executable_path_true(self, games_repo):
        games_repo.add(_make_game())
        assert games_repo.exists_by_executable_path("C:\\Games\\eldenring.exe") is True

    def test_exists_by_executable_path_false(self, games_repo):
        assert games_repo.exists_by_executable_path("C:\\nowhere.exe") is False


class TestGamesRepositoryUpdate:
    def test_update_changes_name(self, games_repo):
        game = games_repo.add(_make_game())
        game.name = "New Name"
        games_repo.update(game)
        fetched = games_repo.get_by_id(game.id)
        assert fetched.name == "New Name"

    def test_update_changes_is_enabled(self, games_repo):
        game = games_repo.add(_make_game())
        assert game.is_enabled is True
        game.is_enabled = False
        games_repo.update(game)
        fetched = games_repo.get_by_id(game.id)
        assert fetched.is_enabled is False

    def test_update_sets_updated_at(self, games_repo):
        game = games_repo.add(_make_game())
        old_updated_at = game.updated_at
        game.name = "Updated"
        games_repo.update(game)
        fetched = games_repo.get_by_id(game.id)
        assert fetched.updated_at >= old_updated_at

    def test_update_without_id_raises(self, games_repo):
        game = _make_game()  # no id
        with pytest.raises(ValueError):
            games_repo.update(game)

    def test_update_last_played_sets_both_fields(self, games_repo):
        game = games_repo.add(_make_game())
        ts = datetime(2024, 6, 1, 10, 0, 0)
        games_repo.update_last_played(game.id, ts)
        fetched = games_repo.get_by_id(game.id)
        assert fetched.first_played == ts
        assert fetched.last_played == ts

    def test_update_last_played_does_not_overwrite_first_played(self, games_repo):
        game = games_repo.add(_make_game())
        first = datetime(2024, 1, 1, 10, 0, 0)
        second = datetime(2024, 6, 1, 10, 0, 0)
        games_repo.update_last_played(game.id, first)
        games_repo.update_last_played(game.id, second)
        fetched = games_repo.get_by_id(game.id)
        assert fetched.first_played == first   # not overwritten
        assert fetched.last_played == second   # updated


class TestGamesRepositoryDelete:
    def test_delete_removes_game(self, games_repo):
        game = games_repo.add(_make_game())
        games_repo.delete(game.id)
        assert games_repo.get_by_id(game.id) is None

    def test_delete_reduces_count(self, games_repo):
        g1 = games_repo.add(_make_game("G1", "g1.exe", "C:\\g1.exe"))
        games_repo.add(_make_game("G2", "g2.exe", "C:\\g2.exe"))
        assert games_repo.count() == 2
        games_repo.delete(g1.id)
        assert games_repo.count() == 1