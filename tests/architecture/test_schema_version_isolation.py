"""Architecture enforcement: schema.json access isolation.

Rule:
    Only trackora/core/schema_version_manager.py may read or write
    schema.json, and it must not depend on higher-level layers.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWED_FILES = [
    PROJECT_ROOT / "trackora" / "core" / "schema_version_manager.py",
    PROJECT_ROOT / "trackora" / "core" / "backup_manager.py",
]
TEST_FILE = Path(__file__).resolve()

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

DISALLOWED_IMPORTS = {
    "database",
    "services",
    "ui",
    "tracker",
    "trackora_stats",
}


def _iter_source_py_files() -> list[Path]:
    files: list[Path] = []
    for d in SOURCE_DIRS:
        if d.is_dir():
            files.extend(d.rglob("*.py"))
    return files


def _has_schema_json_string(path: Path) -> bool:
    """Check if a file contains the literal string 'schema.json'."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return '"schema.json"' in text or "'schema.json'" in text


def _get_imports(path: Path) -> list[str]:
    """Return a list of first-level package names imported by *path*."""
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


class TestSchemaJsonIsolation:
    """Only schema_version_manager.py may reference schema.json in source code."""

    @pytest.mark.parametrize("filepath", _iter_source_py_files())
    def test_schema_json_only_in_manager(self, filepath: Path) -> None:
        if filepath.resolve() in (f.resolve() for f in ALLOWED_FILES):
            pytest.skip(f"{filepath.name} is an allowed file")
        if filepath.resolve() == TEST_FILE.resolve():
            pytest.skip("this test file is exempt")
        if _has_schema_json_string(filepath):
            pytest.fail(
                f"{filepath.relative_to(PROJECT_ROOT)} contains 'schema.json' "
                f"reference. Only trackora/core/schema_version_manager.py "
                f"and trackora/core/backup_manager.py may reference schema.json."
            )


class TestManagerImportRestrictions:
    """SchemaVersionManager must not import from higher-level layers."""

    SVM_FILE = ALLOWED_FILES[0]  # schema_version_manager.py

    def test_no_disallowed_imports(self) -> None:
        imports = _get_imports(self.SVM_FILE)
        violations = [i for i in imports if i in DISALLOWED_IMPORTS]
        if violations:
            pytest.fail(
                f"{self.SVM_FILE.relative_to(PROJECT_ROOT)} imports from "
                f"disallowed packages: {violations}. "
                f"Allowed: stdlib, trackora.core.paths, trackora.core.schema_version."
            )

    def test_stdlib_and_core_only(self) -> None:
        imports = _get_imports(self.SVM_FILE)
        allowed_trackora = {"trackora"}
        stdlib_prefixes = {
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
        }
        unknown = [
            i
            for i in imports
            if i not in stdlib_prefixes and i not in allowed_trackora
        ]
        if unknown:
            pytest.fail(
                f"Unexpected imports in schema_version_manager.py: {unknown}. "
                f"Only stdlib and trackora.core are allowed."
            )
