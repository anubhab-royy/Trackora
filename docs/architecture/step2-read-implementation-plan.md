# Step 2 Implementation Plan — SchemaVersionManager.read()

**Component:** `trackora/core/schema_version_manager.py`  
**Supporting Type:** `trackora/core/schema_version.py` (add `SchemaVersionError`)  
**Test File:** `tests/test_schema_version_manager.py`  
**Scope:** `__init__`, `read()`, `exists()`, orphan `.tmp` cleanup, corrupt file recovery  
**Out of Scope:** `write()`, `is_compatible()`, `compare()`, `delete()`, `BackupManager`, `MigrationManager`, startup integration

---

## A. Tests — Complete Specification

All tests go in `tests/test_schema_version_manager.py`. Every test uses `tmp_path` isolation — no real filesystem state leaks between tests.

### Fixtures

```python
# Shared fixture for all read tests
@pytest.fixture
def manager(tmp_path: Path) -> SchemaVersionManager:
    """SchemaVersionManager with schema.json in an isolated temp directory."""
    return SchemaVersionManager(schema_path=tmp_path / "schema.json")

# Helper to write a valid schema.json to the manager's path
def _write_valid_json(manager: SchemaVersionManager, version: str = "2.0.0") -> None:
    """Write a syntactically valid schema.json to the manager's schema path."""
    import json
    payload = {
        "schema_version": version,
        "app_version": "2.0.0",
        "updated_at": "2026-06-20T12:00:00Z",
        "description": "test",
    }
    manager._schema_path.write_text(json.dumps(payload, indent=2))
```

---

### A.1 — __init__ Tests

#### Test: `test_init_default_path_resolution`

| Field | Value |
|---|---|
| **Purpose** | Verify that the default constructor resolves `BASE_DIR / "schema.json"` correctly |
| **Input** | `SchemaVersionManager()` with no arguments |
| **Expected** | `manager._schema_path` resolves to `Path(BASE_DIR) / "schema.json"` where `BASE_DIR` comes from `trackora.core.paths` |
| **Fixture** | None (uses real `paths.py` resolution) |
| **Attach** | Must import `from trackora.core.paths import BASE_DIR` and compare |
| **Edge** | Must work in both production and development environments (path changes based on `CURRENT_ENVIRONMENT`) |

#### Test: `test_init_custom_path`

| Field | Value |
|---|---|
| **Purpose** | Verify that an explicit path overrides the default |
| **Input** | `SchemaVersionManager(schema_path=Path("/custom/path/schema.json"))` |
| **Expected** | `manager._schema_path == Path("/custom/path/schema.json")` |
| **Fixture** | None |

#### Test: `test_init_path_type`

| Field | Value |
|---|---|
| **Purpose** | Verify `_schema_path` is stored as a `Path` object, not a string |
| **Input** | `SchemaVersionManager(schema_path=Path("/tmp/schema.json"))` |
| **Expected** | `isinstance(manager._schema_path, Path)` is `True` |

---

### A.2 — read() File Missing

#### Test: `test_read_returns_none_when_missing`

| Field | Value |
|---|---|
| **Purpose** | Verify that `read()` returns `None` when `schema.json` does not exist |
| **Input** | No file at `manager._schema_path` |
| **Expected** | `manager.read()` returns `None` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_none_is_not_an_error`

| Field | Value |
|---|---|
| **Purpose** | Verify that `None` return is silent — no exception raised, no side effects |
| **Input** | No file at path |
| **Expected** | `manager.read()` returns `None`, no files created or modified, log message at INFO level |
| **Fixture** | `manager(tmp_path)` |

---

### A.3 — read() Valid File

#### Test: `test_read_returns_schema_version`

| Field | Value |
|---|---|
| **Purpose** | Verify that a valid `schema.json` returns the correct `SchemaVersion` |
| **Input** | JSON with `schema_version: "2.0.0"`, `app_version: "2.0.0"`, valid `updated_at` |
| **Expected** | `manager.read()` returns `SchemaVersion(2, 0, 0)` |
| **Fixture** | `manager(tmp_path)`, pre-write valid JSON via `_write_valid_json()` |

#### Test: `test_read_returns_correct_version_minor`

| Field | Value |
|---|---|
| **Purpose** | Ensure version parsing works for non-zero minor/patch |
| **Input** | `schema_version: "1.1.0"` |
| **Expected** | `SchemaVersion(1, 1, 0)` |
| **Fixture** | Same pattern |

#### Test: `test_read_returns_correct_version_patch`

| Field | Value |
|---|---|
| **Purpose** | Ensure patch-level version is parsed correctly |
| **Input** | `schema_version: "1.0.3"` |
| **Expected** | `SchemaVersion(1, 0, 3)` |
| **Fixture** | Same pattern |

#### Test: `test_read_unknown_keys_ignored`

| Field | Value |
|---|---|
| **Purpose** | Verify forward-compatibility: extra keys in JSON are silently accepted |
| **Input** | JSON with extra keys: `{"schema_version": "2.0.0", "app_version": "2.0.0", "updated_at": "...", "future_field": "some_value"}` |
| **Expected** | Returns `SchemaVersion(2, 0, 0)` — no error, no warning |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_returns_new_schema_version_each_call`

| Field | Value |
|---|---|
| **Purpose** | Verify that `read()` is stateless — calling it twice returns the same value (reads from disk each time) |
| **Input** | Valid schema.json, then modify the file between calls |
| **Expected** | First call returns original version, second call returns modified version |
| **Fixture** | `manager(tmp_path)` |

---

### A.4 — read() Corrupt File — JSON Parsing Errors

