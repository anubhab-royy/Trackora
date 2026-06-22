"""Steam game detector.

Scans Steam installation for installed games by reading:
  1. libraryfolders.vdf  — lists Steam library paths
  2. appmanifest_*.acf   — per-game metadata in each library

Requires no external dependencies — uses the in-house KV parser.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.kv_parser import KVParserError, parse_kv
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)

# Known Steam redistributables / tools that should not appear as games.
_STEAM_EXCLUDED_APP_IDS: frozenset[str] = frozenset({
    "228980",  # Steamworks Common Redistributables
    "329790",  # Steam Music
    "480",     # Steamworks Common Redistributables (old id)
    "897650",  # Steam Audio
})


class SteamDetector(GameDetector):
    """Detect games installed via Steam."""

    @property
    def platform(self) -> str:
        return "steam"

    def detect(self) -> list[CandidateGame]:
        steam_root = self._find_steam_root()
        if steam_root is None:
            logger.info("Steam not found — skipping Steam detection")
            return []

        candidates: list[CandidateGame] = []
        libraries = self._get_library_paths(steam_root)

        for lib in libraries:
            manifests_dir = Path(lib) / "steamapps"
            if not manifests_dir.is_dir():
                continue
            for manifest_path in sorted(manifests_dir.glob("appmanifest_*.acf")):
                try:
                    game = self._parse_manifest(manifest_path, lib)
                    if game is None:
                        continue
                    if game.platform_id in _STEAM_EXCLUDED_APP_IDS:
                        logger.debug(
                            "Excluded redistributable: %s (%s)",
                            game.name,
                            game.platform_id,
                        )
                        continue
                    candidates.append(game)
                except Exception:
                    logger.exception("Failed to parse Steam manifest %s", manifest_path)

        logger.info("Steam detection complete: %d game(s) found", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Private — Steam root discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _find_steam_root() -> str | None:
        """Locate the Steam installation directory."""
        if os.name == "nt":
            import winreg  # type: ignore[import-untyped]

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Valve\Steam",
                ) as key:
                    path, _ = winreg.QueryValueEx(key, "SteamPath")
                    return path.replace("/", "\\")
            except (OSError, ImportError):
                pass

            # Fallback: common Windows paths
            for base in (
                Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
                Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
            ):
                candidate = base / "Steam"
                if candidate.is_dir():
                    return str(candidate)
        else:
            # macOS
            mac_path = Path.home() / "Library" / "Application Support" / "Steam"
            if mac_path.is_dir():
                return str(mac_path)
            # Linux
            linux_path = Path.home() / ".steam" / "steam"
            if linux_path.is_dir():
                return str(linux_path)
            linux_path2 = Path.home() / ".local" / "share" / "Steam"
            if linux_path2.is_dir():
                return str(linux_path2)

        return None

    # ------------------------------------------------------------------
    # Private — library path discovery
    # ------------------------------------------------------------------

    @staticmethod
    def _get_library_paths(steam_root: str) -> list[str]:
        """Read libraryfolders.vdf and return list of library paths.

        Handles both legacy flat format:
            "1" "C:\\Program Files (x86)\\Steam"
        and modern nested format:
            "0" { "path" "E:\\Applications\\Steam" ... }
        """
        vdf_path = Path(steam_root) / "steamapps" / "libraryfolders.vdf"
        if not vdf_path.is_file():
            logger.warning("libraryfolders.vdf not found at %s", vdf_path)
            return [steam_root]

        try:
            data = parse_kv(vdf_path.read_text("utf-8"))
        except KVParserError:
            logger.exception("Failed to parse libraryfolders.vdf")
            return [steam_root]

        # Case-insensitive lookup: Steam versions differ on key casing
        sections_key = next(
            (k for k in data if k.lower() == "libraryfolders"),
            None,
        )
        folders: dict = data.get(sections_key, {}) if sections_key else {}

        paths: list[str] = [steam_root]
        for key in sorted(folders, key=_numeric_sort_key):
            if not key.isdigit():
                continue
            value = folders[key]
            # Modern format: {"path": "D:\\SteamLibrary", ...}
            if isinstance(value, dict):
                lib_path = value.get("path", "")
            else:
                # Legacy format: "D:\\SteamLibrary"
                lib_path = str(value)
            if lib_path and Path(lib_path).is_dir():
                resolved = str(Path(lib_path).resolve())
                if resolved not in {str(Path(p).resolve()) for p in paths}:
                    paths.append(lib_path)
        return paths

    # ------------------------------------------------------------------
    # Private — manifest parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_manifest(manifest_path: Path, library_path: str) -> CandidateGame | None:
        """Parse a single appmanifest_*.acf file into a CandidateGame."""
        try:
            data = parse_kv(manifest_path.read_text("utf-8"))
        except (KVParserError, OSError):
            logger.exception("Failed to parse manifest %s", manifest_path)
            return None

        app_state = data.get("AppState", {})
        app_id = app_state.get("appid", "")
        name = app_state.get("name", "")
        install_dir = app_state.get("installdir", "")

        if not app_id or not name:
            logger.warning("Incomplete manifest: %s", manifest_path)
            return None

        # Resolve executable path
        exe_path = SteamDetector._resolve_executable(install_dir, library_path)
        if not exe_path:
            # Cannot find executable — still return a candidate with empty path
            # so the user can see the game exists
            exe_path = ""

        return CandidateGame(
            name=name,
            executable_path=exe_path,
            platform="steam",
            platform_id=app_id,
        )

    @staticmethod
    def _resolve_executable(install_dir: str, library_path: str) -> str:
        """Resolve game executable path from install dir + library root."""
        base = Path(library_path) / "steamapps" / "common" / install_dir
        for pattern in ("*.exe", "*.app"):
            matches = list(base.glob(pattern))
            if matches:
                return str(matches[0])
        # Fallback: return the directory itself
        return str(base) if base.is_dir() else ""


def _numeric_sort_key(key: str) -> tuple:
    """Sort key that puts numeric strings in numeric order, others last."""
    try:
        return (0, int(key))
    except ValueError:
        return (1, key)
