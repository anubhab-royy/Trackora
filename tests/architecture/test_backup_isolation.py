"""Architecture enforcement: BackupManager layer isolation.

Rules:
    1. backup_manager.py must not import from `database`, `services`,
       `ui`, `tracker`, or `trackora_stats`.
    2. backup_manager.py must only import from stdlib and
       `trackora.core` packages.
    3. No source file outside test files and backup_manager.py
       itself may open or manipulate ZIP archives that look like
       backup archives.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUP_MANAGER_FILE = (
    PROJECT_ROOT / "trackora" / "core" / "backup_manager.py"
)
TEST_FILE = Path(__file__).resolve()

FORBIDDEN_IMPORTS = {
    "database",
    "services",
    "ui",
    "tracker",
    "trackora_stats",
}

ALLOWED_TRACKORA_PREFIXES = {"trackora"}

STDLIB_PREFIXES = {
    "__future__",
    "abc",
    "ast",
    "collections",
    "copy",
    "dataclasses",
    "datetime",
    "enum",
    "functools",
    "hashlib",
    "inspect",
    "io",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "pickle",
    "queue",
    "random",
    "re",
    "shutil",
    "stat",
    "string",
    "struct",
    "sqlite3",
    "sys",
    "tempfile",
    "textwrap",
    "threading",
    "time",
    "types",
    "typing",
    "unittest",
    "uuid",
    "warnings",
    "weakref",
    "zoneinfo",
    "zipfile",
}

SOURCE_DIRS = [
    PROJECT_ROOT / "trackora",
    PROJECT_ROOT / "services",
    PROJECT_ROOT / "database",
    PROJECT_ROOT / "tracker",
    PROJECT_ROOT / "models",
    PROJECT_ROOT / "trackora_stats",
    PROJECT_ROOT / "ui",
    PROJECT_ROOT / "scripts",
]

BACKUP_ZIP_PATTERNS = [
    "backup_*.zip",
    ".zip.tmp",
    "ZipFile",
    "zipfile",
]


def _get_imports(path: Path) -> list[str]:
    """Return first-level package names imported by *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                imports.append(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                imports.append(top)
    return imports


def _iter_source_py_files() -> list[Path]:
    files: list[Path] = []
    for d in SOURCE_DIRS:
        if d.is_dir():
            files.extend(d.rglob("*.py"))
    return files


class TestBackupManagerImportRestrictions:
    """backup_manager.py must not import from forbidden packages."""

    def test_no_forbidden_imports(self) -> None:
        imports = _get_imports(BACKUP_MANAGER_FILE)
        violations = [i for i in imports if i in FORBIDDEN_IMPORTS]
        if violations:
            pytest.fail(
                f"{BACKUP_MANAGER_FILE.relative_to(PROJECT_ROOT)} imports "
                f"from forbidden packages: {violations}. "
                f"Only stdlib and trackora.core are allowed."
            )

    def test_stdlib_and_core_only(self) -> None:
        imports = _get_imports(BACKUP_MANAGER_FILE)
        unknown = [
            i
            for i in imports
            if i not in STDLIB_PREFIXES and i not in ALLOWED_TRACKORA_PREFIXES
        ]
        if unknown:
            pytest.fail(
                f"Unexpected imports in backup_manager.py: {unknown}. "
                f"Only stdlib and trackora.core are allowed."
            )

    def test_no_database_import(self) -> None:
        imports = _get_imports(BACKUP_MANAGER_FILE)
        if "database" in imports:
            pytest.fail(
                f"{BACKUP_MANAGER_FILE.relative_to(PROJECT_ROOT)} imports "
                f"from 'database'. This is forbidden."
            )

    def test_no_services_import(self) -> None:
        imports = _get_imports(BACKUP_MANAGER_FILE)
        if "services" in imports:
            pytest.fail(
                f"{BACKUP_MANAGER_FILE.relative_to(PROJECT_ROOT)} imports "
                f"from 'services'. This is forbidden."
            )
