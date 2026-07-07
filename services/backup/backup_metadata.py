"""
backup_metadata.py — generates structured backup manifest metadata.
"""

from __future__ import annotations

import sys

from trackora import __version__
from trackora.core.environment import CURRENT_ENVIRONMENT


class BackupMetadata:
    """Helper class to build metadata for database backup manifests."""

    @staticmethod
    def generate(backup_type: str) -> dict[str, str]:
        """Generate metadata dict for a backup."""
        return {
            "environment": CURRENT_ENVIRONMENT,
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
            "application_version": __version__,
            "backup_reason": backup_type,
            "notes": "",
        }
