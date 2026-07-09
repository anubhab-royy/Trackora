"""
HistoryController — Phase 7
Wires HistoryView user actions to SessionHistoryService calls.

Responsibilities:
- Build query from current view filter/sort/page state
- Execute query through the service
- Update the view with results
- Load game list for the filter dropdown
- Provide a refresh method for external use

No SQL. No business logic.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QTimer

from services.session_history_service import (
    SessionHistoryQuery,
    SessionHistoryService,
)
from ui.history.history_view import HistoryView

logger = logging.getLogger(__name__)

_DEBOUNCE_MS: int = 300


class HistoryController:
    """
    Controller for the Session History screen.

    Connects:
        HistoryView signals  →  SessionHistoryService calls  →  HistoryView refresh
    """

    def __init__(
        self,
        view: HistoryView,
        history_service: SessionHistoryService,
    ) -> None:
        self._view = view
        self._service = history_service

        # Debounce timer for search-as-you-type
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._refresh)

        self._connect_signals()
        self._load_games()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Immediately execute a fresh query and update the view."""
        self._do_query()

    # ------------------------------------------------------------------
    # Private — signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._view.query_changed.connect(self._on_query_changed)

    def _on_query_changed(self) -> None:
        """Restart the debounce timer on any filter/sort/page change."""
        self._debounce.start()

    def _load_games(self) -> None:
        """Fetch all games and populate the filter dropdown."""
        games = self._service.get_games()
        self._view.set_games(games)

    # ------------------------------------------------------------------
    # Private — query execution
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Called by the debounce timer — execute the query."""
        self._do_query()

    def _do_query(self) -> None:
        """Build the query from view state and update the view with results."""
        try:
            query = SessionHistoryQuery(
                search_text=self._view.get_search_text(),
                game_id=self._view.get_game_id(),
                date_from=self._view.get_date_from(),
                date_to=self._view.get_date_to(),
                sort_by=self._view.get_sort_by(),
                sort_order=self._view.get_sort_order(),
                page=self._view.get_current_page(),
                page_size=50,
            )

            result = self._service.query(query)
            self._view.set_sessions(result)

        except Exception as exc:
            logger.error("History query failed: %s", exc)
