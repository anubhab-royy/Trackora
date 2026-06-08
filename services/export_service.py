"""
ExportService — Phase 9
CSV export and JSON backup for GameTracker.

Requirements:
    AC-009 — CSV Export
        File created, sessions included, format valid, opens in Excel.
    AC-010 — JSON Backup
        Backup file contains Games, Sessions, Settings.

Architecture notes:
    - Uses repositories for all data access. No SQL.
    - No UI. Callers (controllers) handle file dialogs and user feedback.
    - CSV uses Excel-compatible formatting (UTF-8 BOM, comma separator).
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from database.repositories.games_repository import GamesRepository
from database.repositories.sessions_repository import SessionsRepository
from database.repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)


class ExportService:
    """
    Service for exporting GameTracker data to CSV and JSON.

    Args:
        sessions_repository: Injected SessionsRepository instance.
        games_repository:    Injected GamesRepository instance.
        settings_repository: Injected SettingsRepository instance.
    """

    def __init__(
        self,
        sessions_repository: SessionsRepository,
        games_repository: GamesRepository,
        settings_repository: SettingsRepository,
    ) -> None:
        self._sessions = sessions_repository
        self._games = games_repository
        self._settings = settings_repository

    # ------------------------------------------------------------------
    # CSV Export (AC-009)
    # ------------------------------------------------------------------

    def export_csv(self, filepath: str | Path) -> bool:
        """
        Export all sessions to a CSV file.

        CSV format (Excel-compatible):
            Date,Game,Duration (minutes),Start Time,End Time

        Args:
            filepath: Destination file path.

        Returns:
            True on success, False on failure.
        """
        try:
            path = Path(filepath)
            sessions = self._sessions.get_all()
            games_map = self._build_games_map()

            path.parent.mkdir(parents=True, exist_ok=True)

            with path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Date", "Game", "Duration (minutes)",
                    "Start Time", "End Time",
                ])

                for session in sessions:
                    game_name = games_map.get(session.game_id, f"Unknown ({session.game_id})")
                    duration_min = session.duration_seconds / 60.0
                    writer.writerow([
                        session.start_time.strftime("%Y-%m-%d"),
                        game_name,
                        round(duration_min, 1),
                        session.start_time.strftime("%H:%M"),
                        session.end_time.strftime("%H:%M"),
                    ])

            logger.info("CSV export written: %s (%d sessions)", path, len(sessions))
            return True

        except Exception as exc:
            logger.error("CSV export failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # JSON Backup (AC-010)
    # ------------------------------------------------------------------

    def export_backup(self, filepath: str | Path) -> bool:
        """
        Export all games, sessions, and settings to a JSON backup file.

        Args:
            filepath: Destination file path.

        Returns:
            True on success, False on failure.
        """
        try:
            path = Path(filepath)
            games = self._games.get_all()
            sessions = self._sessions.get_all()
            settings_list = self._settings.get_all()

            backup: dict[str, Any] = {
                "version": "1.0",
                "exported_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                "games": [
                    {
                        "id": g.id,
                        "name": g.name,
                        "process_name": g.process_name,
                        "executable_path": g.executable_path,
                        "icon_path": g.icon_path,
                        "is_enabled": g.is_enabled,
                        "first_played": g.first_played.isoformat() if g.first_played else None,
                        "last_played": g.last_played.isoformat() if g.last_played else None,
                        "created_at": g.created_at.isoformat() if g.created_at else None,
                        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
                    }
                    for g in games
                ],
                "sessions": [
                    {
                        "id": s.id,
                        "game_id": s.game_id,
                        "start_time": s.start_time.isoformat(),
                        "end_time": s.end_time.isoformat(),
                        "duration_seconds": s.duration_seconds,
                        "created_at": s.created_at.isoformat() if s.created_at else None,
                    }
                    for s in sessions
                ],
                "settings": [
                    {
                        "key": st.key,
                        "value": st.value,
                        "updated_at": st.updated_at.isoformat() if st.updated_at else None,
                    }
                    for st in settings_list
                ],
            }

            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(backup, f, indent=2, ensure_ascii=False)

            logger.info(
                "JSON backup written: %s (%d games, %d sessions, %d settings)",
                path,
                len(games),
                len(sessions),
                len(settings_list),
            )
            return True

        except Exception as exc:
            logger.error("JSON backup failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_games_map(self) -> dict[int, str]:
        """Build a mapping of game_id -> game_name."""
        games = self._games.get_all()
        return {g.id: g.name for g in games} if games else {}
