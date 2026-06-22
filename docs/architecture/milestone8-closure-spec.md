# Milestone 8 Closure — Architecture Patch Specification

## Overview

Closes 6 issues identified during the Milestone 8 independent verification audit:

| ID | Issue | Component | Severity |
|---|---|---|---|
| H1 | No post-extraction validation in restore | BackupManager.restore_backup() | High |
| H2 | Safety rollback not atomic | BackupManager._restore_from_safety() | High |
| H3 | Safety backup not verified before rollback | BackupManager._restore_from_safety() | High |
| H4 | Backup failure test is placeholder | test_startup_integration.py | High |
| H5 | SQL injection risk in _column_exists() | v2_0_0_add_discovery_columns.py | High |
| C1 | No end-to-end main() integration test | test_startup_integration.py | Critical |

---

## 1. Restore Validation Workflow

### Current (line 497-518)

```
extract to staging → os.replace(db) → os.replace(schema) → cleanup
```

### Required

```
extract to staging → validate all files → os.replace(db) → os.replace(schema) → cleanup
```

### Validation steps (in order)

1. **Required files check** — `trackora.db`, `schema.json` exist in staging
2. **SHA-256 checksum verification** — each file's checksum matches the manifest
3. **Manifest consistency check** — `file_count` matches actual file count
4. **SQLite database opens** — `sqlite3.connect()` on the staged `trackora.db` succeeds
5. **`PRAGMA integrity_check`** — returns `"ok"` (single row with value `"ok"`)
6. **schema.json validation** — `SchemaVersionManager()` can parse it via `read()`

If any validation step fails:
- Clean up staging directory
- Return `RestoreResult(success=False, error=...)` with specific failure reason
- **Do NOT replace production files**
- **Do NOT attempt rollback** (production state is unchanged)

### Error message format

```
"Restore validation failed: {specific_reason} — production files not modified."
```

---

## 2. Atomic Rollback Workflow

### Current (`_restore_from_safety`, lines 581-590)

```python
with ZipFile(safety_path, "r") as zf:
    db_data = zf.read("trackora.db")
    DATABASE_PATH.write_bytes(db_data)       # direct write — not atomic
    schema_data = zf.read("schema.json")
    schema_path.write_bytes(schema_data)      # direct write — not atomic
```

### Required

```
safety backup → verify_backup() → extract to staging directory → validate → atomic os.replace()
```

### Workflow

1. **Verify safety backup** — call `self.verify_backup(safety_backup_id)`; if fails, raise `RuntimeError` with clear message (no destructive action)
2. **Create staging directory** — `self._backup_dir / f".rollback_{uuid.uuid4().hex[:12]}"`
3. **Extract** `trackora.db` and `schema.json` to staging
4. **Validate extracted files** — SHA-256 checksum match, SQLite open + `PRAGMA integrity_check`, schema.json parseable
5. **Atomic replace** — `os.replace(str(staging_db), str(DATABASE_PATH))` then `os.replace(str(staging_schema), str(schema_path))`
6. **Clean up staging** — `shutil.rmtree(staging_dir)`

### Safety guarantee

At no point should a partial write leave production files in an indeterminate state. If validation fails, the function raises an exception without touching production files.

---

## 3. Safety Backup Verification Before Rollback

### Current (`restore_backup`, lines 526-561)

```python
except Exception as exc:
    self._restore_from_safety(safety_backup_id)  # no verification
```

### Required

```python
except Exception as exc:
    verify_result = self.verify_backup(safety_backup_id)
    if not verify_result.valid:
        logger.critical("Safety backup %s is corrupt: %s", safety_backup_id, verify_result.error)
        return RestoreResult(
            success=False, backup_id=backup_id,
            safety_backup_id=safety_backup_id,
            error=f"Restore failed and safety backup is corrupt. "
                  f"Safety backup {safety_backup_id} is available for manual inspection. "
                  f"Original error: {exc}",
        )
    self._restore_from_safety(safety_backup_id)
```

---

## 4. Startup Integration Test Strategy

