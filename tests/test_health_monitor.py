"""
test_health_monitor.py — unit and integration tests for T-204 Background Health Monitor.
"""

from __future__ import annotations

import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QObject

from services.health.health_status import HealthStatus
from services.health.health_result import HealthResult
from services.health.health_registry import HealthRegistry
from services.health.health_monitor import HealthMonitor
from services.health.health_check import (
    TrackingEngineHealthCheck,
    SQLiteHealthCheck,
    MongoDBHealthCheck,
    UpdateServiceHealthCheck,
    CrashServiceHealthCheck,
    BackgroundWorkersHealthCheck,
)


# ------------------------------------------------------------------
# Test Registry
# ------------------------------------------------------------------

def test_registry_registration() -> None:
    registry = HealthRegistry()
    mock_check = MagicMock()
    mock_check.name.return_value = "Test Check"

    registry.register(mock_check)
    assert len(registry.get_all()) == 1
    assert registry.get_all()[0] == mock_check


# ------------------------------------------------------------------
# Test TrackingEngineHealthCheck
# ------------------------------------------------------------------

def test_tracking_engine_healthy_running() -> None:
    mock_monitor = MagicMock()
    mock_state = MagicMock()
    mock_state.is_running = True
    mock_monitor._thread.is_alive.return_value = True
    mock_monitor._session_manager = MagicMock()

    check = TrackingEngineHealthCheck(mock_monitor, mock_state)
    result = check.check()
    assert result.status == HealthStatus.HEALTHY
    assert result.details["thread_alive"] is True


def test_tracking_engine_healthy_idle() -> None:
    mock_monitor = MagicMock()
    mock_state = MagicMock()
    mock_state.is_running = False
    mock_monitor._thread = None

    check = TrackingEngineHealthCheck(mock_monitor, mock_state)
    result = check.check()
    assert result.status == HealthStatus.HEALTHY
    assert result.details["state_is_running"] is False


def test_tracking_engine_failed() -> None:
    mock_monitor = MagicMock()
    mock_state = MagicMock()
    mock_state.is_running = True
    mock_monitor._thread.is_alive.return_value = False

    check = TrackingEngineHealthCheck(mock_monitor, mock_state)
    result = check.check()
    assert result.status == HealthStatus.FAILED
    assert "dead" in result.message


def test_tracking_engine_recovery() -> None:
    mock_monitor = MagicMock()
    mock_state = MagicMock()
    mock_state.is_running = True

    check = TrackingEngineHealthCheck(mock_monitor, mock_state)
    success = check.recover()
    assert success is True
    assert mock_state.is_running is False
    mock_monitor.start.assert_called_once()


# ------------------------------------------------------------------
# Test SQLiteHealthCheck
# ------------------------------------------------------------------

def test_sqlite_healthy() -> None:
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        (1,),        # SELECT 1;
        ("wal",),    # PRAGMA journal_mode;
    ]
    mock_conn.cursor.return_value = mock_cursor

    check = SQLiteHealthCheck(mock_conn)
    result = check.check()
    assert result.status == HealthStatus.HEALTHY
    assert result.details["journal_mode"].lower() == "wal"


def test_sqlite_warning_not_wal() -> None:
    conn = sqlite3.connect(":memory:")
    # Default journal mode is delete (not WAL)
    check = SQLiteHealthCheck(conn)
    result = check.check()
    assert result.status == HealthStatus.WARNING
    assert "WAL" in result.message
    conn.close()


def test_sqlite_failed_query() -> None:
    conn = sqlite3.connect(":memory:")
    conn.close()  # Force error on check

    check = SQLiteHealthCheck(conn)
    result = check.check()
    assert result.status == HealthStatus.FAILED
    assert "failed" in result.message


# ------------------------------------------------------------------
# Test MongoDBHealthCheck
# ------------------------------------------------------------------

def test_mongodb_warning_no_uri() -> None:
    with patch.dict(os.environ, {"MONGODB_URI": ""}):
        check = MongoDBHealthCheck(MagicMock())
        result = check.check()
        assert result.status == HealthStatus.WARNING
        assert "not configured" in result.message


def test_mongodb_warning_not_available() -> None:
    with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost"}):
        mock_conn = MagicMock()
        mock_conn.is_available = False
        mock_conn._auth_failed = False
        mock_conn.last_error = "Connection timeout"

        check = MongoDBHealthCheck(mock_conn)
        result = check.check()
        assert result.status == HealthStatus.WARNING
        assert "offline" in result.message
        assert result.details["is_available"] is False


def test_mongodb_warning_auth_failed() -> None:
    with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost"}):
        mock_conn = MagicMock()
        mock_conn.is_available = False
        mock_conn._auth_failed = True
        mock_conn.last_error = "bad auth"

        check = MongoDBHealthCheck(mock_conn)
        result = check.check()
        assert result.status == HealthStatus.WARNING
        assert "authentication failed" in result.message
        assert result.details["auth_failed"] is True


def test_mongodb_healthy() -> None:
    with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost"}):
        mock_conn = MagicMock()
        mock_conn.is_available = True
        mock_conn._auth_failed = False

        check = MongoDBHealthCheck(mock_conn)
        result = check.check()
        assert result.status == HealthStatus.HEALTHY
        assert "online" in result.message


# ------------------------------------------------------------------
# Test UpdateServiceHealthCheck
# ------------------------------------------------------------------

def test_update_service_healthy() -> None:
    mock_service = MagicMock()
    mock_service._settings_repo.get_value.return_value = "2026-07-07T00:00:00"
    mock_window = MagicMock()
    mock_window._update_thread = None

    check = UpdateServiceHealthCheck(mock_service, mock_window)
    result = check.check()
    assert result.status == HealthStatus.HEALTHY
    assert result.details["thread_running"] is False


