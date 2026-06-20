"""Battle.net detector.

Reads Battle.net product.db (SQLite) to find installed games.

Note: The product.db schema varies between Battle.net versions.
We query the `products` table which holds installed game records.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)


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

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT uid, product_code, install_path, name FROM products"
            )
            rows = cursor.fetchall()
            conn.close()
        except sqlite3.Error:
            logger.exception("Failed to query Battle.net product DB")
            return []

        candidates: list[CandidateGame] = []
        for row in rows:
            uid = row["uid"] or row["product_code"] or ""
            name = row["name"] or ""
            install_path = row["install_path"] or ""

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
