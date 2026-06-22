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

_MAX_SCAN_DEPTH = 8  # max subdirectory depth to prevent unbounded recursion

_EXECUTABLE_PATTERNS = ("*.exe", "*.app")


class FolderDetector(GameDetector):
    """Scan directories for game executables.

    Args:
        min_size_bytes: Minimum file size in bytes (default 1 MB).
            Overridable for testing.
        max_depth: Maximum directory recursion depth (default 8).
    """

    def __init__(
        self,
        min_size_bytes: int = _MIN_FILE_SIZE_BYTES,
        max_depth: int = _MAX_SCAN_DEPTH,
    ) -> None:
        self._min_size = min_size_bytes
        self._max_depth = max_depth

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
                for entry in self._walk_depth_limited(folder_path):
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

    def _walk_depth_limited(self, root: Path) -> list[Path]:
        """Walk directory tree up to ``_max_depth``, yielding file paths.

        Prevents unbounded recursion on large or deeply-nested directories
        while still finding games in reasonably structured game libraries.
        """
        results: list[Path] = []
        stack: list[tuple[Path, int]] = [(root, 0)]
        visited: set[str] = set()

        while stack:
            current, depth = stack.pop()
            if depth > self._max_depth:
                continue
            if self._is_excluded(current):
                continue
            try:
                with os.scandir(str(current)) as it:
                    for entry in it:
                        try:
                            entry_path = Path(entry.path)
                        except OSError:
                            continue
                        resolved = str(entry_path.resolve()).lower()
                        if resolved in visited:
                            continue
                        visited.add(resolved)
                        if entry.is_dir(follow_symlinks=False):
                            stack.append((entry_path, depth + 1))
                        elif entry.is_file():
                            results.append(entry_path)
            except (PermissionError, OSError):
                continue

        return results

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
