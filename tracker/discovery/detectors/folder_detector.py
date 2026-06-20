"""Generic folder scanner.

Scans user-configured directories for game executables.
Lowest priority — used as fallback when no launcher detects a game.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from tracker.discovery.detector import GameDetector
from tracker.discovery.models import CandidateGame

logger = logging.getLogger(__name__)

_SYSTEM_EXCLUDED_DIRS: frozenset[str] = frozenset({
    "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/lib",
    "/System", "/Library",
    "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
    "C:\\$Recycle.Bin", "C:\\System Volume Information",
})

_MIN_FILE_SIZE_BYTES = 1_048_576  # 1 MB

_EXECUTABLE_PATTERNS = ("*.exe", "*.app")


class FolderDetector(GameDetector):
    """Scan directories for game executables.

    Args:
        min_size_bytes: Minimum file size in bytes (default 1 MB).
            Overridable for testing.
    """

    def __init__(self, min_size_bytes: int = _MIN_FILE_SIZE_BYTES) -> None:
        self._min_size = min_size_bytes

    @property
    def platform(self) -> str:
        return "generic"

    def detect(self, folder_paths: list[str] | None = None) -> list[CandidateGame]:
        """Scan the given folder paths for executables.

        Args:
            folder_paths: Directories to scan. If None, uses an empty list.

        Returns:
            List of discovered candidate games.
        """
        if not folder_paths:
            logger.info("No folders configured for generic scan")
            return []

        candidates: list[CandidateGame] = []
        seen_paths: set[str] = set()

        for folder in folder_paths:
            folder_path = Path(folder)
            if not folder_path.is_dir():
                logger.warning("Scan folder not found: %s", folder)
                continue

            try:
                for entry in folder_path.rglob("*"):
                    if self._is_excluded(entry):
                        continue
                    if not entry.is_file():
                        continue
                    if not self._is_executable(entry):
                        continue
                    if entry.stat().st_size < self._min_size:
                        continue
                    resolved = str(entry.resolve())
                    if resolved in seen_paths:
                        continue
                    seen_paths.add(resolved)

                    name = entry.stem.replace("_", " ").replace("-", " ").title()
                    path_hash = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]

                    candidates.append(
                        CandidateGame(
                            name=name,
                            executable_path=resolved,
                            platform="generic",
                            platform_id=path_hash,
                        )
                    )
            except PermissionError:
                logger.warning("Permission denied scanning: %s", folder)
                continue
            except OSError:
                logger.exception("Error scanning folder: %s", folder)
                continue

        logger.info("Folder scan complete: %d game(s) found", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _is_excluded(path: Path) -> bool:
        """Check if a path is in a system-excluded directory."""
        try:
            resolved = str(path.resolve())
        except OSError:
            return True
        for excluded in _SYSTEM_EXCLUDED_DIRS:
            if resolved.startswith(excluded):
                return True
        # Hidden directories
        for part in path.parts:
            if part.startswith(".") and part != ".":
                return True
        return False

    @staticmethod
    def _is_executable(path: Path) -> bool:
        """Check if the file has an executable extension or flag."""
        if path.suffix.lower() in (".exe", ".app", ".bat", ".cmd", ".bin"):
            return True
        # On Unix, check the executable bit
        if os.name != "nt" and os.access(str(path), os.X_OK):
            return True
        return False
