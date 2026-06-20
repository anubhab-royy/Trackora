# SchemaVersionManager — Implementation Plan

**Component:** `trackora/core/schema_version_manager.py`  
**Supporting Types:** `trackora/core/schema_version.py`  
**Status:** Ready for Implementation  
**Target:** Trackora v2.0.0  

---

## 1. File Manifest

| File | Contents |
|------|----------|
| `trackora/core/schema_version.py` | `SchemaVersion` frozen dataclass, `CompatibilityStatus` dataclass, version comparison helpers |
| `trackora/core/schema_version_manager.py` | `SchemaVersionManager` class — reads/writes/validates `schema.json` |
| `tests/test_schema_version.py` | Unit tests for `SchemaVersion` value object |
| `tests/test_schema_version_manager.py` | Unit tests for `SchemaVersionManager` |
| `tests/test_upgrade_lifecycle.py` | Integration tests for full lifecycle (partial — covers SchemaVersionManager portion) |
| `tests/architecture/test_schema_version_isolation.py` | Architecture enforcement: only this module may read/write `schema.json` |

No existing files are modified for this component alone. `__main__.py` changes come later when all three managers are integrated.

---

## 2. Responsibilities

### Primary

- **Single source of truth** for the current schema version of user data on disk
- **Gatekeeper** that prevents the application from running on incompatible data
- **Version recorder** that persists the schema version after successful migration

### Specific Duties

1. Read `schema.json` from `%APPDATA%/Trackora/` and parse it into a `SchemaVersion`
2. Write `schema.json` atomically (`.tmp` + rename) after migrations complete
3. Compare two `SchemaVersion` instances using strict semver rules (major.minor.patch)
4. Determine compatibility: can the current app version work with this data version?
5. Handle the full matrix: first run, same version, needs migration, newer data, corrupt file
6. Validate `schema.json` structure and content — reject malformed or missing fields
7. Provide a clean `delete()` for testing and emergency recovery

### Non-Responsibilities

- Does NOT apply migrations (that is `MigrationManager`)
- Does NOT create backups (that is `BackupManager`)
- Does NOT know about database internals, repositories, services, or UI
- Does NOT write to any location outside `BASE_DIR`

---

## 3. Public API Design

### 3.1 SchemaVersion (Value Object)

**File:** `trackora/core/schema_version.py`

```python
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaVersion:
    """Immutable semantic version for schema tracking.

    Follows strict MAJOR.MINOR.PATCH semver semantics.
    PATCH must be 0 for initial version of each minor release.
    """

    major: int
    minor: int
    patch: int

    # ── Factories ────────────────────────────────────────────────

    @classmethod
    def from_string(cls, version: str) -> SchemaVersion:
        """Parse 'MAJOR.MINOR.PATCH' string.
        Raises ValueError on invalid format.
        Acceptable: '2.0.0', '1.1.0', '0.9.0'
        Reject: '2.0', '2.0.0.0', 'v2.0.0', 'abc'
        """

    @classmethod
    def current_app_version(cls) -> SchemaVersion:
        """Return SchemaVersion from trackora.__version__ (currently '1.1.0').
        Uses from_string(trackora.__version__).
        """

    # ── Comparison ───────────────────────────────────────────────

    def __lt__(self, other: SchemaVersion) -> bool: ...
    def __le__(self, other: SchemaVersion) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __ne__(self, other: object) -> bool: ...
    def __gt__(self, other: SchemaVersion) -> bool: ...
    def __ge__(self, other: SchemaVersion) -> bool: ...

    def __str__(self) -> str:
        """Return 'MAJOR.MINOR.PATCH' string, e.g. '2.0.0'."""

    # ── Validation ───────────────────────────────────────────────

    @classmethod
    def is_valid_format(cls, version: str) -> bool:
        """Return True if string matches MAJOR.MINOR.PATCH pattern with non-negative integers."""

    # ── Serialization ────────────────────────────────────────────

    def to_dict(self) -> dict[str, int]:
        """Return {'major': X, 'minor': Y, 'patch': Z}."""
```

