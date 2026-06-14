"""Environment-aware single-instance lock for Trackora.

Allows Production and Development instances to run
simultaneously by encoding the environment name
into the lock name.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from trackora.core.environment import CURRENT_ENVIRONMENT

logger = logging.getLogger(__name__)

_LOCK_NAME = f"Trackora-{CURRENT_ENVIRONMENT.value}"
_LOCK_FILE = Path.home() / ".trackora" / f"{_LOCK_NAME}.lock"

_windows_mutex_handle: int | None = None


def acquire() -> bool:
    """Attempt to acquire the single-instance lock.

    Returns True if this is the first instance, False if
    another instance is already running.
    """
    if os.name == "nt":
        return _acquire_windows()
    return _acquire_posix()


def release() -> None:
    """Release the single-instance lock."""
    if os.name == "nt":
        _release_windows()
    else:
        _release_posix()


# ---------------------------------------------------------------------------
# Windows: named mutex via kernel32
# ---------------------------------------------------------------------------


def _acquire_windows() -> bool:
    global _windows_mutex_handle
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex_name = f"Global\\{_LOCK_NAME}"
        handle = kernel32.CreateMutexW(None, True, mutex_name)
        err = ctypes.get_last_error()
        if handle and err != 183:  # ERROR_ALREADY_EXISTS
            _windows_mutex_handle = handle
            logger.debug("Single-instance mutex acquired: %s", mutex_name)
            return True
        if handle:
            kernel32.CloseHandle(handle)
        logger.info("Another Trackora (%s) instance is already running.", CURRENT_ENVIRONMENT.value)
        return False
    except Exception as exc:
        logger.warning("Failed to acquire single-instance mutex: %s", exc)
        return True


def _release_windows() -> None:
    global _windows_mutex_handle
    if _windows_mutex_handle is not None:
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_windows_mutex_handle)
        except Exception:
            pass
        _windows_mutex_handle = None


# ---------------------------------------------------------------------------
# POSIX: lock file with fcntl
# ---------------------------------------------------------------------------


def _acquire_posix() -> bool:
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
        fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            logger.info(
                "Another Trackora (%s) instance is already running.",
                CURRENT_ENVIRONMENT.value,
            )
            return False
        # Store fd for later release
        _acquire_posix.fd = fd  # type: ignore[attr-defined]
        logger.debug("Single-instance lock acquired: %s", _LOCK_FILE)
        return True
    except ImportError:
        logger.warning("fcntl not available; skipping single-instance lock.")
        return True
    except Exception as exc:
        logger.warning("Failed to acquire single-instance lock: %s", exc)
        return True


def _release_posix() -> None:
    fd = getattr(_acquire_posix, "fd", None)
    if fd is not None:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except Exception:
            pass
        try:
            _LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        _acquire_posix.fd = None  # type: ignore[attr-defined]
