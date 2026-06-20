"""Discovery orchestrator.

Runs all enabled detectors and aggregates results with deduplication.
"""

from __future__ import annotations

import logging
import time

from tracker.discovery.detector import GameDetector
from tracker.discovery.detectors.battlenet_detector import BattleNetDetector
from tracker.discovery.detectors.ea_detector import EADetector
from tracker.discovery.detectors.epic_detector import EpicDetector
from tracker.discovery.detectors.folder_detector import FolderDetector
from tracker.discovery.detectors.riot_detector import RiotDetector
from tracker.discovery.detectors.steam_detector import SteamDetector
from tracker.discovery.detectors.ubisoft_detector import UbisoftDetector
from tracker.discovery.models import CandidateGame, DiscoveryResult

logger = logging.getLogger(__name__)

# Detector priority for dedup: lower number = higher priority
_DETECTOR_PRIORITY: dict[str, int] = {
    "steam": 0,
    "epic": 1,
    "battlenet": 2,
    "riot": 3,
    "ubisoft": 4,
    "ea": 5,
    "generic": 6,
}


class DiscoveryOrchestrator:
    """Orchestrates all enabled detectors and aggregates results.

    Args:
        existing_tracker: Optional callable to check if a game is already tracked.
            Expected signature: exists_by_executable_path(path: str) -> bool
    """

    def __init__(
        self,
        exists_by_executable_path=None,
        exists_by_platform_id=None,
    ) -> None:
        self._detectors: list[GameDetector] = [
            SteamDetector(),
            EpicDetector(),
            RiotDetector(),
            BattleNetDetector(),
            UbisoftDetector(),
            EADetector(),
            FolderDetector(),
        ]
        self._exists_by_executable_path = exists_by_executable_path
        self._exists_by_platform_id = exists_by_platform_id

    def scan_all(self, folder_paths: list[str] | None = None) -> DiscoveryResult:
        """Run all detectors and return aggregated, deduplicated results.

        Args:
            folder_paths: Directories for FolderDetector to scan.

        Returns:
            DiscoveryResult with candidates, errors, and timing.
        """
        start = time.perf_counter()
        all_candidates: list[CandidateGame] = []
        errors: list[str] = []

        for detector in self._detectors:
            try:
                if isinstance(detector, FolderDetector):
                    results = detector.detect(folder_paths)
                else:
                    results = detector.detect()
                all_candidates.extend(results)
            except Exception as exc:
                msg = f"{detector.platform}: {exc}"
                logger.exception("Detector %s failed", detector.platform)
                errors.append(msg)

        # Deduplicate
        candidates = self._deduplicate(all_candidates)

        # Exclude already-tracked
        candidates = self._exclude_existing(candidates)

        duration_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            "Discovery scan complete: %d candidate(s) from %d raw, %d error(s) in %dms",
            len(candidates),
            len(all_candidates),
            len(errors),
            duration_ms,
        )

        return DiscoveryResult(
            candidates=candidates,
            errors=errors,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(candidates: list[CandidateGame]) -> list[CandidateGame]:
        """Remove duplicates keeping the highest-priority detector result."""
        best: dict[str, CandidateGame] = {}
        for c in candidates:
            key = c.executable_path
            if key in best:
                existing = best[key]
                existing_priority = _DETECTOR_PRIORITY.get(existing.platform, 99)
                current_priority = _DETECTOR_PRIORITY.get(c.platform, 99)
                if current_priority < existing_priority:
                    best[key] = c
            else:
                best[key] = c
        # Return results ordered by detector priority (highest priority first)
        def sort_key(item: tuple[str, CandidateGame]) -> int:
            return _DETECTOR_PRIORITY.get(item[1].platform, 99)
        return [c for _, c in sorted(best.items(), key=sort_key)]

    def _exclude_existing(self, candidates: list[CandidateGame]) -> list[CandidateGame]:
        """Remove candidates that are already tracked in the database."""
        if not self._exists_by_executable_path and not self._exists_by_platform_id:
            return candidates

        filtered: list[CandidateGame] = []
        for c in candidates:
            # Check by platform_id first
            if self._exists_by_platform_id and c.platform and c.platform_id:
                if self._exists_by_platform_id(c.platform, c.platform_id):
                    continue
            # Check by executable_path
            if self._exists_by_executable_path and c.executable_path:
                if self._exists_by_executable_path(c.executable_path):
                    continue
            filtered.append(c)
        return filtered
