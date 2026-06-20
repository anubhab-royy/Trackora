"""Ubisoft Connect detector.

Reads Ubisoft Connect configuration files to find installed games.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)


class UbisoftDetector(GameDetector):
    """Detect games installed via Ubisoft Connect."""

    @property
    def platform(self) -> str:
        return "ubisoft"

    def detect(self) -> list[CandidateGame]:
        config_dir = self._find_config_dir()
        if config_dir is None:
            logger.info("Ubisoft Connect not found — skipping Ubisoft detection")
            return []

        candidates: list[CandidateGame] = []

        # Scan for game entries in config directory
        for entry in config_dir.iterdir():
            if not entry.is_dir():
                continue
            # Each game subdirectory may contain install info
            game_id = entry.name
            game_name = self._read_game_name(entry)
            if not game_name:
                continue

            exe_path = self._resolve_executable(entry)
            candidates.append(
                CandidateGame(
                    name=game_name,
                    executable_path=exe_path,
                    platform="ubisoft",
                    platform_id=game_id,
                )
            )

        logger.info(
            "Ubisoft detection complete: %d game(s) found", len(candidates)
        )
        return candidates

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _find_config_dir() -> Path | None:
        """Locate Ubisoft Connect config directory."""
        if os.name == "nt":
            base = Path(
                os.environ.get(
                    "LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"
                )
            )
        else:
            base = Path.home() / ".local" / "share"

        # Check both Uplay and Ubisoft Connect paths
        for name in ("Ubisoft Game Launcher", "Ubisoft Connect"):
            candidate = base / name / "games"
            if candidate.is_dir():
                return candidate
        return None

    @staticmethod
    def _read_game_name(game_dir: Path) -> str:
        """Read game name from directory or metadata file."""
        # Use the directory name as a fallback
        name = game_dir.name
        # Try to read a more descriptive name from common metadata files
        info_file = game_dir / "info.txt"
        if info_file.is_file():
            try:
                content = info_file.read_text("utf-8").strip()
                if content:
                    return content
            except OSError:
                pass
        return name.replace("_", " ").replace("-", " ").title()

    @staticmethod
    def _resolve_executable(game_dir: Path) -> str:
        """Resolve executable from game directory."""
        for pattern in ("*.exe", "*.app"):
            matches = list(game_dir.glob(pattern))
            if matches:
                return str(matches[0])
        return str(game_dir)
