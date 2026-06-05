"""
tracker/

Phase 2 — Tracking Engine

Public API surface:
    ProcessMonitor   — background polling thread
    SessionManager   — session lifecycle
    TrackingState    — shared in-memory state
    TrackedGame      — game snapshot dataclass
    ActiveSession    — live session dataclass
"""

from tracker.game_detector import detect_changes, snapshot_running_processes
from tracker.process_monitor import ProcessMonitor
from tracker.session_manager import SessionManager
from tracker.tracking_state import ActiveSession, TrackedGame, TrackingState

__all__ = [
    "ProcessMonitor",
    "SessionManager",
    "TrackingState",
    "TrackedGame",
    "ActiveSession",
    "detect_changes",
    "snapshot_running_processes",
]