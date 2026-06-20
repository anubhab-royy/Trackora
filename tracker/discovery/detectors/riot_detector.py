"""Riot Games client detector.

Reads RiotClientInstalls.json to find installed Riot games.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)

_RIOT_GAME_NAMES: dict[str, str] = {
    "rc_live_league_of_legends": "League of Legends",
    "rc_live_valorant": "VALORANT",
    "rc_live_teamfight_tactics": "Teamfight Tactics",
    "rc_live_legends_of_runeterra": "Legends of Runeterra",
    "rc_live_wild_rift": "Wild Rift",
}

_KNOWN_EXECUTABLES: dict[str, str] = {
    "rc_live_league_of_legends": "LeagueClient.exe",
    "rc_live_valorant": "VALORANT.exe",
    "rc_live_teamfight_tactics": "TFT.exe",
    "rc_live_legends_of_runeterra": "LoR.exe",
}


class RiotDetector(GameDetector):
    """Detect games installed via the Riot client."""

    @property
    def platform(self) -> str:
        return "riot"

    def detect(self) -> list[CandidateGame]:
        config_path = self._find_config_path()
        if config_path is None:
            logger.info("Riot client not found — skipping Riot detection")
            return []

        if not config_path.is_file():
            logger.warning("Riot config not found at %s", config_path)
            return []

        try:
            data = json.loads(config_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to parse Riot config")
            return []

        associated = data.get("associated_client", {})
        candidates: list[CandidateGame] = []

        for game_id, info in associated.items():
            install_path = info.get("rc_install_path", "")
            if not install_path:
                continue

            name = _RIOT_GAME_NAMES.get(game_id, game_id)
            exe_path = self._resolve_executable(install_path, game_id)
            candidates.append(
                CandidateGame(
                    name=name,
                    executable_path=exe_path,
                    platform="riot",
                    platform_id=game_id,
                )
            )

        logger.info("Riot detection complete: %d game(s) found", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _find_config_path() -> Path | None:
        """Locate RiotClientInstalls.json."""
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"))
        else:
            base = Path.home() / ".local" / "share"
        candidate = base / "Riot Games" / "RiotClientInstalls.json"
        return candidate if candidate.is_file() else None

    @staticmethod
    def _resolve_executable(install_path: str, game_id: str) -> str:
        """Resolve the game executable from install path."""
        base = Path(install_path)
        if not base.is_dir():
            return install_path

        # Check known executables
        exe_name = _KNOWN_EXECUTABLES.get(game_id)
        if exe_name:
            exe = base / exe_name
            if exe.is_file():
                return str(exe)

        for pattern in ("*.exe", "*.app"):
            matches = list(base.glob(pattern))
            if matches:
                return str(matches[0])

        return install_path
