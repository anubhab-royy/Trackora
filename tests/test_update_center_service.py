"""Tests for UpdateCenterService — models, DTOs, and version comparison."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from unittest.mock import MagicMock, patch
from urllib.error import URLError

from services.update_center_service import (
    GitHubRelease,
    UpdateCheckError,
    UpdateCenterService,
    UpdateCheckResult,
)

# ──────────────────────────────────────────────
# Step 1 — Version Models & DTOs
# ──────────────────────────────────────────────


class TestGitHubRelease:
    def test_fields(self) -> None:
        r = GitHubRelease(
            tag_name="v2.0.0",
            name="Trackora 2.0.0",
            body="Release notes here",
            published_at="2026-06-20T12:00:00Z",
            html_url="https://github.com/anomalyco/trackora/releases/tag/v2.0.0",
            prerelease=False,
            download_url="https://github.com/anomalyco/trackora/releases/download/v2.0.0/Trackora-Setup-2.0.0.exe",
        )
        assert r.tag_name == "v2.0.0"
        assert r.name == "Trackora 2.0.0"
        assert r.body == "Release notes here"
        assert r.published_at == "2026-06-20T12:00:00Z"
        assert r.html_url == "https://github.com/anomalyco/trackora/releases/tag/v2.0.0"
        assert not r.prerelease
        assert r.download_url == "https://github.com/anomalyco/trackora/releases/download/v2.0.0/Trackora-Setup-2.0.0.exe"

    def test_version_strips_leading_v(self) -> None:
        r = GitHubRelease(
            tag_name="v2.0.0",
            name="", body="",
            published_at="", html_url="",
        )
        assert r.version == "2.0.0"

    def test_version_no_leading_v(self) -> None:
        r = GitHubRelease(
            tag_name="2.0.0",
            name="", body="",
            published_at="", html_url="",
        )
        assert r.version == "2.0.0"

    def test_default_download_url_is_empty(self) -> None:
        r = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        assert r.download_url == ""

    def test_default_prerelease_is_false(self) -> None:
        r = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        assert not r.prerelease


class TestUpdateCheckResult:
    def test_fields(self) -> None:
        r = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=r,
            checked_at="2026-06-20T12:00:00",
            source="remote",
        )
        assert result.update_available
        assert result.current_version == "1.1.0"
        assert result.latest_version == "2.0.0"
        assert result.release is r
        assert result.checked_at == "2026-06-20T12:00:00"
        assert result.source == "remote"
        assert result.error is None
        assert not result.previously_checked

    def test_error_state_no_release(self) -> None:
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version=None,
            release=None,
            checked_at="2026-06-20T12:00:00",
            error="Network error",
            source="error",
        )
        assert not result.update_available
        assert result.latest_version is None
        assert result.release is None
        assert result.error == "Network error"
        assert result.source == "error"

    def test_cache_source(self) -> None:
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version="1.1.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
            source="cache",
        )
        assert result.source == "cache"

    def test_remote_source(self) -> None:
        result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
            source="remote",
        )
        assert result.source == "remote"

    def test_previously_checked_flag(self) -> None:
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version="1.1.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
            source="cache",
            previously_checked=True,
        )
        assert result.previously_checked

    def test_error_default_none(self) -> None:
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version="1.1.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
        )
        assert result.error is None

    def test_checked_at_iso_format(self) -> None:
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        result = UpdateCheckResult(
            update_available=False,
            current_version="1.1.0",
            latest_version="1.1.0",
            release=None,
            checked_at=now,
        )
        assert result.checked_at == now


# ──────────────────────────────────────────────
# Step 2 — Version Comparison
# ──────────────────────────────────────────────


class TestVersionComparison:
    def test_major_bump_is_newer(self) -> None:
        assert UpdateCenterService._is_newer_version("3.0.0")

    def test_minor_bump_is_newer(self) -> None:
        assert UpdateCenterService._is_newer_version("2.1.0")

    def test_patch_bump_is_newer(self) -> None:
        assert UpdateCenterService._is_newer_version("2.0.1")

    def test_same_version_not_newer(self) -> None:
        assert not UpdateCenterService._is_newer_version("2.0.0")

    def test_older_version_not_newer(self) -> None:
        assert not UpdateCenterService._is_newer_version("1.0.0")

    def test_invalid_segment_count_not_newer(self) -> None:
        assert not UpdateCenterService._is_newer_version("1.1.0.0")

    def test_nonsense_string_not_newer(self) -> None:
        assert not UpdateCenterService._is_newer_version("not_a_version")

    def test_empty_string_not_newer(self) -> None:
        assert not UpdateCenterService._is_newer_version("")


# ──────────────────────────────────────────────
# Step 3 — GitHub API Fetch
# ──────────────────────────────────────────────


_SAMPLE_RELEASE_JSON = {
    "tag_name": "v3.0.0",
    "name": "Trackora 3.0.0",
    "body": "## What's New\n- Major update",
    "published_at": "2026-07-01T12:00:00Z",
    "html_url": "https://github.com/anomalyco/trackora/releases/tag/v3.0.0",
    "prerelease": False,
    "assets": [
        {
            "name": "Trackora-Setup-3.0.0.exe",
            "browser_download_url": (
                "https://github.com/anomalyco/trackora/releases/download/"
                "v3.0.0/Trackora-Setup-3.0.0.exe"
            ),
        },
        {
            "name": "Trackora-Portable-3.0.0.zip",
            "browser_download_url": (
                "https://github.com/anomalyco/trackora/releases/download/"
                "v3.0.0/Trackora-Portable-3.0.0.zip"
            ),
        },
    ],
}


class TestAPIFetch:
    def _make_service(self) -> UpdateCenterService:
        return UpdateCenterService()

    @patch("services.update_center_service.urlopen")
    def test_fetch_parses_release(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service()
        release = service._fetch_latest_release()

        assert release.tag_name == "v3.0.0"
        assert release.version == "3.0.0"
        assert release.name == "Trackora 3.0.0"
        assert "Major update" in release.body
        assert release.html_url.startswith("https://github.com")

    @patch("services.update_center_service.urlopen")
    def test_fetch_picks_installer_asset(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service()
        release = service._fetch_latest_release()

        assert "Setup" in release.download_url
        assert release.download_url.endswith(".exe")

    @patch("services.update_center_service.urlopen")
    def test_fetch_no_installer_falls_back_to_exe(
        self, mock_urlopen: MagicMock
    ) -> None:
        data = dict(_SAMPLE_RELEASE_JSON)
        data["assets"] = [
            {
                "name": "Trackora-x64-2.0.0.exe",
                "browser_download_url": (
                    "https://example.com/Trackora-x64-2.0.0.exe"
                ),
            },
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(data).encode("utf-8")
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service()
        release = service._fetch_latest_release()

        assert release.download_url.endswith(".exe")

    @patch("services.update_center_service.urlopen")
    def test_fetch_no_assets_empty_download_url(
        self, mock_urlopen: MagicMock
    ) -> None:
        data = dict(_SAMPLE_RELEASE_JSON)
        data["assets"] = []
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(data).encode("utf-8")
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service()
        release = service._fetch_latest_release()

        assert release.download_url == ""

    @patch("services.update_center_service.urlopen")
    def test_fetch_network_error_raises(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = URLError("Connection refused")

        service = self._make_service()
        with pytest.raises(UpdateCheckError, match="Network error"):
            service._fetch_latest_release()

    @patch("services.update_center_service.urlopen")
    def test_fetch_invalid_json_raises(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service()
        with pytest.raises(UpdateCheckError, match="Invalid JSON"):
            service._fetch_latest_release()

    @patch("services.update_center_service.urlopen")
    def test_fetch_prerelease_flag_parsed(self, mock_urlopen: MagicMock) -> None:
        data = dict(_SAMPLE_RELEASE_JSON)
        data["prerelease"] = True
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(data).encode("utf-8")
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service()
        release = service._fetch_latest_release()

        assert release.prerelease


# ──────────────────────────────────────────────
# Step 4 — ETag/If-None-Match Caching
# ──────────────────────────────────────────────


class TestETagCache:
    def _make_service(self, tmp_path: Path) -> UpdateCenterService:
        return UpdateCenterService(cache_dir=tmp_path)

    @patch("services.update_center_service.urlopen")
    def test_first_fetch_no_etag_sent(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock_response.headers = {"ETag": '"abc123"'}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service(tmp_path)
        service._fetch_latest_release()

        # Verify no If-None-Match in request headers
        call_req = mock_urlopen.call_args[0][0]
        assert not call_req.has_header("If-None-Match")

    def test_etag_file_persistence(self, tmp_path: Path) -> None:
        """Verify ETag file can be written and read."""
        service = self._make_service(tmp_path)
        service._save_etag('"abc123"')
        assert (tmp_path / "latest_release_etag.txt").is_file()
        etag = service._load_etag()
        assert etag == '"abc123"'

    @patch("services.update_center_service.urlopen")
    def test_second_fetch_sends_etag(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        service = self._make_service(tmp_path)
        # Manually save ETag to simulate a previous fetch
        service._save_etag('"abc123"')

        mock2 = MagicMock()
        mock2.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock2.headers = {"ETag": '"abc123"'}

        with patch("services.update_center_service.urlopen") as fresh_mock:
            fresh_mock.return_value.__enter__.return_value = mock2
            service._fetch_latest_release()
            call_req = fresh_mock.call_args[0][0]

        headers = dict(call_req.headers)
        assert "If-none-match" in headers, f"Headers: {headers}"
        assert headers["If-none-match"] == '"abc123"'

    @patch("services.update_center_service.urlopen")
    def test_no_etag_file_sends_without_header(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service(tmp_path)
        service._fetch_latest_release()

        call_req = mock_urlopen.call_args[0][0]
        assert "If-None-Match" not in call_req.headers

    @patch("services.update_center_service.urlopen")
    def test_corrupt_etag_file_ignored(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "latest_release_etag.txt").write_text("", encoding="utf-8")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock_response.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_response

        service = self._make_service(tmp_path)
        service._fetch_latest_release()

        call_req = mock_urlopen.call_args[0][0]
        assert "If-none-match" not in dict(call_req.headers)


# ──────────────────────────────────────────────
# Step 5 — SettingsRepository Integration
# ──────────────────────────────────────────────


class TestSettingsIntegration:
    def _make_service(
        self, settings_repo, tmp_path: Path
    ) -> UpdateCenterService:
        return UpdateCenterService(
            settings_repo=settings_repo, cache_dir=tmp_path,
        )

    def _make_repo(self) -> "SettingsRepository":
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
        from database.repositories.settings_repository import SettingsRepository
        return SettingsRepository(conn)

    def test_check_updates_updates_last_checked(self, tmp_path: Path) -> None:
        """After a successful check, update_last_checked is set."""
        repo = self._make_repo()
        service = self._make_service(repo, tmp_path)

        with patch("services.update_center_service.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
            mock_resp.headers = {"ETag": '"e1"'}
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            service._fetch_and_cache()

        last_checked = repo.get_value("update_last_checked")
        assert last_checked != ""

    def test_rate_limit_skips_api_call(self, tmp_path: Path) -> None:
        """If last_checked < 1h ago, return cached result without API."""
        from datetime import UTC, datetime
        now = datetime.now(UTC).replace(tzinfo=None).isoformat()
        repo = self._make_repo()
        repo.set("update_last_checked", now)

        service = self._make_service(repo, tmp_path)
        service._last_result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=GitHubRelease(
                tag_name="v2.0.0", name="", body="",
                published_at="", html_url="",
            ),
            checked_at="2026-06-20T12:00:00",
        )

        with patch("services.update_center_service.urlopen") as mock_urlopen:
            result = service.check_for_updates()

        mock_urlopen.assert_not_called()
        assert result.previously_checked

    def test_ignore_version_persists(self, tmp_path: Path) -> None:
        repo = self._make_repo()

        service = self._make_service(repo, tmp_path)
        service.ignore_version("2.0.0")

        assert repo.get_value("update_ignored_version") == "2.0.0"

    def test_clear_ignored_version(self, tmp_path: Path) -> None:
        repo = self._make_repo()
        repo.set("update_ignored_version", "2.0.0")

        service = self._make_service(repo, tmp_path)
        service.clear_ignored_version()

        assert repo.get_value("update_ignored_version") == ""

    def test_is_update_available_ignored_version(self, tmp_path: Path) -> None:
        repo = self._make_repo()
        repo.set("update_ignored_version", "2.0.0")

        service = self._make_service(repo, tmp_path)
        release = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        service._last_result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=release,
            checked_at="2026-06-20T12:00:00",
        )

        assert not service.is_update_available()

    def test_is_update_available_newer_not_ignored(self, tmp_path: Path) -> None:
        repo = self._make_repo()

        service = self._make_service(repo, tmp_path)
        release = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        service._last_result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=release,
            checked_at="2026-06-20T12:00:00",
        )

        assert service.is_update_available()

    def test_get_cached_result_returns_last(self, tmp_path: Path) -> None:
        repo = self._make_repo()

        service = self._make_service(repo, tmp_path)
        expected = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
        )
        service._last_result = expected

        assert service.get_cached_result() is expected


# ──────────────────────────────────────────────
# Step 6 — Local Cache File Persistence
# ──────────────────────────────────────────────


class TestCachePersistence:
    def _make_service(self, tmp_path: Path) -> UpdateCenterService:
        return UpdateCenterService(cache_dir=tmp_path)

    def test_cache_file_written_after_fetch(self, tmp_path: Path) -> None:
        service = self._make_service(tmp_path)
        release = GitHubRelease(
            tag_name="v2.0.0", name="Trackora 2.0.0",
            body="Release notes", published_at="2026-06-20T12:00:00Z",
            html_url="https://github.com/anomalyco/trackora/releases/tag/v2.0.0",
            prerelease=False, download_url="https://example.com/setup.exe",
        )
        service._save_cache(release, "2026-06-20T12:00:00")

        cache_file = tmp_path / "latest_release.json"
        assert cache_file.is_file()
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert data["version"] == "2.0.0"
        assert data["tag_name"] == "v2.0.0"
        assert "Release notes" in data["body"]

    def test_load_cache_returns_release(self, tmp_path: Path) -> None:
        service = self._make_service(tmp_path)
        release = GitHubRelease(
            tag_name="v2.0.0", name="", body="Hello",
            published_at="", html_url="",
        )
        service._save_cache(release, "2026-06-20T12:00:00")

        loaded = service._load_cache()
        assert loaded is not None
        assert loaded.version == "2.0.0"
        assert loaded.body == "Hello"

    @patch("services.update_center_service.urlopen")
    def test_fail_fetch_with_cache_fallback(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        """When remote fails but cache exists, return cached result."""
        service = self._make_service(tmp_path)
        # Pre-populate cache
        release = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        service._save_cache(release, "2026-06-20T12:00:00")

        mock_urlopen.side_effect = URLError("Connection refused")

        result = service._fetch_and_cache()
        assert result.source == "cache"
        assert result.latest_version == "2.0.0"

    @patch("services.update_center_service.urlopen")
    def test_fail_fetch_no_cache_error(
        self, mock_urlopen: MagicMock, tmp_path: Path
    ) -> None:
        """When remote fails and no cache, return error result."""
        service = self._make_service(tmp_path)
        mock_urlopen.side_effect = URLError("Connection refused")

        result = service._fetch_and_cache()
        assert result.source == "error"
        assert result.error is not None

    def test_clear_cache_removes_files(self, tmp_path: Path) -> None:
        service = self._make_service(tmp_path)
        release = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        service._save_cache(release, "2026-06-20T12:00:00")
        service._save_etag("abc")
        assert (tmp_path / "latest_release.json").is_file()
        assert (tmp_path / "latest_release_etag.txt").is_file()

        service.clear_cache()

        assert not (tmp_path / "latest_release.json").is_file()
        assert not (tmp_path / "latest_release_etag.txt").is_file()

    def test_get_cached_result_in_memory_preferred(self, tmp_path: Path) -> None:
        """In-memory cache is returned before file cache."""
        service = self._make_service(tmp_path)
        in_memory = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=None,
            checked_at="2026-06-20T12:00:00",
        )
        service._last_result = in_memory

        # Also populate file cache with different data
        release = GitHubRelease(
            tag_name="v1.0.0", name="", body="",
            published_at="", html_url="",
        )
        service._save_cache(release, "2026-06-19T12:00:00")

        cached = service.get_cached_result()
        assert cached is in_memory
        assert cached.latest_version == "2.0.0"

    def test_load_cache_missing_file(self, tmp_path: Path) -> None:
        service = self._make_service(tmp_path)
        assert service._load_cache() is None


# ──────────────────────────────────────────────
# Step 7 — check_for_updates() Orchestration
# ──────────────────────────────────────────────


class TestCheckForUpdates:
    @pytest.fixture
    def service_and_mock(self, tmp_path: Path):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
        )
        from database.repositories.settings_repository import SettingsRepository
        repo = SettingsRepository(conn)

        with patch("services.update_center_service.urlopen") as mock_urlopen:
            service = UpdateCenterService(
                settings_repo=repo, cache_dir=tmp_path,
            )
            yield service, mock_urlopen

    def test_happy_path_new_version(self, service_and_mock) -> None:
        """Remote → newer version → update_available=True, source='remote'."""
        service, mock_urlopen = service_and_mock
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock_resp.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = service.check_for_updates()

        assert result.update_available
        assert result.source == "remote"
        assert result.latest_version == "3.0.0"
        assert result.release is not None

    def test_happy_path_no_update(self, service_and_mock) -> None:
        """Remote → same version → update_available=False."""
        service, mock_urlopen = service_and_mock
        data = dict(_SAMPLE_RELEASE_JSON)
        data["tag_name"] = "v2.0.0"  # same as __version__
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode("utf-8")
        mock_resp.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = service.check_for_updates()

        assert not result.update_available
        assert result.source == "remote"
        assert result.latest_version == "2.0.0"

    def test_rate_limited_returns_cached(self, service_and_mock) -> None:
        """Checked recently → returns cached result, previously_checked=True."""
        service, mock_urlopen = service_and_mock
        repo = service._settings_repo
        repo.set("update_last_checked", datetime.now(UTC).replace(tzinfo=None).isoformat())

        service._last_result = UpdateCheckResult(
            update_available=True,
            current_version="1.1.0",
            latest_version="2.0.0",
            release=GitHubRelease(
                tag_name="v2.0.0", name="", body="",
                published_at="", html_url="",
            ),
            checked_at="2026-06-20T12:00:00",
        )

        result = service.check_for_updates()

        mock_urlopen.assert_not_called()
        assert result.previously_checked

    def test_offline_with_cache(self, service_and_mock) -> None:
        """Network error + valid cache → source='cache'."""
        service, mock_urlopen = service_and_mock
        release = GitHubRelease(
            tag_name="v2.0.0", name="", body="",
            published_at="", html_url="",
        )
        service._save_cache(release, "2026-06-20T12:00:00")

        mock_urlopen.side_effect = URLError("Connection refused")

        result = service.check_for_updates()

        assert result.source == "cache"
        assert result.latest_version == "2.0.0"

    def test_offline_no_cache(self, service_and_mock) -> None:
        """Network error + no cache → source='error'."""
        service, mock_urlopen = service_and_mock
        mock_urlopen.side_effect = URLError("Connection refused")

        result = service.check_for_updates()

        assert result.source == "error"
        assert result.error is not None

    def test_ignored_version_not_available(self, service_and_mock) -> None:
        """Ignored version -> update_available=False."""
        service, mock_urlopen = service_and_mock
        repo = service._settings_repo
        repo.set("update_ignored_version", "3.0.0")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(_SAMPLE_RELEASE_JSON).encode("utf-8")
        mock_resp.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = service.check_for_updates()

        assert not result.update_available

    def test_prerelease_not_available(self, service_and_mock) -> None:
        """Prerelease detected → update_available=False."""
        service, mock_urlopen = service_and_mock
        data = dict(_SAMPLE_RELEASE_JSON)
        data["prerelease"] = True

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode("utf-8")
        mock_resp.headers = {}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = service.check_for_updates()

        assert not result.update_available

