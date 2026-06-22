"""Abstract base class for game launcher detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tracker.discovery.models import CandidateGame


class GameDetector(ABC):
    """Base class for a platform-specific game detector.

    Each subclass implements ``detect()`` to scan a specific game launcher
    and return a list of discovered candidates.
    """

    @property
    @abstractmethod
    def platform(self) -> str:
        """Platform identifier, e.g. 'steam', 'epic', 'generic'."""

    @abstractmethod
    def detect(self) -> list[CandidateGame]:
        """Scan the launcher and return discovered game candidates."""
