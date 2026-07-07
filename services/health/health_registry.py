"""
health_registry.py — manages registration and discovery of service checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.health.health_check import BaseHealthCheck


class HealthRegistry:
    """Registry pattern holding all active BaseHealthCheck instances."""

    def __init__(self) -> None:
        self._checks: dict[str, BaseHealthCheck] = {}

    def register(self, check: BaseHealthCheck) -> None:
        """Add a health check to the registry. Overwrites if name duplicates."""
        self._checks[check.name()] = check

    def get_all(self) -> list[BaseHealthCheck]:
        """Return a list of all registered diagnostic checks."""
        return list(self._checks.values())
