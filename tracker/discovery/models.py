"""DTOs for game discovery.

CandidateGame — a game found by a launcher or folder scan (not yet imported).
DiscoveryResult — aggregated result of a full scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PureWindowsPath


@dataclass(frozen=True)
class CandidateGame:
    """A game discovered by a launcher or folder scanner — not yet imported."""

    name: str
    executable_path: str
    platform: str
    platform_id: str
    icon_path: str = ""
    process_name: str = ""

    def __post_init__(self) -> None:
        if not self.process_name:
            object.__setattr__(
                self, "process_name", PureWindowsPath(self.executable_path).name
            )


@dataclass(frozen=True)
class DiscoveryResult:
    """Result of a full scan across all enabled detectors."""

    candidates: list[CandidateGame]
    errors: list[str]
    duration_ms: int
