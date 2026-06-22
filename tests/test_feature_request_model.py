"""Tests for FeatureRequest model."""

import pytest
from models.support.feature_request import FeatureRequest


class TestFeatureRequest:
    def test_default_priority_is_medium(self):
        req = FeatureRequest(
            title="Test feature",
            description="desc",
            use_case="use case",
        )
        assert req.priority == "medium"

    def test_valid_priorities_accepted(self):
        for p in ("low", "medium", "high"):
            req = FeatureRequest(
                title="Test",
                description="desc",
                use_case="use case",
                priority=p,
            )
            assert req.priority == p

    def test_invalid_priority_raises(self):
        with pytest.raises(ValueError):
            FeatureRequest(
                title="Test",
                description="desc",
                use_case="use case",
                priority="critical",
            )

    def test_id_defaults_to_none(self):
        req = FeatureRequest(
            title="Test",
            description="desc",
            use_case="use case",
        )
        assert req.id is None

    def test_created_at_is_set(self):
        req = FeatureRequest(
            title="Test",
            description="desc",
            use_case="use case",
        )
        assert req.created_at is not None

    def test_repr_contains_title(self):
        req = FeatureRequest(
            title="Dark mode toggle",
            description="desc",
            use_case="use case",
        )
        assert "Dark mode toggle" in repr(req)
