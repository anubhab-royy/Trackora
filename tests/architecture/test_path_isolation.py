"""Architecture enforcement: storage path construction isolation.

Rule 2:
    Only trackora/core/paths.py may contain direct APPDATA/appdata
    resolution logic.

Rule 3:
    Only trackora/core/paths.py may hardcode "Trackora" or "Trackora-Dev"
    for filesystem path construction.
    (Imports, docstrings, comments, logging messages, and UI labels are excluded.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXCLUDED_FILE = PROJECT_ROOT / "trackora" / "core" / "paths.py"

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
TEST_DIR = PROJECT_ROOT / "tests"
if TEST_DIR.is_dir():
    for sub in TEST_DIR.iterdir():
        if sub.is_dir() and sub.name != "architecture":
            SOURCE_DIRS.append(sub)
    for f in TEST_DIR.iterdir():
        if f.is_file() and f.suffix == ".py":
            SOURCE_DIRS.append(f)


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for d in SOURCE_DIRS:
        if d.is_dir():
            files.extend(d.rglob("*.py"))
        elif d.is_file() and d.suffix == ".py":
            files.append(d)
    return files


# Patterns that indicate direct APPDATA resolution
_APPDATA_PATTERNS = [
    '"APPDATA"',
    "'APPDATA'",
]


def _file_contains_appdata_patterns(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    for pat in _APPDATA_PATTERNS:
        if pat in text:
            return True
    return False


class TestRule2AppdataIsolation:
    """Only paths.py may resolve APPDATA."""

    @pytest.mark.parametrize("filepath", _iter_py_files())
    def test_no_appdata_outside_paths_py(self, filepath: Path) -> None:
        if filepath.resolve() == EXCLUDED_FILE.resolve():
            pytest.skip("trackora/core/paths.py is the allowed file")
        if _file_contains_appdata_patterns(filepath):
            pytest.fail(
                f"{filepath.relative_to(PROJECT_ROOT)} contains APPDATA reference. "
                f"Only trackora/core/paths.py may resolve APPDATA."
            )
