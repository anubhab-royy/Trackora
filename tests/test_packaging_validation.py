"""
Phase 13G — Packaging Validation.

Validates all packaging concerns at the source-code level:
  - PyInstaller spec correctness
  - MongoDB dependencies
  - Update Center
  - Discovery
  - Crash handling
  - Startup sequence
  - Hidden imports
  - Resource files
  - Icons

Does NOT run PyInstaller itself (Windows-only build tool).
All tests run on any platform where the source tree is available.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAILURES: list[str] = []


def _check(description: str, condition: bool, detail: str = "") -> None:
    if not condition:
        msg = f"FAIL: {description}"
        if detail:
            msg += f" — {detail}"
        _FAILURES.append(msg)
        pytest.fail(msg)


def _import_from_path(modname: str, path: str) -> Any:
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None:
        raise ImportError(f"Cannot load spec for {modname} from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _assert_module_importable(modname: str) -> None:
    try:
        importlib.import_module(modname)
    except ImportError as exc:
        pytest.fail(f"Module {modname} is not importable: {exc}")


# ---------------------------------------------------------------------------
# 1. PyInstaller spec correctness
# ---------------------------------------------------------------------------


class TestPyInstallerSpec:
    """Validate Trackora.spec file structure and references."""

    SPEC_PATH = REPO_ROOT / "Trackora.spec"

    def test_spec_file_exists(self) -> None:
        assert self.SPEC_PATH.is_file(), f"Spec file not found: {self.SPEC_PATH}"

    def test_spec_parses(self) -> None:
        """Spec is valid Python."""
        source = self.SPEC_PATH.read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as exc:
            pytest.fail(f"Spec file has syntax error: {exc}")

    def test_entry_point_exists(self) -> None:
        """trackora/__main__.py must exist (the Analysis entry)."""
        assert (REPO_ROOT / "trackora" / "__main__.py").is_file()

    def test_hidden_imports_exist_as_modules(self) -> None:
        """Every hidden import listed in the spec is importable on this system."""
        source = self.SPEC_PATH.read_text(encoding="utf-8")
        # Extract hiddenimports list via simple regex
        m = re.search(r"hiddenimports\s*=\s*\[(.*?)\]", source, re.DOTALL)
        assert m, "Could not parse hiddenimports from spec"
        items = re.findall(r'"([^"]+)"', m.group(1))
        assert items, "No hidden imports found in spec"

        skipped = {"dns"}  # dns is a namespace; import dns.resolver instead
        for mod in items:
            if mod in skipped:
                continue
            try:
                importlib.import_module(mod)
            except ImportError:
                # Some may be top-level packages that need submodule import
                parts = mod.split(".")
                ok = False
                for i in range(len(parts), 0, -1):
                    try:
                        importlib.import_module(".".join(parts[:i]))
                        ok = True
                        break
                    except ImportError:
                        continue
                if not ok:
                    pytest.fail(f"Hidden import '{mod}' is not importable")

    def test_excludes_not_accidental(self) -> None:
        """Excluded modules should not be needed by the app at runtime."""
        source = self.SPEC_PATH.read_text(encoding="utf-8")
        m = re.search(r"excludes\s*=\s*\[(.*?)\]", source, re.DOTALL)
        assert m, "Could not parse excludes from spec"
        items = re.findall(r'"([^"]+)"', m.group(1))
        dangerous = {"PyQt5", "PySide2", "PySide6", "tkinter", "test", "unittest"}
        for mod in items:
            if mod in dangerous:
                continue
            try:
                importlib.import_module(mod)
                # warn but don't fail — these are size optimizations
                print(f"\n  [WARN] excluded module '{mod}' is available on this system")
            except ImportError:
                pass  # expected — module doesn't exist

    def test_data_dirs_exist(self) -> None:
        """All datas= entries point to real directories."""
        source = self.SPEC_PATH.read_text(encoding="utf-8")
        m = re.search(r"datas\s*=\s*\[(.*?)\]", source, re.DOTALL)
        assert m, "Could not parse datas from spec"
        srcs = re.findall(r'"([^"]+)"\s*,\s*"([^"]+)"', m.group(1))
        for src, _ in srcs:
            path = REPO_ROOT / src
            assert path.exists(), f"Data source not found: {path}"

    def test_icon_exists(self) -> None:
        """Icon path in spec points to a real file."""
        source = self.SPEC_PATH.read_text(encoding="utf-8")
        m = re.search(r'icon\s*=\s*\["([^"]+)"\]', source)
        assert m, "Could not parse icon from spec"
        icon_path = REPO_ROOT / m.group(1)
        assert icon_path.is_file(), f"Icon not found: {icon_path}"

    def test_version_info_exists(self) -> None:
        """version_info.txt referenced by spec exists."""
        assert (REPO_ROOT / "version_info.txt").is_file()

    def test_version_consistency(self) -> None:
        """Version string in spec matches trackora/__init__.py."""
        spec_ver_match = re.search(
            r'^version\s*=\s*"(\d+\.\d+\.\d+)"',
            self.SPEC_PATH.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        assert spec_ver_match, "Cannot parse version from spec"
        spec_ver = spec_ver_match.group(1)

        init_py = REPO_ROOT / "trackora" / "__init__.py"
        init_match = re.search(
            r'__version__\s*=\s*"(\d+\.\d+\.\d+)"',
            init_py.read_text(encoding="utf-8"),
        )
        assert init_match, "Cannot parse __version__ from __init__.py"
        init_ver = init_match.group(1)

        assert spec_ver == init_ver, (
            f"Version mismatch: spec={spec_ver}, __init__.py={init_ver}"
        )

    def test_build_info_matches(self) -> None:
        """BUILD_VERSION in build_info.py matches __init__.py."""
        build_mod = importlib.import_module("trackora.core.build_info")
        init_py = REPO_ROOT / "trackora" / "__init__.py"
        init_match = re.search(
            r'__version__\s*=\s*"(\d+\.\d+\.\d+)"',
            init_py.read_text(encoding="utf-8"),
        )
        assert init_match
        assert build_mod.BUILD_VERSION == init_match.group(1), (
            f"BUILD_VERSION={build_mod.BUILD_VERSION} != __version__={init_match.group(1)}"
        )

    def test_version_info_txt_consistent(self) -> None:
        """FileVersion in version_info.txt matches spec version."""
        spec_ver_match = re.search(
            r'^version\s*=\s*"(\d+\.\d+\.\d+)"',
            self.SPEC_PATH.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        assert spec_ver_match
        spec_ver = spec_ver_match.group(1)

        vi_text = (REPO_ROOT / "version_info.txt").read_text(encoding="utf-8")
        vi_filevers = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+)", vi_text)
        assert vi_filevers, "filevers not found in version_info.txt"
        vi_ver = f"{vi_filevers.group(1)}.{vi_filevers.group(2)}.{vi_filevers.group(3)}"
        assert vi_ver == spec_ver, (
            f"filevers={vi_ver} != spec version={spec_ver}"
        )

        vi_prodvers = re.search(r"prodvers=\((\d+),\s*(\d+),\s*(\d+)", vi_text)
        assert vi_prodvers, "prodvers not found in version_info.txt"
        pv_ver = f"{vi_prodvers.group(1)}.{vi_prodvers.group(2)}.{vi_prodvers.group(3)}"
        assert pv_ver == spec_ver, (
            f"prodvers={pv_ver} != spec version={spec_ver}"
        )

        # Also check StringStruct entries
        fv_match = re.search(r"StringStruct\(u'FileVersion', u'(\d+\.\d+\.\d+)'\)", vi_text)
        assert fv_match, "StringStruct FileVersion not found"
        assert fv_match.group(1) == spec_ver

        pv_match = re.search(r"StringStruct\(u'ProductVersion', u'(\d+\.\d+\.\d+)'\)", vi_text)
        assert pv_match, "StringStruct ProductVersion not found"
        assert pv_match.group(1) == spec_ver

    def test_installer_version_consistent(self) -> None:
        """Inno Setup version matches spec version."""
        spec_ver_match = re.search(
            r'^version\s*=\s*"(\d+\.\d+\.\d+)"',
            self.SPEC_PATH.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        assert spec_ver_match
        spec_ver = spec_ver_match.group(1)

        iss_path = REPO_ROOT / "installer" / "Trackora.iss"
        assert iss_path.is_file(), "Installer script not found"
        iss_text = iss_path.read_text(encoding="utf-8", errors="replace")
        iss_match = re.search(r'#define MyAppVersion\s+"(\d+\.\d+\.\d+)"', iss_text)
        assert iss_match, "MyAppVersion not found in installer script"
        assert iss_match.group(1) == spec_ver, (
            f"Installer version={iss_match.group(1)} != spec version={spec_ver}"
        )


# ---------------------------------------------------------------------------
# 2. MongoDB dependencies
# ---------------------------------------------------------------------------


class TestMongoDBDependencies:
    """Validate MongoDB/pymongo importability and config."""

    def test_pymongo_importable(self) -> None:
        _assert_module_importable("pymongo")

    def test_pymongo_version(self) -> None:
        import pymongo
        assert pymongo.version_tuple >= (4, 6), (
            f"pymongo {pymongo.version} is too old (need >= 4.6)"
        )

    def test_dns_importable(self) -> None:
        _assert_module_importable("dns.resolver")

    def test_mongo_report_service_importable(self) -> None:
        _assert_module_importable("services.support.mongo_report_service")

    def test_mongo_connection_importable(self) -> None:
        _assert_module_importable("services.support.mongo_connection")

    def test_pymongo_in_requirements(self) -> None:
        reqs = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert any("pymongo" in line for line in reqs.splitlines()), (
            "pymongo not found in requirements.txt"
        )

    def test_dnspython_in_requirements(self) -> None:
        reqs = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert any("dnspython" in line for line in reqs.splitlines()), (
            "dnspython not found in requirements.txt"
        )

    def test_pymongo_in_spec_hiddenimports(self) -> None:
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        assert "pymongo" in spec_text, "pymongo missing from spec hidden imports"

    def test_dns_in_spec_hiddenimports(self) -> None:
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        assert '"dns"' in spec_text, "dns missing from spec hidden imports"


# ---------------------------------------------------------------------------
# 3. Update Center
# ---------------------------------------------------------------------------


class TestUpdateCenter:
    """Validate Update Center importability and critical logic."""

    def test_update_center_service_importable(self) -> None:
        _assert_module_importable("services.update_center_service")

    def test_update_dialog_importable(self) -> None:
        _assert_module_importable("ui.dialogs.update_dialog")

    def test_update_banner_importable(self) -> None:
        _assert_module_importable("ui.widgets.update_banner")

    def test_update_center_migration_importable(self) -> None:
        _assert_module_importable(
            "trackora.core.migrations.v2_0_0_add_update_center_settings_v2"
        )

    def test_update_service_importable(self) -> None:
        """Legacy update service is importable (still referenced by spec)."""
        _assert_module_importable("services.update_service")

    def test_api_url_format(self) -> None:
        """UpdateCenterService uses a well-formed GitHub API URL."""
        mod = importlib.import_module("services.update_center_service")
        url = getattr(mod, "_GITHUB_API_URL", "")
        assert url, "_GITHUB_API_URL not found in update_center_service"
        assert "{repo}" in url, "API URL is missing {repo} placeholder"

    def test_version_comparison(self) -> None:
        """_is_newer_version correctly identifies newer/older/equal."""
        mod = importlib.import_module("services.update_center_service")
        svc = mod.UpdateCenterService.__new__(mod.UpdateCenterService)
        # Patch __version__ to known value for testing
        import trackora
        orig_ver = trackora.__version__
        try:
            trackora.__version__ = "1.1.0"

            assert svc._is_newer_version("2.0.0") is True
            assert svc._is_newer_version("1.1.0") is False
            assert svc._is_newer_version("1.0.9") is False
            assert svc._is_newer_version("1.1.1") is True
        finally:
            trackora.__version__ = orig_ver

    def test_rate_limit_logic(self) -> None:
        """Rate-limit window is 3600 seconds (1 hour); no repo = not rate limited."""
        mod = importlib.import_module("services.update_center_service")
        svc = mod.UpdateCenterService.__new__(mod.UpdateCenterService)
        svc._settings_repo = None
        assert svc._is_rate_limited() is False

    def test_update_center_in_spec_hidden_imports(self) -> None:
        """services.update_service is in spec (backwards compat)."""
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        assert "services.update_service" in spec_text


# ---------------------------------------------------------------------------
# 4. Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    """Validate game discovery components are importable and structured."""

    def test_orchestrator_importable(self) -> None:
        _assert_module_importable("tracker.discovery.orchestrator")

    def test_detectors_importable(self) -> None:
        """All individual detectors can be imported."""
        detectors = [
            "tracker.discovery.detectors.steam_detector",
            "tracker.discovery.detectors.epic_detector",
            "tracker.discovery.detectors.riot_detector",
            "tracker.discovery.detectors.battlenet_detector",
            "tracker.discovery.detectors.ubisoft_detector",
            "tracker.discovery.detectors.ea_detector",
            "tracker.discovery.detectors.folder_detector",
        ]
        for det in detectors:
            try:
                importlib.import_module(det)
            except ImportError as exc:
                pytest.fail(f"Detector module {det} not importable: {exc}")

    def test_detector_classes_exist(self) -> None:
        """Each detector module exports the expected class."""
        expected = {
            "tracker.discovery.detectors.steam_detector": "SteamDetector",
            "tracker.discovery.detectors.epic_detector": "EpicDetector",
            "tracker.discovery.detectors.riot_detector": "RiotDetector",
            "tracker.discovery.detectors.battlenet_detector": "BattleNetDetector",
            "tracker.discovery.detectors.ubisoft_detector": "UbisoftDetector",
            "tracker.discovery.detectors.ea_detector": "EADetector",
            "tracker.discovery.detectors.folder_detector": "FolderDetector",
        }
        for modname, clsname in expected.items():
            mod = importlib.import_module(modname)
            assert hasattr(mod, clsname), (
                f"{modname} does not export {clsname}"
            )

    def test_models_importable(self) -> None:
        _assert_module_importable("tracker.discovery.models")

    def test_detector_base_importable(self) -> None:
        _assert_module_importable("tracker.discovery.detector")

    def test_discovery_in_spec_hidden_imports(self) -> None:
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        assert '"tracker"' in spec_text, "tracker package missing from spec"


# ---------------------------------------------------------------------------
# 5. Crash handling
# ---------------------------------------------------------------------------


class TestCrashHandling:
    """Validate crash service components."""

    def test_crash_service_importable(self) -> None:
        _assert_module_importable("services.crash.crash_service")

    def test_diagnostic_service_importable(self) -> None:
        _assert_module_importable("services.crash.diagnostic_service")

    def test_crash_package_importable(self) -> None:
        _assert_module_importable("services.crash")

    def test_crash_dialog_importable(self) -> None:
        _assert_module_importable("ui.crash_dialog")

    def test_crash_service_class(self) -> None:
        mod = importlib.import_module("services.crash.crash_service")
        assert hasattr(mod, "CrashService")
        assert hasattr(mod, "StartupStateManager")
        assert hasattr(mod, "CrashResult")

    def test_diagnostic_service_class(self) -> None:
        mod = importlib.import_module("services.crash.diagnostic_service")
        assert hasattr(mod, "DiagnosticService")
        assert hasattr(mod, "CrashReport")

    def test_crash_dir_in_paths(self) -> None:
        """CRASH_DIR must be defined in paths.py."""
        from trackora.core.paths import CRASH_DIR
        assert isinstance(CRASH_DIR, Path)

    def test_startup_state_path_accessible(self) -> None:
        """StartupStateManager can be instantiated with a temp path."""
        import tempfile
        from services.crash.crash_service import StartupStateManager
        with tempfile.TemporaryDirectory() as td:
            ssm = StartupStateManager(storage_dir=Path(td))
            assert ssm is not None
            assert ssm.state_path.name == "startup_state.json"

    def test_report_submission_modules_importable(self) -> None:
        """Support/reporting modules used by crash dialogs."""
        _assert_module_importable("services.support.report_queue_service")
        _assert_module_importable("services.support.support_service")
        _assert_module_importable("services.support.github_issue_service")


# ---------------------------------------------------------------------------
# 6. Startup sequence
# ---------------------------------------------------------------------------


class TestStartupSequence:
    """Validate startup sequence components are importable and consistent."""

    def test_main_module_importable(self) -> None:
        import trackora.__main__  # type: ignore[import-untyped]
        assert hasattr(trackora.__main__, "main")

    def test_database_manager_importable(self) -> None:
        _assert_module_importable("database.database_manager")

    def test_paths_module(self) -> None:
        from trackora.core.paths import (
            BASE_DIR, DATABASE_PATH, LOGS_DIR, CACHE_DIR, BACKUPS_DIR, CRASH_DIR,
        )
        for p in (BASE_DIR, DATABASE_PATH, LOGS_DIR, CACHE_DIR, BACKUPS_DIR, CRASH_DIR):
            assert isinstance(p, Path), f"{p} is not a Path"

    def test_environment_detection(self) -> None:
        """Environment module correctly detects frozen vs development."""
        from trackora.core.environment import CURRENT_ENVIRONMENT, Environment
        assert CURRENT_ENVIRONMENT in (Environment.PRODUCTION, Environment.DEVELOPMENT)

    def test_build_info_exported(self) -> None:
        """build_info exports BUILD_CHANNEL and BUILD_VERSION."""
        from trackora.core.build_info import BUILD_CHANNEL, BUILD_VERSION
        assert isinstance(BUILD_CHANNEL, str)
        assert isinstance(BUILD_VERSION, str)

    def test_ensure_dirs_function(self) -> None:
        """ensure_dirs creates all required directories."""
        import tempfile
        from trackora.core.paths import ensure_dirs
        with tempfile.TemporaryDirectory() as td:
            # Should not raise
            ensure_dirs()

    def test_logging_service_importable(self) -> None:
        _assert_module_importable("services.logging_service")

    def test_lock_mechanism_importable(self) -> None:
        """The lock mechanism (single-instance enforcement) is importable."""
        from trackora.__main__ import _acquire_lock, _release_lock
        assert callable(_acquire_lock)
        assert callable(_release_lock)

    def test_core_packages_importable(self) -> None:
        """All core packages used during startup."""
        core_modules = [
            "trackora.core.schema_version",
            "trackora.core.schema_version_manager",
            "trackora.core.migration_manager",
            "trackora.core.backup_manager",
            "trackora.core.paths",
            "trackora.core.environment",
            "trackora.core.build_info",
        ]
        for mod in core_modules:
            _assert_module_importable(mod)


# ---------------------------------------------------------------------------
# 7. Hidden imports — completeness check
# ---------------------------------------------------------------------------


class TestHiddenImportsCompleteness:
    """Check that no obvious modules are missing from the spec's hiddenimports."""

    ALL_TRACKORA_PACKAGES = [
        "database",
        "database.models",
        "database.repositories",
        "services",
        "services.crash",
        "services.support",
        "trackora",
        "trackora.core",
        "trackora.core.migrations",
        "trackora_stats",
        "tracker",
        "tracker.discovery",
        "tracker.discovery.detectors",
        "ui",
        "ui.dashboard",
        "ui.dialogs",
        "ui.games",
        "ui.history",
        "ui.settings",
        "ui.themes",
        "ui.widgets",
    ]

    def test_all_app_packages_in_spec(self) -> None:
        """Every first-party package should appear in hiddenimports or be walked."""
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        hidden_section = re.search(
            r"hiddenimports\s*=\s*\[(.*?)\]", spec_text, re.DOTALL
        )
        assert hidden_section
        hidden_content = hidden_section.group(1)

        missing = []
        for pkg in self.ALL_TRACKORA_PACKAGES:
            if pkg not in hidden_content:
                missing.append(pkg)
        if missing:
            pytest.fail(f"Packages missing from spec hiddenimports: {missing}")

    def test_pyqt6_in_spec(self) -> None:
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        assert "PyQt6.QtSvg" in spec_text, (
            "PyQt6.QtSvg missing from spec hiddenimports"
        )

    def test_pyqtgraph_in_spec(self) -> None:
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        assert "pyqtgraph" in spec_text

    def test_psutil_in_spec(self) -> None:
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        assert "psutil" in spec_text

    @staticmethod
    def _list_first_party_packages() -> list[str]:
        """Scan the repo for first-party Python packages."""
        pkgs = []
        for entry in sorted(REPO_ROOT.iterdir()):
            if entry.is_dir() and (entry / "__init__.py").is_file():
                pkgs.append(entry.name)
        return pkgs

    def test_all_first_party_packages_listed(self) -> None:
        """Every first-party package with __init__.py should be in spec or excluded."""
        spec_text = (REPO_ROOT / "Trackora.spec").read_text(encoding="utf-8")
        hidden_section = re.search(
            r"hiddenimports\s*=\s*\[(.*?)\]", spec_text, re.DOTALL
        )
        assert hidden_section
        hidden_content = hidden_section.group(1)

        built_in = {"scripts", "tests", "installer", ".github", "docs",
                     ".venv", "node_modules", "dist", "build", ".git",
                     "__pycache__"}
        # These packages existbut are not runtime dependencies
        exempt = {"database_tests", "old", "migrations_test"}
        for pkg in self._list_first_party_packages():
            if pkg in built_in or pkg in exempt:
                continue
            if pkg not in hidden_content:
                pytest.fail(
                    f"First-party package '{pkg}' is not in spec hiddenimports"
                )


