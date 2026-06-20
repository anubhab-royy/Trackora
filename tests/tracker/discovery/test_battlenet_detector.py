"""Tests for BattleNetDetector."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from tracker.discovery.detectors.battlenet_detector import BattleNetDetector
from tracker.discovery.models import CandidateGame


class TestBattleNetDetector:
    """BattleNetDetector tests."""

    def _create_product_db(self, path: Path, products: list[dict]) -> None:
        """Create a sample Battle.net product.db for testing."""
        conn = sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE products (uid TEXT, product_code TEXT, install_path TEXT, name TEXT)"
        )
        for p in products:
            conn.execute(
                "INSERT INTO products (uid, product_code, install_path, name) VALUES (?, ?, ?, ?)",
                (p.get("uid", ""), p.get("product_code", ""), p.get("install_path", ""), p.get("name", "")),
            )
        conn.commit()
        conn.close()

    def test_detect_games(self, tmp_path: Path) -> None:
        """Query product.db and return candidates."""
        db_path = tmp_path / "product.db"
        self._create_product_db(db_path, [
            {"uid": "s2", "product_code": "s2", "install_path": str(tmp_path / "StarCraft II"), "name": "StarCraft II"},
            {"uid": "pro", "product_code": "pro", "install_path": str(tmp_path / "Overwatch"), "name": "Overwatch"},
        ])

        # Create install dirs
        (tmp_path / "StarCraft II").mkdir(exist_ok=True)
        (tmp_path / "Overwatch").mkdir(exist_ok=True)

        with patch.object(BattleNetDetector, "_find_db_path", return_value=db_path):
            detector = BattleNetDetector()
            results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        assert "StarCraft II" in names
        assert "Overwatch" in names
        for r in results:
            assert r.platform == "battlenet"

    def test_db_not_found(self) -> None:
        """Return empty list when DB is absent."""
        with patch.object(BattleNetDetector, "_find_db_path", return_value=None):
            detector = BattleNetDetector()
            results = detector.detect()
        assert results == []

    def test_corrupt_db(self, tmp_path: Path) -> None:
        """Return empty list when DB is corrupt."""
        db_path = tmp_path / "product.db"
        db_path.write_text("not a database")

        with patch.object(BattleNetDetector, "_find_db_path", return_value=db_path):
            detector = BattleNetDetector()
            results = detector.detect()
        assert results == []
