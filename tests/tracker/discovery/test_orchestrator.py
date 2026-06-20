"""Tests for DiscoveryOrchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock

from tracker.discovery.models import CandidateGame
from tracker.discovery.orchestrator import DiscoveryOrchestrator


def _make_candidate(
    name: str = "Game",
    exe: str = "/games/game.exe",
    platform: str = "generic",
    platform_id: str = "id1",
) -> CandidateGame:
    return CandidateGame(
        name=name,
        executable_path=exe,
        platform=platform,
        platform_id=platform_id,
    )


class TestDiscoveryOrchestrator:
    """DiscoveryOrchestrator tests."""

    def test_aggregates_all_detectors(self) -> None:
        """All detectors run and candidates are aggregated."""
        # Use a custom instance that skips real detectors for this test
        orch = DiscoveryOrchestrator()
        # Manually replace detectors with simple ones
        class FakeDetector1:
            platform = "test1"
            def detect(self):
                return [_make_candidate(name="A", exe="/a.exe", platform="test1", platform_id="a")]

        class FakeDetector2:
            platform = "test2"
            def detect(self):
                return [_make_candidate(name="B", exe="/b.exe", platform="test2", platform_id="b")]

        orch._detectors = [FakeDetector1(), FakeDetector2()]  # type: ignore[assignment]
        result = orch.scan_all()
        assert len(result.candidates) == 2

    def test_dedup_by_path(self) -> None:
        """Same executable path from two detectors is deduped."""
        orch = DiscoveryOrchestrator()

        class DetectorA:
            platform = "test_a"
            def detect(self):
                return [_make_candidate(name="A", exe="/same.exe", platform="test_a", platform_id="a")]

        class DetectorB:
            platform = "test_b"
            def detect(self):
                return [_make_candidate(name="B", exe="/same.exe", platform="test_b", platform_id="b")]

        orch._detectors = [DetectorA(), DetectorB()]  # type: ignore[assignment]
        result = orch.scan_all()
        # test_a has priority over test_b (lower number)
        # But since these are not in the priority map, they get default priority 99
        # The result should be DetectorA's entry (first encountered)
        assert len(result.candidates) == 1

    def test_dedup_steam_over_generic(self) -> None:
        """Steam entry kept over generic for same path."""
        orch = DiscoveryOrchestrator()

        class GenericDet:
            platform = "generic"
            def detect(self):
                return [_make_candidate(name="Generic", exe="/g/game.exe", platform="generic", platform_id="g")]

        class SteamDet:
            platform = "steam"
            def detect(self):
                return [_make_candidate(name="CS2", exe="/g/game.exe", platform="steam", platform_id="730")]

        orch._detectors = [GenericDet(), SteamDet()]  # type: ignore[assignment]
        result = orch.scan_all()
        assert len(result.candidates) == 1
        assert result.candidates[0].platform == "steam"

    def test_excludes_existing_games(self) -> None:
        """Games already in DB are excluded from results."""
        exists_by_exe = MagicMock()
        exists_by_exe.side_effect = lambda p: p == "/existing.exe"
        exists_by_pid = MagicMock(return_value=False)

        orch = DiscoveryOrchestrator(
            exists_by_executable_path=exists_by_exe,
            exists_by_platform_id=exists_by_pid,
        )

        class Det:
            platform = "test"
            def detect(self):
                return [
                    _make_candidate(name="Existing", exe="/existing.exe", platform="test", platform_id="e"),
                    _make_candidate(name="New", exe="/new.exe", platform="test", platform_id="n"),
                ]

        orch._detectors = [Det()]  # type: ignore[assignment]
        result = orch.scan_all()
        assert len(result.candidates) == 1
        assert result.candidates[0].name == "New"

    def test_excludes_by_platform_id(self) -> None:
        """Games already tracked by platform_id are excluded."""
        exists_by_pid = MagicMock()
        exists_by_pid.side_effect = lambda p, pid: p == "steam" and pid == "730"

        orch = DiscoveryOrchestrator(
            exists_by_platform_id=exists_by_pid,
        )

        class Det:
            platform = "steam"
            def detect(self):
                return [
                    _make_candidate(name="CS2", exe="/cs2.exe", platform="steam", platform_id="730"),
                    _make_candidate(name="Dota 2", exe="/dota2.exe", platform="steam", platform_id="570"),
                ]

        orch._detectors = [Det()]  # type: ignore[assignment]
        result = orch.scan_all()
        assert len(result.candidates) == 1
        assert result.candidates[0].name == "Dota 2"

    def test_collects_detector_errors(self) -> None:
        """Detector errors are collected without aborting other detectors."""
        orch = DiscoveryOrchestrator()

        class FailingDet:
            platform = "failing"
            def detect(self):
                raise RuntimeError("Something went wrong")

        class GoodDet:
            platform = "good"
            def detect(self):
                return [_make_candidate(name="Good", exe="/good.exe", platform="good", platform_id="g")]

        orch._detectors = [FailingDet(), GoodDet()]  # type: ignore[assignment]
        result = orch.scan_all()
        assert len(result.candidates) == 1
        assert len(result.errors) == 1
        assert "failing" in result.errors[0]

    def test_no_detectors(self) -> None:
        """Empty detector list returns empty result."""
        orch = DiscoveryOrchestrator()
        orch._detectors = []  # type: ignore[assignment]
        result = orch.scan_all()
        assert result.candidates == []
        assert result.errors == []
        assert result.duration_ms >= 0

    def test_duration_ms_recorded(self) -> None:
        """Duration is captured and reported."""
        orch = DiscoveryOrchestrator()
        orch._detectors = []  # type: ignore[assignment]
        result = orch.scan_all()
        assert result.duration_ms >= 0
