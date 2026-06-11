"""
SupportCenterController.

Bridges the SupportService (business layer) and the SupportCenterWidget (view).
Contains zero SQL. Contains zero PyQt6 widgets beyond QMessageBox/QFileDialog.
Handles navigation between support pages and read-only data loading.
"""

from __future__ import annotations

import logging

from services.support.support_service import SupportService
from ui.support_center.support_center_widget import SupportCenterWidget

logger = logging.getLogger(__name__)


class SupportCenterController:
    """
    Controller for the Support Center screen.

    Args:
        view:            SupportCenterWidget instance.
        support_service: SupportService instance.
    """

    def __init__(
        self,
        view: SupportCenterWidget,
        support_service: SupportService,
    ) -> None:
        self._view = view
        self._service = support_service
        self._connect_signals()
        self._load_upcoming_updates()
        logger.info("SupportCenterController initialised.")

    def _connect_signals(self) -> None:
        self._view.navigation_requested.connect(self._on_page_changed)

    def _on_page_changed(self, page_key: str) -> None:
        logger.debug("Support page changed: %s", page_key)
        if page_key == "upcoming_updates":
            self._load_upcoming_updates()

    def _load_upcoming_updates(self) -> None:
        try:
            updates = self._service.get_upcoming_updates()
            self._view.set_upcoming_updates(updates)
        except Exception as exc:
            logger.error("Failed to load upcoming updates: %s", exc)

    def navigate_to(self, page: str) -> None:
        """Programmatically navigate to a support page.

        Args:
            page: One of 'report_bug', 'suggest_feature', 'feedback',
                  'upcoming_updates'.
        """
        self._view.navigate_to(page)
