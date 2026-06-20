"""Tests for EpicDetector."""

from __future__ import annotations

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

        (manifest_dir / "LauncherInstalled.dat").write_text(
            f'{{"InstallationList": [{{"AppName": "Fortnite", "DisplayName": "Fortnite", "InstallLocation": "{install_loc}"}}]}}'
        )

        with patch.object(EpicDetector, "_find_manifest_dir", return_value=str(manifest_dir)):
            detector = EpicDetector()
            results = detector.detect()

        assert len(results) == 1
        assert results[0].executable_path == str(exe)
