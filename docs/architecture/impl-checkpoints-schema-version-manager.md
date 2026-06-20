# SchemaVersionManager — Implementation Checklist

**Total Files:** 6 (2 source + 3 test + 0 modified)  
**Methodology:** Test-first (red-green-refactor for each step)  
**Estimated Steps:** 17  

---

## Step 0 — Prerequisites

- [ ] 0.1 Working Python 3.13+ environment with activated venv
- [ ] 0.2 `python -m pytest` passes all 824+ existing tests
- [ ] 0.3 Read existing reference files:
  - `trackora/core/paths.py` (BASE_DIR resolution)
  - `trackora/core/environment.py` (Environment enum)
  - `trackora/__init__.py` (`__version__ = "1.1.0"`)
  - `tests/architecture/test_path_isolation.py` (AST pattern to follow)
- [ ] 0.4 Verify `%APPDATA%/Trackora` is writable (or tmp_path in tests)

---

## Step 1 — SchemaVersion value object

**File:** `trackora/core/schema_version.py`  
**Dependencies:** None (stdlib only: `re`, `dataclasses`)  
**Test file:** `tests/test_schema_version.py`

### 1.1 First test — factory from valid string

- [ ] 1.1.1 **RED:** Write test `test_from_string_valid`
- [ ] 1.1.2 **GREEN:** Implement `SchemaVersion.from_string("2.0.0")` returning dataclass
- [ ] 1.1.3 **REFACTOR:** Clean

**Validation:** `python -m pytest tests/test_schema_version.py::test_from_string_valid -v`

### 1.2 Factory edge cases

- [ ] 1.2.1 **RED:** Write `test_from_string_minimum` ("0.0.0")
- [ ] 1.2.2 **GREEN:** Verify works with zero values
- [ ] 1.2.3 **RED:** Write `test_from_string_multi_digit` ("12.34.56")
- [ ] 1.2.4 **GREEN:** Verify multi-digit parsing

**Validation:** `python -m pytest tests/test_schema_version.py -v` (passes tests 1.1-1.2)

### 1.3 Factory invalid strings

- [ ] 1.3.1 **RED:** Write `test_from_string_invalid_format` (parametrize: "2.0", "v2.0.0", "2.0.0.0", "abc", "", "2.0.0-alpha")
- [ ] 1.3.2 **GREEN:** Raise `ValueError` for all invalid formats
- [ ] 1.3.3 **RED:** Write `test_from_string_negative` ("-1.0.0")
- [ ] 1.3.4 **GREEN:** Verify regex rejects negative numbers

**Validation:** `python -m pytest tests/test_schema_version.py::test_from_string_invalid_format tests/test_schema_version.py::test_from_string_negative -v`

### 1.4 Validation helper

- [ ] 1.4.1 **RED:** Write `test_is_valid_format` (parametrize: valid→True, invalid→False)
- [ ] 1.4.2 **GREEN:** Implement `SchemaVersion.is_valid_format()` classmethod

**Validation:** `python -m pytest tests/test_schema_version.py::test_is_valid_format -v`

### 1.5 Current app version

- [ ] 1.5.1 **RED:** Write `test_current_app_version` — assert matches `trackora.__version__`
- [ ] 1.5.2 **GREEN:** Implement `SchemaVersion.current_app_version()` using `from_string(trackora.__version__)`
- [ ] 1.5.3 **IMPORTANT:** Verify import: `from trackora import __version__` — no circular imports

**Validation:** `python -m pytest tests/test_schema_version.py::test_current_app_version -v`

### 1.6 String serialization

- [ ] 1.6.1 **RED:** Write `test_str` — `str(SchemaVersion(2,0,0)) == "2.0.0"`
- [ ] 1.6.2 **GREEN:** Implement `__str__`
- [ ] 1.6.3 **RED:** Write `test_to_dict` — `to_dict() == {"major":2,"minor":0,"patch":0}`
- [ ] 1.6.4 **GREEN:** Implement `to_dict()`

**Validation:** `python -m pytest tests/test_schema_version.py::test_str tests/test_schema_version.py::test_to_dict -v`

### 1.7 Comparison operators