#### Test: `test_read_corrupt_invalid_json`

| Field | Value |
|---|---|
| **Purpose** | Verify that unparseable JSON raises `SchemaVersionError` |
| **Input** | File content `{invalid json!!!}` |
| **Expected** | `SchemaVersionError` raised with message containing `"invalid JSON"` or similar |
| **Fixture** | `manager(tmp_path)`, write raw garbage to file |

#### Test: `test_read_corrupt_empty_file`

| Field | Value |
|---|---|
| **Purpose** | Verify that an empty file raises `SchemaVersionError` |
| **Input** | Empty file (zero bytes) |
| **Expected** | `SchemaVersionError` raised, message indicates empty file |
| **Fixture** | `manager(tmp_path)`, write empty string to file |

#### Test: `test_read_corrupt_whitespace_only`

| Field | Value |
|---|---|
| **Purpose** | Verify that whitespace-only file raises `SchemaVersionError` |
| **Input** | File content `"   \n\n  "` |
| **Expected** | `SchemaVersionError` raised (json.JSONDecodeError → caught → SchemaVersionError) |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_boolean_top_level`

| Field | Value |
|---|---|
| **Purpose** | Verify that valid JSON that is not an object raises `SchemaVersionError` |
| **Input** | File content `true` (valid JSON, but not a dict) |
| **Expected** | `SchemaVersionError` raised (isinstance check fails) |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_json_array_top_level`

| Field | Value |
|---|---|
| **Purpose** | Verify that a JSON array at top level raises `SchemaVersionError` |
| **Input** | File content `[1, 2, 3]` |
| **Expected** | `SchemaVersionError` raised (not a dict) |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_null_top_level`

| Field | Value |
|---|---|
| **Purpose** | Verify that JSON `null` at top level raises `SchemaVersionError` |
| **Input** | File content `null` |
| **Expected** | `SchemaVersionError` raised |
| **Fixture** | `manager(tmp_path)` |

---

### A.5 — read() Corrupt File — Missing or Invalid Fields

#### Test: `test_read_corrupt_missing_schema_version`

| Field | Value |
|---|---|
| **Purpose** | Verify that JSON missing `schema_version` key raises `SchemaVersionError` |
| **Input** | `{"app_version": "2.0.0", "updated_at": "..."}` |
| **Expected** | `SchemaVersionError` raised, message mentions missing `schema_version` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_missing_app_version`

| Field | Value |
|---|---|
| **Purpose** | Verify that JSON missing `app_version` key raises `SchemaVersionError` |
| **Input** | `{"schema_version": "2.0.0", "updated_at": "..."}` |
| **Expected** | `SchemaVersionError` raised, message mentions missing `app_version` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_missing_updated_at`

| Field | Value |
|---|---|
| **Purpose** | Verify that JSON missing `updated_at` key raises `SchemaVersionError` |
| **Input** | `{"schema_version": "2.0.0", "app_version": "2.0.0"}` |
| **Expected** | `SchemaVersionError` raised, message mentions missing `updated_at` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_schema_version_not_a_string`

| Field | Value |
|---|---|
| **Purpose** | Verify that non-string `schema_version` (e.g., float `2.0`) raises `SchemaVersionError` |
| **Input** | `{"schema_version": 2.0, "app_version": "2.0.0", "updated_at": "..."}` |
| **Expected** | `SchemaVersionError` raised, message indicates non-string type |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_schema_version_invalid_format`

| Field | Value |
|---|---|
| **Purpose** | Verify that unparseable version string raises `SchemaVersionError` |
| **Input** | `schema_version: "abc"` |
| **Expected** | `SchemaVersionError` raised, message mentions invalid version format |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_schema_version_partial_format`

| Field | Value |
|---|---|
| **Purpose** | Verify that malformed version strings raise `SchemaVersionError` |
| **Input** | Parametrize: `"2.0"`, `"v2.0.0"`, `"2.0.0.0"`, `""`, `"-1.0.0"` |
| **Expected** | Each case raises `SchemaVersionError` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_app_version_not_a_string`

| Field | Value |
|---|---|
| **Purpose** | Verify that non-string `app_version` raises `SchemaVersionError` |
| **Input** | `app_version: 123` (integer) |
| **Expected** | `SchemaVersionError` raised, message mentions non-string |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_updated_at_not_a_string`

| Field | Value |
|---|---|
| **Purpose** | Verify that non-string `updated_at` raises `SchemaVersionError` |
| **Input** | `updated_at: 12345` (integer) |
| **Expected** | `SchemaVersionError` raised, message mentions non-string |
| **Fixture** | `manager(tmp_path)` |

---

### A.6 — read() Corrupt File Recovery — Rename Workflow

#### Test: `test_read_corrupt_file_is_renamed`

| Field | Value |
|---|---|
| **Purpose** | Verify that corrupt file is renamed to `.corrupt.<timestamp>` |
| **Input** | Content: `{bad json}` at `manager._schema_path` |
| **Expected** | After `read()` raises: original file no longer exists, a file matching `schema.json.corrupt.*` exists in the same directory |
| **Fixture** | `manager(tmp_path)` |
| **Detail** | Use `os.listdir()` on parent dir to check for `.corrupt` files |

#### Test: `test_read_corrupt_original_content_preserved`

