"""Environment file loader (stdlib-only, no python-dotenv dependency).

Reads ``KEY=VALUE`` pairs from a ``.env`` file and populates
``os.environ`` so that downstream code can read configuration via
``os.environ.get(...)``.

Designed for development convenience.  In packaged/production builds
the operator is expected to set environment variables through the
platform's normal mechanism (systemd, container orchestration, etc.).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _discover_env_file(path: str | Path | None = None) -> Path | None:
    """Locate a ``.env`` file.

    Resolution order (first match wins):
      1. An explicit *path* argument.
      2. ``.env`` in the current working directory.
      3. ``.env`` in the project root (three levels up from this file).
      4. ``.env`` in the application data directory (``BASE_DIR / ".env"``).
         This is the expected location for production / packaged builds.

    Returns ``None`` when no file is found.
    """
    if path is not None:
        p = Path(path)
        if p.is_file():
            return p.resolve()
        return None

    from trackora.core.paths import BASE_DIR

    candidates: list[Path] = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
        BASE_DIR / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_env_file(path: str | Path | None = None) -> None:
    """Load ``KEY=VALUE`` entries from a ``.env`` file into ``os.environ``.

    Only variables that are **not already set** in the environment are
    populated (``os.environ.setdefault`` semantics).  This ensures that
    externally-set variables always take precedence.

    Args:
        path: Optional explicit path to the ``.env`` file.  When
              ``None`` the file is discovered automatically.

    Logging:
        - INFO with the (redacted) count of loaded variables.
        - WARNING when no ``.env`` file is found (not an error —
          production environments are expected to set variables directly).
    """
    env_file = _discover_env_file(path)
    if env_file is None:
        logger.warning("No .env file found — relying on system environment variables.")
        return

    loaded = 0
    skipped = 0
    try:
        text = env_file.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.warning("Could not read .env file (%s): %s", env_file, exc)
        return

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if not key:
            continue
        if key in os.environ:
            skipped += 1
            continue
        os.environ[key] = value
        loaded += 1

    logger.info(
        "Loaded %d variable(s) from %s (skipped %d already-set)",
        loaded, env_file, skipped,
    )
