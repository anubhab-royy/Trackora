"""
DiscoveryDialog — Phase 9
Modal dialog for scanning and importing discovered games.

Stages:
  1. Scanning — shows "Scanning for games..." with per-platform progress
  2. Results — table of discovered candidates with checkboxes
  3. Confirm — "Import Selected" action

No business logic. No direct DB access. Receives DiscoveryOrchestrator.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tracker.discovery.models import CandidateGame
from tracker.discovery.orchestrator import DiscoveryOrchestrator

logger = logging.getLogger(__name__)


class DiscoveryDialog(QDialog):
    """
    Modal dialog that shows discovered game candidates for user selection.

    Usage:
        dialog = DiscoveryDialog(parent, orchestrator)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.get_selected_candidates()
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        orchestrator: Optional[DiscoveryOrchestrator] = None,
        folder_paths: Optional[list[str]] = None,
    ) -> None:
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._folder_paths = folder_paths or []
        self._candidates: list[CandidateGame] = []
        self._checkboxes: list[QCheckBox] = []

        self._setup_ui()
        self._heading.setText("Scanning for games...")
        self._status_label.setText("Initialising detectors...")
        QTimer.singleShot(0, self._run_scan)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selected_candidates(self) -> list[CandidateGame]:
        """Return the subset of candidates the user checked."""
        return [
            c for i, c in enumerate(self._candidates)
            if i < len(self._checkboxes) and self._checkboxes[i].isChecked()
        ]

    # ------------------------------------------------------------------
    # Private — UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("Scan For Games")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Heading
        self._heading = QLabel("Scanning for games...")
        self._heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self._heading)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888888;")
        layout.addWidget(self._status_label)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["", "Game Name", "Platform", "Executable Path"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # Select All checkbox
        self._select_all = QCheckBox("Select All")
        self._select_all.setChecked(True)
        self._select_all.toggled.connect(self._on_select_all_toggled)
        layout.addWidget(self._select_all)

        # Button box
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Import Selected")
        self._ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    # ------------------------------------------------------------------
    # Private — scanning
    # ------------------------------------------------------------------

    def _run_scan(self) -> None:
        """Run the discovery scan and populate results."""
        logger.debug("_run_scan started — orchestrator=%s", self._orchestrator)
        if self._orchestrator is None:
            self._heading.setText("Scanner not available")
            self._status_label.setText("Discovery service is not configured.")
            self._ok_button.setEnabled(False)
            self._cancel_button.setEnabled(True)
            return

        self._heading.setText("Scanning for games...")
        self._status_label.setText("Checking launchers...")
        self._table.setRowCount(0)

        try:
            logger.debug("Calling scan_all(folder_paths=%s)...", self._folder_paths)
            result = self._orchestrator.scan_all(
                self._folder_paths,
                progress_callback=lambda msg: self._status_label.setText(msg),
            )
            logger.debug(
                "scan_all returned %d candidates, %d error(s), %dms",
                len(result.candidates),
                len(result.errors),
                result.duration_ms,
            )
        except Exception as exc:
            logger.exception("scan_all failed: %s", exc)
            self._heading.setText("Scan failed")
            self._status_label.setText(f"Error: {exc}")
            self._ok_button.setEnabled(False)
            self._cancel_button.setEnabled(True)
            return

        self._candidates = result.candidates

        errors = result.errors
        if errors:
            for err in errors:
                logger.warning("Scan warning: %s", err)

        if not self._candidates:
            msg = "No un-tracked games were found on your system."
            if errors:
                msg += f" ({len(errors)} detector(s) reported errors)"
            self._heading.setText("No new games found")
            self._status_label.setText(msg)
            self._ok_button.setEnabled(False)
            self._cancel_button.setEnabled(True)
            return

        self._heading.setText(
            f"{len(self._candidates)} game(s) found"
        )
        status = "Select the games you want to import and click 'Import Selected'."
        if errors:
            status += f" ({len(errors)} warning(s))"
        self._status_label.setText(status)

        self._populate_table()

    def _populate_table(self) -> None:
        """Fill the table with candidate games."""
        logger.debug("_populate_table: %d candidates", len(self._candidates))
        self._table.setRowCount(len(self._candidates))
        self._checkboxes = []

        for i, candidate in enumerate(self._candidates):
            try:
                # Checkbox
                checkbox = QCheckBox()
                checkbox.setChecked(True)
                self._checkboxes.append(checkbox)

                checkbox_widget = QWidget()
                cb_layout = QVBoxLayout(checkbox_widget)
                cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cb_layout.setContentsMargins(0, 0, 0, 0)
                cb_layout.addWidget(checkbox)
                self._table.setCellWidget(i, 0, checkbox_widget)

                # Game name
                self._table.setItem(i, 1, QTableWidgetItem(candidate.name))

                # Platform
                platform_display = candidate.platform.capitalize()
                self._table.setItem(i, 2, QTableWidgetItem(platform_display))

                # Executable path
                self._table.setItem(i, 3, QTableWidgetItem(candidate.executable_path))
            except Exception as exc:
                logger.exception("Error populating row %d: %s", i, exc)

    # ------------------------------------------------------------------
    # Private — slots
    # ------------------------------------------------------------------

    def _on_select_all_toggled(self, checked: bool) -> None:
        """Toggle all checkboxes."""
        for cb in self._checkboxes:
            cb.setChecked(checked)
