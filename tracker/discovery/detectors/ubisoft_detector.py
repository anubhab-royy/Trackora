"""Ubisoft Connect detector.

Reads Ubisoft Connect configuration files and Windows Registry
to find installed games across all drives.
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
        candidates: list[CandidateGame] = []
        seen_paths: set[str] = set()

        # Method 1: Windows Registry (includes non-C: drives)
        reg_candidates = self._detect_from_registry()
        for c in reg_candidates:
            if c.executable_path and c.executable_path not in seen_paths:
                seen_paths.add(c.executable_path)
                candidates.append(c)

        # Method 2: Local config directory (LOCALAPPDATA) for additional games
        config_candidates = self._detect_from_config_dir()
        for c in config_candidates:
            if c.executable_path and c.executable_path not in seen_paths:
                seen_paths.add(c.executable_path)
                candidates.append(c)

        logger.info(
            "Ubisoft detection complete: %d game(s) found", len(candidates)
        )
        return candidates

    # ------------------------------------------------------------------
    # Registry-based detection (cross-drive)
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_from_registry() -> list[CandidateGame]:
        """Read Ubisoft game install paths from Windows Registry.

        Registry location:
          HKLM\\SOFTWARE\\WOW6432Node\\Ubisoft\\Launcher\\Installs
          HKCU\\Software\\Ubisoft\\Launcher\\Installs

        Each subkey corresponds to a game UUID with values:
          - InstallDir  (REG_SZ)  -- absolute install path
          - GameName    (REG_SZ)  -- display name
        """
        if os.name != "nt":
            return []

        try:
            import winreg
        except ImportError:
            return []

        candidates: list[CandidateGame] = []

        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Ubisoft\Launcher\Installs"),
            (winreg.HKEY_CURRENT_USER, r"Software\Ubisoft\Launcher\Installs"),
        ]

        for hive, key_path in registry_paths:
            try:
                with winreg.OpenKey(hive, key_path) as parent_key:
                    index = 0
                    while True:
                        try:
                            game_guid = winreg.EnumKey(parent_key, index)
                            index += 1
                        except OSError:
                            break

                        try:
                            with winreg.OpenKey(parent_key, game_guid) as game_key:
                                install_dir, _ = winreg.QueryValueEx(game_key, "InstallDir")
                                game_name, _ = winreg.QueryValueEx(game_key, "GameName")
                        except OSError:
                            continue

                        if not install_dir or not os.path.isdir(install_dir):
                            continue

                        exe_path = UbisoftDetector._resolve_executable_from_path(
                            Path(install_dir)
                        )
                        candidates.append(
                            CandidateGame(
                                name=game_name or game_guid,
                                executable_path=exe_path,
                                platform="ubisoft",
                                platform_id=game_guid,
                            )
                        )
            except OSError:
                continue

        return candidates

    # ------------------------------------------------------------------
    # Config-directory detection (legacy fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_from_config_dir() -> list[CandidateGame]:
        """Scan the LOCALAPPDATA config directory for game entries."""
        config_dir = UbisoftDetector._find_config_dir()
        if config_dir is None:
            return []

        candidates: list[CandidateGame] = []

        for entry in config_dir.iterdir():
            if not entry.is_dir():
                continue
            game_id = entry.name
            game_name = UbisoftDetector._read_game_name(entry)
            if not game_name:
                continue
            exe_path = UbisoftDetector._resolve_executable_from_config_dir(entry)
            candidates.append(
                CandidateGame(
                    name=game_name,
                    executable_path=exe_path,
                    platform="ubisoft",
                    platform_id=game_id,
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Shared helpers
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

        for name in ("Ubisoft Game Launcher", "Ubisoft Connect"):
            candidate = base / name / "games"
            if candidate.is_dir():
                return candidate
        return None

    @staticmethod
    def _read_game_name(game_dir: Path) -> str:
        """Read game name from directory or metadata file."""
        name = game_dir.name
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
    def _resolve_executable_from_config_dir(game_dir: Path) -> str:
        """Resolve executable from config directory symlink."""
        for pattern in ("*.exe", "*.app"):
            matches = list(game_dir.glob(pattern))
            if matches:
                return str(matches[0])
        return str(game_dir)

    @staticmethod
    def _resolve_executable_from_path(install_path: Path) -> str:
        """Resolve executable from absolute install path."""
        if not install_path.is_dir():
            return str(install_path)
        for pattern in ("*.exe", "*.app"):
            matches = list(install_path.glob(pattern))
            if matches:
                return str(matches[0])
        return str(install_path)