- [ ] 1.7.1 **RED:** Write `test_eq_same`, `test_eq_different`
- [ ] 1.7.2 **GREEN:** Implement `__eq__` (dataclass auto-generates with frozen=True)
- [ ] 1.7.3 **RED:** Write `test_lt_major`, `test_lt_minor`, `test_lt_patch`
- [ ] 1.7.4 **GREEN:** Implement `__lt__`: compare (major, minor, patch) as tuples
- [ ] 1.7.5 **RED:** Write `test_gt` — delegate to `__lt__`
- [ ] 1.7.6 **GREEN:** Implement `__gt__`, `__le__`, `__ge__`, `__ne__` in terms of `__lt__` and `__eq__`
- [ ] 1.7.7 **RED:** Write `test_sorting` — sort `[SchemaVersion(2,0,0), SchemaVersion(1,0,0)]` → `[1.0.0, 2.0.0]`
- [ ] 1.7.8 **GREEN:** Verify sorting works with `functools.total_ordering`
- [ ] 1.7.9 **RED:** Write `test_immutability` — try `sv.major = 3` → `FrozenInstanceError`
- [ ] 1.7.10 **RED:** Write `test_hashable` — `{SchemaVersion(1,0,0): "ok"}` — works as dict key

**Validation:** `python -m pytest tests/test_schema_version.py -v` (all 18+ tests pass)

### 1.8 CompatibilityStatus

- [ ] 1.8.1 Define `CompatibilityStatus` frozen dataclass in `schema_version.py`
- [ ] 1.8.2 No tests needed for a pure dataclass (add if any logic is added)
- [ ] 1.8.3 Define `SchemaVersionError(Exception)` in `schema_version.py`

**Checkpoint 1:** `python -m pytest tests/test_schema_version.py -v` — ALL PASS

---

## Step 2 — SchemaVersionManager read

**File:** `trackora/core/schema_version_manager.py`  
**Dependencies:** `schema_version.py`, `paths.py`  
**Test file:** `tests/test_schema_version_manager.py`

### 2.1 Test fixture and init

- [ ] 2.1.1 Write `conftest.py` fixture inside test file:
  ```python
  @pytest.fixture
  def manager(tmp_path: Path) -> SchemaVersionManager:
      return SchemaVersionManager(schema_path=tmp_path / "schema.json")
  ```
- [ ] 2.1.2 **RED:** Write `test_init_default_path` — default constructor resolves `BASE_DIR / "schema.json"`
- [ ] 2.1.3 **GREEN:** Implement `__init__` with `BASE_DIR` from `trackora.core.paths`

**Validation:** `python -m pytest tests/test_schema_version_manager.py::test_init_default_path -v`

### 2.2 read() — file missing

- [ ] 2.2.1 **RED:** Write `test_read_returns_none_when_missing` — `read()` → `None`
- [ ] 2.2.2 **GREEN:** Implement `read()` with `except FileNotFoundError: return None`

**Validation:** `python -m pytest tests/test_schema_version_manager.py::test_read_returns_none_when_missing -v`

### 2.3 read() — valid file

- [ ] 2.3.1 **RED:** Write `test_read_returns_version_when_exists`:
  1. Write valid JSON to `schema.json`
  2. `read()` → `SchemaVersion(2,0,0)`
- [ ] 2.3.2 **GREEN:** Implement JSON parsing with required field validation
- [ ] 2.3.3 **RED:** Write `test_read_unknown_keys_ignored` — extra keys in JSON are silently accepted
- [ ] 2.3.4 **GREEN:** Verify forward-compatibility

**Validation:** `python -m pytest tests/test_schema_version_manager.py::test_read_returns_version_when_exists -v`

### 2.4 read() — corrupt file recovery

- [ ] 2.4.1 **RED:** Write `test_read_corrupt_json` — invalid JSON content → `SchemaVersionError`
- [ ] 2.4.2 **GREEN:** Catch `json.JSONDecodeError`, rename to `.corrupt.<ts>`, raise `SchemaVersionError`
- [ ] 2.4.3 **RED:** Write `test_read_corrupt_file_renamed` — verify `.corrupt` file exists after error
- [ ] 2.4.4 **GREEN:** Implement rename with timestamp
- [ ] 2.4.5 **RED:** Write `test_read_corrupt_empty` — empty file
- [ ] 2.4.6 **RED:** Write `test_read_corrupt_missing_key` — missing `schema_version` field
- [ ] 2.4.7 **RED:** Write `test_read_corrupt_invalid_version` — version string "abc"
- [ ] 2.4.8 **RED:** Write `test_read_corrupt_float_version` — version is `2.0` (float) not `"2.0"` (string)
- [ ] 2.4.9 **GREEN:** Handle all corrupt cases through same code path

