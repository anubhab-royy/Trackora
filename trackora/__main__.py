"""
Trackora entry point.

Assembles all layers via dependency injection and starts the application
with an upgrade lifecycle (schema check → backup → migrate), then normal
initialisation (repos → services → UI).
"""

from __future__ import annotations

import atexit
import logging
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from database.database_manager import DatabaseManager
from database.repositories import (
    ActiveSessionsRepository,
    GamesRepository,
    SessionsRepository,
    SettingsRepository,
)
from services.crash.crash_service import CrashService
from services.crash.diagnostic_service import DiagnosticService
from services.export_service import ExportService
from services.game_service import GameService
from services.logging_service import LoggingService
from services.session_history_service import SessionHistoryService
from services.startup_service import StartupService
from services.support.report_queue_service import ReportQueueService
from services.support.mongo_connection import MongoConnection
from services.support.mongo_report_service import MongoReportService
from services.support.support_service import SupportService
from services.update_announcements_service import UpdateAnnouncementsService
from trackora.core.backup_manager import BackupManager
from trackora.core.environment import CURRENT_ENVIRONMENT
from trackora.core.env import load_env_file
from trackora.core.migration_manager import MigrationManager
from trackora.core.paths import DATABASE_PATH, ensure_dirs
from trackora.core.schema_version import SchemaVersion
from trackora.core.schema_version_manager import SchemaVersionManager
from trackora.core.single_instance import acquire as _acquire_lock
from trackora.core.single_instance import release as _release_lock
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

logger = logging.getLogger(__name__)

_EXPECTED_GAME_COLUMNS: frozenset[str] = frozenset({
    "platform", "platform_id", "is_auto_discovered",
})


def _ensure_schema_columns(conn: object) -> None:
    """Add missing columns to the games table if schema.json was written
    without running actual migrations (e.g. a frozen build that couldn't
    discover migration modules via ``pkgutil.iter_modules``).

    Idempotent and safe to call on every startup when schema version matches.
    """
    import sqlite3

    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(games)")
    except sqlite3.OperationalError:
        return  # games table doesn't exist yet — nothing to fix
    existing = {row[1] for row in cursor.fetchall()}
    missing = _EXPECTED_GAME_COLUMNS - existing
    if not missing:
        return

    logger.warning("Games table missing columns: %s — adding them now", missing)
    for col in sorted(missing):
        if col == "platform":
            conn.execute("ALTER TABLE games ADD COLUMN platform TEXT DEFAULT NULL;")
        elif col == "platform_id":
            conn.execute("ALTER TABLE games ADD COLUMN platform_id TEXT DEFAULT NULL;")
        elif col == "is_auto_discovered":
            conn.execute("ALTER TABLE games ADD COLUMN is_auto_discovered INTEGER DEFAULT 0;")
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_games_platform ON games (platform);")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    logger.info("Added missing columns: %s", missing)


