"""
health_status.py — defines health state categories for tracked components.
"""

from __future__ import annotations

from enum import Enum


class HealthStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    FAILED = "failed"