| Field | Value |
|---|---|
| **Purpose** | Verify corrupt file content is preserved (not deleted) in the renamed copy |
| **Input** | Content: `{garbage data here}` |
| **Expected** | The `.corrupt.*` file contains `{garbage data here}` — the original bytes are unchanged |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_rename_timestamp_format`

| Field | Value |
|---|---|
| **Purpose** | Verify the timestamp appended to `.corrupt` files uses `YYYYMMDD_HHMMSS` format |
| **Input** | Any corrupt content |
| **Expected** | Renamed file matches regex `schema\.json\.corrupt\.\d{8}_\d{6}` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_multiple_corrupt_files`

| Field | Value |
|---|---|
| **Purpose** | Verify that multiple corrupt files over time do not collide |
| **Input** | Call `read()` twice on a file that is re-corrupted between calls |
| **Expected** | After first call: one `.corrupt.*` file. After restoring corrupt content and calling again: two `.corrupt.*` files with different timestamps |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_rename_does_not_raise`

| Field | Value |
|---|---|
| **Purpose** | Verify that the rename operation itself does not raise (corrupt file renamed before exception is raised) |
| **Input** | Any corrupt content |
| **Expected** | Exception is `SchemaVersionError`, not `OSError` from rename failure |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_corrupt_rename_fails_silently_logged`

| Field | Value |
|---|---|
| **Purpose** | Verify that if rename fails (permissions), the exception is logged but `SchemaVersionError` is still raised with the original parse error |
| **Input** | Corrupt content, file made read-only or directory made non-writable |
| **Expected** | `SchemaVersionError` raised (not `OSError` from rename), log message about rename failure |
| **Fixture** | `manager(tmp_path)`, simulate permission error via `os.chmod` on parent dir |

#### Test: `test_read_corrupt_after_rename_returns_none`

| Field | Value |
|---|---|
| **Purpose** | Verify that after corrupt → rename, a subsequent `read()` returns `None` (the corrupt file is gone, no schema.json exists) |
| **Input** | Corrupt content, call `read()` twice |
| **Expected** | First call raises `SchemaVersionError`. Second call returns `None` |
| **Fixture** | `manager(tmp_path)` |

---

### A.7 — read() Permission Errors

#### Test: `test_read_permission_denied`

| Field | Value |
|---|---|
| **Purpose** | Verify that a file with no read permission raises `SchemaVersionError` with permission-specific message |
| **Input** | Valid JSON file, `os.chmod(0o000)` applied |
| **Expected** | `SchemaVersionError` raised, message mentions permission denied |
| **Fixture** | `manager(tmp_path)`, pre-write valid JSON, then `chmod 000` |
| **Note** | The corrupt rename must NOT be attempted (cannot rename what cannot be read) |

#### Test: `test_read_directory_as_file`

| Field | Value |
|---|---|
| **Purpose** | Verify that a directory at the schema path raises `SchemaVersionError` |
| **Input** | `schema_path` points to an existing directory |
| **Expected** | `SchemaVersionError` raised |
| **Fixture** | `manager(tmp_path)`, replace file with `os.mkdir(manager._schema_path)` |

#### Test: `test_read_symlink_to_valid_file`

| Field | Value |
|---|---|
| **Purpose** | Verify that reading through a symlink works correctly |
| **Input** | Valid JSON at real path, symlink at `manager._schema_path` pointing to it |
| **Expected** | Returns correct `SchemaVersion` |
| **Fixture** | `manager(tmp_path)`, create symlink |

---

### A.8 — Orphan .tmp Cleanup

#### Test: `test_init_cleans_orphan_tmp`

| Field | Value |
|---|---|
| **Purpose** | Verify that `__init__` removes orphaned `.json.tmp` files from previous crashes |
| **Input** | An orphaned `schema.json.tmp` file exists in the same directory as `schema.json` (which may or may not exist) |
| **Expected** | After `SchemaVersionManager.__init__()`, the `.json.tmp` file is deleted |
| **Fixture** | `manager(tmp_path)`, create `schema.json.tmp` manually |

#### Test: `test_init_cleans_orphan_tmp_no_schema_json`

| Field | Value |
|---|---|
| **Purpose** | Verify orphan cleanup works even when `schema.json` itself does not exist |
| **Input** | Orphan `schema.json.tmp` exists, no `schema.json` |
| **Expected** | `.json.tmp` deleted, no error |
| **Fixture** | `manager(tmp_path)`, create only `.tmp` file |

#### Test: `test_init_cleans_orphan_tmp_schema_json_exists`

| Field | Value |
|---|---|
| **Purpose** | Verify orphan cleanup works when both `schema.json` and `schema.json.tmp` exist |
| **Input** | Valid `schema.json` and orphan `schema.json.tmp` both present |
| **Expected** | `.json.tmp` deleted, `schema.json` untouched, `read()` returns valid version |
| **Fixture** | `manager(tmp_path)`, write both files |

#### Test: `test_init_cleans_orphan_tmp_ignore_other_tmp`

| Field | Value |
|---|---|
| **Purpose** | Verify only `schema.json.tmp` (not arbitrary `.tmp` files) is cleaned |
| **Input** | Orphan `schema.json.tmp` + unrelated `other_file.tmp` |
| **Expected** | `schema.json.tmp` deleted, `other_file.tmp` remains untouched |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_init_orphan_tmp_cleanup_failure_logged`

| Field | Value |
|---|---|
| **Purpose** | Verify that failing to delete orphan `.tmp` is logged but does not raise |
| **Input** | Orphan `.tmp` file made read-only (or directory non-writable) |
| **Expected** | No exception, log warning about failed cleanup |
| **Fixture** | `manager(tmp_path)`, create `.tmp`, make parent read-only |

---

### A.9 — exists() Method

#### Test: `test_exists_true`

| Field | Value |
|---|---|
| **Purpose** | Verify `exists()` returns `True` when `schema.json` exists |
| **Input** | Write valid JSON |
| **Expected** | `manager.exists()` is `True` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_exists_false`

