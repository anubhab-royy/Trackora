"""
SupabaseReportService — Supabase REST API backend for report submissions.

Submits bug reports, feature requests, feedback, and crash reports
to the Supabase ``reports`` table via the REST API.

Implements *AbstractReportService* from *reporting_interface*.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from models.support.bug_report import BugReport
from models.support.feature_request import FeatureRequest
from models.support.feedback_report import FeedbackReport
from services.support.reporting_interface import (
    AbstractReportService,
    ReportType,
    SubmitResult,
)
from trackora import __version__

logger = logging.getLogger(__name__)

_API_TIMEOUT_SECONDS = 15

_ENV_SUPABASE_URL = "SUPABASE_URL"
_ENV_SUPABASE_ANON_KEY = "SUPABASE_ANON_KEY"


# ---------------------------------------------------------------------------
# .env file loader (stdlib-only, no python-dotenv dependency)
# ---------------------------------------------------------------------------


def _discover_env_file() -> Path | None:
    """Look for a .env file relative to the project root or cwd."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_env_vars() -> dict[str, str]:
    """Read key=value pairs from .env file manually."""
    env_file = _discover_env_file()
    if env_file is None:
        return {}
    result: dict[str, str] = {}
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            result[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return result


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SupabaseConfig:
    url: str
    anon_key: str

    @property
    def is_valid(self) -> bool:
        return bool(self.url and self.anon_key)

    @property
    def api_url(self) -> str:
        base = self.url.rstrip("/")
        if not base.startswith("http"):
            base = f"https://{base}"
        return f"{base}/rest/v1/reports"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SupabaseReportService(AbstractReportService):
    """Submits reports to the Supabase ``reports`` table.

    Args:
        supabase_url: Supabase project URL (default: env / .env).
        anon_key:     Supabase anon/public key (default: env / .env).
    """

    def __init__(
        self,
        supabase_url: str | None = None,
        anon_key: str | None = None,
    ) -> None:
        self._config = self._resolve_config(supabase_url, anon_key)

    @property
    def is_configured(self) -> bool:
        """Whether this service has valid Supabase credentials."""
        return self._config.is_valid

    # ------------------------------------------------------------------
    # AbstractReportService — typed convenience methods
    # ------------------------------------------------------------------

    def submit_bug(self, report: BugReport) -> SubmitResult:
        title = report.title
        body = self._build_bug_body(report)
        payload_data = {
            "steps_to_reproduce": report.steps_to_reproduce,
            "expected_behavior": report.expected_behavior,
            "actual_behavior": report.actual_behavior,
            "severity": report.severity,
        }
        return self._submit_report(
            report_type=ReportType.BUG,
            title=title,
            description=body,
            source="support_center",
            payload=payload_data,
        )

    def submit_feature(self, request: FeatureRequest) -> SubmitResult:
        title = request.title
        body = self._build_feature_body(request)
        payload_data = {
            "use_case": request.use_case,
            "priority": request.priority,
        }
        return self._submit_report(
            report_type=ReportType.FEATURE,
            title=title,
            description=body,
            source="support_center",
            payload=payload_data,
        )

    def submit_feedback(self, feedback: FeedbackReport) -> SubmitResult:
        title = feedback.subject
        body = self._build_feedback_body(feedback)
        payload_data = {
            "category": feedback.category,
            "contact_ok": feedback.contact_ok,
        }
        return self._submit_report(
            report_type=ReportType.FEEDBACK,
            title=title,
            description=body,
            source="support_center",
            payload=payload_data,
        )

    def submit_report(
        self, report_type: ReportType, title: str, body: str
    ) -> SubmitResult:
        source = "crash_detector" if report_type == ReportType.CRASH else "support_center"
        return self._submit_report(
            report_type=report_type,
            title=title,
            description=body,
            source=source,
            payload={},
        )

    # ------------------------------------------------------------------
    # Internal: single submission entry point
    # ------------------------------------------------------------------

    def _submit_report(
        self,
        report_type: ReportType,
        title: str,
        description: str,
        source: str,
        payload: dict[str, Any],
    ) -> SubmitResult:
        if not self._config.is_valid:
            return SubmitResult(
                success=False,
                error_message=(
                    "Supabase not configured. "
                    "Set SUPABASE_URL and SUPABASE_ANON_KEY in environment."
                ),
            )

        row = {
            "type": report_type.value,
            "title": title,
            "description": description,
            "app_version": __version__,
            "os": platform.platform(),
            "status": "new",
            "source": source,
            "payload": payload,
        }

        api_url = self._config.api_url
        logger.debug(
            "Supabase request URL: config.url=%s  config.api_url=%s",
            self._config.url,
            api_url,
        )

        data = json.dumps(row).encode("utf-8")
        req = Request(
            api_url,
            data=data,
            headers={
                "apikey": self._config.anon_key,
                "Authorization": f"Bearer {self._config.anon_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )

        logger.debug("Supabase request.full_url=%s", req.full_url)

        try:
            with urlopen(req, timeout=_API_TIMEOUT_SECONDS) as resp:
                logger.info(
                    "Supabase report created: type=%s title=%r status=%d",
                    report_type.value,
                    title,
                    resp.getcode(),
                )
                return SubmitResult(success=True)
        except HTTPError as exc:
            return self._handle_http_error(exc, report_type, title)
        except URLError as exc:
            logger.error("Network error posting to Supabase: %s", exc)
            return SubmitResult(
                success=False,
                error_message=(
                    "Network error: could not reach Supabase. "
                    "Check your internet connection."
                ),
            )
        except Exception as exc:
            logger.exception("Unexpected error posting to Supabase: %s", exc)
            return SubmitResult(
                success=False,
                error_message="An unexpected error occurred while submitting.",
            )

    # ------------------------------------------------------------------
    # Config resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_config(
        url: str | None = None, key: str | None = None,
    ) -> SupabaseConfig:
        """Resolve config from args, env vars, or .env file (priority order).

        Only ``None`` triggers fallback to env / .env; an explicit empty string
        is preserved so callers can signal *no value*.
        """
        env = _load_env_vars()
        resolved_url = (
            url
            if url is not None
            else os.environ.get(_ENV_SUPABASE_URL)
            or env.get(_ENV_SUPABASE_URL)
            or ""
        )
        resolved_key = (
            key
            if key is not None
            else os.environ.get(_ENV_SUPABASE_ANON_KEY)
            or env.get(_ENV_SUPABASE_ANON_KEY)
            or ""
        )
        return SupabaseConfig(url=resolved_url, anon_key=resolved_key)

    # ------------------------------------------------------------------
    # HTTP error handling
    # ------------------------------------------------------------------

    def _handle_http_error(
        self, exc: HTTPError, report_type: ReportType, title: str,
    ) -> SubmitResult:
        status = exc.code
        body_preview = ""
        try:
            body_preview = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass

        if status in (401, 403):
            logger.error(
                "Supabase auth failed (%d) for type=%s title=%r: %s",
                status, report_type.value, title, body_preview,
            )
            return SubmitResult(
                success=False,
                error_message=(
                    "Supabase authentication failed. Check your API key."
                ),
            )
        if status == 409:
            logger.warning(
                "Supabase conflict (%d) for type=%s title=%r: %s",
                status, report_type.value, title, body_preview,
            )
            return SubmitResult(
                success=False,
                error_message="Supabase conflict: the report may be a duplicate.",
            )
        if 400 <= status < 500:
            logger.error(
                "Supabase client error (%d) for type=%s title=%r: %s",
                status, report_type.value, title, body_preview,
            )
            return SubmitResult(
                success=False,
                error_message=(
                    f"Supabase request failed (HTTP {status}). "
                    "Check your configuration."
                ),
            )
        if status >= 500:
            logger.error(
                "Supabase server error (%d) for type=%s title=%r: %s",
                status, report_type.value, title, body_preview,
            )
            return SubmitResult(
                success=False,
                error_message="Supabase server error. Please try again later.",
            )

        logger.error(
            "Supabase unexpected HTTP %d: %s", status, body_preview,
        )
        return SubmitResult(
            success=False,
            error_message=f"Supabase returned HTTP {status}.",
        )

    # ------------------------------------------------------------------
    # Body Templates
    # ------------------------------------------------------------------

    @staticmethod
    def _build_bug_body(report: BugReport) -> str:
        return (
            f"### Description\n{report.description}\n\n"
            f"### Expected Result\n{report.expected_behavior}\n\n"
            f"### Actual Result\n{report.actual_behavior}\n\n"
            f"### Steps to Reproduce\n{report.steps_to_reproduce}\n\n"
            f"---\n"
            f"*Submitted via Trackora*\n"
            f"*Severity: {report.severity}*"
        )

    @staticmethod
    def _build_feature_body(request: FeatureRequest) -> str:
        return (
            f"### Description\n{request.description}\n\n"
            f"### Why Needed\n{request.use_case}\n\n"
            f"---\n"
            f"*Submitted via Trackora*\n"
            f"*Priority: {request.priority}*"
        )

    @staticmethod
    def _build_feedback_body(feedback: FeedbackReport) -> str:
        return (
            f"{feedback.message}\n\n"
            f"---\n"
            f"*Submitted via Trackora*\n"
            f"*Category: {feedback.category}*\n"
            f"*Contact OK: {feedback.contact_ok}*"
        )