def main() -> None:
    LoggingService.setup()

    load_env_file()

    app_version = SchemaVersion.current_app_version()
    logger.info(
        "Trackora starting — version %s, environment %s",
        app_version, CURRENT_ENVIRONMENT.value,
    )

    if not _acquire_lock():
        logger.warning("Another Trackora instance is already running.")
        _app = QApplication(sys.argv)
        QMessageBox.warning(
            None, "Trackora",
            "Another instance of Trackora is already running.",
        )
        sys.exit(1)

    import atexit
    atexit.register(_release_lock)

    app = QApplication(sys.argv)
    app.setApplicationName("Trackora")
    app.setOrganizationName("Trackora")

    ensure_dirs()
    db = DatabaseManager(str(DATABASE_PATH))
    db.initialize()
    conn = db.connection

    # ── Upgrade Lifecycle ─────────────────────────────────────────
    schema_version_manager = SchemaVersionManager()
    data_version = schema_version_manager.read()
    compat = schema_version_manager.is_compatible(app_version, data_version)

    logger.info(
        "App version: %s, Data version: %s | status: %s",
        app_version, data_version, compat.status,
    )

    if not compat.can_proceed and compat.status == "newer_data":
        QMessageBox.critical(
            None, "Incompatible Database",
            compat.message,
        )
        logger.critical("Startup blocked: %s", compat.message)
        sys.exit(2)

    crash_service = CrashService(diagnostic_service=DiagnosticService())
    crash_result = crash_service.check_for_crash()
    if crash_result.has_crashed:
        logger.warning(
            "Previous session crashed — report %s saved to %s",
            crash_result.report.report_id if crash_result.report else "unknown",
            crash_result.report_path,
        )
    crash_service.mark_startup()

    if compat.status == "first_run":
        schema_version_manager.write(app_version)
        logger.info("First run — schema version set to %s", app_version)

    elif compat.status == "ok":
        _ensure_schema_columns(conn)

    elif compat.status == "needs_migration":
        logger.info("Pre-migration backup started")
        backup_manager = BackupManager(schema_version_manager)
        bk = backup_manager.create_backup(backup_type="pre_migration")
        if not bk.success:
            QMessageBox.critical(
                None, "Backup Failed",
                f"Could not create a backup before migration: {bk.error}\n\n"
                "Please ensure the backup directory is writable and has "
                "sufficient disk space.",
            )
            logger.critical("Pre-migration backup failed: %s", bk.error)
            sys.exit(3)

        logger.info("Pre-migration backup completed: %s", bk.backup_id)

        migration_manager = MigrationManager(
            connection=conn,
            schema_version_manager=schema_version_manager,
            backup_manager=backup_manager,
        )
        pending = migration_manager.get_pending_migrations()
        logger.info("Migration started — %d pending", len(pending))
        migration_result = migration_manager.apply_all()

        for attempt in migration_result.results:
            if attempt.success:
                logger.info(
                    "Migration applied: %s (%dms)",
                    attempt.migration_id, attempt.duration_ms,
                )
            else:
                logger.warning(
                    "Migration failed: %s (%dms) — %s",
                    attempt.migration_id, attempt.duration_ms, attempt.error,
                )

        if not migration_result.success:
            logger.critical(
                "Migration failed — applied: %d, failed: %d. "
                "Startup aborted.",
                migration_result.applied_count,
                migration_result.failed_count,
            )
            QMessageBox.critical(
                None, "Migration Failed",
                f"Database migration failed.\n\n"
                f"Applied: {migration_result.applied_count}\n"
                f"Failed: {migration_result.failed_count}\n\n"
                "Trackora cannot start with an incompletely migrated "
                "database.\n\n"
                "A pre-migration backup was created automatically. "
                "To restore, run:\n"
                "  trackora restore <backup_id>",
            )
            sys.exit(4)

        if migration_result.final_version:
            schema_version_manager.write(
                SchemaVersion.from_string(migration_result.final_version),
                description=f"Migration to {migration_result.final_version}",
            )
            logger.info(
                "Schema version updated to %s", migration_result.final_version,
            )
    # ── End Upgrade Lifecycle ─────────────────────────────────────

    games_repo = GamesRepository(conn)
    sessions_repo = SessionsRepository(conn)
    active_sessions_repo = ActiveSessionsRepository(conn)
    settings_repo = SettingsRepository(conn)

    game_service = GameService(games_repo)
    session_history_service = SessionHistoryService(sessions_repo, games_repo)
    statistics_service = StatisticsService(sessions_repo, games_repo)
    PlaytimeCalculator(sessions_repo, games_repo)
    export_service = ExportService(sessions_repo, games_repo, settings_repo)

    # ------------------------------------------------------------------
    # Reporting backend (MongoDB, fallback to offline queue)
    # ------------------------------------------------------------------
    mongo = MongoConnection(
        database_name=os.environ.get("MONGODB_DATABASE"),
    )
    if mongo.health_check():
        logger.info("MongoDB reporting: connected")
    else:
        logger.warning(
            "MongoDB reporting: not available — "
            "reports will be queued offline."
        )
    report_service = MongoReportService(connection=mongo)
    queue_service = ReportQueueService()
    announcements_service = UpdateAnnouncementsService(
        remote_url=(
            "https://raw.githubusercontent.com/"
            "anomalco/trackora-announcements/main/announcements.json"
        ),
    )
    support_service = SupportService(
        github_service=report_service,
        queue_service=queue_service,
        announcements_service=announcements_service,
    )

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
        support_service=support_service,
        report_service=report_service,
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

    atexit.register(crash_service.mark_clean_shutdown)
    logger.info("Trackora started — database: %s", DATABASE_PATH)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
