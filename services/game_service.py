"""
GameService — Phase 5
Mediates between the UI layer and GamesRepository.
No SQL. No UI. Pure service logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from collections.abc import Callable
from typing import Optional, TYPE_CHECKING

from database.models import Game
from database.repositories.games_repository import GamesRepository
from services.delete_game_result import DeleteGameResult

if TYPE_CHECKING:
    from services.delete_game_service import DeleteGameService

logger = logging.getLogger(__name__)


@dataclass
class AddGameRequest:
    """Data transfer object for adding a game."""
    name: str
    executable_path: str
    platform: str = ""
    platform_id: str = ""
    is_auto_discovered: bool = False


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

    def __init__(
        self,
        games_repository: GamesRepository,
        delete_game_service: Optional[DeleteGameService] = None,
    ) -> None:
        self._repo = games_repository
        self._delete_game_service = delete_game_service

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
                platform=request.platform,
                platform_id=request.platform_id,
                is_auto_discovered=request.is_auto_discovered,
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

    def delete_game(self, game_id: int) -> DeleteGameResult | GameServiceResult:
        """Delete a game by id."""
        if self._delete_game_service is not None:
            return self._delete_game_service.delete_game(game_id)

        # Fallback to basic repository delete (for backwards compatibility & testing)
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

    def import_discovered_games(self, candidates: list) -> GameServiceResult:
        """
        Bulk-import discovered game candidates.

        Consolidation-aware duplicate prevention:
        1. Skip by executable_path
        2. Skip by (platform, platform_id)
        3. If a legacy game (empty platform) matches by normalized name, update it
           instead of creating a new record (prevents game consolidation duplicates)
        4. Fall through to create new game

        Returns:
            GameServiceResult with imported/skipped counts.
        """
        if not candidates:
            return GameServiceResult(success=False, message="No games to import.")

        imported = 0
        updated = 0
        skipped = 0

        existing_games = self._repo.get_all()

        for candidate in candidates:
            # 1. Skip duplicates by executable_path
            existing = self._repo.get_by_executable_path(candidate.executable_path)
            if existing is not None:
                skipped += 1
                continue

            # 2. Skip duplicates by (platform, platform_id)
            if candidate.platform and candidate.platform_id:
                existing_platform = self._repo.get_by_platform_id(
                    candidate.platform, candidate.platform_id
                )
                if existing_platform is not None:
                    skipped += 1
                    continue

            # 3. Check for legacy game (no platform) with matching normalized name
            legacy_match = self._find_legacy_by_normalized_name(
                candidate.name, existing_games
            )
            if legacy_match is not None:
                legacy_match.platform = candidate.platform
                legacy_match.platform_id = candidate.platform_id
                legacy_match.is_auto_discovered = True
                self._repo.update(legacy_match)
                updated += 1
                logger.info(
                    "Updated legacy game id=%d with discovered platform %s/%s",
                    legacy_match.id, candidate.platform, candidate.platform_id,
                )
                continue

            # 4. No match found — create new game
            request = AddGameRequest(
                name=candidate.name,
                executable_path=candidate.executable_path,
                platform=candidate.platform,
                platform_id=candidate.platform_id,
                is_auto_discovered=getattr(candidate, "is_auto_discovered", True),
            )

            result = self.add_game(request)
            if result.success:
                imported += 1
            else:
                skipped += 1

        if imported > 0 or updated > 0:
            parts = []
            if imported > 0:
                parts.append(f"{imported} game(s) imported")
            if updated > 0:
                parts.append(f"{updated} legacy game(s) updated")
            if skipped > 0:
                parts.append(f"{skipped} skipped (already exist)")
            msg = ". ".join(parts) + "."
            return GameServiceResult(success=True, message=msg)
        else:
            return GameServiceResult(
                success=False,
                message="No games were imported. All candidates already exist.",
            )

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Strip trademark/symbol characters and lowercase for comparison."""
        return (
            name.replace("\u2122", "")
            .replace("\u00AE", "")
            .replace("\u00A9", "")
            .strip()
            .lower()
        )

    def _find_legacy_by_normalized_name(
        self, name: str, existing_games: list[Game]
    ) -> Game | None:
        """
        Find a legacy game (empty platform) whose normalized name matches.

        Used to prevent creating a duplicate discovered record when a
        manually-added game already exists with the same name.
        """
        norm = self._normalize_name(name)
        for game in existing_games:
            if not game.platform and self._normalize_name(game.name) == norm:
                return game
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_process_name(executable_path: str) -> str:
        """Extract process name (filename) from an executable path."""
        return PureWindowsPath(executable_path).name