| Field | Value |
|---|---|
| **Purpose** | Verify `exists()` returns `False` when `schema.json` does not exist |
| **Input** | No file |
| **Expected** | `manager.exists()` is `False` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_exists_after_orphan_cleanup`

| Field | Value |
|---|---|
| **Purpose** | Verify `exists()` reflects reality after orphan cleanup |
| **Input** | Only orphan `.tmp` file exists, no `schema.json` |
| **Expected** | After `__init__`: orphan cleaned, `exists()` is `False` |
| **Fixture** | `manager(tmp_path)` |

---

### A.10 — Logging Behavior

#### Test: `test_read_missing_logs_info`

| Field | Value |
|---|---|
| **Purpose** | Verify that missing file logs at INFO level with the resolved path |
| **Input** | No file |
| **Expected** | Log message contains `"schema.json"`, `"not found"` or similar, at level INFO |
| **Fixture** | `manager(tmp_path)`, use `caplog` fixture |

#### Test: `test_read_corrupt_logs_warning`

| Field | Value |
|---|---|
| **Purpose** | Verify that corrupt file logs at WARNING level with diagnostic info |
| **Input** | Invalid JSON |
| **Expected** | Log message at WARNING level, contains the renamed path and first N chars of corrupt content |
| **Fixture** | `manager(tmp_path)`, use `caplog` fixture |

#### Test: `test_read_permission_error_logs_error`

| Field | Value |
|---|---|
| **Purpose** | Verify that permission error logs at ERROR level |
| **Input** | File with `chmod 000` |
| **Expected** | Log message at ERROR level, mentions permission |
| **Fixture** | `manager(tmp_path)`, use `caplog` fixture |

---

### A.11 — Unicode and Encoding

#### Test: `test_read_unicode_version_string`

| Field | Value |
|---|---|
| **Purpose** | Verify that `schema_version` with ASCII-only content works (version strings are always ASCII) |
| **Input** | Normal ASCII version |
| **Expected** | Parses correctly |

#### Test: `test_read_unicode_description`

| Field | Value |
|---|---|
| **Purpose** | Verify that non-ASCII characters in `description` field do not break parsing (the description is optional and free-text) |
| **Input** | `description: "Versió 2.0.0 — 模式更新"` (accented + CJK characters) |
| **Expected** | Returns `SchemaVersion(2, 0, 0)` — description is validated for type (string) but not for content |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_utf8_bom`

| Field | Value |
|---|---|
| **Purpose** | Verify that a UTF-8 BOM at the start of the file is handled (Windows text editors may add BOM) |
| **Input** | JSON with `\ufeff` byte order mark prefix |
| **Expected** | Either: correctly parses (if `json.load` handles BOM) OR raises `SchemaVersionError` with clear message. Document the behavior. |
| **Fixture** | `manager(tmp_path)` |

---

### A.12 — Edge Cases

#### Test: `test_read_large_description`

| Field | Value |
|---|---|
| **Purpose** | Verify that a very long description (10KB) does not cause performance or memory issues |
| **Input** | `description` field containing 10,000 characters |
| **Expected** | Returns correct `SchemaVersion`, completes in <100ms |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_file_with_only_required_fields`

| Field | Value |
|---|---|
| **Purpose** | Verify that JSON with only the three required fields (no `description`) works |
| **Input** | `{"schema_version": "2.0.0", "app_version": "2.0.0", "updated_at": "2026-06-20T12:00:00Z"}` |
| **Expected** | Returns `SchemaVersion(2, 0, 0)` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_file_with_null_description`

| Field | Value |
|---|---|
| **Purpose** | Verify that `null` description does not raise (some writers may omit or null the optional field) |
| **Input** | `description: null` |
| **Expected** | Returns correct `SchemaVersion` |
| **Fixture** | `manager(tmp_path)` |

#### Test: `test_read_file_with_empty_description`

| Field | Value |
|---|---|
| **Purpose** | Verify that empty string description is accepted |
| **Input** | `description: ""` |
| **Expected** | Returns correct `SchemaVersion` |
| **Fixture** | `manager(tmp_path)` |

---

## B. SchemaVersionManager.read() Design

### B.1 — __init__() Internal Workflow

```
1. Resolve schema_path:
   └── If schema_path is None →
         schema_path = BASE_DIR / "schema.json"
       Else →
         schema_path = Path(schema_path)  (cast to Path if string)

2. Store: self._schema_path = resolved_path

3. Cleanup orphaned .tmp:
   ├── Compute tmp_path: schema_path.with_suffix(".json.tmp")
   ├── If tmp_path.is_file():
   │     Try: tmp_path.unlink()
   │     Except OSError: logger.warning("Could not clean orphan .tmp file")
   └── (silent if no .tmp exists)
```

### B.2 — read() Internal Workflow

