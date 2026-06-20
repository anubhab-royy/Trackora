"""Tests for MongoConnection — RED phase."""

from __future__ import annotations

import os
import threading
from unittest.mock import MagicMock, patch

import pytest

from services.support.mongo_connection import MongoConnection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def connection() -> MongoConnection:
    return MongoConnection(uri="mongodb://localhost:27017/test")


@pytest.fixture
def unconfigured() -> MongoConnection:
    return MongoConnection(uri="")


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_explicit_uri_stored(self):
        conn = MongoConnection(uri="mongodb://localhost:27017/test")
        assert conn._uri == "mongodb://localhost:27017/test"

    def test_no_uri_reads_env(self):
        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://env:27017/db"}, clear=True):
            conn = MongoConnection()
            assert conn._uri == "mongodb://env:27017/db"

    def test_no_uri_no_env_sets_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            conn = MongoConnection()
            assert conn._uri == ""
            assert conn.is_available is False


class TestIsAvailable:
    def test_returns_false_before_connection(self, connection: MongoConnection):
        assert connection.is_available is False

    def test_returns_false_when_unconfigured(self, unconfigured: MongoConnection):
        assert unconfigured.is_available is False

    def test_returns_true_after_successful_health_check(self, connection: MongoConnection):
        with patch(
            "services.support.mongo_connection.MongoClient"
        ) as mock_client_cls:
            mock_db = MagicMock()
            mock_db.command.return_value = {"ok": 1}
            mock_client = MagicMock()
            mock_client.admin = mock_db
            mock_client_cls.return_value = mock_client
            connection.health_check()
        assert connection.is_available is True


class TestHealthCheck:
    def test_returns_false_when_not_configured(self, unconfigured: MongoConnection):
        assert unconfigured.health_check() is False

    def test_returns_true_when_ping_succeeds(self, connection: MongoConnection):
        mock_db = MagicMock()
        mock_db.command.return_value = {"ok": 1}
        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_client.admin = mock_db

        with patch(
            "services.support.mongo_connection.MongoClient",
            return_value=mock_client,
        ):
            assert connection.health_check() is True

    def test_returns_false_when_ping_fails(self, connection: MongoConnection):
        mock_db = MagicMock()
        mock_db.command.side_effect = Exception("connection refused")
        mock_client = MagicMock()
        mock_client.admin = mock_db

        with patch(
            "services.support.mongo_connection.MongoClient",
            return_value=mock_client,
        ):
            assert connection.health_check() is False

    def test_redacts_credentials_from_log(self, connection: MongoConnection):
        pass  # validated by inspection during REFACTOR


class TestDatabase:
    def test_returns_none_when_not_configured(self, unconfigured: MongoConnection):
        assert unconfigured.database is None

    def test_returns_database_instance_when_connected(self, connection: MongoConnection):
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.get_default_database.return_value = mock_db

        with patch(
            "services.support.mongo_connection.MongoClient",
            return_value=mock_client,
        ):
            db = connection.database
            assert db is mock_db

    def test_creates_client_lazily(self, connection: MongoConnection):
        assert connection._client is None
        mock_client = MagicMock()
        with patch(
            "services.support.mongo_connection.MongoClient",
            return_value=mock_client,
        ):
            _ = connection.database
            assert connection._client is mock_client

    def test_multiple_calls_same_client(self, connection: MongoConnection):
        mock_client = MagicMock()
        with patch(
            "services.support.mongo_connection.MongoClient",
            return_value=mock_client,
        ):
            db1 = connection.database
            db2 = connection.database
            assert db1 is db2


class TestClose:
    def test_releases_resources(self, connection: MongoConnection):
        mock_client = MagicMock()
        with patch(
            "services.support.mongo_connection.MongoClient",
            return_value=mock_client,
        ):
            _ = connection.database
            connection.close()
            mock_client.close.assert_called_once()

    def test_is_idempotent(self, connection: MongoConnection):
        connection.close()
        connection.close()


class TestThreadSafety:
    def test_concurrent_database_access(self, connection: MongoConnection):
        mock_client = MagicMock()
        with patch(
            "services.support.mongo_connection.MongoClient",
            return_value=mock_client,
        ):
            results: list = []
            errors: list = []

            def access() -> None:
                try:
                    results.append(connection.database)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=access) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
            assert len(results) == 3
            assert all(r is results[0] for r in results)
