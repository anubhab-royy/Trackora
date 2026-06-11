"""Tests for BugReport model."""

import pytest
from models.support.bug_report import BugReport


class TestBugReport:
    def test_default_severity_is_medium(self):
        report = BugReport(
            title="Test bug",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        assert report.severity == "medium"

    def test_valid_severities_accepted(self):
        for s in ("low", "medium", "high", "critical"):
            report = BugReport(
                title="Test",
                description="desc",
                steps_to_reproduce="steps",
                expected_behavior="expected",
                actual_behavior="actual",
                severity=s,
            )
            assert report.severity == s

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError):
            BugReport(
                title="Test",
                description="desc",
                steps_to_reproduce="steps",
                expected_behavior="expected",
                actual_behavior="actual",
                severity="urgent",
            )

    def test_id_defaults_to_none(self):
        report = BugReport(
            title="Test",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        assert report.id is None

    def test_created_at_is_set(self):
        report = BugReport(
            title="Test",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        assert report.created_at is not None

    def test_repr_contains_title(self):
        report = BugReport(
            title="Crash on startup",
            description="desc",
            steps_to_reproduce="steps",
            expected_behavior="expected",
            actual_behavior="actual",
        )
        assert "Crash on startup" in repr(report)
