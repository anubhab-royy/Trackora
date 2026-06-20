"""
Tests for GameService — Phase 5

Covers:
    AC-001 Add Game: duplicate prevention, process name detection, persistence
    Edit Game: field validation, duplicate path exclusion, not-found guard
    Delete Game: not-found guard, successful deletion
    Enable / Disable: state toggling, not-found guard, repository error
    Game Model: platform fields
    Import Discovered Games: bulk import with dedup

All tests use unittest.mock to isolate GameService from the database.
The mock mirrors the real GamesRepository interface from Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from database.models.game import Game
from services.game_service import (
    AddGameRequest,
    EditGameRequest,
    GameService,
    GameServiceResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(
    game_id: int = 1,
    name: str = "Test Game",
    process_name: str = "game.exe",
    executable_path: str = r"C:\Games\game.exe",
    is_enabled: bool = True,
    platform: str = "",
    platform_id: str = "",
    is_auto_discovered: bool = False,
) -> Game:
    """Construct a Game with optional platform fields."""
    return Game(
        name=name,
        process_name=process_name,
        executable_path=executable_path,
        is_enabled=is_enabled,
        id=game_id,
        first_played=None,
        last_played=None,
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
        platform=platform,
        platform_id=platform_id,
        is_auto_discovered=is_auto_discovered,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_repo() -> MagicMock:
    """
    A MagicMock that mirrors GamesRepository's public interface.
    Defaults:
        get_all()                       → []
        get_by_id(n)                    → None
        exists_by_executable_path(path) → False
        add(game)                       → game (returned unchanged)
    """
    repo = MagicMock()
    repo.get_all.return_value = []
    repo.get_by_id.return_value = None
    repo.get_by_executable_path.return_value = None
    repo.get_by_platform_id.return_value = None
    repo.exists_by_executable_path.return_value = False
    repo.exists_by_platform_id.return_value = False
    repo.add.side_effect = lambda game: game   # return the same object
    return repo


@pytest.fixture()
def service(mock_repo: MagicMock) -> GameService:
    return GameService(games_repository=mock_repo)


# ---------------------------------------------------------------------------
# Utility — patch Path.is_file
# ---------------------------------------------------------------------------

def _file_exists(exists: bool):
    """Context manager: patch Path.is_file to return `exists`."""
    return patch.object(Path, "is_file", return_value=exists)


# ===========================================================================
# get_all_games
# ===========================================================================

class TestGetAllGames:

    def test_returns_empty_list_when_no_games(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_all.return_value = []
        assert service.get_all_games() == []

    def test_delegates_to_repository(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        games = [_make_game(1, "Alpha"), _make_game(2, "Beta")]
        mock_repo.get_all.return_value = games
        result = service.get_all_games()
        assert result == games
        mock_repo.get_all.assert_called_once()

    def test_returns_empty_list_on_repository_exception(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_all.side_effect = RuntimeError("connection lost")
        result = service.get_all_games()
        assert result == []


# ===========================================================================
# add_game
# ===========================================================================

class TestAddGame:

    def test_rejects_blank_name(self, service: GameService) -> None:
        req = AddGameRequest(name="   ", executable_path=r"C:\game.exe")
        result = service.add_game(req)
        assert result.success is False
        assert "name" in result.message.lower()

    def test_rejects_empty_executable_path(self, service: GameService) -> None:
        req = AddGameRequest(name="My Game", executable_path="")
        result = service.add_game(req)
        assert result.success is False

    def test_rejects_nonexistent_file(self, service: GameService) -> None:
        req = AddGameRequest(name="My Game", executable_path=r"C:\missing\game.exe")
        with _file_exists(False):
            result = service.add_game(req)
        assert result.success is False

    def test_rejects_duplicate_executable_path(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """AC-001: No duplicate game is created."""
        mock_repo.get_by_executable_path.return_value = _make_game(name="Existing Game")

        req = AddGameRequest(name="New Game", executable_path=r"C:\Games\game.exe")
        with _file_exists(True):
            result = service.add_game(req)

        assert result.success is False
        assert "already" in result.message.lower()
        mock_repo.add.assert_not_called()

    def test_adds_game_successfully(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """AC-001: Game is added to database and returned."""
        mock_repo.exists_by_executable_path.return_value = False

        req = AddGameRequest(name="Counter-Strike 2", executable_path=r"C:\Games\cs2.exe")
        with _file_exists(True):
            result = service.add_game(req)

        assert result.success is True
        assert result.game is not None
        mock_repo.add.assert_called_once()

    def test_process_name_extracted_from_executable_filename(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """AC-001: Process name is detected from the executable."""
        mock_repo.exists_by_executable_path.return_value = False

        # Capture the Game object passed to repo.add
        captured: list[Game] = []
        def capture_add(game: Game) -> Game:
            captured.append(game)
            return game
        mock_repo.add.side_effect = capture_add

        req = AddGameRequest(
            name="The Witcher 3",
            executable_path=r"C:\Games\witcher3\witcher3.exe",
        )
        with _file_exists(True):
            result = service.add_game(req)

        assert result.success is True
        assert len(captured) == 1
        assert captured[0].process_name == "witcher3.exe"

    def test_process_name_is_only_filename_not_full_path(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """Process name must be the bare filename, not the full path."""
        mock_repo.exists_by_executable_path.return_value = False
        captured: list[Game] = []
        mock_repo.add.side_effect = lambda g: captured.append(g) or g

        req = AddGameRequest(
            name="Deep Rock",
            executable_path=r"C:\Program Files\Steam\steamapps\FSD\Binaries\Win64\FSD-Win64-Shipping.exe",
        )
        with _file_exists(True):
            service.add_game(req)

        assert captured[0].process_name == "FSD-Win64-Shipping.exe"

    def test_returns_failure_when_repository_raises(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.exists_by_executable_path.return_value = False
        mock_repo.add.side_effect = RuntimeError("disk full")

        req = AddGameRequest(name="Game", executable_path=r"C:\game.exe")
        with _file_exists(True):
            result = service.add_game(req)

        assert result.success is False
        assert result.game is None

    def test_trims_name_whitespace(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """Leading/trailing whitespace in name is stripped before persistence."""
        mock_repo.exists_by_executable_path.return_value = False
        captured: list[Game] = []
        mock_repo.add.side_effect = lambda g: captured.append(g) or g

        req = AddGameRequest(name="  Hades  ", executable_path=r"C:\Hades\Hades.exe")
        with _file_exists(True):
            result = service.add_game(req)

        assert result.success is True
        assert captured[0].name == "Hades"


# ===========================================================================
# edit_game
# ===========================================================================

class TestEditGame:

    def test_rejects_blank_name(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game()
        req = EditGameRequest(game_id=1, name="", executable_path=r"C:\game.exe")
        with _file_exists(True):
            result = service.edit_game(req)
        assert result.success is False

    def test_rejects_nonexistent_file(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game()
        req = EditGameRequest(game_id=1, name="X", executable_path=r"C:\missing.exe")
        with _file_exists(False):
            result = service.edit_game(req)
        assert result.success is False

    def test_rejects_when_game_not_found(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = None
        req = EditGameRequest(game_id=99, name="X", executable_path=r"C:\x.exe")
        with _file_exists(True):
            result = service.edit_game(req)
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_rejects_executable_path_used_by_different_game(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """Editing game 1 to use game 2's executable is not allowed."""
        mock_repo.get_by_id.return_value = _make_game(
            game_id=1, executable_path=r"C:\game1.exe"
        )
        # The path we want belongs to a different game
        mock_repo.get_by_executable_path.return_value = _make_game(
            game_id=2, name="Other Game", executable_path=r"C:\game2.exe"
        )

        req = EditGameRequest(game_id=1, name="Game One", executable_path=r"C:\game2.exe")
        with _file_exists(True):
            result = service.edit_game(req)

        assert result.success is False
        mock_repo.update.assert_not_called()

    def test_allows_same_path_for_same_game(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """Editing a game without changing executable_path must succeed."""
        game = _make_game(game_id=1, executable_path=r"C:\Games\game.exe")
        mock_repo.get_by_id.return_value = game
        # The path exists, but it belongs to this game — service skips duplicate check
        # because the path hasn't changed.
        mock_repo.exists_by_executable_path.return_value = True  # irrelevant; path unchanged

        req = EditGameRequest(
            game_id=1, name="Renamed", executable_path=r"C:\Games\game.exe"
        )
        with _file_exists(True):
            result = service.edit_game(req)

        # exists_by_executable_path must NOT have been called (path unchanged)
        mock_repo.exists_by_executable_path.assert_not_called()
        assert result.success is True

    def test_updates_name_and_process_name(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        game = _make_game(
            game_id=1,
            name="Old Name",
            executable_path=r"C:\Games\oldgame.exe",
        )
        mock_repo.get_by_id.return_value = game
        mock_repo.exists_by_executable_path.return_value = False

        req = EditGameRequest(
            game_id=1, name="New Name", executable_path=r"C:\Games\newgame.exe"
        )
        with _file_exists(True):
            result = service.edit_game(req)

        assert result.success is True
        # repo.update must have been called with the mutated game
        mock_repo.update.assert_called_once()
        updated_game: Game = mock_repo.update.call_args[0][0]
        assert updated_game.name == "New Name"
        assert updated_game.process_name == "newgame.exe"
        assert updated_game.executable_path == r"C:\Games\newgame.exe"

    def test_returns_failure_when_repository_raises(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game()
        mock_repo.exists_by_executable_path.return_value = False
        mock_repo.update.side_effect = RuntimeError("write error")

        req = EditGameRequest(game_id=1, name="X", executable_path=r"C:\game.exe")
        with _file_exists(True):
            result = service.edit_game(req)

        assert result.success is False


# ===========================================================================
# delete_game
# ===========================================================================

class TestDeleteGame:

    def test_rejects_nonexistent_game(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = None
        result = service.delete_game(99)
        assert result.success is False
        assert "not found" in result.message.lower()
        mock_repo.delete.assert_not_called()

    def test_deletes_successfully(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game(game_id=1)
        result = service.delete_game(1)
        assert result.success is True
        mock_repo.delete.assert_called_once_with(1)

    def test_returns_failure_when_repository_raises(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game()
        mock_repo.delete.side_effect = RuntimeError("foreign key constraint")
        result = service.delete_game(1)
        assert result.success is False
        assert result.game is None


# ===========================================================================
# set_enabled
# ===========================================================================

class TestSetEnabled:

    def test_enables_a_disabled_game(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game(is_enabled=False)
        result = service.set_enabled(1, enabled=True)
        assert result.success is True
        mock_repo.set_enabled.assert_called_once_with(1, True)

    def test_disables_an_enabled_game(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game(is_enabled=True)
        result = service.set_enabled(1, enabled=False)
        assert result.success is True
        mock_repo.set_enabled.assert_called_once_with(1, False)

    def test_rejects_nonexistent_game(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = None
        result = service.set_enabled(999, enabled=True)
        assert result.success is False
        assert "not found" in result.message.lower()
        mock_repo.set_enabled.assert_not_called()

    def test_returns_failure_when_repository_raises(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game()
        mock_repo.set_enabled.side_effect = RuntimeError("db locked")
        result = service.set_enabled(1, enabled=False)
        assert result.success is False

    def test_success_message_includes_game_name(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        mock_repo.get_by_id.return_value = _make_game(name="Cyberpunk 2077")
        result = service.set_enabled(1, enabled=False)
        assert result.success is True
        assert "Cyberpunk 2077" in result.message


# ===========================================================================
# Game Model — platform fields
# ===========================================================================

class TestGameModel:

    def test_accepts_platform_fields(self) -> None:
        game = Game(
            name="CS2",
            process_name="cs2.exe",
            executable_path="/games/cs2.exe",
            platform="steam",
            platform_id="730",
            is_auto_discovered=True,
        )
        assert game.platform == "steam"
        assert game.platform_id == "730"
        assert game.is_auto_discovered is True

    def test_defaults_to_empty_platform(self) -> None:
        game = Game(
            name="Game",
            process_name="game.exe",
            executable_path="/game.exe",
        )
        assert game.platform == ""
        assert game.platform_id == ""
        assert game.is_auto_discovered is False

    def test_backwards_compatible_construction(self) -> None:
        """Existing code that constructs Game without platform fields still works."""
        game = Game(
            name="Legacy",
            process_name="legacy.exe",
            executable_path="/legacy.exe",
        )
        assert game.platform == ""
        assert game.platform_id == ""
        assert game.is_auto_discovered is False


# ===========================================================================
# AddGameRequest — platform fields
# ===========================================================================

class TestAddGameRequest:

    def test_accepts_platform_fields(self) -> None:
        req = AddGameRequest(
            name="CS2",
            executable_path="/cs2.exe",
            platform="steam",
            platform_id="730",
            is_auto_discovered=True,
        )
        assert req.platform == "steam"
        assert req.platform_id == "730"
        assert req.is_auto_discovered is True

    def test_defaults_to_empty_platform(self) -> None:
        req = AddGameRequest(name="Game", executable_path="/game.exe")
        assert req.platform == ""
        assert req.platform_id == ""
        assert req.is_auto_discovered is False


# ===========================================================================
# Import Discovered Games
# ===========================================================================

class TestImportDiscoveredGames:

    def test_imports_valid_candidates(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """Multiple valid candidates are imported."""
        mock_repo.exists_by_executable_path.return_value = False
        mock_repo.add.side_effect = lambda g: g

        candidates = [
            _make_candidate("CS2", "/cs2.exe", "steam", "730"),
            _make_candidate("Dota 2", "/dota2.exe", "steam", "570"),
        ]

        with _file_exists(True):
            result = service.import_discovered_games(candidates)

        assert result.success is True
        assert "2" in result.message

    def test_skips_duplicates_by_executable_path(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """Duplicate by executable_path is skipped."""
        existing_game = _make_game(name="Existing Game", executable_path="/existing.exe")
        mock_repo.get_by_executable_path.side_effect = lambda p: existing_game if p == "/existing.exe" else None
        mock_repo.add.side_effect = lambda g: g

        candidates = [
            _make_candidate("Exist", "/existing.exe", "steam", "1"),
            _make_candidate("New", "/new.exe", "steam", "2"),
        ]

        with _file_exists(True):
            result = service.import_discovered_games(candidates)

        assert result.success is True
        assert "1" in result.message
        assert mock_repo.add.call_count == 1

    def test_empty_candidates_list(self, service: GameService) -> None:
        """Empty list returns failure with no import message."""
        result = service.import_discovered_games([])
        assert result.success is False
        assert "No games" in result.message

    def test_repository_error_handled_gracefully(
        self, service: GameService, mock_repo: MagicMock
    ) -> None:
        """Repository error during import returns failure."""
        mock_repo.exists_by_executable_path.return_value = False
        mock_repo.add.side_effect = RuntimeError("disk full")

        candidates = [_make_candidate("CS2", "/cs2.exe", "steam", "730")]

        with _file_exists(True):
            result = service.import_discovered_games(candidates)

        assert result.success is False


# ===========================================================================
# _extract_process_name (static helper)
# ===========================================================================

class TestExtractProcessName:

    def test_windows_absolute_path(self) -> None:
        assert (
            GameService._extract_process_name(r"C:\Games\MyGame\game.exe")
            == "game.exe"
        )

    def test_deep_windows_path(self) -> None:
        assert (
            GameService._extract_process_name(
                r"C:\Program Files (x86)\Steam\steamapps\common\Hades\Hades.exe"
            )
            == "Hades.exe"
        )

    def test_unix_style_path(self) -> None:
        assert (
            GameService._extract_process_name("/home/user/games/witcher3.exe")
            == "witcher3.exe"
        )

    def test_filename_only(self) -> None:
        assert GameService._extract_process_name("game.exe") == "game.exe"


# ---------------------------------------------------------------------------
# Helpers for discovery tests
# ---------------------------------------------------------------------------

def _make_candidate(
    name: str = "Game",
    exe: str = "/game.exe",
    platform: str = "steam",
    platform_id: str = "id",
) -> object:
    """Create a duck-typed candidate game object for service testing."""
    from types import SimpleNamespace
    return SimpleNamespace(
        name=name,
        executable_path=exe,
        platform=platform,
        platform_id=platform_id,
        is_auto_discovered=True,
        process_name="",
    )
