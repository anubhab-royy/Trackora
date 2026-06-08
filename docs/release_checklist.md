# GameTracker Release Checklist

Version: 1.0 RC1

---

## Database

- [x] Database initializes correctly
- [x] WAL mode enabled
- [x] Foreign keys enabled
- [x] No schema errors
- [x] CRUD operations tested (320 tests pass)

---

## Tracking

- [x] Game detection works
- [x] Session creation works
- [x] Session completion works
- [x] Multiple launches tested
- [x] Long sessions tested
- [x] Process monitoring via psutil

---

## Recovery

- [x] Crash recovery tested
- [x] Shutdown recovery tested
- [x] Active session recovery tested
- [x] RecoveryManager verified with tests

---

## Statistics

- [x] Lifetime statistics verified
- [x] Daily statistics verified
- [x] Weekly statistics verified
- [x] Monthly statistics verified
- [x] Trend calculations verified
- [x] All statistics tested with data-driven tests

---

## UI

- [x] Dashboard loads (DashboardWidget + DashboardController)
- [x] Games screen functional (GamesView + GamesController)
- [x] History screen functional (HistoryView + HistoryController)
- [x] Charts screen functional (ChartsView + ChartsController)
- [ ] Settings screen functional (ui/settings/ module missing — planned)
- [x] Dark theme functional (ThemeManager with dark/light QSS)
- [x] Light theme functional
- [ ] Main window assembly missing (no main.py or MainWindow yet)
- [ ] Sidebar/navigation wiring missing (no QStackedWidget assembly)

---

## Charts

- [x] Daily chart functional (DailyActivityChart)
- [x] Monthly chart functional (MonthlyTrendChart)
- [x] Distribution chart functional (GameDistributionChart)

---

## Services

- [x] Tray icon functional (TrayService with context menu)
- [x] Startup registration functional (StartupService — Windows/Linux)
- [x] CSV export functional (ExportService)
- [x] JSON export functional (ExportService)
- [x] Logging functional (LoggingService with daily rotation)

---

## Testing

- [x] Unit tests pass (320 passed)
- [x] Integration tests pass
- [x] Coverage > 80% (verified)
- [ ] Integration audit completed (see integration_audit.md)

---

## Performance

- [ ] CPU usage < 1% (not yet measured — requires running application)
- [ ] Memory usage < 100 MB (not yet measured — requires running application)
- [ ] Startup time < 3 seconds (not yet measured — requires assembled application)

---

## Packaging

- [x] PyInstaller build documented (see BUILD.md)
- [ ] Executable built and tested (requires main.py + PyInstaller)
- [ ] Installer built (not yet — future enhancement)
- [ ] Uninstaller configured (not yet — future enhancement)

---

## Documentation

- [x] README complete
- [x] Installation guide complete (in README)
- [x] Build guide complete (BUILD.md)
- [x] Architecture document complete (docs/architecture.md)
- [x] Release checklist updated

---

## Release Approval

Release Candidate: **PENDING** — requires application entry point assembly

Date: 2026-06-09

---

Version: 1.0.0-rc1

Approved By:

---
