"""Tests for UpdateAnnouncementsService."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.update_announcements_service import (
    AnnouncementsResult,
    FeatureAnnouncement,
    UpdateAnnouncementsService,
)

_VALID_REMOTE_DATA = {
    "current_version": "1.0.0",
    "upcoming_version": "1.1.0",
    "features": [
        {
            "title": "New Feature",
            "description": "A great new feature.",
            "version": "1.1.0",
            "is_published": False,
        },
        {
            "title": "Bug Fixes",
            "description": "Various bug fixes.",
            "version": "1.1.0",
            "is_published": True,
        },
    ],
}


def _service_with_cache(tmp_path: Path, data: dict | None = None) -> UpdateAnnouncementsService:
    svc = UpdateAnnouncementsService(
        remote_url="https://example.com/announcements.json",
        cache_dir=tmp_path,
    )
    if data is not None:
        svc._cache_path.write_text(json.dumps(data), encoding="utf-8")
    return svc


# ======================================================================
# FeatureAnnouncement dataclass
# ======================================================================


class TestFeatureAnnouncement:
    def test_default_is_published(self):
        fa = FeatureAnnouncement(title="A", description="B", version="1.0")
        assert fa.is_published is False

    def test_all_fields(self):
        fa = FeatureAnnouncement(
            title="Title", description="Desc", version="1.1",
            is_published=True,
        )
        assert fa.title == "Title"
        assert fa.description == "Desc"
        assert fa.version == "1.1"
        assert fa.is_published is True


# ======================================================================
# AnnouncementsResult dataclass
# ======================================================================


class TestAnnouncementsResult:
    def test_minimal(self):
        ar = AnnouncementsResult(
            current_version="1.0", upcoming_version="1.1", features=[],
        )
        assert ar.current_version == "1.0"
        assert ar.upcoming_version == "1.1"
        assert ar.features == []
        assert ar.source == "remote"

    def test_with_features(self):
        fa = FeatureAnnouncement(title="A", description="B", version="1.0")
        ar = AnnouncementsResult(
            current_version="1.0", upcoming_version="1.1",
            features=[fa], source="cache",
        )
        assert ar.source == "cache"
        assert len(ar.features) == 1
        assert ar.features[0].title == "A"


# ======================================================================
# Remote fetch
# ======================================================================


class TestFetchRemote:
    def test_successful_fetch(self, tmp_path):
        svc = _service_with_cache(tmp_path)
        response_data = json.dumps(_VALID_REMOTE_DATA).encode("utf-8")

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = response_data
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = svc.get_announcements()

        assert result.current_version == "1.0.0"
        assert result.upcoming_version == "1.1.0"
        assert len(result.features) == 2
        assert result.features[0].title == "New Feature"
        assert result.features[1].is_published is True
        assert result.source == "remote"

    def test_network_failure_falls_back_to_cache(self, tmp_path):
        svc = _service_with_cache(tmp_path, data=_VALID_REMOTE_DATA)

        from urllib.error import URLError

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("Connection refused")
            result = svc.get_announcements()

        assert result.current_version == "1.0.0"
        assert result.source == "cache"

    def test_network_failure_no_cache_returns_fallback(self, tmp_path):
        svc = _service_with_cache(tmp_path)  # no cache data

        from urllib.error import URLError

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("Connection refused")
            result = svc.get_announcements()

        assert result.source == "fallback"
        assert result.current_version == "—"
        assert len(result.features) >= 1

    def test_invalid_json_raises(self, tmp_path):
        svc = _service_with_cache(tmp_path)

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"not json"
            mock_urlopen.return_value.__enter__.return_value = mock_response

            with pytest.raises(json.JSONDecodeError):
                svc.refresh()

    def test_timeout(self, tmp_path):
        svc = _service_with_cache(tmp_path)

        from urllib.error import URLError

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("timed out")
            with pytest.raises(URLError):
                svc.refresh()


# ======================================================================
# Cache
# ======================================================================


class TestCache:
    def test_successful_fetch_updates_cache(self, tmp_path):
        svc = _service_with_cache(tmp_path)

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(
                _VALID_REMOTE_DATA
            ).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            svc.get_announcements()

        assert svc._cache_path.is_file()
        cached = json.loads(svc._cache_path.read_text(encoding="utf-8"))
        assert cached["current_version"] == "1.0.0"
        assert len(cached["features"]) == 2

    def test_get_cached_returns_none_when_missing(self, tmp_path):
        svc = _service_with_cache(tmp_path)
        assert svc.get_cached() is None

    def test_get_cached_returns_data(self, tmp_path):
        svc = _service_with_cache(tmp_path, data=_VALID_REMOTE_DATA)
        result = svc.get_cached()
        assert result is not None
        assert result.current_version == "1.0.0"
        assert result.source == "cache"

    def test_corrupted_cache_returns_none(self, tmp_path):
        svc = _service_with_cache(tmp_path)
        svc._cache_path.write_text("not json", encoding="utf-8")
        cached = svc.get_cached()
        assert cached is None

    def test_corrupted_cache_triggers_fallback(self, tmp_path):
        svc = _service_with_cache(tmp_path)
        svc._cache_path.write_text("not json", encoding="utf-8")

        from urllib.error import URLError

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("offline")
            result = svc.get_announcements()

        assert result.source == "fallback"

    def test_cache_is_atomic(self, tmp_path):
        svc = _service_with_cache(tmp_path)

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(
                _VALID_REMOTE_DATA
            ).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            svc.get_announcements()

        # No .tmp files left behind
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_clear_cache(self, tmp_path):
        svc = _service_with_cache(tmp_path, data=_VALID_REMOTE_DATA)
        assert svc._cache_path.is_file()
        svc.clear_cache()
        assert not svc._cache_path.is_file()

    def test_clear_cache_no_file_does_not_raise(self, tmp_path):
        svc = _service_with_cache(tmp_path)
        svc.clear_cache()  # should not raise


# ======================================================================
# Refresh (force remote)
# ======================================================================


class TestRefresh:
    def test_refresh_returns_remote_data(self, tmp_path):
        svc = _service_with_cache(tmp_path)

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(
                _VALID_REMOTE_DATA
            ).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = svc.refresh()

        assert result.current_version == "1.0.0"
        assert result.source == "remote"

    def test_refresh_propagates_network_error(self, tmp_path):
        svc = _service_with_cache(tmp_path)

        from urllib.error import URLError

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("timeout")
            with pytest.raises(URLError):
                svc.refresh()

    def test_refresh_updates_cache(self, tmp_path):
        svc = _service_with_cache(tmp_path)

        updated = dict(_VALID_REMOTE_DATA)
        updated["current_version"] = "1.1.0"

        with patch(
            "services.update_announcements_service.urlopen"
        ) as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(updated).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            svc.refresh()

        cached = json.loads(svc._cache_path.read_text(encoding="utf-8"))
        assert cached["current_version"] == "1.1.0"


# ======================================================================
# Parsing
# ======================================================================


class TestParsing:
    def test_missing_top_level_keys(self):
        with pytest.raises(ValueError, match="top-level keys"):
            UpdateAnnouncementsService._parse_json({})

    def test_missing_features_key(self):
        with pytest.raises(ValueError, match="top-level keys"):
            UpdateAnnouncementsService._parse_json(
                {"current_version": "1.0", "upcoming_version": "1.1"}
            )

    def test_features_not_a_list(self):
        with pytest.raises(ValueError, match="features.*list"):
            UpdateAnnouncementsService._parse_json({
                "current_version": "1.0",
                "upcoming_version": "1.1",
                "features": "not a list",
            })

    def test_feature_missing_keys(self):
        with pytest.raises(ValueError, match="features\\[0\\] missing"):
            UpdateAnnouncementsService._parse_json({
                "current_version": "1.0",
                "upcoming_version": "1.1",
                "features": [{"title": "Only title"}],
            })

    def test_feature_not_a_dict(self):
        with pytest.raises(ValueError, match="features\\[0\\] is not an object"):
            UpdateAnnouncementsService._parse_json({
                "current_version": "1.0",
                "upcoming_version": "1.1",
                "features": ["not a dict"],
            })

    def test_valid_parse(self):
        result = UpdateAnnouncementsService._parse_json({
            "current_version": "1.0",
            "upcoming_version": "1.1",
            "features": [
                {
                    "title": "Feat 1",
                    "description": "Desc 1",
                    "version": "1.1",
                    "is_published": True,
                },
            ],
        })
        assert result.current_version == "1.0"
        assert result.upcoming_version == "1.1"
        assert len(result.features) == 1
        assert result.features[0].title == "Feat 1"
        assert result.features[0].is_published is True


# ======================================================================
# Serialization roundtrip
# ======================================================================


class TestSerialization:
    def test_serialize_roundtrip(self):
        fa = FeatureAnnouncement(
            title="A", description="B", version="1.0", is_published=True
        )
        ar = AnnouncementsResult(
            current_version="1.0", upcoming_version="1.1",
            features=[fa], source="remote",
        )
        data = UpdateAnnouncementsService._serialize(ar)
        assert data["current_version"] == "1.0"
        assert data["upcoming_version"] == "1.1"
        assert len(data["features"]) == 1
        assert data["features"][0]["title"] == "A"

        restored = UpdateAnnouncementsService._parse_json(data)
        assert restored.current_version == "1.0"
        assert restored.features[0].is_published is True


# ======================================================================
# Default cache dir
# ======================================================================


class TestDefaultCacheDir:
    def test_returns_path_object(self):
        d = UpdateAnnouncementsService._default_cache_dir()
        assert isinstance(d, Path)