**Validation:** `python -m pytest tests/test_schema_version_manager.py -v` (passes all read tests)

**Checkpoint 2:** ALL read tests pass

---

## Step 3 — SchemaVersionManager write

### 3.1 write() — basic

- [ ] 3.1.1 **RED:** Write `test_write_creates_file`:
  1. `write(SchemaVersion(2,0,0), "test")`
  2. File exists, valid JSON
  3. Contains `schema_version: "2.0.0"`, `app_version`, `updated_at`, `description`
- [ ] 3.1.2 **GREEN:** Implement `write()` with `json.dumps` + `Path.write_text`

**Validation:** `python -m pytest tests/test_schema_version_manager.py::test_write_creates_file -v`

### 3.2 write() — atomicity

- [ ] 3.2.1 **RED:** Write `test_write_atomicity`:
  1. `write(v1)` → file exists with v1
  2. Simulate crash during write: write .tmp, crash before rename
  3. Verify `schema.json` still has v1 (not partial v2)
- [ ] 3.2.2 **GREEN:** Implement `.tmp` + `os.replace` pattern in private `_write_atomic()`

**Validation:** `python -m pytest tests/test_schema_version_manager.py::test_write_atomicity -v`

### 3.3 write() — overwrite and parent dir

- [ ] 3.3.1 **RED:** Write `test_write_overwrites` — write v1, write v2, read back v2
- [ ] 3.3.2 **GREEN:** Verify overwrite works (natural consequence of atomic write)
- [ ] 3.3.3 **RED:** Write `test_write_creates_parent_dir` — parent directory missing → created
- [ ] 3.3.4 **GREEN:** Add `parent.mkdir(parents=True, exist_ok=True)` before write

**Validation:** Both tests pass

### 3.4 write() — errors

- [ ] 3.4.1 **RED:** Write `test_write_disk_full` — mock `write_text` to raise `OSError`
- [ ] 3.4.2 **GREEN:** Propagate `OSError` (caller handles)
- [ ] 3.4.3 **RED:** Write `test_write_permission_error` — mock `mkdir` to raise `PermissionError`
- [ ] 3.4.4 **GREEN:** Propagate `PermissionError` (subclass of `OSError`)

**Validation:** `python -m pytest tests/test_schema_version_manager.py::test_write_disk_full -v`

**Checkpoint 3:** ALL read + write tests pass

---

## Step 4 — SchemaVersionManager is_compatible

### 4.1 Compatibility matrix

- [ ] 4.1.1 **RED:** Write `test_is_compatible_first_run` — `data_version=None`:
  - `can_proceed=True`, `status="first_run"`
- [ ] 4.1.2 **GREEN:** Implement `is_compatible()` — branch on `data_version is None`
- [ ] 4.1.3 **RED:** Write `test_is_compatible_same_version`:
  - `app=SchemaVersion(2,0,0)`, `data=SchemaVersion(2,0,0)`
  - `can_proceed=True`, `status="ok"`
- [ ] 4.1.4 **GREEN:** Branch on `data_version == app_version`
- [ ] 4.1.5 **RED:** Write `test_is_compatible_needs_migration`:
  - `app=SchemaVersion(2,0,0)`, `data=SchemaVersion(1,1,0)`
  - `can_proceed=True`, `status="needs_migration"`
- [ ] 4.1.6 **GREEN:** Branch on `data_version < app_version`
- [ ] 4.1.7 **RED:** Write `test_is_compatible_newer_data`:
  - `app=SchemaVersion(2,0,0)`, `data=SchemaVersion(2,1,0)`
  - `can_proceed=False`, `status="newer_data"`
- [ ] 4.1.8 **GREEN:** Branch on `data_version > app_version`
- [ ] 4.1.9 **RED:** Write `test_is_compatible_newer_major`:
  - `app=SchemaVersion(2,0,0)`, `data=SchemaVersion(3,0,0)`
  - `can_proceed=False`, `status="newer_data"`
- [ ] 4.1.10 **GREEN:** Verify standard comparison handles major version
- [ ] 4.1.11 **RED:** Write `test_is_compatible_error_message`:
  - newer_data case → message contains "requires Trackora 2.1.0 or newer"

**Validation:** `python -m pytest tests/test_schema_version_manager.py -v` (passes all compatibility tests)

**Checkpoint 4:** ALL tests pass

---

## Step 5 — remaining methods and edge cases

### 5.1 compare, delete, exists