```
read():
1. Check file existence:
   ├── If not self._schema_path.is_file():
   │     logger.info("Schema file not found: %s", self._schema_path)
   │     return None
   │     (This is the FIRST RUN path — caller will create schema.json)

2. Read file content:
   ├── Try: raw_text = self._schema_path.read_text(encoding="utf-8")
   ├── Except PermissionError:
   │     logger.error("Permission denied reading schema file: %s", ...)
   │     raise SchemaVersionError("Permission denied reading schema file")
   ├── Except FileNotFoundError:     (race condition — deleted between check and read)
   │     return None  (treat as first run)
   ├── Except OSError as exc:
   │     logger.error("Cannot read schema file: %s", exc)
   │     raise SchemaVersionError(f"Cannot read schema file: {exc}")

3. Parse JSON:
   ├── Try: data = json.loads(raw_text)
   ├── Except json.JSONDecodeError:
   │     self._rename_corrupt(raw_text, "invalid JSON")
   │     raise SchemaVersionError("Schema file contains invalid JSON")

4. Validate top-level type:
   ├── If not isinstance(data, dict):
   │     self._rename_corrupt(raw_text, "not a JSON object")
   │     raise SchemaVersionError("Schema file is not a JSON object")

5. Validate required fields exist and are strings:
   ├── For each field in REQUIRED_FIELDS = ("schema_version", "app_version", "updated_at"):
   │     If field not in data:
   │       self._rename_corrupt(raw_text, f"missing required field: {field}")
   │       raise SchemaVersionError(f"Missing required field: {field}")
   │     If not isinstance(data[field], str):
   │       self._rename_corrupt(raw_text, f"field {field} is not a string")
   │       raise SchemaVersionError(f"Field '{field}' must be a string")

6. Validate schema_version format:
   ├── Try: version = SchemaVersion.from_string(data["schema_version"])
   ├── Except ValueError:
   │     self._rename_corrupt(raw_text, f"invalid schema_version: {data['schema_version']}")
   │     raise SchemaVersionError(f"Invalid schema_version: {data['schema_version']}")

7. Validate app_version format:    (informational field — validate it exists as string,
   │                                but for robustness also check format. If invalid format,
   │                                log warning and continue — do NOT corrupt-rename.)

8. Validate updated_at format:     (optional strict validation — validate it exists as string.
   │                                ISO-8601 format check is strict.)

9. Return version:
   └── logger.debug("Schema version read: %s", version)
       return version
```

### B.3 — Validation Sequence

```
read() validation is a strict linear gate:

1. [GATE] File exists?        NO  → return None (first run)
                                │
                                YES
                                ▼
2. [GATE] Readable?          NO  → SchemaVersionError (permission)
                                │
                                YES
                                ▼
3. [GATE] Valid JSON?         NO  → corrupt → rename → SchemaVersionError
                                │
                                YES
                                ▼
4. [GATE] Is a dict?          NO  → corrupt → rename → SchemaVersionError
                                │
                                YES
                                ▼
5. [GATE] Has schema_version?  NO  → corrupt → rename → SchemaVersionError
                                │
                                YES
                                ▼
6. [GATE] schema_version       NO  → corrupt → rename → SchemaVersionError
   is a string?                     
                                │
                                YES
                                ▼
7. [GATE] schema_version       NO  → corrupt → rename → SchemaVersionError
   is valid semver?                 
                                │
                                YES
                                ▼
8. [GATE] Has app_version?     NO  → corrupt → rename → SchemaVersionError
                                │
                                YES
                                ▼
9. [GATE] app_version          NO  → corrupt → rename → SchemaVersionError
   is a string?                     
                                │
                                YES
                                ▼
10.[GATE] Has updated_at?      NO  → corrupt → rename → SchemaVersionError
                                │
                                YES
                                ▼
11.[GATE] updated_at           NO  → corrupt → rename → SchemaVersionError
   is a string?                     
                                │
                                YES
                                ▼
                        return SchemaVersion
```

Gates 5-11 all route through the same `_rename_corrupt()` path and raise `SchemaVersionError`. The difference is only the error message content.

### B.4 — Error Handling Flow

```
read() entry
    │
    ├── FileNotFoundError → return None            (first run — not an error)
    │
    ├── PermissionError → SchemaVersionError       (block startup — admin issue)
    │                    (no rename — can't read to rename)
    │
    ├── OSError → SchemaVersionError               (block startup — filesystem issue)
    │             (no rename — disk may be failing)
    │
    ├── json.JSONDecodeError → SchemaVersionError  (corrupt — rename, preserve for forensics)
    │                           (file renamed to .corrupt.<ts>)
    │
    ├── validation: not a dict → SchemaVersionError  (corrupt — rename)
    │
    ├── validation: missing field → SchemaVersionError  (corrupt — rename)
    │
    ├── validation: field not string → SchemaVersionError  (corrupt — rename)
    │
    └── validation: bad version → SchemaVersionError  (corrupt — rename)
```

**Exception hierarchy:**

```
SchemaVersionError(Exception)
    └── Raised for: corrupt JSON, invalid format, missing fields, permission denied,
                    read errors, directory-instead-of-file
    └── Message includes specific reason for the failure
```

The caller (`__main__.py` later, unit tests now) is responsible for:
- Catching `SchemaVersionError` and determining recovery (for now, propagate in tests)
- Catching `return None` and treating as first run

### B.5 — Corrupt File Recovery Flow

```
_rename_corrupt(file_content: str, reason: str) → None
1. Generate timestamp: datetime.now().strftime("%Y%m%d_%H%M%S")
2. Compose target path: schema_path.parent / f"schema.json.corrupt.{timestamp}"
3. Try:
     os.rename(self._schema_path, target_path)
     logger.warning("Corrupt schema file renamed to %s (reason: %s)", target_path, reason)
     logger.warning("Corrupt content (first 200 chars): %s", file_content[:200])
4. Except OSError as exc:
     logger.error("Could not rename corrupt schema file: %s", exc)
     # Continue — SchemaVersionError is raised regardless
```

Note: If `_rename_corrupt` fails (permissions, cross-device link), the original corrupt file remains in place. This is acceptable — on next startup, it will be detected again and retried.

### B.6 — Orphan .tmp Cleanup Behavior