### 3.2 CompatibilityStatus

**File:** `trackora/core/schema_version.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompatibilityStatus:
    """Result of comparing app version to data version.

    Attributes:
        can_proceed:  True if the application may continue starting up.
        status:       Categorical result string.
        message:      Human-readable explanation for logging/UI.
    """

    can_proceed: bool
    status: str  # "ok" | "needs_migration" | "newer_data" | "first_run" | "error"
    message: str
```

Status semantics:

| status | can_proceed | Meaning | User-Facing Message |
|---|---|---|---|
| `ok` | True | Data version matches app version | None (silent) |
| `needs_migration` | True | Data version is older; migration will run | None (silent — migration is automatic) |
| `first_run` | True | No `schema.json`; fresh install | None (silent) |
| `newer_data` | False | Data version exceeds app version | "This database requires Trackora X.Y.Z or newer. Please update Trackora." |
| `error` | False | `schema.json` is corrupt or unreadable | "Schema version information is corrupted. Trackora cannot start. Please restore from backup or contact support." |

### 3.3 SchemaVersionManager

**File:** `trackora/core/schema_version_manager.py`

```python
from __future__ import annotations

from pathlib import Path


class SchemaVersionManager:
    """Manages the schema.json lifecycle.

    This is the single source of truth for the schema version of
    user data on disk.  It lives in trackora.core because it must be
    usable before the database layer is initialised.

    The manager stores version metadata in a single JSON file at
    BASE_DIR / "schema.json".  All writes are atomic (write to .tmp,
    then os.replace) to prevent partial-file reads after crashes.
    """

    def __init__(
        self,
        schema_path: Path | None = None,
    ) -> None:
        """Initialise the manager.

        Args:
            schema_path: Optional explicit path to schema.json.
                         Defaults to BASE_DIR / 'schema.json'
                         where BASE_DIR comes from trackora.core.paths.
        """

    # ── Read ───────────────────────────────────────────────────

    def read(self) -> SchemaVersion | None:
        """Read the schema version from schema.json.

        Returns:
            SchemaVersion if the file exists and is valid.
            None if the file does not exist (first run).

        Raises:
            SchemaVersionError: If the file exists but is corrupt,
                                has invalid format, or is unreadable.
        """

    # ── Write ──────────────────────────────────────────────────

    def write(self, version: SchemaVersion, description: str = "") -> None:
        """Atomically write schema version to schema.json.

        Uses .tmp + os.replace pattern for crash safety.
        Creates parent directory if it does not exist.

        Args:
            version:     The schema version to persist.
            description: Optional human-readable description.

        Raises:
            OSError: If the file cannot be written (permissions, disk full).
        """

    # ── Compatibility ──────────────────────────────────────────

    def is_compatible(
        self,
        app_version: SchemaVersion,
        data_version: SchemaVersion | None,
    ) -> CompatibilityStatus:
        """Determine whether the application can run with this data version.

        Args:
            app_version:  The schema version this application supports.
            data_version: The schema version of the user data on disk,
                          or None if no schema.json exists.

        Returns:
            CompatibilityStatus with can_proceed, status, and message.
        """

    # ── Comparison (delegates to SchemaVersion) ────────────────

    @staticmethod
    def compare(
        a: SchemaVersion, b: SchemaVersion
    ) -> int:
        """Compare two versions.

        Returns -1 if a < b, 0 if a == b, 1 if a > b.
        """

    # ── Delete ─────────────────────────────────────────────────

    def delete(self) -> None:
        """Delete schema.json.  Intended for testing only.
        Raises OSError if deletion fails (excluding FileNotFoundError).
        """

    # ── Helpers ────────────────────────────────────────────────

    def exists(self) -> bool:
        """Return True if schema.json exists on disk."""
```

---

## 4. Internal Data Structures

### 4.1 schema.json Format

