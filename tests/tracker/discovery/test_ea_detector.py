"""Tests for EADetector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tracker.discovery.detectors.ea_detector import EADetector


class TestEADetector:
    """EADetector tests."""

    def _create_install_record(self, directory: Path, title_id: str, display_name: str, install_path: str) -> Path:
        """Create an EA install record JSON file."""
        record = {
            "titleId": title_id,
            "displayName": display_name,
            "installPath": install_path,
        }
        record_path = directory / f"{title_id}.json"
        record_path.write_text(json.dumps(record))
        return record_path

    def test_detect_games_from_files(self, tmp_path: Path) -> None:
        """Parse EA install records and return candidates."""
        records_dir = tmp_path / "EA" / "install-record"
        records_dir.mkdir(parents=True)

        bf_dir = tmp_path / "BF2042"
        bf_dir.mkdir()
        (bf_dir / "BF2042.exe").write_text("fake")

        sw_dir = tmp_path / "SWJS"
        sw_dir.mkdir()
        (sw_dir / "SWJS.exe").write_text("fake")

        self._create_install_record(records_dir, "bf2042", "Battlefield 2042", str(bf_dir))
        self._create_install_record(records_dir, "swjs", "Star Wars Jedi: Survivor", str(sw_dir))

        with patch.object(EADetector, "_find_install_records_dir", return_value=records_dir):
            detector = EADetector()
            results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        assert "Battlefield 2042" in names
        assert "Star Wars Jedi: Survivor" in names
        for r in results:
            assert r.platform == "ea"

    def test_not_installed(self) -> None:
        """Return empty list when EA App absent."""
        with patch.object(EADetector, "_find_install_records_dir", return_value=None):
            detector = EADetector()
            results = detector.detect()
        assert results == []

    def test_empty_records_dir(self, tmp_path: Path) -> None:
        """Return empty list when records directory is empty."""
        records_dir = tmp_path / "empty"
        records_dir.mkdir()

        with patch.object(EADetector, "_find_install_records_dir", return_value=records_dir):
            detector = EADetector()
            results = detector.detect()
        assert results == []

    def test_detect_from_registry_fallback(self, tmp_path: Path) -> None:
        """Fall back to registry detection when no install records."""
        records_dir = tmp_path / "empty"
        records_dir.mkdir()

        mock_key = MagicMock()
        mock_game_key = MagicMock()
        mock_game_key.name = "Battlefield 2042"

        def enum_key_side_effect(key, index):
            names = ["Battlefield 2042", "The Sims 4"]
            if index >= len(names):
                raise OSError
            return names[index]

        def query_value_side_effect(key, value_name):
            paths = {
                "Battlefield 2042": str(tmp_path / "BF2042"),
                "The Sims 4": str(tmp_path / "Sims4"),
            }
            return (paths[key.name], 1)

        with patch.object(EADetector, "_find_install_records_dir", return_value=records_dir):
            with patch("tracker.discovery.detectors.ea_detector.winreg") as mock_winreg:
                mock_winreg.HKEY_LOCAL_MACHINE = "HKLM"
                mock_winreg.OpenKey = MagicMock(return_value=mock_key)
                mock_winreg.EnumKey = MagicMock(side_effect=enum_key_side_effect)

                mock_winreg.OpenKey.side_effect = lambda parent, name: (
                    setattr(mock_game_key, "name", name) or mock_game_key
                )

                mock_winreg.QueryValueEx = MagicMock(side_effect=query_value_side_effect)
                mock_winreg.CloseKey = MagicMock()

                detector = EADetector()
                results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        assert "Battlefield 2042" in names
        assert "The Sims 4" in names
        for r in results:
            assert r.platform == "ea"
