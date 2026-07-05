"""
UpdateCenterService — Phase 10
Checks GitHub Releases for newer versions and notifies the user.

Provides:
    - Version comparison (semver)
    - GitHub Releases API check with ETag caching
    - SettingsRepository integration (last_checked, ignored_version)
    - Local cache file persistence (offline fallback)
    - Rate-limit safety (min 1 hour between checks)

Architecture:
    - No PyQt6 imports
    - No UI imports
    - Uses stdlib urllib.request (no new dependencies)
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from trackora import __version__
from trackora.core.paths import CACHE_DIR

logger = logging.getLogger(__name__)

_GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"
_CONNECTION_TIMEOUT = 5
_CACHE_FILENAME = "latest_release.json"
_ETAG_FILENAME = "latest_release_etag.txt"


# ──────────────────────────────────────────────
# DTOs
# ──────────────────────────────────────────────


@dataclass
class GitHubRelease:
    """A release from the GitHub API."""

    tag_name: str
    name: str
    body: str
    published_at: str
    html_url: str
    prerelease: bool = False
    download_url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", self.tag_name.lstrip("v"))


@dataclass
class UpdateCheckResult:
    """Result of an update check."""

    update_available: bool
    current_version: str
    latest_version: str | None
    release: GitHubRelease | None
    checked_at: str
    error: str | None = None
    source: str = "remote"
    previously_checked: bool = False


class UpdateCheckError(Exception):
    """Raised when the update check fails."""


class UpdateCenterService:
    """
    Checks for Trackora updates via the GitHub Releases API.

    Args:
        settings_repo: SettingsRepository for persisting check state.
        repo: GitHub repository in "owner/name" format.
              Defaults to "anomalyco/trackora".
        cache_dir: Directory for cache files. Defaults to CACHE_DIR.
    """

    def __init__(
        self,
        settings_repo: object | None = None,
        repo: str = "anomalyco/trackora",
        cache_dir: Path | None = None,
    ) -> None:
        self._settings_repo = settings_repo
        self._repo = repo
        self._cache_dir = cache_dir or CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self._cache_dir / _CACHE_FILENAME
        self._etag_path = self._cache_dir / _ETAG_FILENAME
        self._last_result: UpdateCheckResult | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_for_updates(self, force: bool = False) -> UpdateCheckResult:
        """
        Check GitHub for a newer version of Trackora.

        If force is True, bypasses the rate-limiting cooldown check.
        Otherwise, returns cached result if checked within the last hour.
        """
        if not force and self._is_rate_limited():
            cached = self._get_cached_or_error()
            if cached:
                cached.previously_checked = True
            return cached or self._error_result("Update check already performed recently. Please try again later.")

        return self._fetch_and_cache()

    def is_update_available(self) -> bool:
        """Return True if a newer, non-ignored version was found."""
        if self._last_result is None or not self._last_result.release:
            return False
        if self._settings_repo is None:
            return False
        ignored = self._settings_repo.get_value("update_ignored_version")
        if not ignored:
            return self._last_result.update_available
        return (
            self._last_result.update_available
            and self._last_result.latest_version != ignored
        )

    def get_cached_result(self) -> UpdateCheckResult | None:
        """Return the last check result, or None if not yet checked."""
        return self._last_result

    def ignore_version(self, version: str) -> None:
        """Persist an ignored version so it won't trigger notifications."""
        if self._settings_repo is not None:
            self._settings_repo.set("update_ignored_version", version)

    def clear_ignored_version(self) -> None:
        """Remove the ignored-version setting."""
        if self._settings_repo is not None:
            self._settings_repo.set("update_ignored_version", "")

    def clear_cache(self) -> None:
        """Remove cache and ETag files."""
        for path in [self._cache_path, self._etag_path]:
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Internal: fetch + cache
    # ------------------------------------------------------------------

    def _fetch_and_cache(self) -> UpdateCheckResult:
        """Fetch latest release from GitHub, cache, and return result."""
        now = datetime.now(UTC).replace(tzinfo=None)
        checked_at = now.isoformat()

        try:
            release = self._fetch_latest_release()
        except UpdateCheckError as e:
            self._update_last_checked(checked_at)
            cached = self._load_cache()
            if cached:
                return UpdateCheckResult(
                    update_available=self._is_newer_version(cached.version),
                    current_version=__version__,
                    latest_version=cached.version,
                    release=cached,
                    checked_at=checked_at,
                    source="cache",
                )
            return UpdateCheckResult(
                update_available=False,
                current_version=__version__,
                latest_version=None,
                release=None,
                checked_at=checked_at,
                error=str(e),
                source="error",
            )

        ignored = (
            self._settings_repo.get_value("update_ignored_version")
            if self._settings_repo else ""
        )
        is_newer = self._is_newer_version(release.version)
        is_ignored = bool(release.version == ignored or release.prerelease)
        update_available = is_newer and not is_ignored

        self._save_cache(release, checked_at)
        self._update_last_checked(checked_at)

        self._last_result = UpdateCheckResult(
            update_available=update_available,
            current_version=__version__,
            latest_version=release.version,
            release=release,
            checked_at=checked_at,
            source="remote",
        )
        return self._last_result

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    def _is_rate_limited(self) -> bool:
        if self._settings_repo is None:
            return False
        last = self._settings_repo.get_value("update_last_checked")
        if not last:
            return False
        try:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is not None:
                last_dt = last_dt.replace(tzinfo=None)
            now = datetime.now(UTC).replace(tzinfo=None)
            return (now - last_dt).total_seconds() < 3600
        except (ValueError, TypeError):
            return False

    def _update_last_checked(self, checked_at: str) -> None:
        if self._settings_repo is not None:
            self._settings_repo.set("update_last_checked", checked_at)

    def _get_cached_or_error(self) -> UpdateCheckResult | None:
        """Return in-memory last_result if available."""
        if self._last_result is not None:
            return self._last_result
        cached = self._load_cache()
        if cached:
            return UpdateCheckResult(
                update_available=self._is_newer_version(cached.version),
                current_version=__version__,
                latest_version=cached.version,
                release=cached,
                checked_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
                source="cache",
            )
        return None

    # ------------------------------------------------------------------
    # Internal: filesystem cache
    # ------------------------------------------------------------------

    def _save_cache(self, release: GitHubRelease, checked_at: str) -> None:
        """Write release info to cache file (atomic write)."""
        data = {
            "tag_name": release.tag_name,
            "version": release.version,
            "name": release.name,
            "body": release.body,
            "published_at": release.published_at,
            "html_url": release.html_url,
            "prerelease": release.prerelease,
            "download_url": release.download_url,
            "cached_at": checked_at,
        }
        tmp = self._cache_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(self._cache_path))
        except OSError as e:
            logger.warning("Cannot write update cache: %s", e)

    def _load_cache(self) -> GitHubRelease | None:
        """Read release info from cache file."""
        if not self._cache_path.is_file():
            return None
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return GitHubRelease(
                tag_name=data.get("tag_name", ""),
                name=data.get("name", ""),
                body=data.get("body", ""),
                published_at=data.get("published_at", ""),
                html_url=data.get("html_url", ""),
                prerelease=data.get("prerelease", False),
                download_url=data.get("download_url", ""),
            )
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning("Cannot read update cache: %s", e)
            return None

    @staticmethod
    def _error_result(msg: str) -> UpdateCheckResult:
        return UpdateCheckResult(
            update_available=False,
            current_version=__version__,
            latest_version=None,
            release=None,
            checked_at=datetime.now(UTC).replace(tzinfo=None).isoformat(),
            error=msg,
            source="error",
        )

    # ------------------------------------------------------------------
    # Internal: API fetch
    # ------------------------------------------------------------------

    def _fetch_latest_release(self) -> GitHubRelease:
        """Query the GitHub Releases API and parse the response."""
        url = _GITHUB_API_URL.format(repo=self._repo)
        headers = {"Accept": "application/json", "User-Agent": "Trackora"}

        etag = self._load_etag()
        if etag:
            headers["If-None-Match"] = etag

        req = Request(url, headers=headers)

        context = ssl.create_default_context()
        try:
            with urlopen(req, timeout=_CONNECTION_TIMEOUT, context=context) as response:
                raw = response.read().decode("utf-8")
                response_etag = response.headers.get("ETag")
                if response_etag:
                    self._save_etag(response_etag)
        except URLError as e:
            raise UpdateCheckError(f"Network error: {e}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise UpdateCheckError(f"Invalid JSON: {e}") from e

        tag = data.get("tag_name", "")
        body = data.get("body", "")
        html_url = data.get("html_url", "")
        published_at = data.get("published_at", "")
        prerelease = data.get("prerelease", False)
        download_url = self._resolve_download_url(data.get("assets", []))

        return GitHubRelease(
            tag_name=tag,
            name=data.get("name", ""),
            body=body,
            published_at=published_at,
            html_url=html_url,
            prerelease=prerelease,
            download_url=download_url,
        )

    @staticmethod
    def _resolve_download_url(assets: list[dict]) -> str:
        """Find the best download asset: prefer installer .exe."""
        download_url = ""
        for asset in assets:
            name = asset.get("name", "")
            if "Setup" in name or "Installer" in name:
                download_url = asset.get("browser_download_url", "")
                break
        if not download_url:
            for asset in assets:
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset.get("browser_download_url", "")
                    break
        return download_url

    # ------------------------------------------------------------------
    # Internal: ETag caching
    # ------------------------------------------------------------------

    def _load_etag(self) -> str | None:
        """Load saved ETag from cache file."""
        if self._etag_path.is_file():
            etag = self._etag_path.read_text(encoding="utf-8").strip()
            return etag if etag else None
        return None

    def _save_etag(self, etag: str) -> None:
        """Save ETag to cache file."""
        self._etag_path.write_text(etag, encoding="utf-8")

    @staticmethod
    def _is_newer_version(latest: str) -> bool:
        """Compare versions using strict semver tuple comparison."""
        try:
            current = tuple(int(x) for x in __version__.split("."))
            latest_tuple = tuple(int(x) for x in latest.split("."))
            if len(current) != len(latest_tuple):
                logger.warning(
                    "Version segment count mismatch: %s vs %s",
                    __version__, latest,
                )
                return False
            return latest_tuple > current
        except (ValueError, TypeError):
            logger.warning(
                "Could not compare versions: %s vs %s", __version__, latest
            )
            return False
