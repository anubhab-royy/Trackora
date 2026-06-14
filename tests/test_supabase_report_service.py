"""Tests for SupabaseReportService."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.reporting_interface import ReportType, SubmitResult
from services.support.supabase_report_service import (
    SupabaseConfig,
    SupabaseReportService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> SupabaseReportService:
    return SupabaseReportService(
        supabase_url="https://testproject.supabase.co",
        anon_key="test-anon-key",
    )


# ---------------------------------------------------------------------------
# SupabaseConfig
# ---------------------------------------------------------------------------


class TestSupabaseConfig:
    def test_valid_config(self):
        cfg = SupabaseConfig(url="https://x.supabase.co", anon_key="key")
        assert cfg.is_valid is True

    def test_empty_url_invalid(self):
        cfg = SupabaseConfig(url="", anon_key="key")
        assert cfg.is_valid is False

    def test_empty_key_invalid(self):
        cfg = SupabaseConfig(url="https://x.supabase.co", anon_key="")
        assert cfg.is_valid is False

    def test_both_empty_invalid(self):
        cfg = SupabaseConfig(url="", anon_key="")
        assert cfg.is_valid is False

    def test_api_url_format(self):
        cfg = SupabaseConfig(url="https://x.supabase.co", anon_key="key")
        assert cfg.api_url == "https://x.supabase.co/rest/v1/reports"

    def test_api_url_strips_trailing_slash(self):
        cfg = SupabaseConfig(url="https://x.supabase.co/", anon_key="key")
        assert cfg.api_url == "https://x.supabase.co/rest/v1/reports"

    def test_api_url_adds_https_if_missing(self):
        cfg = SupabaseConfig(url="x.supabase.co", anon_key="key")
        assert cfg.api_url == "https://x.supabase.co/rest/v1/reports"


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


class TestResolveConfig:
    def test_constructor_args_take_priority(self):
        svc = SupabaseReportService(
            supabase_url="https://from-arg.supabase.co",
            anon_key="from-arg-key",
        )
        assert svc._config.url == "https://from-arg.supabase.co"
        assert svc._config.anon_key == "from-arg-key"

    def test_falls_back_to_env_vars(self):
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://from-env.supabase.co",
            "SUPABASE_ANON_KEY": "from-env-key",
        }, clear=True):
            svc = SupabaseReportService()
            assert svc._config.url == "https://from-env.supabase.co"
            assert svc._config.anon_key == "from-env-key"

    def test_falls_back_to_dotenv(self, tmp_path: Path):
        dotenv = tmp_path / ".env"
        dotenv.write_text(
            "SUPABASE_URL=https://from-dotenv.supabase.co\n"
            "SUPABASE_ANON_KEY=from-dotenv-key\n",
            encoding="utf-8",
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("services.support.supabase_report_service._discover_env_file", return_value=dotenv),
        ):
            svc = SupabaseReportService()
            assert svc._config.url == "https://from-dotenv.supabase.co"
            assert svc._config.anon_key == "from-dotenv-key"

    def test_empty_when_no_source(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("services.support.supabase_report_service._discover_env_file", return_value=None),
        ):
            svc = SupabaseReportService()
            assert svc._config.url == ""
            assert svc._config.anon_key == ""
            assert svc._config.is_valid is False


# ---------------------------------------------------------------------------
# _submit_report – HTTP interactions
# ---------------------------------------------------------------------------


class TestSubmitReportHTTP:
    """Exercises the single internal _submit_report gate."""

    @staticmethod
    def _mock_urlopen(success: bool = True, status: int = 201) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = status
        mock_urlopen = MagicMock()
        if success:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
        else:
            mock_urlopen.side_effect = Exception("unexpected")
        return mock_urlopen

    def test_invalid_config_returns_error(self):
        svc = SupabaseReportService(supabase_url="", anon_key="")
        result = svc._submit_report(
            report_type=ReportType.BUG,
            title="Test",
            description="Body",
            source="support_center",
            payload={},
        )
        assert result.success is False
        assert "not configured" in (result.error_message or "").lower()

    def test_successful_submission(self, service):
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = service._submit_report(
                report_type=ReportType.BUG,
                title="Test Bug",
                description="Bug body",
                source="support_center",
                payload={"key": "value"},
            )

        assert result.success is True
        assert result.error_message is None

    def test_sends_correct_headers(self, service):
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            service._submit_report(
                report_type=ReportType.BUG,
                title="Test",
                description="Body",
                source="support_center",
                payload={},
            )

            call_args = mock_urlopen.call_args[0][0]
            headers = call_args.headers
            assert headers["Apikey"] == "test-anon-key"
            assert headers["Authorization"] == "Bearer test-anon-key"
            assert headers["Content-type"] == "application/json"
            assert headers["Prefer"] == "return=minimal"

    def test_sends_correct_url(self, service):
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            service._submit_report(
                report_type=ReportType.BUG,
                title="Test",
                description="Body",
                source="support_center",
                payload={},
            )

            call_args = mock_urlopen.call_args[0][0]
            assert call_args.full_url == (
                "https://testproject.supabase.co/rest/v1/reports"
            )

    def test_sends_correct_json_body(self, service):
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            service._submit_report(
                report_type=ReportType.FEATURE,
                title="New Feature",
                description="Feature desc",
                source="support_center",
                payload={"priority": "high"},
            )

            call_args = mock_urlopen.call_args[0][0]
            body = json.loads(call_args.data)

        assert body["type"] == "feature-request"
        assert body["title"] == "New Feature"
        assert body["description"] == "Feature desc"
        assert body["source"] == "support_center"
        assert body["payload"] == {"priority": "high"}
        assert body["status"] == "new"
        assert isinstance(body["app_version"], str) and body["app_version"]
        assert isinstance(body["os"], str) and body["os"]

    def test_http_401_returns_auth_error(self, service):
        self._assert_http_error(service, 401, "authentication")

    def test_http_403_returns_auth_error(self, service):
        self._assert_http_error(service, 403, "authentication")

    def test_http_409_returns_conflict_error(self, service):
        self._assert_http_error(service, 409, "duplicate")

    def test_http_400_returns_client_error(self, service):
        self._assert_http_error(service, 400, "configuration")

    def test_http_500_returns_server_error(self, service):
        self._assert_http_error(service, 500, "later")

    @staticmethod
    def _assert_http_error(service: SupabaseReportService, status: int, keyword: str):
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            # Build a real HTTPError
            from urllib.error import HTTPError
            exc = HTTPError(
                url="https://test.supabase.co/rest/v1/reports",
                code=status,
                msg="Error",
                hdrs={},
                fp=MagicMock(),
            )
            exc.read.return_value = b"{}"
            mock_urlopen.side_effect = exc

            result = service._submit_report(
                report_type=ReportType.BUG,
                title="Test",
                description="Body",
                source="support_center",
                payload={},
            )

        assert result.success is False
        assert keyword.lower() in (result.error_message or "").lower()

    def test_urlerror_returns_network_error(self, service):
        from urllib.error import URLError

        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = URLError("connection refused")

            result = service._submit_report(
                report_type=ReportType.BUG,
                title="Test",
                description="Body",
                source="support_center",
                payload={},
            )

        assert result.success is False
        assert "network" in (result.error_message or "").lower()


# ---------------------------------------------------------------------------
# Typed convenience methods
# ---------------------------------------------------------------------------


class TestSubmitBug:
    def test_submit_bug_maps_correctly(self):
        report = BugReport(
            title="Test Bug",
            description="Bug description",
            steps_to_reproduce="1. Do this",
            expected_behavior="Should work",
            actual_behavior="Does not work",
            severity="high",
        )

        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )

        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_bug(report)

        assert result.success is True
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["type"] == "bug"
        assert call_body["title"] == "Test Bug"
        assert "Bug description" in call_body["description"]
        assert call_body["source"] == "support_center"
        assert call_body["payload"]["severity"] == "high"
        assert call_body["payload"]["steps_to_reproduce"] == "1. Do this"

    def test_submit_bug_empty_payload(self):
        report = BugReport(
            title="Minimal",
            description="",
            steps_to_reproduce="",
            expected_behavior="",
            actual_behavior="",
            severity="low",
        )
        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_bug(report)

        assert result.success is True


class TestSubmitFeature:
    def test_submit_feature_maps_correctly(self):
        request = FeatureRequest(
            title="New feature",
            description="Feature description",
            use_case="To improve workflow",
            priority="medium",
        )

        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )

        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_feature(request)

        assert result.success is True
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["type"] == "feature-request"
        assert call_body["title"] == "New feature"
        assert "Feature description" in call_body["description"]
        assert call_body["source"] == "support_center"
        assert call_body["payload"]["use_case"] == "To improve workflow"
        assert call_body["payload"]["priority"] == "medium"


class TestSubmitFeedback:
    def test_submit_feedback_maps_correctly(self):
        feedback = FeedbackReport(
            subject="Great app",
            message="I love this app!",
            category="praise",
            contact_ok=True,
        )

        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )

        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_feedback(feedback)

        assert result.success is True
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["type"] == "feedback"
        assert call_body["title"] == "Great app"
        assert "I love this app!" in call_body["description"]
        assert call_body["source"] == "support_center"
        assert call_body["payload"]["category"] == "praise"
        assert call_body["payload"]["contact_ok"] is True


class TestSubmitReport:
    def test_crash_uses_crash_detector_source(self):
        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_report(
                ReportType.CRASH, "App crashed", "Stack trace..."
            )

        assert result.success is True
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["type"] == "crash"
        assert call_body["source"] == "crash_detector"

    def test_bug_uses_support_center_source(self):
        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )
        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_report(
                ReportType.BUG, "Bug title", "Bug body"
            )

        assert result.success is True
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["source"] == "support_center"

    def test_invalid_config_returns_error(self):
        svc = SupabaseReportService(supabase_url="", anon_key="")
        result = svc.submit_report(ReportType.BUG, "Title", "Body")
        assert result.success is False


# ---------------------------------------------------------------------------
# AbstractReportService contract compliance
# ---------------------------------------------------------------------------


class TestContractCompliance:
    def test_is_instance_of_abstract(self):
        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )
        from services.support.reporting_interface import AbstractReportService
        assert isinstance(svc, AbstractReportService)


# ---------------------------------------------------------------------------
# Integration: SupportService + SupabaseReportService
# ---------------------------------------------------------------------------


class TestSupportServiceIntegration:
    """SupabaseReportService wired through SupportService (DI chain)."""

    def test_submit_bug_via_support_service(self):
        """Bug submitted through SupportService reaches Supabase backend."""
        from services.support.support_service import SupportService

        supabase = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="test-key",
        )
        svc = SupportService(github_service=supabase)

        report = BugReport(
            title="Integration Bug",
            description="Bug description",
            steps_to_reproduce="1. Step one",
            expected_behavior="Should work",
            actual_behavior="Does not work",
        )

        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_bug_report(report)

        assert result.github_success is True
        assert result.local_stored is True

        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["type"] == "bug"
        assert call_body["title"] == "Integration Bug"
        assert call_body["source"] == "support_center"

    def test_submit_feature_via_support_service(self):
        """Feature request through SupportService reaches Supabase."""
        from services.support.support_service import SupportService

        supabase = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="test-key",
        )
        svc = SupportService(github_service=supabase)

        request = FeatureRequest(
            title="Integration Feature",
            description="Feature desc",
            use_case="To improve workflow",
        )

        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_feature_request(request)

        assert result.github_success is True
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["type"] == "feature-request"
        assert call_body["title"] == "Integration Feature"

    def test_submit_feedback_via_support_service(self):
        """Feedback through SupportService reaches Supabase."""
        from services.support.support_service import SupportService

        supabase = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="test-key",
        )
        svc = SupportService(github_service=supabase)

        feedback = FeedbackReport(
            subject="Integration Feedback",
            message="Great app!",
            category="praise",
        )

        with patch(
            "services.support.supabase_report_service.urlopen"
        ) as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 201
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = svc.submit_feedback(feedback)

        assert result.github_success is True
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert call_body["type"] == "feedback"

    def test_unconfigured_does_not_crash_support_service(self):
        """Missing Supabase config does not break SupportService creation."""
        from services.support.support_service import SupportService

        supabase = SupabaseReportService(
            supabase_url="",
            anon_key="",
        )
        assert supabase.is_configured is False

        svc = SupportService(github_service=supabase)
        assert svc is not None

        report = BugReport(
            title="Offline Bug",
            description="desc",
            steps_to_reproduce="s",
            expected_behavior="e",
            actual_behavior="a",
        )
        result = svc.submit_bug_report(report)
        assert result.github_success is False
        assert result.local_stored is True


# ---------------------------------------------------------------------------
# is_configured property
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_configured_returns_true(self):
        svc = SupabaseReportService(
            supabase_url="https://test.supabase.co",
            anon_key="key",
        )
        assert svc.is_configured is True

    def test_unconfigured_returns_false(self):
        svc = SupabaseReportService(supabase_url="", anon_key="")
        assert svc.is_configured is False

    def test_reads_from_env(self):
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://env-test.supabase.co",
            "SUPABASE_ANON_KEY": "env-key",
        }, clear=True):
            svc = SupabaseReportService()
            assert svc.is_configured is True
