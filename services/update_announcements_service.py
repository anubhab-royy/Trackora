"""
UpdateAnnouncementsService — fetches, caches, and serves upcoming-version
announcements from a remote JSON source (GitHub raw file).

Provides offline support via local cache and graceful fallback
when the remote is unreachable or the data is corrupted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from trackora.core.paths import BASE_DIR

logger = logging.getLogger(__name__)

_REMOTE_TIMEOUT_SECONDS = 10
_CACHE_FILENAME = "update_announcements_cache.json"

# ---- DTOs ------------------------------------------------------------------


@dataclass
class FeatureAnnouncement:
    """A single feature in an upcoming release."""

    title: str
    description: str
    version: str
    is_published: bool = False


@dataclass
class AnnouncementsResult:
    """Complete result of an update announcements fetch.

    Attributes:
        current_version:  The currently released version (e.g. "1.1.0").
        upcoming_version: The next planned version (e.g. "1.2.0").
        features:         List of announced features.
        source:           Where the data came from:
                          "remote", "cache", or "fallback".
    """
    current_version: str
    upcoming_version: str
    features: list[FeatureAnnouncement]
    source: str = "remote"


# Default fallback shown when no remote or cache is available.
_FALLBACK_RESULT = AnnouncementsResult(
    current_version="—",
    upcoming_version="—",
    features=[
        FeatureAnnouncement(
            title="Stay Tuned",
            description="Update announcements will appear here "
                        "once the remote source is reachable.",
            version="—",
        ),
    ],
    source="fallback",
)

# ---- Expected JSON keys ---------------------------------------------------

_REQUIRED_TOP_KEYS = {"current_version", "upcoming_version", "features"}
_REQUIRED_FEATURE_KEYS = {"title", "description", "version"}

# ---- Service ---------------------------------------------------------------


class UpdateAnnouncementsService:
    """Fetches update announcements from a remote JSON endpoint.

    Caches the last successful response so the UI always has
    something to display, even offline.

    Args:
        remote_url: URL of the remote JSON file.
        cache_dir:  Directory for the local cache file.
                    Defaults to %APPDATA%/Trackora/.
    """

    def __init__(
        self,
        remote_url: str,
        cache_dir: Path | None = None,
    ) -> None:
        self._remote_url = remote_url
        self._cache_dir = cache_dir or self._default_cache_dir()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self._cache_dir / _CACHE_FILENAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_announcements(self) -> AnnouncementsResult:
        """Return announcements, trying remote -> cache -> fallback.

        The remote fetch is attempted first.  On success the result
        is cached and returned.  On failure the cached version is
        served.  If there is no cache either, a static fallback is
        returned so the UI is never empty.
        """
        try:
            result = self._fetch_remote()
            self._save_cache(result)
            return result
        except Exception as exc:
            logger.warning("Remote fetch failed: %s", exc)
            cached = self._load_cache()
            if cached is not None:
                logger.info("Serving announcements from cache.")
                return cached
            logger.info("No cached announcements; using fallback.")
            return _FALLBACK_RESULT

    def refresh(self) -> AnnouncementsResult:
        """Force a remote fetch, ignoring cache.

        Returns the remote result on success.  On failure the
        exception propagates (caller should handle it).
        """
        result = self._fetch_remote()
        self._save_cache(result)
        logger.info("Announcements refreshed from remote.")
        return result

    def get_cached(self) -> AnnouncementsResult | None:
        """Return the cached announcements without hitting the network.

        Returns None if the cache is missing or corrupt.
        """
        return self._load_cache()

    def clear_cache(self) -> None:
        """Delete the local cache file."""
        try:
            if self._cache_path.is_file():
                self._cache_path.unlink()
                logger.debug("Announcements cache cleared.")
        except OSError as exc:
            logger.warning("Cannot clear announcements cache: %s", exc)

    # ------------------------------------------------------------------
    # Remote fetch
    # ------------------------------------------------------------------

    def _fetch_remote(self) -> AnnouncementsResult:
        req = Request(
            self._remote_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Trackora/1.1",
            },
        )
        try:
            with urlopen(req, timeout=_REMOTE_TIMEOUT_SECONDS) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except URLError as exc:
            logger.error("Network error fetching announcements: %s", exc)
            raise
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON from announcements URL: %s", exc)
            raise

        return self._parse_json(raw)

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _save_cache(self, result: AnnouncementsResult) -> None:
        payload = self._serialize(result)
        tmp = self._cache_path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            import os
            os.replace(str(tmp), str(self._cache_path))
            logger.debug("Announcements cache updated.")
        except OSError as exc:
            logger.warning("Cannot write announcements cache: %s", exc)

    def _load_cache(self) -> AnnouncementsResult | None:
        if not self._cache_path.is_file():
            return None
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            result = self._parse_json(raw)
            result.source = "cache"
            return result
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning("Corrupted announcements cache: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Parsing / serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(data: dict[str, Any]) -> AnnouncementsResult:
        missing = _REQUIRED_TOP_KEYS - set(data.keys())
        if missing:
            raise ValueError(
                f"Missing required top-level keys: {missing}"
            )

        raw_features: list[dict[str, Any]] = data["features"]
        if not isinstance(raw_features, list):
            raise ValueError("'features' must be a list.")

        features: list[FeatureAnnouncement] = []
        for i, f in enumerate(raw_features):
            if not isinstance(f, dict):
                raise ValueError(f"features[{i}] is not an object.")
            f_missing = _REQUIRED_FEATURE_KEYS - set(f.keys())
            if f_missing:
                raise ValueError(
                    f"features[{i}] missing keys: {f_missing}"
                )
            features.append(
                FeatureAnnouncement(
                    title=str(f["title"]),
                    description=str(f["description"]),
                    version=str(f["version"]),
                    is_published=bool(f.get("is_published", False)),
                )
            )

        return AnnouncementsResult(
            current_version=str(data["current_version"]),
            upcoming_version=str(data["upcoming_version"]),
            features=features,
            source="remote",
        )

    @staticmethod
    def _serialize(result: AnnouncementsResult) -> dict[str, Any]:
        return {
            "current_version": result.current_version,
            "upcoming_version": result.upcoming_version,
            "features": [
                {
                    "title": f.title,
                    "description": f.description,
                    "version": f.version,
                    "is_published": f.is_published,
                }
                for f in result.features
            ],
        }

    # ------------------------------------------------------------------
    # Default paths
    # ------------------------------------------------------------------

    @staticmethod
    def _default_cache_dir() -> Path:
        return BASE_DIR
