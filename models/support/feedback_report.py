from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass
class FeedbackReport:
    subject: str
    message: str
    category: str = "general"
    contact_ok: bool = False
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    id: str | None = None

    def __post_init__(self) -> None:
        valid = {"general", "praise", "complaint"}
        if self.category not in valid:
            raise ValueError(
                f"Category must be one of {valid}, got '{self.category}'"
            )
