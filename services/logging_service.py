"""
LoggingService — Phase 9
Daily rotating log files for Trackora.

Log file format:
    logs/YYYY-MM-DD.log

Each day gets a separate file. Old files are never auto-deleted;
the user may delete them manually.

Architecture notes:
    - Configures Python's logging module on first setup.
    - Thread-safe via logging.Handler internals.
    - Call setup() once at application startup.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from trackora import __version__

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _get_default_log_dir() -> Path:
    """Return a platform-appropriate log directory.

    On Windows:  %APPDATA%/Trackora/logs/
    On Linux:     ~/.local/share/Trackora/logs/
    When frozen:  same as above (never next to the executable).
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "Trackora" / "logs"


_DEFAULT_LOG_DIR = _get_default_log_dir()


class LoggingService:
    """
    Configures and manages application logging.

    Usage:
        LoggingService.setup()
        # or with custom path:
        LoggingService.setup(log_dir=Path("/custom/path/logs"))

    The root logger is configured once. Subsequent calls to setup()
    are ignored unless force=True is passed.
    """

    _initialized: bool = False

    @classmethod
    def setup(
        cls,
        log_dir: Optional[Path] = None,
        level: int = logging.DEBUG,
        force: bool = False,
    ) -> None:
        """
        Configure daily rotating file logging.

        Args:
            log_dir: Directory for log files. Defaults to <project>/logs/.
            level:   Logging level (default: DEBUG).
            force:   Reconfigure even if already initialized.
        """
        if cls._initialized and not force:
            return

        if log_dir is None:
            log_dir = _DEFAULT_LOG_DIR

        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "trackora.log"
        handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight",
            interval=1,
            backupCount=0,  # never delete old logs
            encoding="utf-8",
            delay=False,
        )
        handler.setLevel(level)
        formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        handler.setFormatter(formatter)

        root = logging.getLogger()
        root.setLevel(level)

        # Remove any existing handlers to avoid duplicates on re-setup
        if force:
            for h in root.handlers[:]:
                root.removeHandler(h)

        root.addHandler(handler)

        # Add console handler so errors are visible in the terminal
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        console.setFormatter(formatter)
        root.addHandler(console)

        cls._initialized = True
        logging.getLogger(cls.__name__).info(
            "LoggingService initialized. Log file: %s", log_file
        )

    @classmethod
    def get_log_dir(cls) -> Path:
        """Return the default log directory path (APPDATA-safe)."""
        return _get_default_log_dir()
