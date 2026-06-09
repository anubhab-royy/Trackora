"""
UpdateService — Phase 10
Checks GitHub Releases for newer versions and notifies the user.

Provides:
    - Version comparison (semver)
    - GitHub Releases API check
    - Notification when update is available
    - Download link for the new installer

Usage:
    update_service = UpdateService("yourusername/gametracker")
    update_service.check_for_updates()
    if update_service.update_available:
        # show notification / dialog
        update_service.get_download_url()
"""

from __future__ import annotations

import json
import logging
import ssl
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

from gametracker import __version__

logger = logging.getLogger(__name__)

_GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"
_CONNECTION_TIMEOUT = 5  # seconds


@dataclass
class UpdateInfo:
    """Information about an available update."""

    latest_version: str
    download_url: str
    release_notes: str = ""
    is_newer: bool = False


class UpdateService:
    """
    Checks for GameTracker updates via the GitHub Releases API.

    Args:
        repo: GitHub repository in "owner/name" format.
              Defaults to "yourusername/gametracker".
    """

    def __init__(self, repo: str = "yourusername/gametracker") -> None:
        self._repo = repo
        self._update_info: Optional[UpdateInfo] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def update_available(self) -> bool:
        """Return True if a newer version was found."""
        return self._update_info is not None and self._update_info.is_newer

    @property
    def update_info(self) -> Optional[UpdateInfo]:
        """Return the last check result, or None if not checked."""
        return self._update_info

    def check_for_updates(self) -> Optional[UpdateInfo]:
        """
        Check the GitHub Releases API for a newer version.

        Returns:
            UpdateInfo if the check succeeded, None on failure.
        """
        try:
            info = self._fetch_latest_release()
            info.is_newer = self._is_newer_version(info.latest_version)
            self._update_info = info
            if info.is_newer:
                logger.info(
                    "Update available: %s → %s",
                    __version__,
                    info.latest_version,
                )
            else:
                logger.debug("GameTracker is up to date (%s).", __version__)
            return info
        except Exception as exc:
            logger.warning("Update check failed: %s", exc)
            return None

    def get_download_url(self) -> Optional[str]:
        """Return the download URL for the latest release, or None."""
        if self._update_info is not None:
            return self._update_info.download_url
        return None

    def get_latest_version(self) -> Optional[str]:
        """Return the latest version string, or None."""
        if self._update_info is not None:
            return self._update_info.latest_version
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_latest_release(self) -> UpdateInfo:
        """Query the GitHub Releases API and parse the response."""
        url = _GITHUB_API_URL.format(repo=self._repo)
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "GameTracker"})

        context = ssl.create_default_context()
        response = urlopen(req, timeout=_CONNECTION_TIMEOUT, context=context)
        data = json.loads(response.read().decode("utf-8"))

        tag = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "")

        # Find the first .exe asset (prefer the installer over the raw exe)
        assets = data.get("assets", [])
        download_url = ""
        for asset in assets:
            name = asset.get("name", "")
            if "Setup" in name or "Installer" in name:
                download_url = asset.get("browser_download_url", "")
                break
        if not download_url:
            # Fallback: first .exe asset
            for asset in assets:
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset.get("browser_download_url", "")
                    break

        return UpdateInfo(latest_version=tag, download_url=download_url, release_notes=body)

    @staticmethod
    def _is_newer_version(latest: str) -> bool:
        """Compare versions using simple tuple comparison."""
        try:
            current = tuple(int(x) for x in __version__.split("."))
            latest_tuple = tuple(int(x) for x in latest.split("."))
            return latest_tuple > current
        except (ValueError, TypeError):
            logger.warning("Could not compare versions: %s vs %s", __version__, latest)
            return False
