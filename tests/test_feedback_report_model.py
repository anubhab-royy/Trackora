"""Tests for FeedbackReport model."""

import pytest
from models.support.feedback_report import FeedbackReport


class TestFeedbackReport:
    def test_default_category_is_general(self):
        fb = FeedbackReport(subject="Test", message="msg")
        assert fb.category == "general"

    def test_valid_categories_accepted(self):
        for c in ("general", "praise", "complaint"):
            fb = FeedbackReport(subject="Test", message="msg", category=c)
            assert fb.category == c

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError):
            FeedbackReport(subject="Test", message="msg", category="spam")

    def test_contact_ok_defaults_false(self):
        fb = FeedbackReport(subject="Test", message="msg")
        assert fb.contact_ok is False

    def test_id_defaults_to_none(self):
        fb = FeedbackReport(subject="Test", message="msg")
        assert fb.id is None

    def test_created_at_is_set(self):
        fb = FeedbackReport(subject="Test", message="msg")
        assert fb.created_at is not None

    def test_repr_contains_subject(self):
        fb = FeedbackReport(
            subject="Great app!", message="I love Trackora"
        )
        assert "Great app!" in repr(fb)
