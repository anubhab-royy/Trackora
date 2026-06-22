"""EA App detector.

Reads EA App install records and/or registry to find installed games.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]


class EADetector(GameDetector):
    """Detect games installed via the EA App."""

    @property
    def platform(self) -> str:
        return "ea"

    def detect(self) -> list[CandidateGame]:
        candidates = self._detect_from_files()

        if not candidates:
            candidates = self._detect_from_registry()

        logger.info("EA detection complete: %d game(s) found", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Private — file-based detection (install-record/*.json)
    # ------------------------------------------------------------------

    def _detect_from_files(self) -> list[CandidateGame]:
        """Detect games from install-record JSON files."""
        install_records_dir = self._find_install_records_dir()
        if install_records_dir is None:
            logger.info("EA App not found — skipping EA file detection")
            return []

        if not install_records_dir.is_dir():
            logger.warning("EA install records dir not found at %s", install_records_dir)
            return []

        candidates: list[CandidateGame] = []

        for record_file in install_records_dir.glob("*.json"):
            try:
                data = json.loads(record_file.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.exception("Failed to parse EA install record %s", record_file)
                continue

            display_name = data.get("displayName", "")
            install_path = data.get("installPath", "")
            title_id = data.get("titleId", record_file.stem)

            if not display_name:
                continue

            exe_path = self._resolve_executable(install_path)
            candidates.append(
                CandidateGame(
                    name=display_name,
                    executable_path=exe_path,
                    platform="ea",
                    platform_id=title_id,
                )
            )

        return candidates

    def _detect_from_registry(self) -> list[CandidateGame]:
        """Detect EA games from registry as a fallback."""
        if winreg is None:
            return []

        candidates: list[CandidateGame] = []
        seen_paths: set[str] = set()

        for root_key in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EA Games"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EA Games"),
        ):
            try:
                key_handle = winreg.OpenKey(root_key[0], root_key[1])
            except OSError:
                continue

            i = 0
            while True:
                try:
                    game_key_name = winreg.EnumKey(key_handle, i)
                    i += 1
                except OSError:
                    break

                try:
                    game_key = winreg.OpenKey(key_handle, game_key_name)
                except OSError:
                    continue

                try:
                    install_dir, _ = winreg.QueryValueEx(game_key, "Install Dir")
                except OSError:
                    winreg.CloseKey(game_key)
                    continue

                winreg.CloseKey(game_key)

                if not install_dir or install_dir in seen_paths:
                    continue
                seen_paths.add(install_dir)

                exe_path = self._resolve_executable(install_dir)
                candidates.append(
                    CandidateGame(
                        name=game_key_name,
                        executable_path=exe_path,
                        platform="ea",
                        platform_id="",
                    )
                )

            winreg.CloseKey(key_handle)

        return candidates

    # ------------------------------------------------------------------
    # Private — path discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _find_install_records_dir() -> Path | None:
        """Locate EA App install records directory."""
        if os.name == "nt":
            base = Path(
                os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local")
            )
        else:
            base = Path.home() / ".local" / "share"

        candidate = base / "Electronic Arts" / "EA Desktop" / "install-record"
        return candidate if candidate.is_dir() else None

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
