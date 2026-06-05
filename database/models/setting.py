# Setting dataclass + bool/int

"""
Setting model for GameTracker.

Maps directly to the `settings` table defined in database_schema.md.

The settings table uses a key/value store approach.
Known keys (as of v1.0):
    - dark_mode              ("true" / "false")
    - start_with_windows     ("true" / "false")
    - backup_enabled         ("true" / "false")
    - minimize_to_tray       ("true" / "false")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Setting:
    """
    Represents a single application setting entry.

    Matches the `settings` table schema exactly:
        key        TEXT PRIMARY KEY
        value      TEXT
        updated_at DATETIME
    """

    key: str
    value: str
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Validate fields after construction."""
        if not self.key or not self.key.strip():
            raise ValueError("Setting key must not be empty.")

    # ------------------------------------------------------------------
    # Typed convenience accessors
    # ------------------------------------------------------------------

    def as_bool(self) -> bool:
        """Interpret the stored value as a boolean."""
        return self.value.strip().lower() in {"true", "1", "yes"}

    def as_int(self) -> int:
        """Interpret the stored value as an integer."""
        return int(self.value)

    def as_float(self) -> float:
        """Interpret the stored value as a float."""
        return float(self.value)

    @classmethod
    def from_bool(cls, key: str, value: bool) -> "Setting":
        """Factory for boolean settings."""
        return cls(key=key, value="true" if value else "false")