- [ ] 5.1.1 **RED:** Write `test_compare_less` / `test_compare_equal` / `test_compare_greater`
  - delegate to `SchemaVersion.__lt__` / `__eq__`
- [ ] 5.1.2 **GREEN:** Implement `compare(a, b)` — `-1 if a < b else 0 if a == b else 1`
- [ ] 5.1.3 **RED:** Write `test_delete_removes_file` — write, delete, `exists()==False`
- [ ] 5.1.4 **RED:** Write `test_delete_missing_file` — delete non-existent → no error
- [ ] 5.1.5 **GREEN:** Implement `delete()` with `FileNotFoundError` suppression
- [ ] 5.1.6 **RED:** Write `test_exists_true` / `test_exists_false`
- [ ] 5.1.7 **GREEN:** Implement `exists()` — `self._schema_path.is_file()`

**Validation:** `python -m pytest tests/test_schema_version_manager.py -v`

### 5.2 Round-trip and edge cases

- [ ] 5.2.1 **RED:** Write `test_round_trip` — write 3 versions, read each back
- [ ] 5.2.2 **GREEN:** Verify serialization round-trips correctly
- [ ] 5.2.3 **RED:** Write `test_unicode_description` — description with Unicode characters
- [ ] 5.2.4 **GREEN:** Ensure `ensure_ascii=False` in JSON dump
- [ ] 5.2.5 **RED:** Write `test_tmp_file_cleanup` — orphaned .tmp file from previous crash → cleaned on write
- [ ] 5.2.6 **GREEN:** Clean up orphaned `.tmp` files in `write()`
- [ ] 5.2.7 **RED:** Write `test_read_permission_error` — chmod 000 on file, verify error
- [ ] 5.2.8 **GREEN:** Handle `PermissionError` without renaming (can't rename what you can't read)

**Validation:** `python -m pytest tests/test_schema_version_manager.py::test_round_trip -v`

**Checkpoint 5:** ALL unit tests pass (both test files)

---

## Step 6 — Validation: full test suite

- [ ] 6.1 Run all SchemaVersion tests:
  ```bash
  python -m pytest tests/test_schema_version.py -v
  ```
  Expected: 18+ tests, all PASS

- [ ] 6.2 Run all SchemaVersionManager tests:
  ```bash
  python -m pytest tests/test_schema_version_manager.py -v
  ```
  Expected: 20+ tests, all PASS

- [ ] 6.3 Run full project test suite to confirm no regressions:
  ```bash
  python -m pytest --tb=short -q
  ```
  Expected: 824+ tests, all PASS

---

## Step 7 — Integration tests

**File:** `tests/test_upgrade_lifecycle.py`

- [ ] 7.1 Write fixture `existing_v1_database(tmp_path)` — creates `schema.json` with v1.1.0
- [ ] 7.2 **RED:** Write `test_first_run_lifecycle`:
  1. No `schema.json` → `read()` → None → `is_compatible()` → first_run
  2. `write(current_version)` → file created with correct content
- [ ] 7.3 **RED:** Write `test_upgrade_lifecycle`:
  1. `schema.json` = 1.1.0 → `is_compatible(app=2.0.0)` → needs_migration
- [ ] 7.4 **RED:** Write `test_block_newer_data_lifecycle`:
  1. `schema.json` = 2.1.0 → `is_compatible(app=2.0.0)` → can_proceed=False
- [ ] 7.5 **RED:** Write `test_corrupt_recovery_lifecycle`:
  1. Corrupt `schema.json` → `read()` raises → file renamed → `read()` → None → first_run
- [ ] 7.6 **RED:** Write `test_environment_isolation_lifecycle`:
  1. Override `BASE_DIR` to simulate Dev environment
  2. Verify schema.json goes to `Trackora-Dev/schema.json`

**Validation:** `python -m pytest tests/test_upgrade_lifecycle.py -v`

---

## Step 8 — Architecture enforcement test

**File:** `tests/architecture/test_schema_version_isolation.py`

- [ ] 8.1 Read `tests/architecture/test_path_isolation.py` (reference pattern)
- [ ] 8.2 **RED:** Write `test_schema_json_isolation`:
  - Scan all `.py` files for `"schema.json"` or `'schema.json'` patterns
  - Fail if found outside `schema_version_manager.py`