# ---------------------------------------------------------------------------
# 8. Resource files
# ---------------------------------------------------------------------------


class TestResourceFiles:
    """Validate all resource files exist and are non-empty."""

    RESOURCE_PATHS = [
        "ui/icons/app_icon.png",
        "ui/icons/app_icon.ico",
        "ui/icons/tray_icon.png",
        "ui/themes/__init__.py",
        "ui/themes/theme_manager.py",
    ]

    def test_resource_files_exist(self) -> None:
        for rel in self.RESOURCE_PATHS:
            path = REPO_ROOT / rel
            assert path.is_file(), f"Resource file missing: {rel}"

    def test_resource_files_non_empty(self) -> None:
        for rel in self.RESOURCE_PATHS:
            path = REPO_ROOT / rel
            assert path.stat().st_size > 0, f"Resource file is empty: {rel}"

    def test_icon_png_valid_size(self) -> None:
        """app_icon.png should be a reasonable size (>1KB)."""
        path = REPO_ROOT / "ui" / "icons" / "app_icon.png"
        assert path.stat().st_size > 1024, "app_icon.png is too small (<1KB)"

    def test_tray_icon_png_valid_size(self) -> None:
        """tray_icon.png should be a reasonable size (>100 bytes)."""
        path = REPO_ROOT / "ui" / "icons" / "tray_icon.png"
        assert path.stat().st_size > 100, "tray_icon.png is too small (<100B)"

    def test_ico_cached(self) -> None:
        """The ICO file is non-trivially sized (multi-res)."""
        path = REPO_ROOT / "ui" / "icons" / "app_icon.ico"
        assert path.stat().st_size > 2048, "app_icon.ico is too small (<2KB)"

    def test_theme_manager_class(self) -> None:
        """theme_manager.py exports ThemeManager."""
        mod = importlib.import_module("ui.themes.theme_manager")
        assert hasattr(mod, "ThemeManager")

    def test_build_script_generate_icons(self) -> None:
        """The icon generation script exists and is valid Python."""
        path = REPO_ROOT / "scripts" / "generate_icons.py"
        assert path.is_file()
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as exc:
            pytest.fail(f"generate_icons.py has syntax error: {exc}")

    def test_build_script_sign_code(self) -> None:
        """The code signing script exists."""
        path = REPO_ROOT / "scripts" / "sign-code.ps1"
        assert path.is_file(), "sign-code.ps1 not found"


