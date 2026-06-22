"""Tests for BattleNetDetector."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from tracker.discovery.detectors.battlenet_detector import (
    BattleNetDetector,
    _parse_protobuf_db,
    _parse_sqlite_db,
)


class TestBattleNetDetector:
    """BattleNetDetector tests."""

    def _create_sqlite_db(self, path: Path, products: list[dict]) -> None:
        """Create a sample SQLite product.db for testing."""
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

    def _create_protobuf_db(self, path: Path, games: list[dict]) -> None:
        """Create a mock protobuf product.db with readable strings."""
        data = bytearray()
        for game in games:
            uid = game.get("uid", "")
            name = game.get("name", "")
            install_path = game.get("install_path", "")
            for field_num, val in [(1, uid), (4, name), (3, install_path)]:
                if val:
                    tag = (field_num << 3) | 2
                    encoded = val.encode("utf-8")
                    length = len(encoded)
                    data.append(tag)
                    while length > 0x7F:
                        data.append((length & 0x7F) | 0x80)
                        length >>= 7
                    data.append(length & 0x7F)
                    data.extend(encoded)
        path.write_bytes(bytes(data))

    def test_sqlite_detect_games(self, tmp_path: Path) -> None:
        """Query SQLite product.db and return candidates."""
        db_path = tmp_path / "product.db"
        self._create_sqlite_db(db_path, [
            {"uid": "s2", "product_code": "s2", "install_path": str(tmp_path / "StarCraft II"), "name": "StarCraft II"},
            {"uid": "pro", "product_code": "pro", "install_path": str(tmp_path / "Overwatch"), "name": "Overwatch"},
        ])

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

    def test_protobuf_detect_games(self, tmp_path: Path) -> None:
        """Parse protobuf product.db and return candidates."""
        db_path = tmp_path / "product.db"
        games = [
            {"uid": "pro", "name": "Overwatch", "install_path": str(tmp_path / "Overwatch")},
            {"uid": "wow", "name": "World of Warcraft", "install_path": str(tmp_path / "World of Warcraft")},
        ]
        self._create_protobuf_db(db_path, games)

        (tmp_path / "Overwatch").mkdir(exist_ok=True)
        (tmp_path / "World of Warcraft").mkdir(exist_ok=True)

        with patch.object(BattleNetDetector, "_find_db_path", return_value=db_path):
            detector = BattleNetDetector()
            results = detector.detect()

        assert len(results) == 2
        names = {r.name for r in results}
        assert "Overwatch" in names
        assert "World of Warcraft" in names
        for r in results:
            assert r.platform == "battlenet"

    def test_parse_protobuf_db_extraction(self, tmp_path: Path) -> None:
        """_parse_protobuf_db extracts game entries from protobuf file."""
        db_path = tmp_path / "product.db"
        games = [
            {"uid": "pro", "name": "Overwatch", "install_path": str(tmp_path / "Overwatch")},
        ]
        self._create_protobuf_db(db_path, games)
        (tmp_path / "Overwatch").mkdir(exist_ok=True)

        entries = _parse_protobuf_db(db_path)
        assert len(entries) > 0
        assert any(e["uid"] == "pro" for e in entries)
