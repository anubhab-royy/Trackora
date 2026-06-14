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
from pathlib import Path

from trackora.core.environment import CURRENT_ENVIRONMENT, Environment


def _get_base_dir_name() -> str:
    mapping = {
        Environment.PRODUCTION: "Trackora",
        Environment.DEVELOPMENT: "Trackora-Dev",
    }
    return mapping[CURRENT_ENVIRONMENT]


def _resolve_base_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".local" / "share"
    return base / _get_base_dir_name()


BASE_DIR: Path = _resolve_base_dir()

DATABASE_PATH: Path = BASE_DIR / "trackora.db"

LOGS_DIR: Path = BASE_DIR / "logs"
REPORTS_DIR: Path = BASE_DIR / "reports"
CRASH_DIR: Path = BASE_DIR / "crash_reports"

CACHE_DIR: Path = BASE_DIR / "cache"
CONFIG_DIR: Path = BASE_DIR / "config"

SCREENSHOTS_DIR: Path = BASE_DIR / "screenshots"

BACKUPS_DIR: Path = BASE_DIR / "backups"
EXPORTS_DIR: Path = BASE_DIR / "exports"
IMPORTS_DIR: Path = BASE_DIR / "imports"


def ensure_dirs() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
