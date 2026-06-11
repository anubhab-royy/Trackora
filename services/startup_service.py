"""
StartupService — Phase 9
Manages automatic startup for Trackora.

Windows: Uses HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
Linux:   Uses $HOME/.config/autostart/*.desktop file (XDG spec).

If the platform is not supported, all methods return False / no-op.

Architecture notes:
    - No UI. No SQL. No repository access.
    - Settings persistence is managed by the caller (SettingsRepository).
    - Startup state is detected by checking the actual OS mechanism,
      not by reading a cached setting.
"""

from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_AUTOSTART_DIR = Path.home() / ".config" / "autostart"
_DESKTOP_FILE_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=Trackora
Exec={executable}
Terminal=false
X-GNOME-Autostart-enabled=true
"""


def _get_app_path() -> str:
    """Return the path to the current executable.

    For a bundled app (PyInstaller) this returns sys.executable.
    For development, returns the absolute path to the interpreter + main script.
    """
    exe = sys.executable
    # PyInstaller sets sys.frozen
    if hasattr(sys, "frozen") and sys.frozen:
        return str(Path(exe).resolve())
    # Development: try to find main.py or a script entry point
    return str(Path(exe).resolve())


class StartupService:
    """
    Service for managing OS-level auto-start registration.

    Methods return True on success, False on failure (or unsupported platform).
    """

    @staticmethod
    def is_supported() -> bool:
        """Return True if the current platform supports auto-start."""
        system = platform.system()
        return system in ("Windows", "Linux")

    @staticmethod
    def is_registered() -> bool:
        """
        Return True if Trackora is registered to start automatically.

        Returns False on unsupported platforms or if registration is missing.
        """
        system = platform.system()
        if system == "Windows":
            return _windows_is_registered()
        if system == "Linux":
            return _linux_is_registered()
        return False

    @staticmethod
    def register() -> bool:
        """
        Register Trackora to start automatically on login.

        Returns:
            True if registration succeeded (or was already registered).
            False on unsupported platforms or failure.
        """
        system = platform.system()
        if system == "Windows":
            return _windows_register()
        if system == "Linux":
            return _linux_register()
        logger.warning("Auto-start not supported on platform: %s", system)
        return False

    @staticmethod
    def unregister() -> bool:
        """
        Remove Trackora from auto-start.

        Returns:
            True if unregistration succeeded (or was not registered).
            False on unsupported platforms or failure.
        """
        system = platform.system()
        if system == "Windows":
            return _windows_unregister()
        if system == "Linux":
            return _linux_unregister()
        logger.warning("Auto-start not supported on platform: %s", system)
        return False


# ---------------------------------------------------------------------------
# Windows implementation (registry)
# ---------------------------------------------------------------------------

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_VALUE = "Trackora"


def _windows_is_registered() -> bool:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, _REG_VALUE)
            return True
    except (ImportError, OSError):
        return False


def _windows_register() -> bool:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, _REG_VALUE, 0, winreg.REG_SZ, _get_app_path())
        logger.info("Windows auto-start registered.")
        return True
    except (ImportError, OSError) as exc:
        logger.error("Failed to register Windows auto-start: %s", exc)
        return False


def _windows_unregister() -> bool:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _REG_VALUE)
        logger.info("Windows auto-start unregistered.")
        return True
    except (ImportError, OSError) as exc:
        logger.error("Failed to unregister Windows auto-start: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Linux implementation (XDG autostart .desktop file)
# ---------------------------------------------------------------------------

_DESKTOP_FILE = _AUTOSTART_DIR / "Trackora.desktop"


def _linux_is_registered() -> bool:
    return _DESKTOP_FILE.is_file()


def _linux_register() -> bool:
    try:
        _AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        content = _DESKTOP_FILE_TEMPLATE.format(executable=_get_app_path())
        _DESKTOP_FILE.write_text(content, encoding="utf-8")
        _DESKTOP_FILE.chmod(0o755)
        logger.info("Linux auto-start registered: %s", _DESKTOP_FILE)
        return True
    except OSError as exc:
        logger.error("Failed to register Linux auto-start: %s", exc)
        return False


def _linux_unregister() -> bool:
    try:
        if _DESKTOP_FILE.exists():
            _DESKTOP_FILE.unlink()
            logger.info("Linux auto-start unregistered.")
        return True
    except OSError as exc:
        logger.error("Failed to unregister Linux auto-start: %s", exc)
        return False
