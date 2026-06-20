"""Epic Games launcher detector.

Reads LauncherInstalled.dat (JSON) to find installed Epic games.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)


class EpicDetector(GameDetector):
    """Detect games installed via the Epic Games Launcher."""

    @property
    def platform(self) -> str:
        return "epic"

    def detect(self) -> list[CandidateGame]:
        manifest_dir = self._find_manifest_dir()
        if manifest_dir is None:
            logger.info("Epic launcher not found — skipping Epic detection")
            return []

        manifest_path = Path(manifest_dir) / "LauncherInstalled.dat"
        if not manifest_path.is_file():
            logger.warning("Epic manifest not found at %s", manifest_path)
            return []

        try:
            data = json.loads(manifest_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to parse Epic manifest")
            return []

        installs = data.get("InstallationList", [])
        candidates: list[CandidateGame] = []

        for entry in installs:
            app_name = entry.get("AppName", "")
            display_name = entry.get("DisplayName", "")
            install_location = entry.get("InstallLocation", "")

            if not app_name or not display_name:
                continue

            exe_path = self._resolve_executable(install_location, entry)
            candidates.append(
                CandidateGame(
                    name=display_name,
                    executable_path=exe_path,
                    platform="epic",
                    platform_id=app_name,
                )
            )

        logger.info("Epic detection complete: %d game(s) found", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _find_manifest_dir() -> str | None:
        """Locate the Epic launcher data directory."""
        if os.name == "nt":
            program_data = os.environ.get(
                "PROGRAMDATA", "C:\\ProgramData"
            )
            candidate = Path(program_data) / "Epic" / "UnrealEngineLauncher"
            if candidate.is_dir():
                return str(candidate)
        else:
            # Linux/macOS: check common locations
            for base in (
                Path.home() / ".config" / "Epic",
                Path.home() / "Library" / "Application Support" / "Epic",
            ):
                candidate = base / "UnrealEngineLauncher"
                if candidate.is_dir():
                    return str(candidate)

        return None

    @staticmethod
    def _resolve_executable(install_location: str, entry: dict) -> str:
        """Resolve the game executable path."""
        base = Path(install_location)
        if not base.is_dir():
            return install_location

        # Use LaunchExecutable if provided
        launch_exe = entry.get("LaunchExecutable", "")
        if launch_exe:
            exe = base / launch_exe
            if exe.is_file():
                return str(exe)

        # Scan for executables
        for pattern in ("*.exe", "*.app"):
            matches = list(base.glob(pattern))
            if matches:
                return str(matches[0])

        return install_location
