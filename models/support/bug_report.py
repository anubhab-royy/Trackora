from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass
class BugReport:
    title: str
    description: str
    steps_to_reproduce: str
    expected_behavior: str
    actual_behavior: str
    severity: str = "medium"
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    id: str | None = None

    def __post_init__(self) -> None:
        valid = {"low", "medium", "high", "critical"}
        if self.severity not in valid:
            raise ValueError(f"Severity must be one of {valid}, got '{self.severity}'")
