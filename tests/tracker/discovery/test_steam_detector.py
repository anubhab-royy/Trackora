"""Tests for SteamDetector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tracker.discovery.detectors.steam_detector import SteamDetector
from tracker.discovery.models import CandidateGame


FIXTURES = Path(__file__).parent / "fixtures"


class TestSteamDetector:
    """SteamDetector tests."""

    def test_detect_cs2_from_manifest(self, tmp_path: Path) -> None:
        """Detect Counter-Strike 2 from appmanifest_730.acf."""
        steam_root = tmp_path / "steam"
        steam_root.mkdir()
        manifest_dir = steam_root / "steamapps"
        manifest_dir.mkdir()

        (manifest_dir / "appmanifest_730.acf").write_bytes(
            (FIXTURES / "steam_appmanifest_730.acf").read_bytes()
        )

        with patch.object(SteamDetector, "_find_steam_root", return_value=str(steam_root)):
            detector = SteamDetector()
            results = detector.detect()

        assert len(results) == 1
        assert results[0].name == "Counter-Strike 2"
        assert results[0].platform == "steam"
        assert results[0].platform_id == "730"

    def test_detect_multiple_games(self, tmp_path: Path) -> None:
        """Detect multiple games from multiple manifests."""
        steam_root = tmp_path / "steam_multi"
        steam_root.mkdir()
        manifest_dir = steam_root / "steamapps"
        manifest_dir.mkdir()

        (manifest_dir / "appmanifest_730.acf").write_bytes(
            (FIXTURES / "steam_appmanifest_730.acf").read_bytes()
        )
        (manifest_dir / "appmanifest_570.acf").write_bytes(
            (FIXTURES / "steam_appmanifest_570.acf").read_bytes()
        )

        with patch.object(SteamDetector, "_find_steam_root", return_value=str(steam_root)):
            detector = SteamDetector()
            results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        assert "Counter-Strike 2" in names
        assert "Dota 2" in names

    def test_steam_not_installed(self) -> None:
        """Return empty list when Steam is not installed."""
        with patch.object(SteamDetector, "_find_steam_root", return_value=None):
            detector = SteamDetector()
            results = detector.detect()
        assert results == []

    def test_empty_library(self, tmp_path: Path) -> None:
        """Return empty list when no manifests exist."""
        steam_root = tmp_path / "steam_empty"
        steam_root.mkdir()
        (steam_root / "steamapps").mkdir()

        with patch.object(SteamDetector, "_find_steam_root", return_value=str(steam_root)):
            detector = SteamDetector()
            results = detector.detect()
        assert results == []

    def test_skips_corrupt_manifest(self, tmp_path: Path) -> None:
        """Skip corrupt manifest but still parse valid ones."""
        steam_root = tmp_path / "steam_partial"
        steam_root.mkdir()
        manifest_dir = steam_root / "steamapps"
        manifest_dir.mkdir()

        (manifest_dir / "appmanifest_730.acf").write_bytes(
            (FIXTURES / "steam_appmanifest_730.acf").read_bytes()
        )
        (manifest_dir / "appmanifest_999.acf").write_text('"AppState"\n{\n"appid" "999"\n')

        with patch.object(SteamDetector, "_find_steam_root", return_value=str(steam_root)):
            detector = SteamDetector()
            results = detector.detect()

        assert len(results) == 1
        assert results[0].platform_id == "730"

    def test_resolves_executable_path(self, tmp_path: Path) -> None:
        """Resolve executable path from install dir."""
        steam_root = tmp_path / "steam_exe"
        steam_root.mkdir()
        manifest_dir = steam_root / "steamapps"
        manifest_dir.mkdir()

        (manifest_dir / "appmanifest_730.acf").write_bytes(
            (FIXTURES / "steam_appmanifest_730.acf").read_bytes()
        )

        # Create a fake install dir with an exe
        install_dir = steam_root / "steamapps" / "common" / "Counter-Strike Global Offensive"
        install_dir.mkdir(parents=True)
        exe_path = install_dir / "cs2.exe"
        exe_path.write_text("fake exe")

        with patch.object(SteamDetector, "_find_steam_root", return_value=str(steam_root)):
            detector = SteamDetector()
            results = detector.detect()

        assert len(results) == 1
        assert results[0].executable_path == str(exe_path)
