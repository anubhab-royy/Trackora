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
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        
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
        return False


def _release_windows() -> None:
    global _windows_mutex_handle
    if _windows_mutex_handle is not None:
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.CloseHandle(_windows_mutex_handle)
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


def activate_existing_instance() -> bool:
    """Finds the existing window of Trackora and activates it.
    
    Restores the window if it was minimized, and brings it to foreground.
    """
    if os.name == "nt":
        return _activate_windows_window()
    return False


def _activate_windows_window() -> bool:
    try:
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        
        # Define argtypes and restype
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        
        user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        user32.AllowSetForegroundWindow.restype = wintypes.BOOL
        
        from trackora.core.environment import Environment, CURRENT_ENVIRONMENT
        target_title = "Trackora [DEV]" if CURRENT_ENVIRONMENT == Environment.DEVELOPMENT else "Trackora"
        
        # 1. Try FindWindowW
        hwnd = user32.FindWindowW(None, target_title)
        
        # 2. Try EnumWindows as fallback
        if not hwnd:
            found: list[wintypes.HWND] = []
            
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetWindowTextW.restype = ctypes.c_int
            
            def enum_cb(h, l):
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    if buf.value == target_title:
                        found.append(h)
                        return False  # Stop enumeration
                return True
                
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if found:
                hwnd = found[0]
                
        if hwnd:
            # Allow the target window to take foreground (ASFW_ANY = -1)
            user32.AllowSetForegroundWindow(0xFFFFFFFF)  # -1 as DWORD is 0xFFFFFFFF
            
            # Restore if minimized (SW_RESTORE = 9)
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)
            else:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
                
            # Bring to foreground & focus
            user32.SetForegroundWindow(hwnd)
            return True
            
        return False
    except Exception as exc:
        logger.warning("Failed to activate existing window: %s", exc)
        return False