def test_update_service_stuck_thread() -> None:
    mock_service = MagicMock()
    mock_service._settings_repo.get_value.return_value = "2026-07-07T00:00:00"
    mock_window = MagicMock()
    mock_thread = MagicMock()
    mock_thread.isRunning.return_value = True
    mock_window._update_thread = mock_thread

    check = UpdateServiceHealthCheck(mock_service, mock_window)
    
    # Run check 5 times to trigger consecutive runs > 4
    for _ in range(5):
        result = check.check()
    
    assert result.status == HealthStatus.WARNING
    assert "stuck" in result.message


# ------------------------------------------------------------------
# Test CrashServiceHealthCheck
# ------------------------------------------------------------------

def test_crash_service_healthy() -> None:
    mock_crash = MagicMock()
    mock_crash.state_manager.state_path.is_file.return_value = True
    mock_recovery = MagicMock()

    with patch("os.access", return_value=True):
        check = CrashServiceHealthCheck(mock_crash, mock_recovery)
        result = check.check()
        assert result.status == HealthStatus.HEALTHY


def test_crash_service_failed_writable() -> None:
    mock_crash = MagicMock()
    mock_crash.state_manager.state_path.is_file.return_value = True
    mock_recovery = MagicMock()

    with patch("os.access", return_value=False):
        check = CrashServiceHealthCheck(mock_crash, mock_recovery)
        result = check.check()
        assert result.status == HealthStatus.FAILED
        assert "writable" in result.message


# ------------------------------------------------------------------
# Test BackgroundWorkersHealthCheck
# ------------------------------------------------------------------

def test_background_workers_healthy() -> None:
    mock_window = MagicMock()
    mock_window._queue_retry_timer.isActive.return_value = True

    check = BackgroundWorkersHealthCheck(mock_window)
    result = check.check()
    assert result.status == HealthStatus.HEALTHY


def test_background_workers_warning() -> None:
    mock_window = MagicMock()
    mock_window._queue_retry_timer.isActive.return_value = False

    check = BackgroundWorkersHealthCheck(mock_window)
    result = check.check()
    assert result.status == HealthStatus.WARNING
    assert "timer" in result.message


def test_background_workers_recovery() -> None:
    mock_window = MagicMock()
    mock_window._queue_retry_timer.isActive.return_value = False

    check = BackgroundWorkersHealthCheck(mock_window)
    success = check.recover()
    assert success is True
    mock_window._queue_retry_timer.start.assert_called_once_with(60000)


# ------------------------------------------------------------------
# Test HealthMonitor Orchestrator & Logging & Notifications
# ------------------------------------------------------------------

class NotificationListener(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.notifications: list[tuple[str, str]] = []

    def on_notification(self, title: str, message: str) -> None:
        self.notifications.append((title, message))


def test_health_monitor_logging_and_notifications() -> None:
    registry = HealthRegistry()
    
    # 1. Register a check that changes states
    mock_check = MagicMock()
    mock_check.name.return_value = "Mock Service"
    mock_check.check.side_effect = [
        HealthResult(HealthStatus.HEALTHY, "All good"),
        HealthResult(HealthStatus.FAILED, "Crashed"),
        HealthResult(HealthStatus.FAILED, "Still crashed"), # No transition
        HealthResult(HealthStatus.HEALTHY, "Recovered"),
    ]
    registry.register(mock_check)

    monitor = HealthMonitor(registry)
    listener = NotificationListener()
    monitor.notification_requested.connect(listener.on_notification)

    # First check (HEALTHY)
    monitor.run_checks()
    assert len(listener.notifications) == 0

    # Second check (transition HEALTHY -> FAILED)
    monitor.run_checks()
    assert len(listener.notifications) == 1
    assert listener.notifications[0][0] == "Trackora Alert — Mock Service"

    # Third check (FAILED -> FAILED, no transition notification should trigger)
    monitor.run_checks()
    assert len(listener.notifications) == 1

    # Fourth check (transition FAILED -> HEALTHY)
    monitor.run_checks()
    assert len(listener.notifications) == 1  # No notification on healthy return, only log info


def test_mongodb_pending_is_healthy() -> None:
    from unittest.mock import PropertyMock
    with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost"}):
        mock_conn = MagicMock()
        type(mock_conn).is_pending = PropertyMock(return_value=True)
        mock_conn.is_available = False
        mock_conn._auth_failed = False

        check = MongoDBHealthCheck(mock_conn)
        result = check.check()
        assert result.status == HealthStatus.HEALTHY
        assert "pending" in result.message
        assert result.details["pending"] is True


def test_mongodb_transition_pending_to_warning_emits_notification() -> None:
    from unittest.mock import PropertyMock
    with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost"}):
        mock_conn = MagicMock()
        is_pending_mock = PropertyMock(side_effect=[True, False, False])
        type(mock_conn).is_pending = is_pending_mock
        
        is_available_mock = PropertyMock(side_effect=[False, False, False])
        type(mock_conn).is_available = is_available_mock
        
        mock_conn._auth_failed = False
        mock_conn.last_error = "Connection lost"

        check = MongoDBHealthCheck(mock_conn)
        registry = HealthRegistry()
        registry.register(check)

        monitor = HealthMonitor(registry)
        listener = NotificationListener()
        monitor.notification_requested.connect(listener.on_notification)

        monitor.run_checks()
        assert len(listener.notifications) == 0

        monitor.run_checks()
        assert len(listener.notifications) == 1
        assert "offline" in listener.notifications[0][1]

        monitor.run_checks()
        assert len(listener.notifications) == 1

