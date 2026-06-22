"""Integration tests for the discovery flow.

Tests the full pipeline:
  DiscoveryOrchestrator → GameService.import_discovered_games()
  → GamesRepository.add()

Uses in-memory SQLite for persistence and mock detectors.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from database.models.game import Game
from database.repositories.games_repository import GamesRepository
from services.game_service import GameService
from tracker.discovery.models import CandidateGame
from tracker.discovery.orchestrator import DiscoveryOrchestrator


@pytest.fixture()
def db_connection() -> sqlite3.Connection:
    """Create an in-memory SQLite database with the games table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            process_name TEXT NOT NULL,
            executable_path TEXT NOT NULL,
            icon_path TEXT DEFAULT '',
            is_enabled INTEGER DEFAULT 1,
            platform TEXT DEFAULT NULL,
            platform_id TEXT DEFAULT NULL,
            is_auto_discovered INTEGER DEFAULT 0,
            first_played TEXT,
            last_played TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    return conn


@pytest.fixture()
def repo(db_connection: sqlite3.Connection) -> GamesRepository:
    return GamesRepository(db_connection)


@pytest.fixture()
def service(repo: GamesRepository) -> GameService:
    return GameService(repo)


@pytest.fixture()
def orchestrator(repo: GamesRepository) -> DiscoveryOrchestrator:
    return DiscoveryOrchestrator(
        exists_by_executable_path=repo.get_by_executable_path,
        exists_by_platform_id=repo.exists_by_platform_id,
    )


class TestDiscoveryIntegration:
    """End-to-end discovery flow tests."""

    def test_scan_and_import_flow(
        self, orchestrator: DiscoveryOrchestrator, service: GameService
    ) -> None:
        """Full flow: scan → candidates → import → persisted."""
        # Replace real detectors with mock that returns known candidates
        mock_detector = MagicMock()
        mock_detector.platform = "steam"
        mock_detector.detect.return_value = [
            CandidateGame(
                name="Counter-Strike 2",
                executable_path="/games/cs2.exe",
                platform="steam",
                platform_id="730",
            ),
            CandidateGame(
                name="Dota 2",
                executable_path="/games/dota2.exe",
                platform="steam",
                platform_id="570",
            ),
        ]
        orchestrator._detectors = [mock_detector]

        # Also patch Path.is_file for GameService validation
        with patch("pathlib.Path.is_file", return_value=True):
            result = orchestrator.scan_all()

        assert len(result.candidates) == 2
        assert len(result.errors) == 0

        # Import the candidates
        with patch("pathlib.Path.is_file", return_value=True):
            import_result = service.import_discovered_games(result.candidates)

        assert import_result.success is True
        assert "2" in import_result.message

        # Verify persistence
        games = service.get_all_games()
        assert len(games) == 2
        names = {g.name for g in games}
        assert "Counter-Strike 2" in names
        assert "Dota 2" in names

        # Verify platform fields persisted
        cs2 = [g for g in games if g.name == "Counter-Strike 2"][0]
        assert cs2.platform == "steam"
        assert cs2.platform_id == "730"
        assert cs2.is_auto_discovered is True

    def test_duplicate_not_imported(
        self, orchestrator: DiscoveryOrchestrator, service: GameService, repo: GamesRepository
    ) -> None:
        """Already-tracked game is not re-imported."""
        # Pre-insert a game
        existing = Game(
            name="CS2",
            process_name="cs2.exe",
            executable_path="/games/cs2.exe",
            platform="steam",
            platform_id="730",
            is_auto_discovered=True,
        )
        repo.add(existing)

        mock_detector = MagicMock()
        mock_detector.platform = "steam"
        mock_detector.detect.return_value = [
            CandidateGame(
                name="Counter-Strike 2",
                executable_path="/games/cs2.exe",
                platform="steam",
                platform_id="730",
            ),
        ]
        orchestrator._detectors = [mock_detector]

        with patch("pathlib.Path.is_file", return_value=True):
            result = orchestrator.scan_all()

        # Should be excluded since it's already tracked
        assert len(result.candidates) == 0

    def test_orchestrator_returns_no_candidates_when_all_exist(
        self, orchestrator: DiscoveryOrchestrator, service: GameService, repo: GamesRepository
    ) -> None:
        """When all candidates are already tracked, scan returns empty."""
        repo.add(Game(name="A", process_name="a.exe", executable_path="/a.exe"))
        repo.add(Game(name="B", process_name="b.exe", executable_path="/b.exe"))

        mock_detector = MagicMock()
        mock_detector.platform = "steam"
        mock_detector.detect.return_value = [
            CandidateGame(name="A", executable_path="/a.exe", platform="steam", platform_id="1"),
            CandidateGame(name="B", executable_path="/b.exe", platform="steam", platform_id="2"),
        ]
        orchestrator._detectors = [mock_detector]

        with patch("pathlib.Path.is_file", return_value=True):
            result = orchestrator.scan_all()

        assert len(result.candidates) == 0
