# imports all three above

"""
tracker/process_monitor.py

The heartbeat of the tracking engine.

ProcessMonitor runs a background thread that polls the OS every
POLL_INTERVAL_SECONDS (default: 5) seconds.  On each tick it:

  1. Takes a snapshot of all running processes via game_detector.
  2. Asks GameDetector what changed (starts / stops).
  3. Delegates to SessionManager to act on those changes.

Threading model
---------------
The monitor runs in a daemon thread so it is automatically stopped when the
main process exits.  A threading.Event is used as the stop signal, making
it trivial to shut down cleanly in tests.

Dependency injection
--------------------
All collaborators are injected.  The snapshot function is also injectable
(defaults to game_detector.snapshot_running_processes) so tests can supply
a deterministic fake without patching globals.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from tracker import game_detector
from tracker.game_detector import DetectionResult, detect_changes
from tracker.session_manager import SessionManager
from tracker.tracking_state import TrackedGame, TrackingState

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS: float = 5.0


class ProcessMonitor:
    """
    Polls running OS processes on a background thread and triggers
    session open/close events via SessionManager.
    """

    def __init__(
        self,
        state: TrackingState,
        session_manager: SessionManager,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        snapshot_fn: Callable[[], dict[str, int]] | None = None,
    ) -> None:
        """
        Args:
            state:           Shared TrackingState; ProcessMonitor reads it,
                             SessionManager mutates it.
            session_manager: Handles session creation and completion.
            poll_interval:   Seconds between process scans.  Lowered in tests.
            snapshot_fn:     Callable that returns {proc_name.lower(): pid}.
                             Defaults to the real psutil-based implementation.
        """
        self._state = state
        self._session_manager = session_manager
        self._poll_interval = poll_interval
        self._snapshot_fn = snapshot_fn or game_detector.snapshot_running_processes

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread.  No-op if already running."""
        if self._state.is_running:
            logger.warning("ProcessMonitor.start() called but monitor is already running")
            return

        self._stop_event.clear()
        self._state.is_running = True

        self._thread = threading.Thread(
            target=self._run,
            name="ProcessMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("ProcessMonitor started (poll_interval=%.1fs)", self._poll_interval)

    def stop(self, timeout: float = 10.0) -> None:
        """
        Signal the polling loop to stop and wait for the thread to finish.

        Args:
            timeout: Maximum seconds to wait for the thread to join.
        """
        if not self._state.is_running:
            return

        logger.info("ProcessMonitor stopping …")
        self._stop_event.set()
        self._state.is_running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("ProcessMonitor thread did not stop within %.1fs", timeout)

        logger.info("ProcessMonitor stopped")

    @property
    def is_running(self) -> bool:
        return self._state.is_running

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main loop executed on the background thread."""
        logger.debug("ProcessMonitor thread entering poll loop")
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("Unhandled error in ProcessMonitor._tick()")
            # Use Event.wait so stop() interrupts the sleep immediately
            self._stop_event.wait(timeout=self._poll_interval)

        logger.debug("ProcessMonitor thread exiting poll loop")

    def _tick(self) -> None:
        """Single detection pass.  Called once per poll interval."""
        running = self._snapshot_fn()
        result: DetectionResult = detect_changes(self._state, running)

        for game_id, pid in result.started:
            self._session_manager.start_session(game_id=game_id, process_id=pid)

        for game_id in result.stopped:
            self._session_manager.end_session(game_id=game_id)

    # ------------------------------------------------------------------
    # Dynamic game registration (called from UI / service layer)
    # ------------------------------------------------------------------

    def reload_tracked_games(self, games: list[TrackedGame]) -> None:
        """
        Replace the full set of tracked games without restarting the monitor.

        Safe to call from any thread: Python's GIL protects the dict mutations
        here.  For Phase 2 this is sufficient; a lock can be added later if
        needed.
        """
        self._state.tracked_games.clear()
        for game in games:
            self._state.tracked_games[game.game_id] = game
        self._state.rebuild_index()
        logger.info("Tracked games reloaded: %d games", len(games))