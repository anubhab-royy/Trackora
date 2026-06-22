"""Tests for discovery models and GameDetector ABC."""

from __future__ import annotations

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame, DiscoveryResult


class TestCandidateGame:
    """CandidateGame dataclass tests."""

    def test_stores_all_fields(self):
        game = CandidateGame(
            name="Test Game",
            executable_path="/path/to/game.exe",
            platform="steam",
            platform_id="730",
        )
        assert game.name == "Test Game"
        assert game.executable_path == "/path/to/game.exe"
        assert game.platform == "steam"
        assert game.platform_id == "730"
        assert game.process_name == "game.exe"
        assert game.icon_path == ""

    def test_is_frozen(self):
        game = CandidateGame(
            name="G", executable_path="/g.exe", platform="epic", platform_id="x"
        )
        try:
            game.name = "New"
            assert False, "Should have raised AttributeError"
        except AttributeError:
            pass

    def test_auto_derives_process_name(self):
        game = CandidateGame(
            name="G",
            executable_path=r"C:\Games\MyGame\game.exe",
            platform="steam",
            platform_id="123",
        )
        assert game.process_name == "game.exe"

    def test_uses_provided_process_name(self):
        game = CandidateGame(
            name="G",
            executable_path=r"C:\Games\g.exe",
            platform="generic",
            platform_id="hash",
            process_name="custom.exe",
        )
        assert game.process_name == "custom.exe"

    def test_empty_executable_path_process_name(self):
        game = CandidateGame(
            name="G",
            executable_path="",
            platform="generic",
            platform_id="x",
        )
        assert game.process_name == ""


class TestDiscoveryResult:
    """DiscoveryResult dataclass tests."""

    def test_aggregates_candidates_and_errors(self):
        candidates = [
            CandidateGame(name="A", executable_path="/a.exe", platform="s", platform_id="1"),
            CandidateGame(name="B", executable_path="/b.exe", platform="s", platform_id="2"),
        ]
        errors = ["Steam not found"]
        result = DiscoveryResult(candidates=candidates, errors=errors, duration_ms=42)
        assert result.candidates == candidates
        assert result.errors == errors
        assert result.duration_ms == 42

    def test_empty_result(self):
        result = DiscoveryResult(candidates=[], errors=[], duration_ms=0)
        assert result.candidates == []
        assert result.errors == []


class TestGameDetectorABC:
    """GameDetector abstract base class tests."""

    def test_cannot_instantiate(self):
        try:
            GameDetector()  # type: ignore[abstract]
            assert False, "Should have raised TypeError"
        except TypeError:
            pass

    def test_subclass_must_implement_abstract_methods(self):
        class Incomplete(GameDetector):
            pass

        try:
            Incomplete()  # type: ignore[abstract]
            assert False, "Should have raised TypeError"
        except TypeError:
            pass

    def test_concrete_subclass_works(self):
        class Concrete(GameDetector):
            @property
            def platform(self) -> str:
                return "test"

            def detect(self) -> list:
                return []

        instance = Concrete()
        assert instance.platform == "test"
        assert instance.detect() == []