**Location:** `%APPDATA%/Trackora/schema.json`

```json
{
  "schema_version": "2.0.0",
  "app_version": "2.0.0",
  "updated_at": "2026-06-20T12:00:00Z",
  "description": "Schema version after application of v2.0.0 migrations"
}
```

### 4.2 Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | `string` | Yes | `MAJOR.MINOR.PATCH` of the database schema. This is the authoritative version. |
| `app_version` | `string` | Yes | The Trackora version that last wrote this file. Informational only; not used for compatibility checks. |
| `updated_at` | `string` | Yes | ISO-8601 UTC timestamp of last write. |
| `description` | `string` | No | Free-text description of what this version means. |

### 4.3 Internal State

The `SchemaVersionManager` holds no mutable internal state. `__init__` stores only:

```python
self._schema_path: Path  # resolved path to schema.json
```

No cache, no lazy loading, no mutable counters. Every `read()` reads from disk. Every `write()` writes to disk. This keeps the manager stateless and predictable.

### 4.4 JSON Schema Validation

On `read()`, the manager validates the JSON file against these rules:

```
Required top-level keys:  schema_version, app_version, updated_at
schema_version format:    must match ^\d+\.\d+\.\d+$
app_version format:       must match ^\d+\.\d+\.\d+$
updated_at format:        must be valid ISO-8601
Extra keys:               silently ignored (forward-compatible)
```

If validation fails, the manager raises `SchemaVersionError` with the specific reason.

### 4.5 Exception Classes

```python
class SchemaVersionError(Exception):
    """Raised when schema.json is corrupt, invalid, or unreadable.

    The corrupt file is renamed to schema.json.corrupt.<timestamp>
    before the exception is raised, so the application can recover
    by creating a fresh schema.json (first-run treatment).
    """
```

---

## 5. Error Handling

### 5.1 Error Matrix

| Condition | Detected In | Behavior | Recovery |
|---|---|---|---|
| File does not exist | `read()` | Return `None` | Caller treats as first run |
| File exists but empty | `read()` | Raise `SchemaVersionError("empty file")` | Rename to `.corrupt`, return `None` |
| File exists but invalid JSON | `read()` (json.JSONDecodeError) | Raise `SchemaVersionError("invalid JSON")` | Rename to `.corrupt`, return `None` |
| Missing `schema_version` key | `read()` (KeyError) | Raise `SchemaVersionError("missing key")` | Rename to `.corrupt`, return `None` |
| `schema_version` is not valid semver | `read()` (ValueError from `from_string`) | Raise `SchemaVersionError("invalid version")` | Rename to `.corrupt`, return `None` |
| Permission denied reading | `read()` (PermissionError) | Raise `SchemaVersionError("permission denied")` | Log, propagate — caller must block startup |
| Write fails (disk full) | `write()` (OSError) | Raise `OSError` with detail | Caller must abort migration |
| Write fails (permissions) | `write()` (PermissionError) | Raise `OSError` with detail | Caller must abort migration |
| Delete called on missing file | `delete()` | Silently succeed (FileNotFoundError suppressed) | Normal — test cleanup |
| `schema_version` is a float not string | `read()` | Detect non-string, raise `SchemaVersionError` | Rename to `.corrupt`, return `None` |

### 5.2 Corrupt File Handling

When `read()` encounters a corrupt file it cannot parse:

1. Read current contents into a diagnostic log message
2. Rename `schema.json` → `schema.json.corrupt.<YYYYMMDD_HHMMSS>`
3. Return `None` (same as first run)
4. Log a warning with the diagnostic and the renamed path

This ensures the application can still start (treated as first run) while preserving the corrupt file for forensic analysis.

### 5.3 Atomic Write Protocol

```python
def _write_atomic(self, payload: dict) -> None:
    """Write JSON payload to schema.json using atomic .tmp + rename."""
    self._schema_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = self._schema_path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(str(tmp_path), str(self._schema_path))
```

