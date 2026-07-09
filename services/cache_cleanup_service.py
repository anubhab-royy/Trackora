"""
CacheCleanupService: Handles filesystem cleanup for deleted games.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from trackora.core.paths import BASE_DIR, CACHE_DIR

logger = logging.getLogger(__name__)


class CacheCleanupService:
    """
    Service responsible for cleaning up non-database cache/asset files for a game.
    """

    def __init__(self, cache_dir: Path = CACHE_DIR, base_dir: Path = BASE_DIR) -> None:
        self._cache_dir = cache_dir
        self._base_dir = base_dir

    def cleanup_game_artifacts(self, game_id: int, game_name: str, icon_path: str = "") -> None:
        """
        Removes any game-specific cached files or local assets.
        Best-effort only.
        """
        logger.info("Cache cleanup started for game_id=%d (%s)", game_id, game_name)

        files_removed = 0
        files_missing = 0

        # We inspect CACHE_DIR
        logger.info("Directory inspected: %s", self._cache_dir)

        # 1. Clean up icon if it exists inside our CACHE_DIR or BASE_DIR
        if icon_path:
            try:
                icon_file = Path(icon_path)
                # SAFETY CHECK: Only delete if it lies inside Trackora's AppData directory (BASE_DIR)
                is_sub_path = False
                try:
                    icon_file.resolve().relative_to(self._base_dir.resolve())
                    is_sub_path = True
                except ValueError:
                    pass

                if is_sub_path:
                    if icon_file.is_file():
                        # Handle read-only permissions before deleting
                        if not os.access(icon_file, os.W_OK):
                            os.chmod(icon_file, 0o666)
                        icon_file.unlink()
                        files_removed += 1
                        logger.info("Files removed: %s", icon_file)
                    else:
                        logger.info("Files already missing: %s", icon_path)
                        files_missing += 1
                else:
                    logger.info("Files already missing or outside app data directory: %s", icon_path)
                    files_missing += 1
            except Exception as exc:
                logger.warning("Cleanup warnings: Failed to delete icon %s: %s", icon_path, exc)

        # 2. Check for future-proofing game-specific temp/cache files in CACHE_DIR
        # Files named like game_<id>_* or <game_name>_* inside CACHE_DIR
        normalized_name = game_name.strip().lower().replace(" ", "_")
        try:
            if self._cache_dir.is_dir():
                for item in self._cache_dir.iterdir():
                    if item.is_file():
                        name = item.name.lower()
                        if name.startswith(f"game_{game_id}_") or name.startswith(f"{normalized_name}_"):
                            try:
                                if not os.access(item, os.W_OK):
                                    os.chmod(item, 0o666)
                                item.unlink()
                                files_removed += 1
                                logger.info("Files removed: %s", item)
                            except Exception as exc:
                                logger.warning("Cleanup warnings: Failed to delete cache file %s: %s", item, exc)
        except Exception as exc:
            logger.warning("Cleanup warnings: Error scanning cache directory: %s", exc)

        logger.info("Cleanup completed for game_id=%d. Removed: %d, Missing: %d", game_id, files_removed, files_missing)
