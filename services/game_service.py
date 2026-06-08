"""
GameService — Phase 5
Mediates between the UI layer and GamesRepository.
No SQL. No UI. Pure service logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Optional

from database.models import Game
from database.repositories.games_repository import GamesRepository

logger = logging.getLogger(__name__)


@dataclass
class AddGameRequest:
    """Data transfer object for adding a game."""
    name: str
    executable_path: str


@dataclass
class EditGameRequest:
    """Data transfer object for editing a game."""
    game_id: int
    name: str
    executable_path: str


@dataclass
class GameServiceResult:
    """Result returned from GameService operations."""
    success: bool
    message: str
    game: Optional[Game] = None


class GameService:
    """
    Service for game management operations.

    Responsibilities:
    - Validate inputs before passing to repository
    - Detect process name from executable path
    - Prevent duplicate games
    - Enable/disable games
    - Delete games

    Rules:
    - No SQL here
    - No UI here
    - All persistence delegated to GamesRepository
    """

    def __init__(self, games_repository: GamesRepository) -> None:
        self._repo = games_repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_games(self) -> list[Game]:
        """Return all games ordered by name."""
        try:
            return self._repo.get_all()
        except Exception as exc:
            logger.error("Failed to retrieve games: %s", exc)
            return []

    def get_game_by_id(self, game_id: int) -> Optional[Game]:
        """Return a single game by primary key, or None."""
        try:
            return self._repo.get_by_id(game_id)
        except Exception as exc:
            logger.error("Failed to retrieve game %d: %s", game_id, exc)
            return None

    def add_game(self, request: AddGameRequest) -> GameServiceResult:
        """
        Validate and add a new game.

        Validates:
        - Name is not empty
        - Executable path is not empty and file exists
        - No duplicate game with same executable path
        """
        name = request.name.strip()
        executable_path = request.executable_path.strip()

        if not name:
            return GameServiceResult(success=False, message="Game name cannot be empty.")

        if not executable_path:
            return GameServiceResult(
                success=False, message="Executable path cannot be empty."
            )

        if not Path(executable_path).is_file():
            return GameServiceResult(
                success=False,
                message=f"Executable not found:\n{executable_path}",
            )

        # Duplicate check by executable path
        existing = self._repo.get_by_executable_path(executable_path)
        if existing is not None:
            return GameServiceResult(
                success=False,
                message=f'A game with this executable already exists: "{existing.name}".',
            )

        process_name = self._extract_process_name(executable_path)

        try:
            game = Game(
                name=name,
                process_name=process_name,
                executable_path=executable_path,
            )
            game = self._repo.add(game)
            logger.info("Added game: %s (process: %s)", name, process_name)
            return GameServiceResult(success=True, message="Game added successfully.", game=game)
        except Exception as exc:
            logger.error("Failed to add game '%s': %s", name, exc)
            return GameServiceResult(
                success=False, message="Failed to save game. Please try again."
            )

    def edit_game(self, request: EditGameRequest) -> GameServiceResult:
        """
        Validate and update an existing game.

        Validates:
        - Game exists
        - Name is not empty
        - Executable path is not empty and file exists
        - No duplicate executable path (excluding self)
        """
        name = request.name.strip()
        executable_path = request.executable_path.strip()

        if not name:
            return GameServiceResult(success=False, message="Game name cannot be empty.")

        if not executable_path:
            return GameServiceResult(
                success=False, message="Executable path cannot be empty."
            )

        if not Path(executable_path).is_file():
            return GameServiceResult(
                success=False,
                message=f"Executable not found:\n{executable_path}",
            )

        existing_game = self._repo.get_by_id(request.game_id)
        if existing_game is None:
            return GameServiceResult(success=False, message="Game not found.")

        # Duplicate check — allow same path for this game
        duplicate = self._repo.get_by_executable_path(executable_path)
        if duplicate is not None and duplicate.id != request.game_id:
            return GameServiceResult(
                success=False,
                message=f'Another game already uses this executable: "{duplicate.name}".',
            )

        process_name = self._extract_process_name(executable_path)

        try:
            existing_game.name = name
            existing_game.process_name = process_name
            existing_game.executable_path = executable_path
            self._repo.update(existing_game)
            logger.info("Updated game id=%d: %s", request.game_id, name)
            return GameServiceResult(
                success=True, message="Game updated successfully.", game=existing_game
            )
        except Exception as exc:
            logger.error("Failed to update game %d: %s", request.game_id, exc)
            return GameServiceResult(
                success=False, message="Failed to update game. Please try again."
            )

    def delete_game(self, game_id: int) -> GameServiceResult:
        """Delete a game by id."""
        game = self._repo.get_by_id(game_id)
        if game is None:
            return GameServiceResult(success=False, message="Game not found.")

        try:
            self._repo.delete(game_id)
            logger.info("Deleted game id=%d", game_id)
            return GameServiceResult(success=True, message="Game deleted successfully.")
        except Exception as exc:
            logger.error("Failed to delete game %d: %s", game_id, exc)
            return GameServiceResult(
                success=False, message="Failed to delete game. Please try again."
            )

    def set_enabled(self, game_id: int, enabled: bool) -> GameServiceResult:
        """Enable or disable tracking for a game."""
        game = self._repo.get_by_id(game_id)
        if game is None:
            return GameServiceResult(success=False, message="Game not found.")

        try:
            self._repo.set_enabled(game_id, enabled)
            state = "enabled" if enabled else "disabled"
            logger.info("Game id=%d tracking %s", game_id, state)
            return GameServiceResult(success=True, message=f'Tracking {state} for "{game.name}".')
        except Exception as exc:
            logger.error("Failed to set enabled state for game %d: %s", game_id, exc)
            return GameServiceResult(
                success=False, message="Failed to update tracking state."
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_process_name(executable_path: str) -> str:
        """Extract process name (filename) from an executable path."""
        return PureWindowsPath(executable_path).name