Guarantees:
- If the process crashes during `write_text()`, only the `.tmp` file exists — `schema.json` is untouched
- If the process crashes during `os.replace()`, either old `schema.json` exists (crash before replace) or new one exists (crash after replace) — never a partial file
- The `.tmp` file may be orphaned; it is cleaned on next `write()` or can be cleaned by a startup cleanup routine

---

## 6. Integration Points

### 6.1 Module Dependencies

```
SchemaVersionManager
  ├── trackora/core/paths.py        (for BASE_DIR)
  ├── trackora/core/schema_version  (for SchemaVersion, CompatibilityStatus)
  ├── trackora/__init__.py          (for __version__ string, via SchemaVersion.current_app_version())
  ├── json (stdlib)
  ├── os (stdlib)
  ├── pathlib (stdlib)
  ├── datetime (stdlib — for updated_at)
  └── logging (stdlib)
```

### 6.2 Integration with __main__.py

The `SchemaVersionManager` is the first upgrade component to run. It is instantiated and called immediately after `db.initialize()`:

```python
# In __main__.py — between db.initialize() and repository creation:

schema_version_manager = SchemaVersionManager()
data_version = schema_version_manager.read()
compatible, status = schema_version_manager.is_compatible(
    SchemaVersion.current_app_version(), data_version
)

if not compatible:
    # Show blocking error dialog with status.message
    # sys.exit(2)

if status.status == "first_run":
    schema_version_manager.write(SchemaVersion.current_app_version(),
                                  description="Initial schema for fresh install")

elif status.status == "needs_migration":
    # BackupManager + MigrationManager run here (separate implementation)
    pass

# Normal startup continues...
```

### 6.3 Integration with MigrationManager

`MigrationManager` receives `SchemaVersionManager` via constructor injection:

```python
class MigrationManager:
    def __init__(
        self,
        connection: sqlite3.Connection,
        schema_version_manager: SchemaVersionManager,
        backup_manager: BackupManager,
    ) -> None: ...
```

After `MigrationManager.apply_all()` succeeds, it calls:

```python
self._schema_version_manager.write(
    SchemaVersion.from_string(last_migration.app_version),
    description=f"Applied {n} migration(s): {migration_list}"
)
```

### 6.4 Integration with BackupManager

`BackupManager` receives `SchemaVersionManager` via constructor injection (optional, for reading/writing schema version into backup manifests):

```python
class BackupManager:
    def __init__(
        self,
        backup_dir: Path | None = None,
        source_db: Path | None = None,
        schema_manager: SchemaVersionManager | None = None,
    ) -> None: ...
```

### 6.5 Integration with Architecture Tests

The architecture test `test_schema_version_isolation.py` uses AST scanning (following the existing pattern in `tests/architecture/test_path_isolation.py`) to verify that only `schema_version_manager.py` contains references to `schema.json`.

---

## 7. Unit Tests

### 7.1 Test File: `tests/test_schema_version.py`

Target: `SchemaVersion` value object (frozen dataclass)

| Test | Scenario | Assertion |
|---|---|---|
| `test_from_string_valid` | "2.0.0" → SchemaVersion(2,0,0) | major=2, minor=0, patch=0 |
| `test_from_string_minimum` | "0.0.0" → SchemaVersion(0,0,0) | major=0, minor=0, patch=0 |
| `test_from_string_multi_digit` | "12.34.56" → SchemaVersion(12,34,56) | major=12, minor=34, patch=56 |
| `test_from_string_invalid_format` | "2.0", "v2.0.0", "2.0.0.0", "abc" | Raises ValueError |
| `test_from_string_negative` | "-1.0.0" | Raises ValueError |
| `test_from_string_empty` | "" | Raises ValueError |
| `test_is_valid_format` | Valid strings → True, invalid → False | Correct boolean |
| `test_current_app_version` | Reads `trackora.__version__` | Returns correct SchemaVersion |
| `test_str` | SchemaVersion(2,0,0) → "2.0.0" | String matches |
| `test_to_dict` | SchemaVersion(2,0,0) → {"major":2,"minor":0,"patch":0} | Dict matches |
| `test_eq_same` | (2,0,0) == (2,0,0) | True |
| `test_eq_different` | (2,0,0) == (1,1,0) | False |
| `test_lt_major` | (1,9,9) < (2,0,0) | True |
| `test_lt_minor` | (2,0,0) < (2,1,0) | True |
| `test_lt_patch` | (2,0,0) < (2,0,1) | True |
| `test_gt` | (2,0,0) > (1,9,9) | True |
| `test_sorting` | List of mixed versions | Sorted correctly |
| `test_immutability` | Attempt to set attribute | Raises FrozenInstanceError |
| `test_hashable` | Use in set/dict | Works as key |

