"""
Tests for HistoryController — Phase 7

Covers:
  - SessionHistoryService.query builds the correct query
  - Pagination and total counts
  - Duration formatting
  - Controller delegates correctly to the service
"""

from __future__ import annotations

from datetime import datetime, date
from unittest.mock import MagicMock

import pytest

from database.models import SessionView
from services.session_history_service import (
    SessionHistoryQuery,
    SessionHistoryResult,
    SessionHistoryService,
    format_duration,
)


# ---------------------------------------------------------------------------
# format_duration unit tests
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_zero_seconds(self) -> None:
        assert format_duration(0) == "0m"

    def test_negative_seconds(self) -> None:
        assert format_duration(-100) == "0m"

    def test_minutes_only(self) -> None:
        assert format_duration(1800) == "30m"

    def test_one_hour_exactly(self) -> None:
        assert format_duration(3600) == "1h 0m"

    def test_hours_and_minutes(self) -> None:
        assert format_duration(5400) == "1h 30m"

    def test_large_value(self) -> None:
        assert format_duration(513_000) == "142h 30m"

    def test_one_second(self) -> None:
        assert format_duration(1) == "0m"

    def test_one_minute(self) -> None:
        assert format_duration(60) == "1m"


# ---------------------------------------------------------------------------
# SessionHistoryService tests
# ---------------------------------------------------------------------------

NOW = datetime(2024, 6, 15, 10, 0, 0)


def _make_session_view(
    session_id: int = 1,
    game_id: int = 1,
    game_name: str = "Test Game",
    duration: int = 3600,
) -> SessionView:
    return SessionView(
        id=session_id,
        game_id=game_id,
        game_name=game_name,
        start_time=NOW,
        end_time=datetime(2024, 6, 15, 11, 0, 0),
        duration_seconds=duration,
        created_at=NOW,
    )


class TestSessionHistoryService:

    def test_query_returns_result_dataclass(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.query_sessions.return_value = (0, [])

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        result = service.query(SessionHistoryQuery())
        assert isinstance(result, SessionHistoryResult)

    def test_query_delegates_to_repository(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.query_sessions.return_value = (1, [_make_session_view()])

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        result = service.query(SessionHistoryQuery(page_size=10))

        mock_sessions_repo.query_sessions.assert_called_once()
        assert result.total_count == 1
        assert len(result.sessions) == 1
        assert result.sessions[0].game_name == "Test Game"

    def test_query_converts_minutes_to_seconds(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.query_sessions.return_value = (0, [])

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        q = SessionHistoryQuery(
            min_duration_minutes=30,
            max_duration_minutes=120,
        )
        service.query(q)

        call_kwargs = mock_sessions_repo.query_sessions.call_args.kwargs
        assert call_kwargs["min_duration"] == 1800   # 30 * 60
        assert call_kwargs["max_duration"] == 7200    # 120 * 60

    def test_query_computes_total_pages(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.query_sessions.return_value = (55, [_make_session_view()] * 50)

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        result = service.query(SessionHistoryQuery(page=0, page_size=50))

        assert result.total_count == 55
        assert result.total_pages == 2

    def test_query_second_page(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.query_sessions.return_value = (55, [_make_session_view(session_id=i + 51) for i in range(5)])

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        result = service.query(SessionHistoryQuery(page=1, page_size=50))

        assert len(result.sessions) == 5
        assert result.page == 1

    def test_query_total_duration(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        sessions = [
            _make_session_view(session_id=1, duration=3600),
            _make_session_view(session_id=2, duration=1800),
        ]
        mock_sessions_repo.query_sessions.return_value = (2, sessions)

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        result = service.query(SessionHistoryQuery())

        assert result.total_duration_seconds == 5400

    def test_query_handles_exception(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.query_sessions.side_effect = RuntimeError("db error")

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        result = service.query(SessionHistoryQuery())

        assert result.total_count == 0
        assert result.sessions == []

    def test_get_games_delegates(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_games_repo.get_all.return_value = []

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        games = service.get_games()
        assert games == []
        mock_games_repo.get_all.assert_called_once()

    def test_get_games_handles_exception(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_games_repo.get_all.side_effect = RuntimeError("db error")

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        games = service.get_games()
        assert games == []

    def test_get_all_sessions_total_duration(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.get_lifetime_total_seconds.return_value = 99999

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        total = service.get_all_sessions_total_duration()
        assert total == 99999

    def test_get_all_sessions_total_duration_handles_exception(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        mock_sessions_repo.get_lifetime_total_seconds.side_effect = RuntimeError("db error")

        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)
        total = service.get_all_sessions_total_duration()
        assert total == 0


# ---------------------------------------------------------------------------
# SessionHistoryQuery tests
# ---------------------------------------------------------------------------

class TestSessionHistoryQuery:
    def test_default_values(self) -> None:
        q = SessionHistoryQuery()
        assert q.search_text == ""
        assert q.game_id is None
        assert q.page == 0
        assert q.page_size == 50
        assert q.sort_by == "start_time"
        assert q.sort_order == "DESC"

    def test_custom_values(self) -> None:
        q = SessionHistoryQuery(
            search_text="Witcher",
            game_id=1,
            page=2,
            page_size=25,
            sort_by="duration_seconds",
            sort_order="ASC",
        )
        assert q.search_text == "Witcher"
        assert q.game_id == 1
        assert q.page == 2
        assert q.page_size == 25
        assert q.sort_by == "duration_seconds"
        assert q.sort_order == "ASC"


# ---------------------------------------------------------------------------
# SessionHistoryResult tests
# ---------------------------------------------------------------------------

class TestSessionHistoryResult:
    def test_default_values(self) -> None:
        r = SessionHistoryResult()
        assert r.sessions == []
        assert r.total_count == 0
        assert r.page == 0
        assert r.page_size == 50
        assert r.total_pages == 0
        assert r.total_duration_seconds == 0

    def test_total_pages_through_query(self) -> None:
        mock_sessions_repo = MagicMock()
        mock_games_repo = MagicMock()
        service = SessionHistoryService(mock_sessions_repo, mock_games_repo)

        # 0 results → 0 pages
        mock_sessions_repo.query_sessions.return_value = (0, [])
        r = service.query(SessionHistoryQuery(page_size=50))
        assert r.total_pages == 0

        # 25 results → 1 page (fits in one page)
        mock_sessions_repo.query_sessions.return_value = (25, [_make_session_view()] * 25)
        r = service.query(SessionHistoryQuery(page_size=50))
        assert r.total_pages == 1

        # 50 results → 1 page (exactly one page)
        mock_sessions_repo.query_sessions.return_value = (50, [_make_session_view()] * 50)
        r = service.query(SessionHistoryQuery(page_size=50))
        assert r.total_pages == 1

        # 51 results → 2 pages
        mock_sessions_repo.query_sessions.return_value = (51, [_make_session_view()] * 50)
        r = service.query(SessionHistoryQuery(page_size=50))
        assert r.total_pages == 2

        # 101 results → 3 pages
        mock_sessions_repo.query_sessions.return_value = (101, [_make_session_view()] * 50)
        r = service.query(SessionHistoryQuery(page_size=50))
        assert r.total_pages == 3
