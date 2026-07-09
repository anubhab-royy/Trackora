"""
Tests for MongoDB Validation (T-230)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest
import pymongo.errors
from services.support.mongo_connection import MongoConnection, MongoValidationStatus


def test_missing_uri():
    conn = MongoConnection(uri="")
    status = conn.validate()
    assert status == MongoValidationStatus.CONFIGURATION_MISSING
    assert "MONGODB_URI is empty" in conn.last_error
    assert conn.auth_failed is False
    assert conn.is_available is False


def test_invalid_uri_format():
    conn = MongoConnection(uri="invalid-uri-format")
    status = conn.validate()
    assert status == MongoValidationStatus.CONFIGURATION_MISSING
    assert conn.auth_failed is False


def test_missing_database_name():
    # Database name is not provided in uri path, and not in constructor, and not in env
    conn = MongoConnection(uri="mongodb://localhost:27017")
    status = conn.validate()
    assert status == MongoValidationStatus.CONFIGURATION_MISSING
    assert "Database name is not configured" in conn.last_error


def test_successful_connection():
    conn = MongoConnection(uri="mongodb://localhost:27017/test")
    
    mock_db = MagicMock()
    mock_db.command.return_value = {"ok": 1}
    mock_db["bug_reports"].find_one.return_value = {}
    mock_db["bug_reports"].insert_one.return_value = MagicMock(inserted_id="dummy_id")
    
    mock_client = MagicMock()
    mock_client.admin = mock_db
    mock_client.__getitem__.return_value = mock_db

    with patch("services.support.mongo_connection.MongoClient", return_value=mock_client) as mock_client_cls:
        status = conn.validate(force=True)
        assert status == MongoValidationStatus.CONNECTED
        assert conn.is_available is True
        assert conn.last_error is None
        assert conn.auth_failed is False


def test_authentication_failure():
    conn = MongoConnection(uri="mongodb://user:pass@localhost:27017/test")
    
    mock_client = MagicMock()
    # Raise OperationFailure with error code 18 (AuthenticationFailed)
    mock_client.admin.command.side_effect = pymongo.errors.OperationFailure("Auth failed", code=18)
    
    with patch("services.support.mongo_connection.MongoClient", return_value=mock_client):
        status = conn.validate(force=True)
        assert status == MongoValidationStatus.AUTHENTICATION_FAILED
        assert conn.auth_failed is True
        assert conn.is_available is False


def test_permission_error():
    conn = MongoConnection(uri="mongodb://user:pass@localhost:27017/test")
    
    mock_db = MagicMock()
    # Ping succeeds, but write fails with OperationFailure with error code 13 (Unauthorized)
    mock_db.command.return_value = {"ok": 1}
    mock_db["bug_reports"].find_one.return_value = {}
    mock_db["bug_reports"].insert_one.side_effect = pymongo.errors.OperationFailure("Not authorized", code=13)
    
    mock_client = MagicMock()
    mock_client.admin = mock_db
    mock_client.__getitem__.return_value = mock_db
    
    with patch("services.support.mongo_connection.MongoClient", return_value=mock_client):
        status = conn.validate(force=True)
        assert status == MongoValidationStatus.PERMISSION_ERROR
        assert conn.auth_failed is False


def test_timeout():
    conn = MongoConnection(uri="mongodb://localhost:27017/test")
    
    mock_client = MagicMock()
    mock_client.admin.command.side_effect = pymongo.errors.ServerSelectionTimeoutError("Server selection timeout")
    
    with patch("services.support.mongo_connection.MongoClient", return_value=mock_client):
        status = conn.validate(force=True)
        assert status == MongoValidationStatus.TIMEOUT
        assert conn.auth_failed is False


def test_dns_failure():
    conn = MongoConnection(uri="mongodb://localhost:27017/test")
    
    mock_client = MagicMock()
    mock_client.admin.command.side_effect = pymongo.errors.ConnectionFailure("could not resolve hostname")
    
    with patch("services.support.mongo_connection.MongoClient", return_value=mock_client):
        status = conn.validate(force=True)
        assert status == MongoValidationStatus.DNS_ERROR
        assert conn.auth_failed is False


def test_cached_validation_reuse():
    conn = MongoConnection(uri="mongodb://localhost:27017/test")
    
    mock_db = MagicMock()
    mock_db.command.return_value = {"ok": 1}
    mock_db["bug_reports"].find_one.return_value = {}
    mock_db["bug_reports"].insert_one.return_value = MagicMock(inserted_id="dummy_id")
    mock_client = MagicMock()
    mock_client.admin = mock_db
    mock_client.__getitem__.return_value = mock_db

    with patch("services.support.mongo_connection.MongoClient", return_value=mock_client) as mock_client_cls:
        # First call triggers creation
        status1 = conn.validate(force=True)
        assert status1 == MongoValidationStatus.CONNECTED
        assert mock_client_cls.call_count == 1
        
        # Second call uses cached status (not forcing)
        status2 = conn.validate(force=False)
        assert status2 == MongoValidationStatus.CONNECTED
        assert mock_client_cls.call_count == 1  # Should NOT call MongoClient constructor again!
