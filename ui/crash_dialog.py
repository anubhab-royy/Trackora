"""
CrashDialog — user-facing notification after an unexpected shutdown.

Presents three options:
  - Send Report    (submit via AbstractReportService backend)
  - Review Report  (show the JSON content in a text view)
  - Dismiss        (delete the crash report file)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.crash.diagnostic_service import CrashReport, DiagnosticService
from services.support.support_service import SupportService

logger = logging.getLogger(__name__)


class CrashDialog(QDialog):
    """Modal dialog shown on crash detection.

    Signals are not used; the caller checks the result code
    (QDialog.Accepted / Rejected) and inspects action_taken.
    """

    ACTION_SEND = "send"
    ACTION_REVIEW = "review"
    ACTION_DISMISS = "dismiss"

    def __init__(
        self,
        report: CrashReport,
        report_path: Path,
        support_service: SupportService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._report = report
        self._report_path = report_path
        self._support_service = support_service
        self._issue_url: str | None = None
        self._action_taken: str | None = None

        self.setWindowTitle("Trackora — Unexpected Shutdown")
        self.setMinimumSize(520, 320)
        self.setModal(True)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def action_taken(self) -> str | None:
        return self._action_taken

    @property
    def issue_url(self) -> str | None:
        return self._issue_url

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel(
            "<b>Unexpected shutdown detected.</b><br><br>"
            "Trackora did not exit cleanly last time. "
            "A diagnostic report has been saved locally."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Summary
        summary = QLabel(
            f"App version: {self._report.app_version}<br>"
            f"OS: {self._report.os_platform} &mdash; {self._report.os_version}<br>"
            f"Time: {self._report.timestamp}<br>"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # Buttons
        btn_layout = QHBoxLayout()

        send_btn = QPushButton("&Send Report")
        send_btn.clicked.connect(self._on_send)
        btn_layout.addWidget(send_btn)

        review_btn = QPushButton("&Review Report")
        review_btn.clicked.connect(self._on_review)
        btn_layout.addWidget(review_btn)

        dismiss_btn = QPushButton("&Dismiss")
        dismiss_btn.clicked.connect(self._on_dismiss)
        btn_layout.addWidget(dismiss_btn)

        layout.addLayout(btn_layout)

        # Status area
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._status_label)

        self._review_area = QPlainTextEdit()
        self._review_area.setReadOnly(True)
        self._review_area.setVisible(False)
        layout.addWidget(self._review_area, stretch=1)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        if self._support_service is None:
            self._status_label.setText(
                "Unable to submit report right now. "
                "Use Review Report to view the details manually."
            )
            return

        self._set_buttons_enabled(False)
        self._status_label.setText("Submitting crash report...")

        try:
            result = self._support_service.submit_crash_report(self._report)
            if result.github_success:
                self._issue_url = result.github_url
                self._action_taken = self.ACTION_SEND
                self._status_label.setText(
                    f"Crash report submitted: "
                    f'<a href="{result.github_url}">{result.github_url}</a>'
                )
                self._delete_report_file()
            elif result.queued:
                self._status_label.setText(
                    "Report saved locally and will be sent automatically."
                )
            else:
                self._status_label.setText(
                    f"Failed to submit: {result.github_error}"
                )
        except Exception as exc:
            logger.exception("Crash report submission error")
            self._status_label.setText(f"Submission error: {exc}")
        finally:
            self._set_buttons_enabled(True)

    def _on_review(self) -> None:
        self._action_taken = self.ACTION_REVIEW
        data = DiagnosticService.serialize(self._report)
        text = json.dumps(data, indent=2, default=str)
        self._review_area.setPlainText(text)
        self._review_area.setVisible(True)
        self._status_label.setText("Reviewing crash report (read-only).")

    def _on_dismiss(self) -> None:
        self._action_taken = self.ACTION_DISMISS
        self._delete_report_file()
        self.accept()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _delete_report_file(self) -> None:
        try:
            if self._report_path.is_file():
                self._report_path.unlink()
                logger.info("Crash report deleted: %s", self._report_path)
        except OSError as exc:
            logger.warning("Cannot delete crash report: %s", exc)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn in self.findChildren(QPushButton):
            btn.setEnabled(enabled)