### 7.2 Test File: `tests/test_schema_version_manager.py`

Target: `SchemaVersionManager`

**Fixture:**

```python
@pytest.fixture
def manager(tmp_path: Path) -> SchemaVersionManager:
    """SchemaVersionManager with schema.json in tmp_path."""
    return SchemaVersionManager(schema_path=tmp_path / "schema.json")

@pytest.fixture
def manager_with_file(tmp_path: Path) -> tuple[SchemaVersionManager, Path]:
    """Manager with a valid schema.json already written."""
    schema_path = tmp_path / "schema.json"
    mgr = SchemaVersionManager(schema_path=schema_path)
    mgr.write(SchemaVersion(2, 0, 0), description="test")
    return mgr, schema_path
```

| Test | Scenario | Steps |
|---|---|---|
| `test_init_default_path` | Default constructor | `BASE_DIR / "schema.json"` is resolved |
| `test_read_returns_none_when_missing` | No file on disk | Returns None |
| `test_read_returns_version_when_exists` | Valid file | Returns SchemaVersion(2,0,0) |
| `test_write_creates_file` | Fresh write | File exists, content is valid JSON |
| `test_write_atomicity` | Crash during write | .tmp file, no partial .json |
| `test_write_overwrites` | Write twice | Second write replaces content |
| `test_write_creates_parent_dir` | Parent missing | Directory created automatically |
| `test_read_corrupt_json` | Invalid JSON content | Raises SchemaVersionError, file renamed to .corrupt |
| `test_read_corrupt_empty` | Empty file | Raises SchemaVersionError, file renamed |
| `test_read_corrupt_missing_key` | Missing `schema_version` | Raises SchemaVersionError, file renamed |
| `test_read_corrupt_invalid_version` | "abc" as version | Raises SchemaVersionError, file renamed |
| `test_read_corrupt_unknown_keys_preserved` | Extra keys in JSON | Silently ignores, returns version |
| `test_read_permission_error` | Permission denied on file | Raises SchemaVersionError, no rename |
| `test_write_disk_full` | OSError during write | Raises OSError |
| `test_write_permission_error` | OSError during write | Raises OSError |
| `test_is_compatible_first_run` | data_version=None | can_proceed=True, status="first_run" |
| `test_is_compatible_same_version` | app=2.0.0, data=2.0.0 | can_proceed=True, status="ok" |
| `test_is_compatible_needs_migration` | app=2.0.0, data=1.1.0 | can_proceed=True, status="needs_migration" |
| `test_is_compatible_newer_data` | app=2.0.0, data=2.1.0 | can_proceed=False, status="newer_data" |
| `test_is_compatible_newer_data_major` | app=2.0.0, data=3.0.0 | can_proceed=False, status="newer_data" |
| `test_is_compatible_older_version` | app=2.0.0, data=1.0.0 | can_proceed=True, status="needs_migration" |
| `test_compare_less` | (1,0,0) vs (2,0,0) | Returns -1 |
| `test_compare_equal` | (2,0,0) vs (2,0,0) | Returns 0 |
| `test_compare_greater` | (3,0,0) vs (2,0,0) | Returns 1 |
| `test_delete_removes_file` | Existing file | File gone, exists() returns False |
| `test_delete_missing_file` | File does not exist | No error |
| `test_exists_true` | File exists | True |
| `test_exists_false` | No file | False |
| `test_round_trip` | Write then read | Same SchemaVersion returned |
| `test_schema_version_in_message` | newer_data status | Message contains the required version |

