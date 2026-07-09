# Trackora

**Automatic Gaming Session Tracker for Windows**

Trackora runs silently in your system tray, automatically detects when you play games, and provides detailed analytics of your gaming habits. Privacy-first — all data stays on your machine.

![Trackora Dashboard](docs/assets/Dashboard.png)

## Key Features

- **Automatic Game Detection** — Detects running games via process monitoring. Works with any executable.
- **Game Discovery** — Automatically finds installed games from Steam, Epic, Battle.net, EA, Ubisoft, and Riot.
- **Session Tracking** — Records start/end times with automatic crash recovery.
- **Analytics Dashboard** — Lifetime, daily, weekly, and monthly playtime statistics.
- **Interactive Charts** — Daily activity heatmap, monthly trends, game distribution.
- **Session History** — Browse, search, and filter past sessions with export to CSV/JSON.
- **Backup & Recovery** — Automatic database backup and crash-safe session recovery.
- **MongoDB Reporting** — Optional cloud reporting to your own MongoDB Atlas cluster.
- **Support Center** — In-app bug reports and feature requests via GitHub Issues.
- **Silent Startup** — Minimize to system tray on launch for frictionless background execution.
- **Background Updates** — Off-thread update checker keeps main UI fast and responsive.
- **Dark & Light Themes** — Toggle between dark and light mode.
- **Local-Only by Default** — All data stored in SQLite. No cloud, no accounts, no telemetry.

## Installation

### Windows Installer (Recommended)

1. Download `Trackora-Setup-2.0.1.exe` from the [Releases](https://github.com/anubhab-royy/Trackora/releases) page
2. Run the installer
3. Launch Trackora from the Start Menu

The installer automatically handles upgrades from older versions and migrates your data.

### Portable Executable

Download `Trackora.exe` from the Releases page and run it directly. No installation needed.

### System Requirements

- Windows 10 or 11 (64-bit)
- 50 MB disk space
- 1 GB RAM

## Development Setup

### Prerequisites

- Python 3.13+
- Git

### Quick Start

```bash
git clone https://github.com/anubhab-royy/Trackora.git
cd Trackora
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
python -m trackora
```

### Run Tests

```bash
python -m pytest
```

### Build Executable

```bash
pip install pyinstaller
pyinstaller Trackora.spec
```

See [BUILD.md](BUILD.md) for detailed instructions.

## Architecture Overview

Trackora is a modular monolith with 7 layers:

| Layer | Directory | Responsibility |
|-------|-----------|----------------|
| Tracking | `tracker/` | Game detection, session management, crash recovery |
| Database | `database/` | SQLite persistence (models, repositories) |
| Statistics | `trackora_stats/` | Playtime calculation, trend analysis |
| Services | `services/` | Business logic, system tray, export, updates |
| UI | `ui/` | PyQt6 views, controllers, charts, themes |
| Support | `models/support/` | Bug reports, feature requests |
| Core | `trackora/core/` | Backup, migration, environment, paths |

## Data Storage

| Data | Windows Path |
|------|-------------|
| Database | `%APPDATA%\Trackora\trackora.db` |
| Logs | `%APPDATA%\Trackora\logs\` |
| Backups | `%APPDATA%\Trackora\backups\` |

No data is stored in the installation directory. Uninstalling preserves your data.

## Roadmap

### v2.1.0 (Planned)
- **Game activity insights** — Per-game achievements, playtime goals
- **Session tagging** — Custom labels and notes for sessions
- **Plugins** — Community-extensible detection and reporting

### Future Releases
- **Cross-platform** — Linux and macOS native builds

### Completed & Released
- **v2.0.1 (Released)** — Silent startup (`--silent`), background update thread, direct installer download links, cascading game deletion, robust offline queue schema validations and quarantine gates.
- **v2.0.0 (Released)** — MongoDB cloud backups, Automatic game discovery from 6 launchers (Steam, Epic, Battle.net, EA, Ubisoft, Riot), interactive pyqtgraph analytics, database backup manager and schema version migrations.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. All contributions welcome — bug reports, feature requests, documentation, and code.

## Security

Report vulnerabilities privately per our [security policy](SECURITY.md).

## License

[MIT](LICENSE.md)
