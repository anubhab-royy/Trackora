"""
health_result.py — data transfer object containing the outcome of a health check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.health.health_status import HealthStatus


@dataclass(frozen=True)
class HealthResult:
    """Outcome status and metadata for a single health check."""

    status: HealthStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
