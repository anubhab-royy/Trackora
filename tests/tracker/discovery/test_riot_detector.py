"""Tests for RiotDetector."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from tracker.discovery.detectors.riot_detector import RiotDetector


FIXTURES = Path(__file__).parent / "fixtures"


class TestRiotDetector:
    """RiotDetector tests."""

    def test_detect_games_dict_format(self, tmp_path: Path) -> None:
        """Parse RiotClientInstalls.json with dict values (legacy format)."""
        base = tmp_path / "Riot Games"
        base.mkdir()
        (base / "RiotClientInstalls.json").write_bytes(
            (FIXTURES / "riot_installs.json").read_bytes()
        )

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

    def test_detect_games_string_format(self, tmp_path: Path) -> None:
        """Parse RiotClientInstalls.json with string values (modern format).

        In this format keys are install paths and values are Riot Client
        executable paths.
        """
        val_dir = tmp_path / "Riot Games" / "VALORANT" / "live"
        val_dir.mkdir(parents=True)
        (val_dir / "VALORANT.exe").write_text("fake")

        config = {
            "associated_client": {
                str(val_dir): str(tmp_path / "Riot Games" / "Riot Client" / "RiotClientServices.exe"),
            }
        }
        config_path = tmp_path / "RiotClientInstalls.json"
        config_path.write_text(json.dumps(config))

        with patch.object(RiotDetector, "_find_config_path", return_value=config_path):
            detector = RiotDetector()
            results = detector.detect()

        assert len(results) == 1
        assert "Valorant" in results[0].name
        assert results[0].platform == "riot"
        assert results[0].platform_id.startswith("riot_")

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

    def test_find_config_programdata(self, tmp_path: Path) -> None:
        """_find_config_path checks ProgramData first."""
        cfg = tmp_path / "ProgramData" / "Riot Games" / "RiotClientInstalls.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("{}")

        with patch("tracker.discovery.detectors.riot_detector.os.name", "nt"):
            with patch.dict(os.environ, {"PROGRAMDATA": str(tmp_path / "ProgramData")}, clear=True):
                result = RiotDetector._find_config_path()

        assert result == cfg

    def test_find_config_localappdata_fallback(self, tmp_path: Path) -> None:
        """_find_config_path falls back to LocalAppData."""
        cfg = tmp_path / "LocalAppData" / "Riot Games" / "RiotClientInstalls.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("{}")

        with patch("tracker.discovery.detectors.riot_detector.os.name", "nt"):
            with patch.dict(os.environ, {
                "PROGRAMDATA": str(tmp_path / "ProgramData"),
                "LOCALAPPDATA": str(tmp_path / "LocalAppData"),
            }, clear=True):
                result = RiotDetector._find_config_path()

        assert result == cfg

    def test_game_name_from_path(self) -> None:
        """_game_name_from_path derives name from directory name."""
        assert RiotDetector._game_name_from_path("C:\\Riot Games\\VALORANT\\live") == "Valorant"
        assert RiotDetector._game_name_from_path("C:\\Riot Games\\League of Legends") == "League Of Legends"
