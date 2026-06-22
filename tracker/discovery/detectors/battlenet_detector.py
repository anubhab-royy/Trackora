"""Battle.net detector.

Reads Battle.net product.db to find installed games.
Supports both SQLite (legacy) and protobuf (modern) formats.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)

_SQLITE_MAGIC = b"SQLite format 3\0"

_PROTOBUF_FIELD_UID = 1
_PROTOBUF_FIELD_NAME = 4
_PROTOBUF_FIELD_INSTALL_PATH = 3


class BattleNetDetector(GameDetector):
    """Detect games installed via Battle.net."""

    @property
    def platform(self) -> str:
        return "battlenet"

    def detect(self) -> list[CandidateGame]:
        db_path = self._find_db_path()
        if db_path is None:
            logger.info("Battle.net not found — skipping Battle.net detection")
            return []

        if not db_path.is_file():
            logger.warning("Battle.net DB not found at %s", db_path)
            return []

        entries = self._parse_product_db(db_path)
        candidates: list[CandidateGame] = []

        for entry in entries:
            uid = entry.get("uid", "") or entry.get("product_code", "") or ""
            name = entry.get("name", "") or ""
            install_path = entry.get("install_path", "") or ""

            if not name or not uid:
                continue

            exe_path = self._resolve_executable(install_path)
            candidates.append(
                CandidateGame(
                    name=name,
                    executable_path=exe_path,
                    platform="battlenet",
                    platform_id=uid,
                )
            )

        logger.info("Battle.net detection complete: %d game(s) found", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _find_db_path() -> Path | None:
        """Locate Battle.net product.db."""
        if os.name == "nt":
            base = Path(
                os.environ.get("PROGRAMDATA", "C:\\ProgramData")
            )
        else:
            base = Path.home() / ".config"

        candidate = base / "Battle.net" / "Agent" / "product.db"
        return candidate if candidate.is_file() else None

    @staticmethod
    def _parse_product_db(db_path: Path) -> list[dict[str, str]]:
        """Parse product.db, supporting both SQLite and protobuf formats."""
        header = db_path.read_bytes()[:16]

        if header == _SQLITE_MAGIC:
            return _parse_sqlite_db(db_path)

        return _parse_protobuf_db(db_path)

    @staticmethod
    def _resolve_executable(install_path: str) -> str:
        """Resolve executable from install path."""
        base = Path(install_path)
        if not base.is_dir():
            return install_path

        for pattern in ("*.exe", "*.app"):
            matches = list(base.glob(pattern))
            if matches:
                return str(matches[0])

        return install_path


def _parse_sqlite_db(db_path: Path) -> list[dict[str, str]]:
    """Parse product.db as SQLite (legacy format)."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT uid, product_code, install_path, name FROM products"
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "uid": row["uid"] or row["product_code"] or "",
                "name": row["name"] or "",
                "install_path": row["install_path"] or "",
            }
            for row in rows
        ]
    except sqlite3.Error:
        logger.exception("Failed to query Battle.net product DB (SQLite)")
        return []


def _parse_protobuf_db(db_path: Path) -> list[dict[str, str]]:
    """Parse product.db as protobuf binary (modern format).

    Decodes protobuf wire format to extract string fields (uid, name,
    install_path) by known field numbers.
    """
    try:
        raw = db_path.read_bytes()
    except OSError:
        logger.exception("Failed to read Battle.net product DB")
        return []

    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    i = 0
    n = len(raw)

    while i < n:
        tag, i = _read_varint(raw, i)
        if i >= n:
            break

        field_number = tag >> 3
        wire_type = tag & 0x07

        if field_number < 1 or field_number > 20:
            if wire_type == 0:
                _, i = _skip_varint(raw, i)
            elif wire_type == 2:
                length, i = _read_varint(raw, i)
                if length >= 0 and i + length <= n:
                    i += length
            elif wire_type == 5:
                i += 4
            elif wire_type == 1:
                i += 8
            continue

        if wire_type == 2:
            length, i = _read_varint(raw, i)
            if length < 0 or i + length > n:
                break
            value = raw[i:i + length]
            i += length

            s = _try_decode_utf8(value)
            if s is None:
                continue

            if field_number == _PROTOBUF_FIELD_UID:
                # New uid — save previous entry if complete
                if current.get("uid") and current.get("uid") != s:
                    if _is_complete_entry(current):
                        entries.append(current)
                    current = {}
                current["uid"] = s
            elif field_number == _PROTOBUF_FIELD_INSTALL_PATH:
                current["install_path"] = s
            elif field_number == _PROTOBUF_FIELD_NAME:
                current["name"] = s

        elif wire_type == 0:
            _, i = _skip_varint(raw, i)

        elif wire_type == 5:
            i += 4

        elif wire_type == 1:
            i += 8

        else:
            break

    if _is_complete_entry(current):
        entries.append(current)

    return entries


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Read a protobuf varint, returning (value, new_offset)."""
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return value, offset
    return value, offset


def _skip_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Skip past a varint, returning (value, new_offset)."""
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, offset
        shift += 7
    return value, offset


def _try_decode_utf8(data: bytes) -> str | None:
    """Try to decode bytes as UTF-8; return None on failure."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _is_complete_entry(entry: dict[str, str]) -> bool:
    """Check if a protobuf entry has both uid and at least one of name/install_path."""
    has_uid = bool(entry.get("uid"))
    has_info = bool(entry.get("name")) or bool(entry.get("install_path"))
    return has_uid and has_info

