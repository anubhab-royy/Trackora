"""
UpdateDialog — Phase 10

Modal dialog showing update check results:
- Update available: release notes, Download / Ignore / Remind Later buttons
- Up to date: informational message and Close button
- Error: error message and Close button
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from services.update_center_service import UpdateCheckResult

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    """
    Modal dialog for displaying update check results.

    Args:
        result: The UpdateCheckResult to display.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        result: UpdateCheckResult,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self.ignored_version: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setMinimumSize(500, 400)
        self.resize(550, 450)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        if self._result.update_available and self._result.release:
            self._build_update_available(layout)
        elif self._result.error:
            self._build_error(layout)
        else:
            self._build_up_to_date(layout)

    def _build_update_available(self, layout: QVBoxLayout) -> None:
        release = self._result.release
        assert release is not None

        self.setWindowTitle("Update Available")

        title = QLabel(f"Trackora {release.version} is available!")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        notes = QTextBrowser()
        notes.setMarkdown(release.body)
        notes.setOpenExternalLinks(True)
        notes.setMinimumHeight(200)
        layout.addWidget(notes, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        download_btn = QPushButton("Download")
        download_btn.setObjectName("DownloadButton")
        download_btn.clicked.connect(self._on_download)
        btn_layout.addWidget(download_btn)

        ignore_btn = QPushButton("Ignore This Version")
        ignore_btn.setObjectName("IgnoreButton")
        ignore_btn.clicked.connect(self._on_ignore)
        btn_layout.addWidget(ignore_btn)

        remind_btn = QPushButton("Remind Later")
        remind_btn.setObjectName("RemindButton")
        remind_btn.clicked.connect(self._on_remind_later)
        btn_layout.addWidget(remind_btn)

        layout.addLayout(btn_layout)

    def _build_up_to_date(self, layout: QVBoxLayout) -> None:
        self.setWindowTitle("Up to Date")

        msg = QLabel(
            f"Trackora {self._result.current_version} is the latest version."
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _build_error(self, layout: QVBoxLayout) -> None:
        self.setWindowTitle("Update Check Failed")

        msg = QLabel("Could not check for updates. Please try again later.")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        detail = QLabel(self._result.error or "")
        detail.setWordWrap(True)
        detail.setObjectName("ErrorDetail")
        layout.addWidget(detail)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_download(self) -> None:
        if self._result.release:
            url = self._result.release.download_url or self._result.release.html_url
            QDesktopServices.openUrl(QUrl(url))
        self.accept()

    def _on_ignore(self) -> None:
        if self._result.release:
            self.ignored_version = self._result.release.version
        self.accept()

    def _on_remind_later(self) -> None:
        self.ignored_version = None
        self.accept()
