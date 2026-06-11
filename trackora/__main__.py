"""
Trackora entry point.

Assembles all layers via dependency injection and starts the application
with a QApplication, main window, system tray, and background process monitor.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from database.database_manager import DatabaseManager
from database.repositories import (
    ActiveSessionsRepository,
    GamesRepository,
    SessionsRepository,
    SettingsRepository,
)
from services.export_service import ExportService
from services.game_service import GameService
from services.logging_service import LoggingService
from services.session_history_service import SessionHistoryService
from services.startup_service import StartupService
from trackora_stats.playtime_calculator import PlaytimeCalculator
from trackora_stats.statistics_service import StatisticsService
from tracker import (
    ProcessMonitor,
    RecoveryManager,
    SessionManager,
    TrackedGame,
    TrackingState,
)
from ui.main_window import MainWindow
from ui.themes.theme_manager import ThemeManager


def main() -> None:
    LoggingService.setup()
    logger = logging.getLogger(__name__)

    app = QApplication(sys.argv)
    app.setApplicationName("Trackora")
    app.setOrganizationName("Trackora")

    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = DatabaseManager(str(db_path))
    db.initialize()
    conn = db.connection

    games_repo = GamesRepository(conn)
    sessions_repo = SessionsRepository(conn)
    active_sessions_repo = ActiveSessionsRepository(conn)
    settings_repo = SettingsRepository(conn)

    game_service = GameService(games_repo)
    session_history_service = SessionHistoryService(sessions_repo, games_repo)
    statistics_service = StatisticsService(sessions_repo, games_repo)
    PlaytimeCalculator(sessions_repo, games_repo)
    export_service = ExportService(sessions_repo, games_repo, settings_repo)

    tracking_state = TrackingState()
    session_manager = SessionManager(
        state=tracking_state,
        active_sessions_repo=active_sessions_repo,
        sessions_repo=sessions_repo,
        games_repo=games_repo,
    )
    recovery = RecoveryManager(
        active_sessions_repo=active_sessions_repo,
        sessions_repo=sessions_repo,
    )
    process_monitor = ProcessMonitor(
        state=tracking_state,
        session_manager=session_manager,
    )

    result = recovery.recover()
    if result.recovered_sessions:
        logger.info("Recovered %d orphaned session(s)", len(result.recovered_sessions))
    if result.discarded_count:
        logger.info("Discarded %d invalid session(s)", result.discarded_count)

    theme_manager = ThemeManager()

    window = MainWindow(
        game_service=game_service,
        session_history_service=session_history_service,
        statistics_service=statistics_service,
        export_service=export_service,
        theme_manager=theme_manager,
        settings_repo=settings_repo,
        active_sessions_repo=active_sessions_repo,
        games_repo=games_repo,
        tracking_state=tracking_state,
    )

    def reload_tracked_games() -> None:
        games = game_service.get_all_games()
        tracked = [
            TrackedGame(
                game_id=g.id or 0,
                name=g.name,
                process_name=g.process_name,
                is_enabled=g.is_enabled,
            )
            for g in games
        ]
        process_monitor.reload_tracked_games(tracked)

    reload_tracked_games()

    sync_timer = QTimer()
    sync_timer.timeout.connect(reload_tracked_games)
    sync_timer.start(10000)

    theme_manager.apply_theme(app, theme_manager.current_theme)

    process_monitor.start()
    window.show()

    logger.info("Trackora started — database: %s", db_path)
    sys.exit(app.exec())


def _get_db_path() -> Path:
    """Return the database path.

    On Windows:  %APPDATA%/Trackora/trackora.db
    On Linux:     ~/.trackora/trackora.db
    When frozen:  same as above (never next to the executable).
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home()
        base = base / ".trackora"
        return base / "trackora.db"
    return base / "Trackora" / "trackora.db"


if __name__ == "__main__":
    main()
