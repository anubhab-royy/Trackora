# Trackora v2.0.0 — Release Notes

## What's New in Trackora v2.0.0

Trackora v2.0.0 transforms the app from a simple session tracker into a full-featured gaming analytics platform.

### 🎮 Automatic Game Discovery

Trackora now automatically finds installed games from:
- **Steam** — Reads library folders and app manifests
- **Epic Games** — Detects manifests in the Epic launcher directory
- **Battle.net** — Parses Battle.net configuration
- **EA App** — Detects EA-installed games
- **Ubisoft Connect** — Reads Ubisoft installation data
- **Riot Games** — Detects League of Legends, VALORANT, and more

No manual configuration needed. Games appear automatically.

### 📊 Analytics Dashboard

A redesigned dashboard shows you:
- Lifetime playtime and session counts
- Daily, weekly, and monthly statistics
- Game-specific breakdowns with playtime per game
- Interactive charts: daily activity heatmap, monthly trends, game distribution

### 📈 Interactive Charts

Three new chart types give you visual insight into your gaming habits:
- **Daily Activity** — See which hours you play most
- **Monthly Trends** — Track playtime changes over months
- **Game Distribution** — Compare time spent across games

### ☁️ MongoDB Support (Optional)

Connect your own MongoDB Atlas cluster for cloud-based reporting. All data stays local by default — this is an opt-in feature for users who want remote access to their statistics.

### 🔄 Backup & Recovery

Trackora now automatically handles:
- Database backup with JSON export
- Crash detection and recovery
- Session state persistence across restarts
- Safe shutdown and startup state management

### ⬆️ Upgrade Framework

Upgrading from the old GameTracker v0.9.0 or Trackora v1.0.0 is seamless:
- Automatic schema migration
- Old data is preserved and migrated
- Installer handles the entire upgrade process

### 🆘 Support Center

Submit bug reports and feature requests directly from the app:
- In-app form submission
- Optional offline queue for when you're not connected
- Automatic crash report generation

### 🛠 For Developers

- Full test suite with 370+ tests
- Type hints throughout the codebase
- Performance benchmarks validated against NFR targets
- Clean modular architecture for easy contribution

## Installation

Download `Trackora_Setup_v2.0.0.exe` from the Releases page and run it. The installer will:
1. Detect and upgrade any previous installation
2. Migrate your existing data
3. Set up Trackora with all your settings preserved

### System Requirements

- Windows 10 or 11 (64-bit)
- 50 MB disk space
- 1 GB RAM

## Upgrade Notes

- If upgrading from GameTracker v0.9.0 or Trackora v1.0.0, your data will be automatically migrated
- The installer preserves your SQLite database in `%APPDATA%\Trackora\`
- No configuration changes needed after upgrade

## Known Limitations

- Game discovery requires game launchers to be installed and configured
- MongoDB reporting requires a self-hosted MongoDB Atlas cluster
- Linux and macOS builds are not yet available as distributable packages
- Some antivirus software may flag the PyInstaller-packaged executable (false positive)
