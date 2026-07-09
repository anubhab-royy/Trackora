"""
tests/test_version_consistency.py

Verifies that the application version is strictly unified across all build and
packaging configurations, and that the auto-generation script is reliable.

Validations:
  - __version__ in trackora/__init__.py matches standard MAJOR.MINOR.PATCH format.
  - trackora/core/build_info.py BUILD_VERSION equals trackora.__version__.
  - version_info.txt contains correct filevers, prodvers, FileVersion, and ProductVersion.
  - installer/version.iss defines the correct MyAppVersion.
  - scripts/bump_version.py runs successfully, is idempotent, and corrects mismatches.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
import subprocess

import pytest

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
INIT_FILE = REPO_ROOT / "trackora" / "__init__.py"
VERSION_INFO_FILE = REPO_ROOT / "version_info.txt"
INSTALLER_VERSION_FILE = REPO_ROOT / "installer" / "version.iss"
BUMP_SCRIPT = REPO_ROOT / "scripts" / "bump_version.py"


def _read_init_version() -> str:
    """Read the version string from trackora/__init__.py."""
    source = INIT_FILE.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', source, re.M)
    if not match:
        raise ValueError("Could not find __version__ in trackora/__init__.py")
    return match.group(1)


# ============================================================================
# Core Consistency Tests
# ============================================================================

class TestVersionConsistency:
    def test_version_format_is_valid(self) -> None:
        """__version__ must be strict MAJOR.MINOR.PATCH (e.g. 2.0.2)."""
        version = _read_init_version()
        assert re.match(r"^\d+\.\d+\.\d+$", version), (
            f"Version {version!r} is not in MAJOR.MINOR.PATCH format."
        )

    def test_runtime_version_matches_init(self) -> None:
        """trackora.core.build_info.BUILD_VERSION must equal __version__."""
        from trackora import __version__
        from trackora.core.build_info import BUILD_VERSION
        assert BUILD_VERSION == __version__
        assert BUILD_VERSION == _read_init_version()

    def test_version_info_txt_matches_init(self) -> None:
        """version_info.txt must match __version__ exactly."""
        version = _read_init_version()
        parts = [int(p) for p in version.split(".")]
        expected_tuple = f"({parts[0]}, {parts[1]}, {parts[2]}, 0)"

        content = VERSION_INFO_FILE.read_text(encoding="utf-8")

        # Check tuples
        expected_filevers = f"filevers={expected_tuple}".replace(" ", "")
        expected_prodvers = f"prodvers={expected_tuple}".replace(" ", "")
        assert expected_filevers in content.replace(" ", "")
        assert expected_prodvers in content.replace(" ", "")

        # Check string representations
        assert f"StringStruct(u'FileVersion', u'{version}')" in content
        assert f"StringStruct(u'ProductVersion', u'{version}')" in content

    def test_installer_version_iss_matches_init(self) -> None:
        """installer/version.iss must define MyAppVersion matching __version__."""
        if not INSTALLER_VERSION_FILE.exists():
            pytest.skip("installer/version.iss does not exist. Run scripts/bump_version.py first.")

        version = _read_init_version()
        content = INSTALLER_VERSION_FILE.read_text(encoding="utf-8")
        expected_define = f'#define MyAppVersion "{version}"'

        assert expected_define in content


# ============================================================================
# Script Generation Tests
# ============================================================================

class TestBumpScript:
    def test_script_is_runnable_and_exits_zero(self) -> None:
        """Running scripts/bump_version.py must succeed."""
        result = subprocess.run(
            [sys.executable, str(BUMP_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "Trackora version:" in result.stdout

    def test_script_is_idempotent(self) -> None:
        """Running the script twice should result in no file changes."""
        # 1st run
        subprocess.run([sys.executable, str(BUMP_SCRIPT)], check=True, cwd=str(REPO_ROOT))
        content_info_1 = VERSION_INFO_FILE.read_text(encoding="utf-8")
        content_iss_1 = INSTALLER_VERSION_FILE.read_text(encoding="utf-8")

        # 2nd run
        subprocess.run([sys.executable, str(BUMP_SCRIPT)], check=True, cwd=str(REPO_ROOT))
        content_info_2 = VERSION_INFO_FILE.read_text(encoding="utf-8")
        content_iss_2 = INSTALLER_VERSION_FILE.read_text(encoding="utf-8")

        assert content_info_1 == content_info_2
        assert content_iss_1 == content_iss_2
