"""
SupportCenterWidget.

Main view for the Support Center.
Displays four sub-views switched by top navigation buttons:
  - Report Bug
  - Suggest Feature
  - General Feedback
  - Upcoming Updates
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.update_announcements_service import AnnouncementsResult

logger = logging.getLogger(__name__)

_PAGES = ["report_bug", "suggest_feature", "feedback", "upcoming_updates"]
_PAGE_LABELS = {
    "report_bug": "Report Bug",
    "suggest_feature": "Suggest Feature",
    "feedback": "General Feedback",
    "upcoming_updates": "Upcoming Updates",
}


class SupportCenterWidget(QWidget):
    """Support Center main widget with internal page navigation."""

    navigation_requested = pyqtSignal(str)
    submit_requested = pyqtSignal(str)
    refresh_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._updates_container: QVBoxLayout | None = None
        self._submit_buttons: dict[str, QPushButton] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_upcoming_updates(self, updates: list[object]) -> None:
        """Populate the Upcoming Updates page with update items.

        Args:
            updates: List of objects with .title, .description, .version, .is_published.
                     Usually extracted from AnnouncementsResult.features.
        """
        if self._updates_container is None:
            return
        self._clear_layout(self._updates_container)
        if not updates:
            label = QLabel("No upcoming updates planned.")
            label.setObjectName("EmptyStateLabel")
            self._updates_container.addWidget(label)
            return
        for item in updates:
            card = QFrame()
            card.setObjectName("StatCard")
            card.setFixedHeight(100)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)

            title = QLabel(item.title)
            title.setStyleSheet("font-size: 15px; font-weight: 700;")
            card_layout.addWidget(title)

            desc = QLabel(item.description)
            desc.setStyleSheet("font-size: 12px; color: #a6adc8;")
            desc.setWordWrap(True)
            card_layout.addWidget(desc)

            version_label = QLabel(f"v{item.version}")
            version_label.setStyleSheet("font-size: 11px; color: #6c7086;")
            card_layout.addWidget(version_label)

            self._updates_container.addWidget(card)

    def set_announcements(self, announcements: AnnouncementsResult) -> None:
        """Populate the Upcoming Updates page with version info + features.

        Shows the current version, upcoming version, and a card for each
        announced feature.
        """
        if self._updates_container is None:
            return
        self._clear_layout(self._updates_container)

        # Version info
        version_info = QLabel(
            f"<b>Current version:</b> {announcements.current_version} &mdash; "
            f"<b>Upcoming version:</b> {announcements.upcoming_version}"
        )
        version_info.setWordWrap(True)
        version_info.setStyleSheet("font-size: 13px; color: #a6adc8; "
                                   "padding: 0 0 8px 0;")
        self._updates_container.addWidget(version_info)

        source_label = QLabel(f"Source: {announcements.source}")
        source_label.setStyleSheet("font-size: 11px; color: #6c7086; "
                                   "padding: 0 0 4px 0;")
        self._updates_container.addWidget(source_label)

        # Features
        features = announcements.features
        if not features:
            empty = QLabel("No upcoming features announced.")
            empty.setObjectName("EmptyStateLabel")
            self._updates_container.addWidget(empty)
            return

        for item in features:
            card = QFrame()
            card.setObjectName("StatCard")
            card.setFixedHeight(100)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)

            title = QLabel(item.title)
            title.setStyleSheet("font-size: 15px; font-weight: 700;")
            card_layout.addWidget(title)

            desc = QLabel(item.description)
            desc.setStyleSheet("font-size: 12px; color: #a6adc8;")
            desc.setWordWrap(True)
            card_layout.addWidget(desc)

            version_label = QLabel(f"v{item.version}")
            version_label.setStyleSheet("font-size: 11px; color: #6c7086;")
            card_layout.addWidget(version_label)

            self._updates_container.addWidget(card)

    def set_refresh_enabled(self, enabled: bool) -> None:
        """Enable or disable the refresh button."""
        if hasattr(self, "_refresh_btn") and self._refresh_btn is not None:
            self._refresh_btn.setEnabled(enabled)

    def navigate_to(self, page_key: str) -> None:
        """Programmatically navigate to a support page."""
        self._on_nav_clicked(page_key)

    def set_submitting(self, page_key: str, submitting: bool) -> None:
        """Enable or disable the submit button and show a loading state."""
        btn = self._submit_buttons.get(page_key)
        if btn is not None:
            btn.setEnabled(not submitting)
            btn.setText("Submitting..." if submitting else "Submit")

    def set_submit_result(
        self, page_key: str, success: bool, message: str
    ) -> None:
        """Show submission result on the given page."""
        label = self._status_labels.get(page_key)
        if label is None:
            return
        color = "#a6e3a1" if success else "#f38ba8"
        label.setStyleSheet(
            f"font-size: 12px; color: {color}; padding: 4px 0;"
        )
        label.setText(message)

    def clear_submit_result(self, page_key: str) -> None:
        """Clear the submission status message."""
        label = self._status_labels.get(page_key)
        if label is not None:
            label.setText("")

    def get_bug_form_data(self) -> dict:
        return {
            "title": self._bug_title.text().strip(),
            "description": self._bug_description.toPlainText().strip(),
            "steps": self._bug_steps.toPlainText().strip(),
            "expected": self._bug_expected.text().strip(),
            "actual": self._bug_actual.text().strip(),
            "severity": self._bug_severity.currentText(),
        }

    def get_feature_form_data(self) -> dict:
        return {
            "title": self._feature_title.text().strip(),
            "description": self._feature_description.toPlainText().strip(),
            "use_case": self._feature_use_case.toPlainText().strip(),
            "priority": self._feature_priority.currentText(),
        }

    def get_feedback_form_data(self) -> dict:
        return {
            "subject": self._feedback_subject.text().strip(),
            "message": self._feedback_message.toPlainText().strip(),
            "category": self._feedback_category.currentText(),
            "contact_ok": self._feedback_contact.isChecked(),
        }

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("SupportCenterWidget")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(20)

        heading = QLabel("Support Center")
        heading.setObjectName("PageTitle")
        layout.addWidget(heading)

        layout.addWidget(self._build_nav_bar())
        layout.addWidget(self._build_page_stack())
        layout.addStretch()

    def _build_nav_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("SupportNavBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(8)

        for page_key in _PAGES:
            label = _PAGE_LABELS[page_key]
            btn = QPushButton(label)
            btn.setObjectName("SecondaryButton")
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=page_key: self._on_nav_clicked(k))
            bar_layout.addWidget(btn)
            self._nav_buttons[page_key] = btn

        bar_layout.addStretch()
        return bar

    def _build_page_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.setObjectName("SupportPages")

        self._stack.addWidget(self._build_report_bug_page())
        self._stack.addWidget(self._build_suggest_feature_page())
        self._stack.addWidget(self._build_feedback_page())
        self._stack.addWidget(self._build_upcoming_updates_page())

        return self._stack

    def _build_report_bug_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        form_intro = QLabel(
            "Use this form to report a bug. "
            "Please provide as much detail as possible."
        )
        form_intro.setWordWrap(True)
        form_intro.setStyleSheet("font-size: 13px; color: #6c7086;")
        layout.addWidget(form_intro)

        layout.addWidget(self._make_field_label("Title"))
        self._bug_title = QLineEdit()
        self._bug_title.setPlaceholderText("Brief summary of the bug")
        layout.addWidget(self._bug_title)

        layout.addWidget(self._make_field_label("Description"))
        self._bug_description = QPlainTextEdit()
        self._bug_description.setPlaceholderText("Detailed description of the issue")
        self._bug_description.setFixedHeight(80)
        layout.addWidget(self._bug_description)

        layout.addWidget(self._make_field_label("Steps to Reproduce"))
        self._bug_steps = QPlainTextEdit()
        self._bug_steps.setPlaceholderText("1.\n2.\n3.")
        self._bug_steps.setFixedHeight(80)
        layout.addWidget(self._bug_steps)

        layout.addWidget(self._make_field_label("Expected Behavior"))
        self._bug_expected = QLineEdit()
        self._bug_expected.setPlaceholderText("What should happen")
        layout.addWidget(self._bug_expected)

        layout.addWidget(self._make_field_label("Actual Behavior"))
        self._bug_actual = QLineEdit()
        self._bug_actual.setPlaceholderText("What actually happens")
        layout.addWidget(self._bug_actual)

        layout.addWidget(self._make_field_label("Severity"))
        self._bug_severity = QComboBox()
        self._bug_severity.addItems(["low", "medium", "high", "critical"])
        layout.addWidget(self._bug_severity)

        layout.addWidget(self._build_submit_section("report_bug"))
        return page

    def _build_suggest_feature_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        form_intro = QLabel(
            "Suggest a new feature or improvement for Trackora."
        )
        form_intro.setWordWrap(True)
        form_intro.setStyleSheet("font-size: 13px; color: #6c7086;")
        layout.addWidget(form_intro)

        layout.addWidget(self._make_field_label("Title"))
        self._feature_title = QLineEdit()
        self._feature_title.setPlaceholderText("Feature name")
        layout.addWidget(self._feature_title)

        layout.addWidget(self._make_field_label("Description"))
        self._feature_description = QPlainTextEdit()
        self._feature_description.setPlaceholderText(
            "Detailed description of the feature"
        )
        self._feature_description.setFixedHeight(100)
        layout.addWidget(self._feature_description)

        layout.addWidget(self._make_field_label("Use Case"))
        self._feature_use_case = QPlainTextEdit()
        self._feature_use_case.setPlaceholderText(
            "How would this feature be used?"
        )
        self._feature_use_case.setFixedHeight(80)
        layout.addWidget(self._feature_use_case)

        layout.addWidget(self._make_field_label("Priority"))
        self._feature_priority = QComboBox()
        self._feature_priority.addItems(["low", "medium", "high"])
        layout.addWidget(self._feature_priority)

        layout.addWidget(self._build_submit_section("suggest_feature"))
        return page

    def _build_feedback_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        form_intro = QLabel(
            "Share your thoughts about Trackora \u2014 praise, complaints, "
            "or general suggestions."
        )
        form_intro.setWordWrap(True)
        form_intro.setStyleSheet("font-size: 13px; color: #6c7086;")
        layout.addWidget(form_intro)

        layout.addWidget(self._make_field_label("Subject"))
        self._feedback_subject = QLineEdit()
        self._feedback_subject.setPlaceholderText("Subject of your feedback")
        layout.addWidget(self._feedback_subject)

        layout.addWidget(self._make_field_label("Message"))
        self._feedback_message = QPlainTextEdit()
        self._feedback_message.setPlaceholderText("Write your feedback here")
        self._feedback_message.setFixedHeight(120)
        layout.addWidget(self._feedback_message)

        layout.addWidget(self._make_field_label("Category"))
        self._feedback_category = QComboBox()
        self._feedback_category.addItems(["general", "praise", "complaint"])
        layout.addWidget(self._feedback_category)

        self._feedback_contact = QCheckBox(
            "I am willing to be contacted about my feedback"
        )
        layout.addWidget(self._feedback_contact)

        layout.addWidget(self._build_submit_section("feedback"))
        return page

    def _build_upcoming_updates_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        intro = QLabel("See what\u2019s coming next in Trackora.")
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 13px; color: #6c7086;")
        layout.addWidget(intro)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("SecondaryButton")
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.setMaximumWidth(120)
        self._refresh_btn.clicked.connect(self._on_refresh)
        layout.addWidget(self._refresh_btn)

        self._updates_container = QVBoxLayout()
        self._updates_container.setSpacing(10)
        layout.addLayout(self._updates_container)

        loading = QLabel("Loading upcoming updates...")
        loading.setObjectName("EmptyStateLabel")
        self._updates_container.addWidget(loading)

        layout.addStretch()
        return page

    def _on_refresh(self) -> None:
        self.refresh_requested.emit()

    def _build_submit_section(self, page_key: str) -> QWidget:
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 8, 0, 0)
        section_layout.setSpacing(4)

        self._status_labels[page_key] = QLabel("")
        section_layout.addWidget(self._status_labels[page_key])

        btn = QPushButton("Submit")
        btn.setFixedHeight(36)
        btn.setMaximumWidth(160)
        btn.clicked.connect(lambda: self.submit_requested.emit(page_key))
        section_layout.addWidget(btn)
        self._submit_buttons[page_key] = btn

        return section

    # ------------------------------------------------------------------
    # Internal Slots
    # ------------------------------------------------------------------

    def _on_nav_clicked(self, page_key: str) -> None:
        try:
            idx = _PAGES.index(page_key)
            self._stack.setCurrentIndex(idx)
            self._update_nav_style(page_key)
            self.navigation_requested.emit(page_key)
        except ValueError:
            logger.warning("Unknown support page: %s", page_key)

    def _update_nav_style(self, active_key: str) -> None:
        for key, btn in self._nav_buttons.items():
            if key == active_key:
                btn.setObjectName("")
                btn.setStyleSheet("")
            else:
                btn.setObjectName("SecondaryButton")
                btn.setStyleSheet("")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_field_label(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("SectionLabel")
        return label

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