### 7.3 Edge Cases

| Test | Rationale |
|---|---|
| `test_tmp_file_cleanup` | Orphaned .tmp from previous crash is cleaned on write |
| `test_unicode_in_description` | Description may contain non-ASCII characters |
| `test_concurrent_read_write` | With threading lock or single-instance — verify no race |
| `test_symlink_schema_path` | If schema.json is a symlink (edge case) |
| `test_very_large_description` | Description field size limits |
| `test_schema_version_float_in_json` | JSON may serialize 2.0 as 2.0 (float) — must catch |
| `test_updated_at_format` | Must be valid ISO-8601 with timezone |

---

## 8. Integration Tests

### 8.1 Test File: `tests/test_upgrade_lifecycle.py`

Partial — only SchemaVersionManager integration tests for now; full lifecycle tests added when all three managers exist.

| Test | Scenario | Steps |
|---|---|---|
| `test_first_run_detection` | No schema.json, no database | `read()` → None → `is_compatible()` → first_run → `write()` |
| `test_version_upgrade_flow` | schema.json = 1.1.0, app = 2.0.0 | `read()` → 1.1.0 → `is_compatible()` → needs_migration |
| `test_version_block_newer` | schema.json = 2.1.0, app = 2.0.0 | `read()` → 2.1.0 → `is_compatible()` → can_proceed=False |
| `test_same_version_skip_migration` | schema.json = 2.0.0, app = 2.0.0 | `read()` → 2.0.0 → `is_compatible()` → ok → skip |
| `test_corrupt_file_recovery` | schema.json = "{garbage}" | `read()` → raises → file renamed → retry → None → first_run |
| `test_downgrade_rejected` | schema.json = 2.0.0, app = 1.1.0 | `is_compatible()` → newer_data → blocked |

### 8.2 Test Fixtures for Integration

```python
@pytest.fixture
def real_paths_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SchemaVersionManager:
    """Integration fixture that uses real paths.py resolution with tmp_path as BASE_DIR."""
    monkeypatch.setattr(
        "trackora.core.paths.BASE_DIR", tmp_path
    )
    from trackora.core.paths import BASE_DIR
    return SchemaVersionManager(schema_path=BASE_DIR / "schema.json")

@pytest.fixture
def existing_v1_database(tmp_path: Path) -> Path:
    """Create a schema.json representing a v1.1.0 installation."""
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({
        "schema_version": "1.1.0",
        "app_version": "1.1.0",
        "updated_at": "2026-01-15T00:00:00Z",
        "description": "Initial v1.1.0 installation"
    }))
    return tmp_path
```

---

## 9. Architecture Tests

### 9.1 Test File: `tests/architecture/test_schema_version_isolation.py`

**Rule:** No file outside `trackora/core/schema_version_manager.py` may read or write `schema.json`.

**Pattern:** Follows the existing AST-based scanning pattern in `tests/architecture/test_path_isolation.py` and `test_environment_isolation.py`.

```python
"""Architecture enforcement: schema.json access isolation.

Rule:
    Only trackora/core/schema_version_manager.py may read or write
    the schema.json file that stores version metadata.

    No other file may contain:
        "schema.json"
        schema.json
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXCLUDED_FILE = PROJECT_ROOT / "trackora" / "core" / "schema_version_manager.py"
EXCLUDED_TEST_FILE = PROJECT_ROOT / "tests" / "test_schema_version_manager.py"

# Source directories to scan (same as test_path_isolation.py)
SOURCE_DIRS = [...]

# Patterns indicating direct schema.json access
_SCHEMA_JSON_PATTERNS = [
    '"schema.json"',
    "'schema.json'",
]

# ... AST scanning logic follows same pattern as test_path_isolation.py ...
```

