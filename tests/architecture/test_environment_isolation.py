"""Architecture enforcement: APP_ENV access isolation.

Rule 1:
    Only trackora/core/environment.py may read APP_ENV.
    No other file may contain:
        APP_ENV
        os.getenv("APP_ENV")
        os.environ.get("APP_ENV")
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXCLUDED_FILE = PROJECT_ROOT / "trackora" / "core" / "environment.py"

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


_APP_ENV_PATTERNS = [
    '"APP_ENV"',
    "'APP_ENV'",
]


def _file_contains_patterns(path: Path, patterns: list[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    for pat in patterns:
        if pat in text:
            return True
    return False


class TestRule1AppEnvIsolation:
    """Only environment.py may reference APP_ENV."""

    @pytest.mark.parametrize("filepath", _iter_py_files())
    def test_no_app_env_outside_environment_py(self, filepath: Path) -> None:
        if filepath.resolve() == EXCLUDED_FILE.resolve():
            pytest.skip("trackora/core/environment.py is the allowed file")
        if _file_contains_patterns(filepath, _APP_ENV_PATTERNS):
            pytest.fail(
                f"{filepath.relative_to(PROJECT_ROOT)} contains APP_ENV reference. "
                f"Only trackora/core/environment.py may read APP_ENV."
            )