```
__init__():
1. Compute tmp_path = self._schema_path.with_suffix(".json.tmp")
2. If tmp_path.is_file():
     Try:
       tmp_path.unlink()
       logger.debug("Cleaned orphan temporary file: %s", tmp_path)
     Except OSError as exc:
       logger.warning("Could not clean orphan temporary file %s: %s", tmp_path, exc)
3. (No action if .tmp does not exist)
```

**Scope:** Only `schema.json.tmp` (the specific `.tmp` file matching our schema path). Does NOT scan for arbitrary `.tmp` files in the directory.

**Timing:** Runs once in `__init__()`, not in `read()`. This ensures cleanup happens even if `read()` is never called (though in practice `read()` is always called after construction).

---

## C. Internal Method Design

The following private methods support `read()`. They are implementation details, not part of the public API.

```python
class SchemaVersionManager:
    # __init__ and read (public) — designed above

    # ── Internal helpers ──────────────────────────────────────

    @staticmethod
    def _required_fields() -> tuple[str, ...]:
        """Return the required top-level keys in schema.json.
        Returns: ("schema_version", "app_version", "updated_at")
        Used for validation; extracted to a constant-like method for testability.
        """

    def _rename_corrupt(self, content: str, reason: str) -> None:
        """Rename the current schema.json to schema.json.corrupt.<timestamp>.
        Called when the file cannot be parsed or validated.
        Preserves the original content for forensic analysis.
        Logs warning with reason and first 200 chars of content.
        If rename fails (permissions), logs error and continues.
        """

    def _clean_orphan_tmp(self) -> None:
        """Delete orphaned schema.json.tmp file if it exists.
        Called once during __init__.
        Failures are logged but not propagated.
        """
```

### Dependencies for schema_version_manager.py

```
stdlib:
  - json          (json.loads, json.JSONDecodeError)
  - logging       (logger.info, logger.warning, logger.error)
  - os            (os.rename, os.replace in future)
  - pathlib       (Path)

Internal:
  - trackora.core.paths           → BASE_DIR (for default path resolution)
  - trackora.core.schema_version  → SchemaVersion, SchemaVersionError

Must NOT import:
  - Any database module
  - Any service module
  - Any UI module
  - Any tracker module
```

---

## D. Acceptance Criteria

### D.1 — Constructor

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-01 | Default constructor resolves `BASE_DIR / "schema.json"` | `test_init_default_path_resolution` |
| AC-READ-02 | Explicit `schema_path` overrides default | `test_init_custom_path` |
| AC-READ-03 | `schema_path` stored as `Path` object | `test_init_path_type` |
| AC-READ-04 | Orphan `.json.tmp` file is cleaned on construction | `test_init_cleans_orphan_tmp` |
| AC-READ-05 | Orphan cleanup failure is logged, not raised | `test_init_orphan_tmp_cleanup_failure_logged` |
| AC-READ-06 | Only matching `.json.tmp` is cleaned, not all `.tmp` | `test_init_cleans_orphan_tmp_ignore_other_tmp` |

### D.2 — read() — File Missing

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-07 | `read()` returns `None` when file does not exist | `test_read_returns_none_when_missing` |
| AC-READ-08 | `None` return has no side effects (no files created/deleted) | `test_read_none_is_not_an_error` |
| AC-READ-09 | Missing file logs at INFO level | `test_read_missing_logs_info` |

### D.3 — read() — Valid File

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-10 | `read()` returns correct `SchemaVersion` for valid JSON | `test_read_returns_schema_version` |
| AC-READ-11 | Minor and patch versions parse correctly | `test_read_returns_correct_version_minor` + `test_read_returns_correct_version_patch` |
| AC-READ-12 | Extra unknown JSON keys are silently ignored | `test_read_unknown_keys_ignored` |
| AC-READ-13 | Each `read()` call reads fresh from disk (stateless) | `test_read_returns_new_schema_version_each_call` |

### D.4 — read() — Corrupt File Handling

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-14 | Invalid JSON raises `SchemaVersionError` | `test_read_corrupt_invalid_json` |
| AC-READ-15 | Empty file raises `SchemaVersionError` | `test_read_corrupt_empty_file` |
| AC-READ-16 | Whitespace-only file raises `SchemaVersionError` | `test_read_corrupt_whitespace_only` |
| AC-READ-17 | Non-dict JSON raises `SchemaVersionError` | `test_read_corrupt_boolean_top_level`, `test_read_corrupt_json_array_top_level`, `test_read_corrupt_null_top_level` |
| AC-READ-18 | Missing `schema_version` raises `SchemaVersionError` | `test_read_corrupt_missing_schema_version` |
| AC-READ-19 | Missing `app_version` raises `SchemaVersionError` | `test_read_corrupt_missing_app_version` |
| AC-READ-20 | Missing `updated_at` raises `SchemaVersionError` | `test_read_corrupt_missing_updated_at` |
| AC-READ-21 | Non-string `schema_version` raises `SchemaVersionError` | `test_read_corrupt_schema_version_not_a_string` |
| AC-READ-22 | Invalid `schema_version` format raises `SchemaVersionError` | `test_read_corrupt_schema_version_invalid_format`, `test_read_corrupt_schema_version_partial_format` |
| AC-READ-23 | Non-string `app_version` raises `SchemaVersionError` | `test_read_corrupt_app_version_not_a_string` |
| AC-READ-24 | Non-string `updated_at` raises `SchemaVersionError` | `test_read_corrupt_updated_at_not_a_string` |

