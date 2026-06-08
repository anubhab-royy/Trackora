# Building GameTracker

Build a standalone executable using PyInstaller.

## Prerequisites

```bash
pip install -r requirements.txt
```

## Creating the Entry Point

GameTracker requires a `main.py` entry point that assembles all layers. Create one following the architecture in `docs/architecture.md`:

```python
# main.py (example — customize as needed)
import sys
from PyQt6.QtWidgets import QApplication
from database.database_manager import DatabaseManager
from database.repositories import GamesRepository, SessionsRepository, ActiveSessionsRepository, SettingsRepository
from tracker import ProcessMonitor, SessionManager, RecoveryManager, TrackingState
from statistics import StatisticsService, PlaytimeCalculator
from services import GameService, SessionHistoryService, LoggingService, TrayService, StartupService, ExportService
from ui.themes import ThemeManager
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    # Database
    db = DatabaseManager("gametracker.db")
    conn = db.get_connection()
    games_repo = GamesRepository(conn)
    sessions_repo = SessionsRepository(conn)
    active_sessions_repo = ActiveSessionsRepository(conn)
    settings_repo = SettingsRepository(conn)

    # Theme
    theme_manager = ThemeManager()
    theme_manager.apply_to(app)

    # Tracking
    tracking_state = TrackingState()
    process_monitor = ProcessMonitor()
    session_manager = SessionManager(sessions_repo, active_sessions_repo, games_repo)
    recovery = RecoveryManager(sessions_repo, active_sessions_repo, games_repo)

    # Services
    game_service = GameService(games_repo)
    session_history_service = SessionHistoryService(sessions_repo, games_repo)
    stats_service = StatisticsService(sessions_repo, games_repo)
    playtime_calc = PlaytimeCalculator(sessions_repo)
    logging_service = LoggingService()
    startup_service = StartupService("GameTracker")
    tray_service = TrayService(app)
    export_service = ExportService(sessions_repo, games_repo, settings_repo)

    # Main window
    window = MainWindow(
        game_service=game_service,
        session_history_service=session_history_service,
        stats_service=stats_service,
        playtime_calculator=playtime_calc,
        export_service=export_service,
        theme_manager=theme_manager,
        settings_repo=settings_repo,
    )
    window.show()

    # Start tracking loop
    from PyQt6.QtCore import QTimer
    def tick():
        active = active_sessions_repo.get_all()
        for pid in list(active.keys()):
            if not process_monitor.is_running(pid):
                session_manager.end_session(pid)
        # Check for new game processes
        for game in games_repo.get_all():
            pid = process_monitor.find_process(game.executable_path)
            if pid and pid not in active:
                session_manager.start_session(game.id, pid, game.name)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(5000)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

## PyInstaller Build

```bash
# Install PyInstaller
pip install pyinstaller

# Build single-file executable
pyinstaller --onefile \
    --windowed \
    --name "GameTracker" \
    --add-data "ui/themes:ui/themes" \
    --hidden-import "PyQt6.QtSvg" \
    --hidden-import "pyqtgraph" \
    main.py

# The executable will be in dist/GameTracker.exe (Windows)
# or dist/GameTracker (Linux/macOS)
```

## Build Options

| Flag | Purpose |
|------|---------|
| `--onefile` | Single executable output |
| `--windowed` | No console window (Windows/macOS) |
| `--name` | Output executable name |
| `--add-data` | Include theme and resource files |
| `--hidden-import` | Force inclusion of dynamic imports |
| `--icon` | Set application icon (optional) |

## Troubleshooting

- **Missing modules**: Add `--hidden-import` flags for any dynamic imports
- **Theme files not found**: Verify the `--add-data` paths match your project structure
- **Database path**: Use `os.path.join(os.path.dirname(sys.executable), "gametracker.db")` in the executable context
- **Logging directory**: Create `logs/` next to the executable or use `APPDATA`/`~/.local/share`
