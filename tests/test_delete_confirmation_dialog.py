"""
Tests for DeleteConfirmationDialog — Phase 14
Uses pytest-qt / QApplication fixture for GUI testing.
"""

from __future__ import annotations

import sys
import pytest

# Guard: skip entire module if PyQt6 is not installed or display unavailable.
pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog

from ui.dialogs.delete_confirmation_dialog import DeleteConfirmationDialog


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class TestDeleteConfirmationDialog:

    def test_dialog_shows_game_name(self, qapp) -> None:
        """Verifies that the dialog displays the correct game name in the heading."""
        dialog = DeleteConfirmationDialog("Cyberpunk 2077")
        assert dialog is not None

        # Check title/heading contains the name
        heading = dialog.findChild(object, "DialogTitle")
        assert heading is not None
        assert 'Cyberpunk 2077' in heading.text()

    def test_dialog_displays_warning_and_summary_text(self, qapp) -> None:
        """Verifies warning text and removed resources list are present in the dialog."""
        dialog = DeleteConfirmationDialog("Cyberpunk 2077")

        # Find all QLabel child widgets
        labels = dialog.findChildren(object)
        text_content = [label.text() for label in labels if hasattr(label, "text")]

        # Verify warning text
        assert any("cannot be undone" in text for text in text_content)

        # Verify list of items removed is summarized
        assert any("Game entry" in text for text in text_content)
        assert any("Session history" in text for text in text_content)
        assert any("Statistics and analytics" in text for text in text_content)
        assert any("Local Trackora data" in text for text in text_content)

    def test_cancel_button_triggers_rejection(self, qapp) -> None:
        """Verifies that clicking the Cancel button rejects the dialog."""
        dialog = DeleteConfirmationDialog("Cyberpunk 2077")
        dialog.cancel_btn.click()
        assert dialog.result() == QDialog.DialogCode.Rejected

    def test_delete_button_triggers_acceptance(self, qapp) -> None:
        """Verifies that clicking the Delete Game button accepts the dialog."""
        dialog = DeleteConfirmationDialog("Cyberpunk 2077")
        dialog.delete_btn.click()
        assert dialog.result() == QDialog.DialogCode.Accepted

    def test_default_focus_and_tab_navigation(self, qapp) -> None:
        """Verifies that the Cancel button has default focus/is default, preventing accidental enter-key trigger."""
        dialog = DeleteConfirmationDialog("Cyberpunk 2077")
        dialog.show()

        # Cancel should be default
        assert dialog.cancel_btn.isDefault() is True
        assert dialog.delete_btn.isDefault() is False

        # Cancel should have focus initially (or be the designated focus widget)
        assert dialog.focusWidget() == dialog.cancel_btn

        dialog.close()

    def test_escape_cancels_dialog(self, qapp) -> None:
        """Verifies that pressing the Escape key cancels/rejects the dialog."""
        dialog = DeleteConfirmationDialog("Cyberpunk 2077")
        dialog.show()

        # Simulate Escape key press event
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier
        )
        dialog.keyPressEvent(event)

        assert dialog.result() == QDialog.DialogCode.Rejected
        dialog.close()
