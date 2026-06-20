"""
SchemaVersion — immutable semantic version value object.

This is the foundational type for the Upgrade Foundation.
It represents a strict MAJOR.MINOR.PATCH semantic version
and provides parsing, comparison, and serialization.

Architecture rules:
    - No database imports.
    - No service imports.
    - No UI imports.
    - Only depends on stdlib and trackora.__version__.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering


# Regex for strict MAJOR.MINOR.PATCH with non-negative integers only.
_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@total_ordering
@dataclass(frozen=True)
class SchemaVersion:
    """Immutable semantic version for schema tracking.

    Attributes:
        major: MAJOR version — incremented for incompatible schema changes.
        minor: MINOR version — incremented for backward-compatible additions.
        patch: PATCH version — incremented for backward-compatible fixes.
    """

    major: int
    minor: int
    patch: int

    # ── Factories ──────────────────────────────────────────────────────

    @classmethod
    def from_string(cls, version: str) -> SchemaVersion:
        """Parse a ``MAJOR.MINOR.PATCH`` string.

        Args:
            version: A version string like ``"2.0.0"``.

        Returns:
            A new SchemaVersion instance.

        Raises:
            ValueError: If the string does not match MAJOR.MINOR.PATCH
                        with non-negative integers.
        """
        match = _VERSION_PATTERN.match(version)
        if match is None:
            raise ValueError(
                f"Invalid schema version: {version!r}. "
                f"Expected format: MAJOR.MINOR.PATCH (e.g. '2.0.0')."
            )
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    @classmethod
    def current_app_version(cls) -> SchemaVersion:
        """Return the schema version corresponding to the current application.

        Reads ``trackora.__version__`` and parses it.

        Returns:
            The SchemaVersion for the running application.
        """
        from trackora import __version__

        return cls.from_string(__version__)

    # ── Validation ─────────────────────────────────────────────────────

    @classmethod
    def is_valid_format(cls, version: str) -> bool:
        """Return True if *version* matches the MAJOR.MINOR.PATCH pattern."""
        return _VERSION_PATTERN.match(version) is not None

    # ── Comparison ──────────────────────────────────────────────────────

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SchemaVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __eq__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, SchemaVersion):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))

    # ── Serialization ──────────────────────────────────────────────────

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def to_dict(self) -> dict[str, int]:
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
        }


@dataclass(frozen=True)
class CompatibilityStatus:
    """Result of comparing app version to data version.

    Attributes:
        can_proceed:  True if the application may continue starting up.
        status:       Categorical result string.
        message:      Human-readable explanation for logging/UI.
    """

    can_proceed: bool
    status: str  # "ok" | "needs_migration" | "newer_data" | "first_run" | "error"
    message: str


class SchemaVersionError(Exception):
    """Raised when schema.json is corrupt, invalid, or unreadable.

    The corrupt file is renamed to schema.json.corrupt.<timestamp>
    before the exception is raised, so the application can recover
    by creating a fresh schema.json (first-run treatment).
    """
