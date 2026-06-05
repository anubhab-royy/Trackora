# imports tracker.tracking_state

"""
tracker/game_detector.py

Responsible for inspecting a snapshot of running OS processes and
deciding which tracked games have started or stopped since the last poll.

Deliberately stateless: it receives the current TrackingState and a set
of running process names, then returns what changed.  This makes it
completely unit-testable without touching psutil or a real OS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tracker.tracking_state import TrackedGame, TrackingState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectionResult:
    """Output of a single detection pass."""

    started: list[tuple[int, int]]   # [(game_id, pid), ...]  — games that just appeared
    stopped: list[int]               # [game_id, ...]          — games that just disappeared


def detect_changes(
    state: TrackingState,
    running_processes: dict[str, int],   # process_name.lower() -> pid
) -> DetectionResult:
    """
    Compare running_processes against the current TrackingState and return
    what changed.

    Args:
        state:             Current tracker state (tracked games + active sessions).
        running_processes: Mapping of lower-cased process names to their PIDs,
                           as returned by the OS.  Caller is responsible for
                           building this from psutil (or a mock).

    Returns:
        DetectionResult with lists of newly-started and newly-stopped game_ids.
    """
    started: list[tuple[int, int]] = []
    stopped: list[int] = []

    # --- Detect starts ---
    for proc_name, pid in running_processes.items():
        game = state.find_game_by_process(proc_name)
        if game is None:
            continue                            # not a tracked game
        if state.is_game_active(game.game_id):
            continue                            # already tracking this game
        started.append((game.game_id, pid))
        logger.info("Detected start: game_id=%d name=%r pid=%d", game.game_id, game.name, pid)

    # --- Detect stops ---
    for game_id, session in list(state.active_sessions.items()):
        proc_name = state.tracked_games[game_id].process_name.lower()
        if proc_name not in running_processes:
            stopped.append(game_id)
            logger.info(
                "Detected stop: game_id=%d name=%r was_pid=%d",
                game_id,
                state.tracked_games[game_id].name,
                session.process_id,
            )

    return DetectionResult(started=started, stopped=stopped)


def snapshot_running_processes() -> dict[str, int]:
    """
    Return a dict of {process_name.lower(): pid} for every process currently
    running on the system.

    This is the ONLY place in the tracker layer that calls psutil directly,
    making it trivial to mock in tests.

    Only the first instance of a process name is kept (pid collision is
    acceptable for our use-case: we track the game, not the specific PID).
    """
    import psutil  # imported here so the module loads without psutil in tests

    result: dict[str, int] = {}
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                pid = proc.info["pid"]
                if name and name not in result:
                    result[name] = pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        logger.exception("Unexpected error while snapshotting processes")
    return result