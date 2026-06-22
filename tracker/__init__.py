"""
Tracker Layer
Responsible for process detection, session management, crash recovery,
and automatic game discovery.
"""

from tracker.discovery.models import CandidateGame, DiscoveryResult
from tracker.process_monitor import ProcessMonitor
from tracker.recovery_manager import RecoveryManager, RecoveryResult, RecoveredSession
from tracker.session_manager import SessionManager
from tracker.tracking_state import ActiveSession, TrackedGame, TrackingState

__all__ = [
    "ActiveSession",
    "CandidateGame",
    "DiscoveryResult",
    "ProcessMonitor",
    "RecoveredSession",
    "RecoveryManager",
    "RecoveryResult",
    "SessionManager",
    "TrackedGame",
    "TrackingState",
]
