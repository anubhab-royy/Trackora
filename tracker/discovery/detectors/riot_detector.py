"""Riot Games client detector.

Reads RiotClientInstalls.json to find installed Riot games.
Handles both old format (dict values with rc_install_path / rc_display_name)
and new format (string values where keys are install paths).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)

# Known Riot game display names — used as fallback when config does not
# provide rc_display_name.  The dynamic path is the source of truth.
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

        for game_key, info in associated.items():
            if isinstance(info, dict):
                candidate = self._candidate_from_dict(game_key, info)
            elif isinstance(info, str):
                candidate = self._candidate_from_string(game_key, info)
            else:
                continue

            if candidate is not None:
                candidates.append(candidate)

        logger.info("Riot detection complete: %d game(s) found", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Private — format-specific parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _candidate_from_dict(game_id: str, info: dict) -> CandidateGame | None:
        """Build a candidate from dict-format associated_client entry."""
        install_path = info.get("rc_install_path", "")
        if not install_path:
            return None

        name = (
            info.get("rc_display_name", "")
            or _RIOT_GAME_NAMES.get(game_id, "")
            or game_id.replace("rc_live_", "").replace("_", " ").title()
        )
        exe_path = RiotDetector._resolve_executable(install_path, game_id)
        return CandidateGame(
            name=name,
            executable_path=exe_path,
            platform="riot",
            platform_id=game_id,
        )

    @staticmethod
    def _candidate_from_string(install_path: str, _exe_hint: str) -> CandidateGame | None:
        """Build a candidate from string-format associated_client entry.

        In this format the key IS the install path and the value is a
        RiotClientServices.exe path (used only as a hint).
        """
        if not install_path:
            return None

        name = RiotDetector._game_name_from_path(install_path)
        game_id = f"riot_{name.lower().replace(' ', '_')}"
        exe_path = RiotDetector._resolve_executable(install_path, "VALORANT.exe")
        if not exe_path and _exe_hint:
            hint_path = Path(_exe_hint)
            if hint_path.is_file():
                exe_path = str(hint_path)

        return CandidateGame(
            name=name,
            executable_path=exe_path,
            platform="riot",
            platform_id=game_id,
        )

    # ------------------------------------------------------------------
    # Private — path discovery / resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _find_config_path() -> Path | None:
        """Locate RiotClientInstalls.json.

        Checks %PROGRAMDATA% (primary for modern installations) first,
        then falls back to %LOCALAPPDATA%.
        """
        if os.name != "nt":
            candidate = Path.home() / ".local" / "share" / "Riot Games" / "RiotClientInstalls.json"
            return candidate if candidate.is_file() else None

        program_data = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData"))
        candidate = program_data / "Riot Games" / "RiotClientInstalls.json"
        if candidate.is_file():
            return candidate

        local_app_data = Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"))
        candidate = local_app_data / "Riot Games" / "RiotClientInstalls.json"
        return candidate if candidate.is_file() else None

    @staticmethod
    def _resolve_executable(install_path: str, game_id_or_exe: str) -> str:
        """Resolve the game executable from install path."""
        base = Path(install_path)
        if not base.is_dir():
            return install_path

        exe_name = _KNOWN_EXECUTABLES.get(game_id_or_exe, game_id_or_exe)
        exe = base / exe_name
        if exe.is_file():
            return str(exe)

        for pattern in ("*.exe", "*.app"):
            matches = list(base.glob(pattern))
            if matches:
                return str(matches[0])

        return install_path

    @staticmethod
    def _game_name_from_path(install_path: str) -> str:
        """Derive a human-friendly game name from the install path."""
        path = Path(install_path)
        name = path.name
        if name.lower() in ("live", "game", "bin", "gameclient"):
            name = path.parent.name
        return name.replace("_", " ").replace("-", " ").title()