### D.5 — read() — Corrupt File Recovery (Rename)

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-25 | Corrupt file is renamed to `.corrupt.<timestamp>` | `test_read_corrupt_file_is_renamed` |
| AC-READ-26 | Original content is preserved in renamed copy | `test_read_corrupt_original_content_preserved` |
| AC-READ-27 | Timestamp uses `YYYYMMDD_HHMMSS` format | `test_read_corrupt_rename_timestamp_format` |
| AC-READ-28 | Multiple corrupt files create distinct `.corrupt` files | `test_read_corrupt_multiple_corrupt_files` |
| AC-READ-29 | Rename failure does not prevent `SchemaVersionError` | `test_read_corrupt_rename_fails_silently_logged` |
| AC-READ-30 | After rename, next `read()` returns `None` | `test_read_corrupt_after_rename_returns_none` |
| AC-READ-31 | Rename failure is logged at ERROR level | Implicit in `test_read_corrupt_rename_fails_silently_logged` |

### D.6 — read() — Permission Errors

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-32 | Permission denied raises `SchemaVersionError` with permission message | `test_read_permission_denied` |
| AC-READ-33 | Directory at schema path raises `SchemaVersionError` | `test_read_directory_as_file` |
| AC-READ-34 | Symlink to valid file works correctly | `test_read_symlink_to_valid_file` |

### D.7 — exists() Method

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-35 | `exists()` returns `True` when file exists | `test_exists_true` |
| AC-READ-36 | `exists()` returns `False` when file does not exist | `test_exists_false` |
| AC-READ-37 | `exists()` reflects reality after orphan cleanup | `test_exists_after_orphan_cleanup` |

### D.8 — Unicode and Edge Cases

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-38 | Unicode description is accepted | `test_read_unicode_description` |
| AC-READ-39 | UTF-8 BOM handling is documented (pass or fail) | `test_read_utf8_bom` |
| AC-READ-40 | Large description does not cause slowdown | `test_read_large_description` |
| AC-READ-41 | File with only required fields works | `test_read_file_with_only_required_fields` |
| AC-READ-42 | `null` description is accepted | `test_read_file_with_null_description` |
| AC-READ-43 | Empty description is accepted | `test_read_file_with_empty_description` |

### D.9 — Non-Functional

| ID | Criterion | Target |
|---|---|---|
| AC-READ-44 | `read()` on valid file completes in <10ms | Benchmarked |
| AC-READ-45 | `read()` on missing file completes in <1ms | Benchmarked |
| AC-READ-46 | `__init__()` with no orphan cleanup completes in <1ms | Benchmarked |
| AC-READ-47 | Manager is stateless — multiple instances with same path are interchangeable | Verified by design |
| AC-READ-48 | No database, service, UI, or tracker imports exist | Code review |
| AC-READ-49 | Orphan `.tmp` cleanup does not raise exceptions | `test_init_orphan_tmp_cleanup_failure_logged` |

### D.10 — Regression

| ID | Criterion | How Verified |
|---|---|---|
| AC-READ-50 | All 70 existing `test_schema_version.py` tests still pass | `pytest tests/test_schema_version.py -q` |
| AC-READ-51 | No existing non-PyQt6 tests break | `pytest --ignore=tests/test_crash_dialog.py --ignore=tests/test_dashboard_controller.py ... -q` (exclude PyQt6-dependent) |

---

## E. Implementation Sequence

```
RED→GREEN→REFACTOR per test group:

Phase 2.1 — __init__ and SchemaVersionError
  ├── Add SchemaVersionError exception to trackora/core/schema_version.py
  ├── test_init_default_path_resolution  (RED→GREEN)
  ├── test_init_custom_path              (RED→GREEN)
  ├── test_init_path_type                (RED→GREEN)
  └── (orphan .tmp cleanup deferred to Phase 2.4)

Phase 2.2 — read() missing file
  ├── test_read_returns_none_when_missing  (RED→GREEN)
  ├── test_read_none_is_not_an_error       (RED→GREEN)
  └── test_read_missing_logs_info         (RED→GREEN)

Phase 2.3 — read() valid file
  ├── test_read_returns_schema_version      (RED→GREEN)
  ├── test_read_returns_correct_version_minor_patch  (RED→GREEN)
  ├── test_read_unknown_keys_ignored        (RED→GREEN)
  └── test_read_returns_new_schema_version_each_call  (RED→GREEN)

Phase 2.4 — orphan .tmp cleanup
  ├── test_init_cleans_orphan_tmp           (RED→GREEN)
  ├── test_init_cleans_orphan_tmp_no_schema_json (RED→GREEN)
  ├── test_init_cleans_orphan_tmp_schema_json_exists (RED→GREEN)
  ├── test_init_cleans_orphan_tmp_ignore_other_tmp  (RED→GREEN)
  └── test_init_orphan_tmp_cleanup_failure_logged    (RED→GREEN)

Phase 2.5 — read() corrupt JSON (rename + preserve)
  ├── _rename_corrupt internal method
  ├── test_read_corrupt_invalid_json        (RED→GREEN)
  ├── test_read_corrupt_file_is_renamed     (RED→GREEN)
  ├── test_read_corrupt_original_content_preserved (RED→GREEN)
  ├── test_read_corrupt_rename_timestamp_format    (RED→GREEN)
  ├── test_read_corrupt_multiple_corrupt_files     (RED→GREEN)
  ├── test_read_corrupt_rename_does_not_raise      (RED→GREEN)
  ├── test_read_corrupt_empty_file          (RED→GREEN)
  ├── test_read_corrupt_whitespace_only     (RED→GREEN)
  ├── test_read_corrupt_after_rename_returns_none  (RED→GREEN)
  └── test_read_corrupt_rename_fails_silently_logged (RED→GREEN)

Phase 2.6 — read() validation (missing/invalid fields)
  ├── test_read_corrupt_missing_schema_version  (RED→GREEN)
  ├── test_read_corrupt_missing_app_version     (RED→GREEN)
  ├── test_read_corrupt_missing_updated_at      (RED→GREEN)
  ├── test_read_corrupt_schema_version_not_a_string    (RED→GREEN)
  ├── test_read_corrupt_schema_version_invalid_format   (RED→GREEN)
  ├── test_read_corrupt_schema_version_partial_format   (RED→GREEN)
  ├── test_read_corrupt_app_version_not_a_string        (RED→GREEN)
  ├── test_read_corrupt_updated_at_not_a_string         (RED→GREEN)
  ├── test_read_corrupt_boolean_top_level       (RED→GREEN)
  ├── test_read_corrupt_json_array_top_level    (RED→GREEN)
  ├── test_read_corrupt_null_top_level          (RED→GREEN)
  └── test_read_file_with_only_required_fields  (RED→GREEN)

Phase 2.7 — read() permission errors
  ├── test_read_permission_denied   (RED→GREEN)
  ├── test_read_directory_as_file   (RED→GREEN)
  └── test_read_symlink_to_valid_file (RED→GREEN)

Phase 2.8 — exists() method
  ├── test_exists_true              (RED→GREEN)
  ├── test_exists_false             (RED→GREEN)
  └── test_exists_after_orphan_cleanup  (RED→GREEN)

Phase 2.9 — unicode and edge cases
  ├── test_read_unicode_description          (RED→GREEN)
  ├── test_read_utf8_bom                     (RED→GREEN)
  ├── test_read_large_description            (RED→GREEN)
  ├── test_read_file_with_null_description   (RED→GREEN)
  └── test_read_file_with_empty_description  (RED→GREEN)

Phase 2.10 — logging verification
  ├── test_read_corrupt_logs_warning   (RED→GREEN with caplog)
  └── test_read_permission_error_logs_error (RED→GREEN with caplog)

Phase 2.11 — final validation
  ├── Full test suite pass
  ├── SchemaVersion regression (70 tests)
  └── Coverage check
```

