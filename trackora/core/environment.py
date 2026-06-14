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
from enum import Enum


class Environment(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"


def _resolve_environment() -> Environment:
    raw = os.environ.get("APP_ENV", "production").strip().lower()
    try:
        return Environment(raw)
    except ValueError:
        return Environment.PRODUCTION


CURRENT_ENVIRONMENT: Environment = _resolve_environment()