### 9.2 Exclusions

The following are NOT flagged:
- `import trackora.core.schema_version_manager` or `from trackora.core.schema_version_manager import ...`
- Comments, docstrings, or log messages mentioning "schema.json" (these are informational)
- Test files (but tests should use `SchemaVersionManager`, not file I/O directly)

---

## 10. Acceptance Criteria

### 10.1 Functional Criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-SVM-01 | `SchemaVersion.from_string("2.0.0")` returns `SchemaVersion(2,0,0)` | Unit test |
| AC-SVM-02 | `SchemaVersion.from_string("invalid")` raises `ValueError` | Unit test |
| AC-SVM-03 | `SchemaVersion.current_app_version()` returns version matching `trackora.__version__` | Unit test |
| AC-SVM-04 | `SchemaVersion.__str__()` returns `"MAJOR.MINOR.PATCH"` | Unit test |
| AC-SVM-05 | Comparison operators (`<`, `==`, `>`) follow semver semantics | Unit test |
| AC-SVM-06 | `SchemaVersionManager()` with default constructor resolves to `BASE_DIR / "schema.json"` | Unit test |
| AC-SVM-07 | `read()` returns `None` when `schema.json` does not exist | Unit test |
| AC-SVM-08 | `read()` returns correct `SchemaVersion` when valid file exists | Unit test |
| AC-SVM-09 | `read()` renames corrupt file to `.corrupt.<timestamp>` and raises `SchemaVersionError` | Unit test |
| AC-SVM-10 | `write()` creates file with correct JSON structure | Unit test |
| AC-SVM-11 | `write()` is atomic: crash produces no partial `.json` file | Unit test (simulate crash) |
| AC-SVM-12 | `write()` creates parent directory if missing | Unit test |
| AC-SVM-13 | `is_compatible(None)` → first_run with `can_proceed=True` | Unit test |
| AC-SVM-14 | `is_compatible(same)` → ok with `can_proceed=True` | Unit test |
| AC-SVM-15 | `is_compatible(older_data)` → needs_migration with `can_proceed=True` | Unit test |
| AC-SVM-16 | `is_compatible(newer_data)` → newer_data with `can_proceed=False` | Unit test |
| AC-SVM-17 | `is_compatible(newer_major)` → newer_data with `can_proceed=False` | Unit test |
| AC-SVM-18 | Corrupt file recovery: corrupt file renamed, application can start as first-run | Integration test |
| AC-SVM-19 | Schema version survives round-trip: write(X) → read() → X | Integration test |

### 10.2 Non-Functional Criteria

| ID | Criterion | Target |
|---|---|---|
| AC-SVM-20 | `read()` on valid file completes in <10ms | Benchmarked |
| AC-SVM-21 | `write()` to fast disk completes in <50ms | Benchmarked |
| AC-SVM-22 | `is_compatible()` completes in <1ms (no I/O) | Benchmarked |
| AC-SVM-23 | SchemaVersionManager adds <50ms to startup time | Benchmarked in full startup |
| AC-SVM-24 | No mutable state — two instances with same path are interchangeable | Unit test |
| AC-SVM-25 | Architecture isolation test passes | Architecture test |

### 10.3 Integration Criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-SVM-26 | Works with environment isolation: Dev path = `Trackora-Dev`, Prod path = `Trackora` | Integration test with monkeypatch |
| AC-SVM-27 | Works with existing paths.py resolution (no hardcoded paths) | Architecture test |
| AC-SVM-28 | All existing 824 tests pass after SchemaVersionManager is added | Regression |

---

## 11. Implementation Sequence

### Step 1: `trackora/core/schema_version.py`

