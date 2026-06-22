# Repository Audit — Trackora v2.0.0

**Date:** 2026-06-22  
**Auditor:** Automated repository audit

---

## Directory Structure

```
Trackora/
├── trackora/              # Application core (12 source files)
│   ├── core/              #   Core modules (backup, migration, paths, env)
│   │   └── migrations/    #   Schema migration files
│   └── ...
├── database/              # Database layer (12 source files)
│   ├── models/            #   Data models
│   └── repositories/      #   CRUD repositories
├── services/              # Business logic & services (19 source files)
│   ├── crash/             #   Crash detection
│   └── support/           #   Support/reporting
├── tracker/               # Game detection & session tracking (14 source files)
│   └── discovery/         #   Game discovery detectors
├── trackora_stats/        # Statistics engine (5 source files)
├── ui/                    # PyQt6 UI layer (25 source files)
│   ├── dashboard/
│   ├── dialogs/
│   ├── games/
│   ├── history/
│   ├── settings/
│   ├── support_center/
│   ├── themes/
│   └── widgets/
├── models/                # Support domain models (4 source files)
├── tests/                 # Test suite (75 test files)
├── docs/                  # Documentation (101 files)
│   ├── architecture/      #   86 architecture/design documents
│   └── releases/          #   5 release milestone documents
├── installer/             # Inno Setup installer
├── scripts/               # Build helper scripts
├── .github/workflows/     # CI/CD pipeline
└── ui/icons/              # Application icons
```

## File Naming Consistency

| Category | Status |
|----------|--------|
| Python source (`.py`) | Consistent — snake_case throughout |
| Root config files | Mixed: `CHANGELOG.md`, `BUILD.md`, `README.md`, `AGENTS.md`, `pytest.ini`, `Trackora.spec` |
| Documentation | Mixed hyphen/underscore: `database_schema.md` vs `installation-guide.md` |
| Phase docs | Mostly consistent `phaseN-*.md`; one outlier `phase-7-completion-report.md` |
| Migration files | Consistent `vX_X_X_*.py` pattern |

## Unused / Dead Files

| File | Size | Issue | Action |
|------|------|-------|--------|
| `trackora/core/supabase_config.py` | ~200 B | Dead code with hardcoded Supabase credentials | **Deleted** |
| `scripts/generate_icons.py` | ~1 KB | One-time utility, not needed in repo | Keep (useful for rebuilds) |

## Temporary Files (Tracked in Git)

| File | Size | Issue | Action |
|------|------|-------|--------|
| `startup.log` | 66.6 KB | Runtime log file | **Removed from tracking**, added to `.gitignore` |
| `trackora/core/backup_manager.py,cover` | 18.6 KB | Coverage.py artifact | **Removed from tracking**, added to `.gitignore` |

## Build Artifacts

| Path | Status |
|------|--------|
| `build/` | Gitignored |
| `dist/` | Gitignored (empty) |
| `installer/Output/` | Gitignored (empty) |
| `__pycache__/` (42 dirs) | Gitignored |

## Duplicate Files

- **`__init__.py`** — 30 copies across packages (normal Python convention)
- **`conftest.py`** — 2 copies in different test directories (different content, normal)
- **`models.py`** — 2 copies in different packages (different content, normal)

## Verdict

Repository structure is clean. No duplicate source files. Build artifacts are properly gitignored. Two files were being tracked that should not have been — both have been corrected.