---

## F. Validation Commands

### Primary — Run all Step 2 tests:

```bash
python -m pytest tests/test_schema_version_manager.py -v
```

### Run single test:

```bash
python -m pytest tests/test_schema_version_manager.py::TestRead::test_read_returns_none_when_missing -v
```

### Run SchemaVersion regression (ensure Step 1 not broken):

```bash
python -m pytest tests/test_schema_version.py -v
```

### Full non-PyQt6 regression (PyQt6-dependent tests excluded):

```bash
python -m pytest \
  tests/test_schema_version.py \
  tests/test_schema_version_manager.py \
  tests/test_bug_report_model.py \
  tests/test_feature_request_model.py \
  tests/test_feedback_report_model.py \
  tests/test_game_detector.py \
  tests/test_tracking_state.py \
  tests/test_session_manager.py \
  -v
```

### Coverage check:

```bash
python -m pytest \
  tests/test_schema_version.py \
  tests/test_schema_version_manager.py \
  --cov=trackora.core.schema_version \
  --cov=trackora.core.schema_version_manager \
  --cov-report=term-missing \
  -v
```

### Step 2 completion validation (run these three commands in sequence):

```bash
# 1. All Step 2 tests pass
python -m pytest tests/test_schema_version_manager.py -q
# Expected: 45+ passed

# 2. Step 1 regression
python -m pytest tests/test_schema_version.py -q
# Expected: 70 passed

# 3. SchemaVersionError imported correctly
python -c "from trackora.core.schema_version import SchemaVersionError; print('OK')"
# Expected: OK
```

---

## G. Files Modified in This Step

| Action | File | Change |
|---|---|---|
| **CREATE** | `trackora/core/schema_version_manager.py` | `SchemaVersionManager` class with `__init__()`, `read()`, `exists()`, `_rename_corrupt()`, `_clean_orphan_tmp()` |
| **MODIFY** | `trackora/core/schema_version.py` | Add `SchemaVersionError(Exception)` exception class |
| **CREATE** | `tests/test_schema_version_manager.py` | 45+ tests for Step 2 scope |

No other files are created or modified.

---

## H. Dependency Chain Within Step 2

```
SchemaVersionError (in schema_version.py)
  │
  ▼
SchemaVersionManager.__init__()    ───→ _clean_orphan_tmp()
  │
  ▼
SchemaVersionManager.read()
  ├── _rename_corrupt()  (called only on corrupt file paths)
  │
  └── depends on: SchemaVersion.from_string()  (from Step 1)
                  SchemaVersion.is_valid_format()  (from Step 1)
                  json.loads()  (stdlib)
                  os.rename()   (stdlib)
```

---

## I. Test Count Summary

| Phase | Tests | Cumulative |
|---|---|---|
| 2.1 — __init__ | 3 | 3 |
| 2.2 — read() missing | 3 | 6 |
| 2.3 — read() valid | 4 | 10 |
| 2.4 — orphan cleanup | 5 | 15 |
| 2.5 — corrupt JSON + rename | 10 | 25 |
| 2.6 — field validation | 12 | 37 |
| 2.7 — permission errors | 3 | 40 |
| 2.8 — exists() | 3 | 43 |
| 2.9 — unicode/edge | 5 | 48 |
| 2.10 — logging | 2 | 50 |

**Total Step 2 tests: approximately 50** (precise count determined during TDD — parametrized tests may increase this).