- Define `SchemaVersion` frozen dataclass
- Implement `from_string()`, `current_app_version()`, `__str__()`, `to_dict()`
- Implement `__lt__`, `__le__`, `__eq__`, `__ne__`, `__gt__`, `__ge__`
- Implement `is_valid_format()` classmethod
- Define `CompatibilityStatus` frozen dataclass
- Define `SchemaVersionError` exception class

### Step 2: `tests/test_schema_version.py`

- Implement all unit tests from section 7.1
- Run: `python -m pytest tests/test_schema_version.py -v`

### Step 3: `trackora/core/schema_version_manager.py`

- Implement `SchemaVersionManager.__init__()` with default path resolution
- Implement `_read_json()` internal method (reads and validates JSON)
- Implement `_write_atomic()` internal method (`.tmp` + rename)
- Implement `read()` with corrupt-file recovery
- Implement `write()` with atomic protocol
- Implement `is_compatible()` with version comparison matrix
- Implement `compare()`, `delete()`, `exists()`

### Step 4: `tests/test_schema_version_manager.py`

- Implement all unit tests from section 7.2
- Run: `python -m pytest tests/test_schema_version_manager.py -v`

### Step 5: Integration test

- Implement `tests/test_upgrade_lifecycle.py` (SchemaVersionManager portion)
- Wire into a temporary `__main__.py` test harness
- Verify first-run, upgrade, and block scenarios

### Step 6: `tests/architecture/test_schema_version_isolation.py`

- Implement AST-based isolation test
- Run: `python -m pytest tests/architecture/test_schema_version_isolation.py -v`

### Step 7: Full regression

- Run: `python -m pytest --cov=trackora --cov=services --cov=database --cov=tracker`

---

## 12. Open Questions

| Question | Decision Needed By | Notes |
|---|---|---|
| Should `SchemaVersion.current_app_version()` read from `trackora.__version__` or from `build_info.BUILD_VERSION`? | Implementation start | Both return the same value; `build_info.py` adds one more import hop. Prefer `trackora.__version__` for directness. |
| What is the retention policy for `.corrupt` renamed files? | Implementation start | Suggestion: keep last 3 corrupt files, delete older on each `read()` error |
| Should `write()` log the new schema version? | Implementation start | Yes — `logger.info("Schema version updated: %s", version)` |
| Should `CompatibilityStatus.message` be internationalized? | v3.0 | Keep English-only for v2.0; i18n is not in scope |
| What happens if `schema.json` was written by a newer version of the same MANAGER (same app version, different schema version)? | Implementation start | This is the "needs_migration" case — correct behavior |
| Who is responsible for deleting orphaned `.tmp` files from previous crashes? | Implementation start | `SchemaVersionManager.__init__()` should clean any `.tmp` file at the schema path |

---

## 13. File Checklist

```
Create:
  trackora/core/schema_version.py
  trackora/core/schema_version_manager.py
  tests/test_schema_version.py
  tests/test_schema_version_manager.py
  tests/architecture/test_schema_version_isolation.py

Modify (when integrating all three managers):
  trackora/__main__.py           (add SchemaVersionManager to startup)
  tests/test_upgrade_lifecycle.py  (add integration tests)

No changes to:
  trackora/core/paths.py         (BASE_DIR already exists)
  trackora/core/environment.py   (environment isolation already complete)
  database/database_manager.py   (schema.json is independent of database)
  Any existing service, repository, or UI file
```

---

## References

- `docs/architecture/upgrade-foundation.md` — Architecture principles and component design
- `docs/architecture/upgrade-foundation-assessment.md` — Audit findings justifying this component
- `docs/architecture/upgrade-foundation-spec.md` — Full architecture specification (detailed)
- `docs/releases/v2.0.0/milestone-8-upgrade-foundation.md` — M8 milestone requirements (FR-01, FR-02, FR-10, FR-11)
- `trackora/core/paths.py` — `BASE_DIR` resolution for default `schema.json` path
- `trackora/core/environment.py` — Environment isolation (Dev/Prod path separation)
- `tests/architecture/test_path_isolation.py` — Existing AST scanning pattern to follow
