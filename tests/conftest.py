# Shared fixtures (in-memory DB)

"""
Pytest fixtures shared across all GameTracker database tests.

All tests use an in-memory SQLite database so:
    - Tests are isolated from each other.
    - Tests leave no files on disk.
    - Tests run fast.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure 'database' package is importable from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from database.database_manager import DatabaseManager
from database.repositories.games_repository import GamesRepository
from database.repositories.sessions_repository import SessionsRepository
from database.repositories.settings_repository import SettingsRepository
from database.repositories.active_sessions_repository import ActiveSessionsRepository


@pytest.fixture
def db_manager():
    """Provide an initialized in-memory DatabaseManager for each test."""
    manager = DatabaseManager(db_path=":memory:")
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture
def connection(db_manager):
    """Provide the raw sqlite3 connection from an initialized DatabaseManager."""
    return db_manager.connection


@pytest.fixture
def games_repo(connection):
    return GamesRepository(connection)


@pytest.fixture
def sessions_repo(connection):
    return SessionsRepository(connection)


@pytest.fixture
def settings_repo(connection):
    return SettingsRepository(connection)


@pytest.fixture
def active_sessions_repo(connection):
    return ActiveSessionsRepository(connection)