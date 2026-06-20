"""Tests for RiotDetector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tracker.discovery.detectors.riot_detector import RiotDetector


FIXTURES = Path(__file__).parent / "fixtures"


class TestRiotDetector:
    """RiotDetector tests."""

    def test_detect_games(self, tmp_path: Path) -> None:
        """Parse RiotClientInstalls.json and return candidates."""
        base = tmp_path / "Riot Games"
        base.mkdir()
        (base / "RiotClientInstalls.json").write_bytes(
            (FIXTURES / "riot_installs.json").read_bytes()
        )

        # Create install dirs with executables
        lol_dir = tmp_path / "Riot Games" / "League of Legends"
        lol_dir.mkdir(parents=True)
        (lol_dir / "LeagueClient.exe").write_text("fake")

        val_dir = tmp_path / "Riot Games" / "VALORANT"
        val_dir.mkdir(parents=True)
        (val_dir / "VALORANT.exe").write_text("fake")

        with patch.object(RiotDetector, "_find_config_path", return_value=base / "RiotClientInstalls.json"):
            detector = RiotDetector()
            results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        assert "League of Legends" in names
        assert "VALORANT" in names
        for r in results:
            assert r.platform == "riot"

    def test_file_missing(self) -> None:
        """Return empty list when config file is absent."""
        detector = RiotDetector()
        with patch.object(RiotDetector, "_find_config_path", return_value=None):
            results = detector.detect()
        assert results == []

    def test_empty_config(self, tmp_path: Path) -> None:
        """Return empty list when config has no associated_client."""
        config = tmp_path / "RiotClientInstalls.json"
        config.write_text("{}")

        with patch.object(RiotDetector, "_find_config_path", return_value=config):
            detector = RiotDetector()
            results = detector.detect()
        assert results == []