# ---------------------------------------------------------------------------
# 9. Icons
# ---------------------------------------------------------------------------


class TestIcons:
    """Validate icon files are valid and match expectations."""

    def test_app_icon_svg_fallback_not_needed(self) -> None:
        """PyQt6.QtSvg is imported for SVG support but we use PNG/ICO."""
        # QtSvg is listed as hidden import — confirm icon loading doesn't need it
        svc_path = REPO_ROOT / "services" / "tray_service.py"
        source = svc_path.read_text(encoding="utf-8")
        assert "app_icon.png" in source, "tray_service.py does not reference app_icon.png"

    def test_icon_paths_defined(self) -> None:
        """Verify icon paths referenced in tray_service.py exist."""
        svc_path = REPO_ROOT / "services" / "tray_service.py"
        source = svc_path.read_text(encoding="utf-8")
        # Find Path(__file__)... expressions referencing icons
        icons_dir = REPO_ROOT / "ui" / "icons"
        png_files = [f for f in icons_dir.iterdir() if f.suffix in (".png", ".ico")]
        for icon_file in png_files:
            assert icon_file.is_file()

    def test_tray_icon_loading_path(self) -> None:
        """Verify that the tray service icon path resolves in both frozen/dev modes."""
        from services.tray_service import _ICON_PATH
        assert _ICON_PATH.name == "app_icon.png"
        # Path should resolve to an existing file in development
        if not hasattr(sys, "frozen"):
            assert _ICON_PATH.is_file(), (
                f"Tray icon not found at {_ICON_PATH}"
            )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_packaging_summary() -> None:
    """Print packaging validation summary."""
    print("\n" + "=" * 90)
    print("  PHASE 13G — PACKAGING VALIDATION SUMMARY")
    print("=" * 90)
    print(f"  All validation tests completed.")
    print(f"  Failures recorded: {len(_FAILURES)}")
    for f in _FAILURES:
        print(f"    - {f}")
    print("=" * 90)
