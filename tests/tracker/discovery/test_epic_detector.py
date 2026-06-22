"""Tests for EpicDetector."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from tracker.discovery.detectors.epic_detector import EpicDetector


FIXTURES = Path(__file__).parent / "fixtures"


class TestEpicDetector:
    """EpicDetector tests."""

    def test_detect_games_from_manifest(self, tmp_path: Path) -> None:
        """Parse LauncherInstalled.dat and return candidates."""
        manifest_dir = tmp_path / "Epic" / "UnrealEngineLauncher"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "LauncherInstalled.dat").write_bytes(
            (FIXTURES / "epic_launcher_installed.dat").read_bytes()
        )

        with patch.object(EpicDetector, "_find_manifest_dir", return_value=str(manifest_dir)):
            detector = EpicDetector()
            results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        ids = {r.platform_id for r in results}
        assert "Fortnite" in names
        assert "Rocket League" in names
        assert "Fortnite" in ids
        assert "Jerry" in ids
        for r in results:
            assert r.platform == "epic"

    def test_file_missing(self) -> None:
        """Return empty list when manifest file is absent."""
        with patch.object(EpicDetector, "_find_manifest_dir", return_value="/nonexistent"):
            detector = EpicDetector()
            results = detector.detect()
        assert results == []

    def test_empty_install_list(self, tmp_path: Path) -> None:
        """Return empty list when InstallationList is empty."""
        manifest_dir = tmp_path / "Epic" / "UEL"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "LauncherInstalled.dat").write_text(
            '{"InstallationList": []}'
        )

        with patch.object(EpicDetector, "_find_manifest_dir", return_value=str(manifest_dir)):
            detector = EpicDetector()
            results = detector.detect()
        assert results == []

    def test_malformed_json(self, tmp_path: Path) -> None:
        """Return empty list when manifest is invalid JSON."""
        manifest_dir = tmp_path / "Epic" / "UEL"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "LauncherInstalled.dat").write_text("not json")

        with patch.object(EpicDetector, "_find_manifest_dir", return_value=str(manifest_dir)):
            detector = EpicDetector()
            results = detector.detect()
        assert results == []

    def test_resolves_executable_path(self, tmp_path: Path) -> None:
        """Resolve executable from InstallLocation."""
        manifest_dir = tmp_path / "Epic" / "UEL"
        manifest_dir.mkdir(parents=True)

        install_loc = tmp_path / "Epic Games" / "Fortnite"
        install_loc.mkdir(parents=True)
        exe = install_loc / "FortniteClient-Win64-Shipping.exe"
        exe.write_text("fake")

        import json
        manifest_data = {
            "InstallationList": [
                {
                    "AppName": "Fortnite",
                    "DisplayName": "Fortnite",
                    "InstallLocation": str(install_loc),
                }
            ]
        }
        (manifest_dir / "LauncherInstalled.dat").write_text(json.dumps(manifest_data))

        with patch.object(EpicDetector, "_find_manifest_dir", return_value=str(manifest_dir)):
            detector = EpicDetector()
            results = detector.detect()

        assert len(results) == 1
        assert results[0].executable_path == str(exe)

    def test_find_manifest_dir_unreal(self, tmp_path: Path) -> None:
        """_find_manifest_dir returns UnrealEngineLauncher when LauncherInstalled.dat exists there."""
        # Create temp layout: only UnrealEngineLauncher has the manifest file
        unreal_dir = tmp_path / "ProgramData" / "Epic" / "UnrealEngineLauncher"
        unreal_dir.mkdir(parents=True)
        (unreal_dir / "LauncherInstalled.dat").write_text("{}")
        # Modern dir exists but has no manifest
        modern_dir = tmp_path / "ProgramData" / "Epic" / "EpicGamesLauncher" / "Data"
        modern_dir.mkdir(parents=True)

        with patch("tracker.discovery.detectors.epic_detector.os.name", "nt"):
            with patch.dict(os.environ, {"PROGRAMDATA": str(tmp_path / "ProgramData")}, clear=True):
                result = EpicDetector._find_manifest_dir()
        assert result is not None
        assert "UnrealEngineLauncher" in result

    def test_find_manifest_dir_epic_games(self, tmp_path: Path) -> None:
        """_find_manifest_dir finds EpicGamesLauncher/Data when LauncherInstalled.dat exists there."""
        # Only the modern EpicGamesLauncher path has the manifest
        modern_dir = tmp_path / "ProgramData" / "Epic" / "EpicGamesLauncher" / "Data"
        modern_dir.mkdir(parents=True)
        (modern_dir / "LauncherInstalled.dat").write_text("{}")
        # Legacy dir also exists but no manifest
        legacy_dir = tmp_path / "ProgramData" / "Epic" / "UnrealEngineLauncher"
        legacy_dir.mkdir(parents=True)

        with patch("tracker.discovery.detectors.epic_detector.os.name", "nt"):
            with patch.dict(os.environ, {"PROGRAMDATA": str(tmp_path / "ProgramData")}, clear=True):
                result = EpicDetector._find_manifest_dir()
        assert result is not None
        assert "EpicGamesLauncher" in result

    def test_detect_with_epic_games_launcher(self, tmp_path: Path) -> None:
        """Detect games using the modern EpicGamesLauncher path."""
        manifest_dir = tmp_path / "Epic" / "EpicGamesLauncher" / "Data"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "LauncherInstalled.dat").write_text(
            '{"InstallationList": [{"AppName": "TestApp", "DisplayName": "Test Game", "InstallLocation": ""}]}'
        )

        with patch.object(EpicDetector, "_find_manifest_dir", return_value=str(manifest_dir)):
            detector = EpicDetector()
            results = detector.detect()

        assert len(results) == 1
        assert results[0].name == "Test Game"
        assert results[0].platform_id == "TestApp"
