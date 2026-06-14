# ============================================================================
# ARCHITECTURE BOUNDARY
#
# This file is the single source of truth for runtime environment
# and application storage paths.
#
# Do not modify without explicit approval.
#
# All environment detection must go through environment.py.
# All runtime path generation must go through paths.py.
#
# ============================================================================

from __future__ import annotations

import os
import sys
from enum import Enum


class Environment(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"


def _is_frozen() -> bool:
    """Return True if running as a frozen/bundled executable (PyInstaller)."""
    return getattr(sys, "frozen", False)


def _resolve_environment() -> Environment:
    explicit = os.environ.get("APP_ENV")
    if explicit is not None:
        raw = explicit.strip().lower()
        try:
            return Environment(raw)
        except ValueError:
            return Environment.PRODUCTION

    if _is_frozen():
        return Environment.PRODUCTION

    return Environment.DEVELOPMENT


CURRENT_ENVIRONMENT: Environment = _resolve_environment()