- [ ] 8.3 **GREEN:** Ensure no accidental references exist
- [ ] 8.4 **RED:** Write `test_schema_version_manager_import_restrictions`:
  - Verify `schema_version_manager.py` does NOT import from:
    - `database`, `services`, `ui`, `tracker`, `trackora_stats`
  - (It should only import from `trackora.core.paths`, `trackora.core.schema_version`, stdlib)
- [ ] 8.5 **GREEN:** Clean up any disallowed imports

**Validation:** `python -m pytest tests/architecture/test_schema_version_isolation.py -v`

---

## Step 9 — Final validation

- [ ] 9.1 Full test suite:
  ```bash
  python -m pytest --tb=short -q --cov=trackora.core.schema_version --cov=trackora.core.schema_version_manager
  ```
  Expected: 99%+ coverage on both source files

- [ ] 9.2 Type check (if mypy is configured):
  ```bash
  python -m mypy trackora/core/schema_version.py trackora/core/schema_version_manager.py
  ```
  Expected: no errors

- [ ] 9.3 Lint:
  ```bash
  python -m ruff check trackora/core/schema_version.py trackora/core/schema_version_manager.py tests/test_schema_version.py tests/test_schema_version_manager.py
  ```
  Expected: no errors

- [ ] 9.4 Full regression:
  ```bash
  python -m pytest --tb=short -q
  ```
  Expected: 860+ tests (824 existing + 40+ new), all PASS

---

## Step 10 — Integration wiring (preview, no code changes)

- [ ] 10.1 Document in `AGENTS.md` (optional): add project rule for `schema_version_manager.py`
- [ ] 10.2 Verify import paths are correct:
  ```python
  from trackora.core.schema_version import SchemaVersion, CompatibilityStatus, SchemaVersionError
  from trackora.core.schema_version_manager import SchemaVersionManager
  ```
- [ ] 10.3 Confirm `__main__.py` wiring plan (no changes yet):
  ```
  ensure_dirs()
  db.initialize()
  svm = SchemaVersionManager()
  data_version = svm.read()
  compatible, status = svm.is_compatible(SchemaVersion.current_app_version(), data_version)
  if not compatible: block with error
  if first_run: svm.write(SchemaVersion.current_app_version())
  ```

---

## Dependency Graph

```
Step 1 (schema_version.py)
  │
  ├── Step 1.1-1.7   SchemaVersion dataclass (18+ tests)
  └── Step 1.8        CompatibilityStatus + SchemaVersionError
       │
       ▼
Step 2-5 (schema_version_manager.py)
  │
  ├── Step 2          read()  — missing, valid, corrupt (10+ tests)
  ├── Step 3          write() — basic, atomic, errors (6+ tests)
  ├── Step 4          is_compatible() — matrix (6+ tests)
  └── Step 5          compare, delete, exists, edge cases (6+ tests)
       │
       ▼
Step 6 (full unit test validation)
       │
       ▼
Step 7 (integration tests)           Step 8 (architecture tests)
       │                                    │
       └─────────────────┬──────────────────┘
                         ▼
               Step 9 (final validation)
```

---

## Quick Reference — Commands

```bash
# Run individual test
python -m pytest tests/test_schema_version.py::test_from_string_valid -v

# Run all tests in a file
python -m pytest tests/test_schema_version.py -v

# Run all new tests (watch mode with pytest-watch if installed)
ptw tests/test_schema_version.py tests/test_schema_version_manager.py

# Full regression
python -m pytest --tb=short -q

# With coverage
python -m pytest --cov=trackora.core.schema_version --cov=trackora.core.schema_version_manager --tb=short -v

# Type check
python -m mypy trackora/core/schema_version.py trackora/core/schema_version_manager.py

# Lint
python -m ruff check trackora/core/schema_version.py trackora/core/schema_version_manager.py

# Format
python -m ruff format trackora/core/schema_version.py trackora/core/schema_version_manager.py
```

---

## Acceptance Criteria Checklist

- [ ] **AC-SVM-01 through AC-SVM-28** all verified (see impl plan doc for full list)
- [ ] No existing tests broken (824+ baseline confirmed)
- [ ] No circular imports
- [ ] No database, service, or UI imports in `schema_version.py` or `schema_version_manager.py`
- [ ] All writes use `.tmp` + `os.replace` atomic pattern
- [ ] Corrupt files renamed (not deleted) with timestamp
- [ ] First-run detection works with no pre-existing `%APPDATA%/Trackora/`
- [ ] Blocking works when data version exceeds app version
- [ ] Architecture isolation test passes