### Goal

Call `trackora.__main__.main()` with all external dependencies mocked.

### Mocks required

| Dependency | Mock strategy |
|---|---|
| `QApplication` | `monkeypatch.setattr("PyQt6.QtWidgets.QApplication.__init__", lambda self, *a, **kw: None)` |
| `QMessageBox` | `monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.critical", lambda *a, **kw: None)` |
| `QMessageBox.warning` | `monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.warning", lambda *a, **kw: None)` |
| `QTimer` | `monkeypatch.setattr("PyQt6.QtCore.QTimer.__init__", lambda self, *a, **kw: None)` |
| `DatabaseManager` | Mock returning a `sqlite3.connect(":memory:")` connection |
| `CrashService` | Mock `check_for_crash()`, `mark_startup()` |
| All repositories | Simple mocks |
| All services | Simple mocks |
| `MainWindow` | `monkeypatch.setattr(UiClass, ...)` |
| `ProcessMonitor` | Mock `.start()` |
| `ThemeManager` | Mock `.apply_theme()` |
| `_acquire_lock` | Return `True` |

### Test scenarios

1. **First run** — no `schema.json` → verify `svm.write()` called, no backup/migration
2. **Normal startup** — same version → no backup/migration, services initialized
3. **Migration needed** — older schema → backup + migration + version write
4. **Newer data blocks** — newer schema → `sys.exit(2)` called

---

## 5. Backup Failure Test Strategy

### Goal

Replace the placeholder `assert True` with a test that actually simulates backup failure.

### Approach

1. Patch `BackupManager.create_backup()` to return `BackupResult(success=False, error="Simulated failure")`
2. Call `main()` (via the startup integration test framework)
3. Verify `QMessageBox.critical` was called with "Backup Failed" title
4. Verify `sys.exit(3)` was called
5. Verify migration was NOT executed

Implementation: use `monkeypatch.setattr` to replace `BackupManager.create_backup` and `pytest.raises(SystemExit)`.

---

## 6. `_column_exists()` Hardening Strategy

### Current

```python
def _column_exists(connection, table, column):
    cursor = connection.cursor()
    cursor.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cursor.fetchall())
```

### Required

Use a safe approach. Options (choose one):

**Option A — Validate table name against allowlist (RECOMMENDED)**

```python
_VALID_TABLES = frozenset({"games"})

def _column_exists(connection, table, column):
    if table not in _VALID_TABLES:
        raise ValueError(f"Unknown table: {table}")
    cursor = connection.cursor()
    cursor.execute("PRAGMA table_info(?);", (table,))  # This won't work — PRAGMA doesn't support param
```

Wait — SQLite PRAGMA statements do not support parameterized `?` placeholders. So we need a different approach.

**Option B — Validate and then use f-string (ACTUAL SOLUTION)**

```python
_VALID_TABLES = frozenset({"games"})

def _column_exists(connection, table, column):
    if table not in _VALID_TABLES:
        raise ValueError(f"Unknown table: {table}")
    cursor = connection.cursor()
    cursor.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cursor.fetchall())
```

Since `PRAGMA` doesn't support parameterized queries, the defense is to validate `table` against a hardcoded allowlist. The `column` parameter is already safe (compared via `==` after fetch, never interpolated).

---

## 7. Acceptance Criteria

| Criteria | Pass condition |
|---|---|
| Restore validation | `restore_backup()` with corrupt staged `trackora.db` returns `success=False` without modifying production files |
| Rollback atomicity | `_restore_from_safety()` uses staging directory + validation + atomic `os.replace()` |
| Safety backup verification | Restore with corrupt safety backup returns graceful error, does not attempt rollback |
| SQL hardening | `_column_exists()` validates table name against allowlist |
| Startup integration test | Test calls `main()` with mocked deps and verifies first-run, normal, migration, and newer-data paths |
| Backup failure test | Test simulates `create_backup()` failure and verifies `sys.exit(3)` |
| No regressions | All existing tests pass |
| Coverage | No decrease in any component's coverage percentage |
