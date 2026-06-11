# Trackora v1.0.0

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

- Windows 10/11 (recommended), Linux, macOS
- Python 3.13+ (for development only)
- 50 MB disk space

## Installation

### Windows Installer (Recommended)

Download the latest installer from the [Releases](https://github.com/yourusername/trackora/releases) page.

1. Run `Trackora-Setup-1.0.0.exe`
2. Follow the installation wizard
3. Launch Trackora from the Start Menu

### Portable Executable (Windows)

Download `Trackora.exe` from the Releases page and run it directly.

### Development Installation

```bash
git clone https://github.com/yourusername/trackora.git
cd trackora
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt
python -m trackora
```

## Runtime Data Locations

When packaged, Trackora stores its data at:

| Data        | Windows Path                               |
|-------------|--------------------------------------------|
| Database    | `%APPDATA%\Trackora\trackora.db`           |
| Logs        | `%APPDATA%\Trackora\logs\`                 |

No data is stored in the installation directory. Uninstalling Trackora will leave your data intact.

## Usage

```bash
python -m trackora
```

Or run the installed executable from the Start Menu.

## Building from Source

See [BUILD.md](BUILD.md) for detailed build instructions for PyInstaller executables and Inno Setup installers.

## Project Structure

```
trackora/
├── database/              # Database layer
│   ├── database_manager.py
│   ├── models/            # Data models
│   └── repositories/      # CRUD repositories
├── tracker/               # Process monitoring & session management
│   ├── process_monitor.py
│   ├── session_manager.py
│   ├── recovery_manager.py
│   └── tracking_state.py
├── trackora_stats/        # Statistics engine
│   ├── statistics_service.py
│   ├── playtime_calculator.py
│   └── trend_analyzer.py
├── services/              # Business logic & system services
│   ├── game_service.py
│   ├── session_history_service.py
│   ├── export_service.py
│   ├── startup_service.py
│   ├── tray_service.py
│   └── logging_service.py
├── ui/                    # PyQt6 user interface
│   ├── dashboard/         # Statistics dashboard
│   ├── games/             # Game management
│   ├── history/           # Session history browser
│   ├── widgets/           # Charts & reusable widgets
│   ├── themes/            # Dark/light theme manager
│   ├── icons/             # Application icons
│   └── controllers/       # UI controllers
├── tests/                 # Pytest test suite
├── docs/                  # Documentation
├── installer/             # Inno Setup installer scripts
├── Trackora.spec          # PyInstaller spec file
├── BUILD.md               # Build instructions
├── requirements.txt
└── README.md
```

## Development

```bash
# Run tests
python -m pytest

# With coverage
python -m pytest --cov=trackora --cov-report=term-missing
```

### Packaging for Distribution

```bash
# Build executable
pyinstaller Trackora.spec

# Create installer (requires Inno Setup)
iscc installer/Trackora.iss
```

## License

MIT
