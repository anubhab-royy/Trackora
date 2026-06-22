from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass
class FeatureRequest:
    title: str
    description: str
    use_case: str
    priority: str = "medium"
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    id: str | None = None

    def __post_init__(self) -> None:
        valid = {"low", "medium", "high"}
        if self.priority not in valid:
            raise ValueError(f"Priority must be one of {valid}, got '{self.priority}'")
