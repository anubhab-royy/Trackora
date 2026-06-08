# GameTracker

A lightweight, privacy-first desktop application that automatically tracks your gaming sessions and provides detailed analytics. Runs silently in the system tray with minimal resource usage.

## Features

- **Automatic Game Detection** — Detects when tracked games are running via process monitoring
- **Session Tracking** — Records session start/end times with automatic crash recovery
- **Session History** — Browse, search, and filter past sessions
- **Statistics Dashboard** — Lifetime, daily, weekly, and monthly playtime statistics
- **Interactive Charts** — Daily activity, monthly trends, and game distribution charts
- **System Tray** — Minimizes to tray, tracking continues in background
- **Startup Registration** — Optionally launches with Windows
- **Export & Backup** — Export sessions to CSV, full backup to JSON
- **Dark & Light Themes** — Toggle between dark and light mode
- **Local-Only Storage** — All data stored in SQLite, no cloud or accounts required

## Requirements

- Python 3.13+
- PyQt6
- psutil
- pyqtgraph
- SQLite3 (included with Python)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/gametracker.git
cd gametracker

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python -m gametracker
```

Or build a standalone executable (see [BUILD.md](BUILD.md)).

## Application Wiring

> **Note:** GameTracker requires an application entry point (`main.py`) and a main window to wire all components together. See `docs/architecture.md` for the component architecture and `BUILD.md` for build instructions.

## Project Structure

```
gametracker/
├── database/              # Database layer
│   ├── database_manager.py
│   ├── models.py
│   └── repositories/      # CRUD repositories
├── tracker/               # Process monitoring & session management
│   ├── process_monitor.py
│   ├── session_manager.py
│   ├── recovery_manager.py
│   └── tracking_state.py
├── statistics/            # Statistics engine
│   ├── statistics_service.py
│   ├── playtime_calculator.py
│   └── trend_analyzer.py
├── services/              # Business logic & system services
│   ├── game_service.py
│   ├── session_history_service.py
│   ├── export_service.py
│   ├── startup_service.py
│   ├── tray_service.py
│   ├── logging_service.py
│   └── formatting.py
├── ui/                    # PyQt6 user interface
│   ├── dashboard/         # Statistics dashboard
│   ├── games/             # Game management
│   ├── history/           # Session history browser
│   ├── widgets/           # Charts & reusable widgets
│   ├── themes/            # Dark/light theme manager
│   ├── controllers/       # UI controllers
│   └── dashboard_controller.py
├── tests/                 # Pytest test suite (320+ tests)
├── docs/                  # Documentation
├── BUILD.md               # Build instructions
├── requirements.txt
└── README.md
```

## Development

```bash
# Run tests
python -m pytest

# With coverage
python -m pytest --cov=gametracker --cov-report=term-missing
```

## Architecture

GameTracker follows a layered architecture:

1. **Database Layer** — SQLite with WAL mode, repositories for CRUD
2. **Tracking Layer** — Process monitoring via psutil, session management
3. **Statistics Layer** — Playtime calculations, trend analysis
4. **UI Layer** — PyQt6 widgets, controllers, theming
5. **Services Layer** — Tray, startup, export, logging

See `docs/architecture.md` for the full architecture document.

## License

MIT
