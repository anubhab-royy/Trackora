# Runtime Environment Architecture

## Principles

1. **Only `environment.py` determines runtime environment.**

2. **Only `paths.py` determines runtime paths.**

3. **No module may read `APP_ENV` directly.**

4. **No module may read `APPDATA` directly.**

5. **No module may construct `Trackora` storage paths.**

6. **All filesystem paths originate from `paths.py`.**

7. **Future features must extend `paths.py` rather than creating independent storage locations.**

---

## Environment Selection

The runtime environment is selected via the `APP_ENV` environment variable:

| `APP_ENV`       | Runtime Directory  |
|-----------------|--------------------|
| `production`    | `%APPDATA%\Trackora`      |
| `development`   | `%APPDATA%\Trackora-Dev`  |

Default: `production`.

Only `trackora/core/environment.py` may read `APP_ENV`.

---

## Architecture Boundary

The following files form the architectural boundary:

```
trackora/core/
├── __init__.py
├── environment.py   — Single source of truth for runtime environment
├── paths.py         — Single source of truth for application storage paths
└── build_info.py    — Build channel and version information
```

### `environment.py`

Provides:

- `Environment` enum: `PRODUCTION`, `DEVELOPMENT`
- `CURRENT_ENVIRONMENT`: The resolved runtime environment

### `paths.py`

Provides:

- `BASE_DIR` — Root application storage directory
- `DATABASE_PATH` — SQLite database path
- `LOGS_DIR` — Log file directory
- `REPORTS_DIR` — Generic reports directory
- `CRASH_DIR` — Crash report storage
- `CACHE_DIR` — Cache files
- `CONFIG_DIR` — Configuration files
- `SCREENSHOTS_DIR` — Screenshot storage
- `BACKUPS_DIR` — Backup storage
- `EXPORTS_DIR` — Export storage
- `IMPORTS_DIR` — Import storage
- `ensure_dirs()` — Create all runtime directories

### `build_info.py`

Provides:

- `BUILD_CHANNEL` — Current build channel (production/development)
- `BUILD_VERSION` — Current application version

---

## Enforcement Rules

### Rule 1 — APP_ENV Isolation

Fail if any file except `trackora/core/environment.py` contains:

- `APP_ENV`

### Rule 2 — APPDATA Isolation

Fail if any file except `trackora/core/paths.py` contains:

- `APPDATA` / `appdata` environment variable reads

### Rule 3 — Storage Path Isolation

Fail if any file outside `trackora/core/paths.py` constructs application
storage paths using `"Trackora"` or `"Trackora-Dev"` as path components.

Not flagged:

- `import trackora`
- Log messages mentioning Trackora
- UI labels or window titles
- Documentation and comments

---

## Examples

### Correct usage

```python
from trackora.core.paths import SCREENSHOTS_DIR, LOGS_DIR

# Use the pre-defined path constants
screenshots = SCREENSHOTS_DIR / "game_01.png"
log_path = LOGS_DIR
```

### Incorrect usage

```python
# BAD: Direct APPDATA access
Path(os.environ.get("APPDATA")) / "Trackora" / "screenshots"

# BAD: Hardcoded path
"%APPDATA%\\Trackora\\logs"

# BAD: Home-based fallback
Path.home() / "AppData" / "Roaming" / "Trackora"
```

---

## Adding New Storage Paths

When a new feature requires a filesystem storage location:

1. Add the new path constant to `trackora/core/paths.py`
2. Add `mkdir` call to `ensure_dirs()` if needed
3. Import from `trackora.core.paths` in the feature code

Do not add new `os.environ.get("APPDATA")` or `Path.home() / "AppData"` calls anywhere in the codebase.
