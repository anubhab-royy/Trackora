"""
Shared formatting utilities for Trackora.

Currently provides:
    format_duration(seconds: int) -> str
        Convert seconds to a human-readable string like "1h 30m".
"""

from __future__ import annotations


def format_duration(seconds: int) -> str:
    """Convert seconds to a human-readable string like '1h 30m'."""
    if seconds <= 0:
        return "0m"
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
