"""Tests for UbisoftDetector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tracker.discovery.detectors.ubisoft_detector import UbisoftDetector


class TestUbisoftDetector:
    """UbisoftDetector tests."""

    def test_detect_games_from_dirs(self, tmp_path: Path) -> None:
        """Detect games from game subdirectories."""
        games_dir = tmp_path / "Ubisoft" / "games"
        games_dir.mkdir(parents=True)

        # Create game dirs
        ac_dir = games_dir / "Assassins Creed Valhalla"
        ac_dir.mkdir()
        (ac_dir / "ACValhalla.exe").write_text("fake")

        fc_dir = games_dir / "Far Cry 6"
        fc_dir.mkdir()
        (fc_dir / "FarCry6.exe").write_text("fake")

        with patch.object(UbisoftDetector, "_find_config_dir", return_value=games_dir):
            detector = UbisoftDetector()
            results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        assert "Assassins Creed Valhalla" in names
        assert "Far Cry 6" in names
        for r in results:
            assert r.platform == "ubisoft"

    def test_config_not_found(self) -> None:
        """Return empty list when config directory absent."""
        with patch.object(UbisoftDetector, "_find_config_dir", return_value=None):
            detector = UbisoftDetector()
            results = detector.detect()
        assert results == []

    def test_empty_games_dir(self, tmp_path: Path) -> None:
        """Return empty list when games directory is empty."""
        games_dir = tmp_path / "empty_games"
        games_dir.mkdir()

        with patch.object(UbisoftDetector, "_find_config_dir", return_value=games_dir):
            detector = UbisoftDetector()
            results = detector.detect()
        assert results == []
