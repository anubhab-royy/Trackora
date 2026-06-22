"""
GamesController — Phase 5
Wires GamesView user actions to GameService calls.

Responsibilities:
- Load game list into the view model
- Handle Add, Edit, Delete, Enable/Disable actions
- Display error/success messages received from GameService
- Refresh the view after mutations

No SQL. No business logic.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import QMessageBox, QWidget

from database.models import Game
from services.game_service import AddGameRequest, EditGameRequest, GameService
from tracker.discovery.orchestrator import DiscoveryOrchestrator
from ui.games.add_game_dialog import AddGameDialog
from ui.games.discovery_dialog import DiscoveryDialog
from ui.games.games_view import GamesView

logger = logging.getLogger(__name__)


class GamesController:
    """
    Controller for the Games management screen.

    Connects:
        GamesView signals  →  GameService calls  →  GamesView refresh
    """

    def __init__(
        self,
        view: GamesView,
        game_service: GameService,
        discovery_orchestrator: Optional[DiscoveryOrchestrator] = None,
    ) -> None:
        self._view = view
        self._service = game_service
        self._orchestrator = discovery_orchestrator
        self._connect_signals()
        self.load_games()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_games(self) -> None:
        """Fetch all games from the service and populate the view."""
        games = self._service.get_all_games()
        self._view.set_games(games)

    # ------------------------------------------------------------------
    # Private — signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._view.add_requested.connect(self._on_add_requested)
        self._view.scan_requested.connect(self._on_scan_requested)
        self._view.edit_requested.connect(self._on_edit_requested)
        self._view.delete_requested.connect(self._on_delete_requested)
        self._view.toggle_enabled_requested.connect(self._on_toggle_enabled)

    # ------------------------------------------------------------------
    # Private — handlers
    # ------------------------------------------------------------------

    def _on_add_requested(self) -> None:
        """Open Add Game dialog and call service on confirmation."""
        dialog = AddGameDialog(parent=self._view)
        if dialog.exec() != AddGameDialog.DialogCode.Accepted:
            return

        request = AddGameRequest(
            name=dialog.get_name(),
            executable_path=dialog.get_executable_path(),
        )
        result = self._service.add_game(request)

        if result.success:
            self.load_games()
            self._view.show_info("Game Added", result.message)
        else:
            self._view.show_error("Add Game Failed", result.message)

    def _on_scan_requested(self) -> None:
        """Open Scan dialog and import selected games."""
        logger.debug("Scan requested — orchestrator=%s", self._orchestrator)
        if self._orchestrator is None:
            self._view.show_error(
                "Scan Unavailable",
                "Game discovery service is not configured.",
            )
            return

        try:
            logger.debug("Creating DiscoveryDialog...")
            dialog = DiscoveryDialog(
                parent=self._view,
                orchestrator=self._orchestrator,
            )
            logger.debug("DiscoveryDialog created, calling exec()...")
            accepted = dialog.exec() == DiscoveryDialog.DialogCode.Accepted
            logger.debug("DiscoveryDialog exec() returned: accepted=%s", accepted)
            if not accepted:
                return
        except Exception as exc:
            logger.exception("DiscoveryDialog failed: %s", exc)
            self._view.show_error(
                "Scan Failed",
                f"An error occurred while scanning for games:\n\n{exc}",
            )
            return

        try:
            candidates = dialog.get_selected_candidates()
            logger.debug("Candidates selected: %d", len(candidates))
            if not candidates:
                return

            result = self._service.import_discovered_games(candidates)
            logger.debug("Import result: success=%s, message=%s", result.success, result.message)
            self.load_games()

            if result.success:
                self._view.show_info("Scan Complete", result.message)
            else:
                self._view.show_info("Scan Complete", result.message)
        except Exception as exc:
            logger.exception("Import failed: %s", exc)
            self._view.show_error(
                "Import Failed",
                f"An error occurred while importing games:\n\n{exc}",
            )

    def _on_edit_requested(self, game: Game) -> None:
        """Open Edit Game dialog pre-populated with existing data."""
        dialog = AddGameDialog(parent=self._view, game=game)
        if dialog.exec() != AddGameDialog.DialogCode.Accepted:
            return

        assert game.id is not None
        request = EditGameRequest(
            game_id=game.id,
            name=dialog.get_name(),
            executable_path=dialog.get_executable_path(),
        )
        result = self._service.edit_game(request)

        if result.success:
            self.load_games()
            self._view.show_info("Game Updated", result.message)
        else:
            self._view.show_error("Edit Game Failed", result.message)

    def _on_delete_requested(self, game: Game) -> None:
        """Ask for confirmation then delete the game."""
        reply = QMessageBox.question(
            self._view,
            "Confirm Delete",
            f'Are you sure you want to delete "{game.name}"?\n\n'
            "This will remove the game from tracking. "
            "Existing session history will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        assert game.id is not None
        result = self._service.delete_game(game.id)

        if result.success:
            self.load_games()
        else:
            self._view.show_error("Delete Game Failed", result.message)

    def _on_toggle_enabled(self, game: Game) -> None:
        """Toggle the tracking enabled state for a game."""
        assert game.id is not None
        new_state = not game.is_enabled
        result = self._service.set_enabled(game.id, new_state)

        if result.success:
            self.load_games()
        else:
            self._view.show_error("Update Failed", result.message)