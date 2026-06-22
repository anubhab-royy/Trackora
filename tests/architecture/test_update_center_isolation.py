"""Architecture isolation tests for Update Center.

Verifies layer isolation:
- services/update_center_service.py does not import UI or PyQt6
- ui/dialogs/update_dialog.py does not import database or tracker layers
- ui/widgets/update_banner.py does not import database or tracker layers
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _parse_imports(filepath: Path) -> list[str]:
    """Return all top-level import targets (module names) from a Python file."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def test_service_does_not_import_ui() -> None:
    """services/update_center_service.py must not import ui.* or PyQt6."""
    service_path = (
        Path(__file__).resolve().parent.parent.parent
        / "services"
        / "update_center_service.py"
    )
    imports = _parse_imports(service_path)

    forbidden = [imp for imp in imports if imp.startswith("ui") or imp.startswith("PyQt6") or imp.startswith("PyQt5")]
    assert not forbidden, f"Service imports forbidden modules: {forbidden}"


def test_service_only_stdlib_and_allowed() -> None:
    """Service should only import stdlib, database.repositories, and trackora."""
    service_path = (
        Path(__file__).resolve().parent.parent.parent
        / "services"
        / "update_center_service.py"
    )
    imports = _parse_imports(service_path)

    allowed_prefixes = (
        "",  # stdlib
        "database.repositories",
        "trackora",
        "services.",
    )

    for imp in imports:
        if imp.startswith("_"):
            continue
        if any(imp.startswith(p) for p in allowed_prefixes):
            continue
        # Check if it's a stdlib module
        if imp in sys.stdlib_module_names:
            continue
        raise AssertionError(f"Service imports disallowed module: {imp}")


def test_dialog_does_not_import_database_or_tracker() -> None:
    """ui/dialogs/update_dialog.py must not import database.* or tracker.*."""
    dialog_path = (
        Path(__file__).resolve().parent.parent.parent
        / "ui"
        / "dialogs"
        / "update_dialog.py"
    )
    imports = _parse_imports(dialog_path)

    forbidden = [imp for imp in imports if imp.startswith("database.") or imp.startswith("tracker.")]
    assert not forbidden, f"Dialog imports forbidden modules: {forbidden}"


def test_banner_does_not_import_database_or_tracker() -> None:
    """ui/widgets/update_banner.py must not import database.* or tracker.*."""
    banner_path = (
        Path(__file__).resolve().parent.parent.parent
        / "ui"
        / "widgets"
        / "update_banner.py"
    )
    imports = _parse_imports(banner_path)

    forbidden = [imp for imp in imports if imp.startswith("database.") or imp.startswith("tracker.")]
    assert not forbidden, f"Banner imports forbidden modules: {forbidden}"


def test_settings_view_does_not_import_database_or_tracker() -> None:
    """ui/settings/settings_view.py must not import database.* or tracker.*."""
    view_path = (
        Path(__file__).resolve().parent.parent.parent
        / "ui"
        / "settings"
        / "settings_view.py"
    )
    imports = _parse_imports(view_path)

    forbidden = [imp for imp in imports if imp.startswith("database.") or imp.startswith("tracker.")]
    assert not forbidden, f"SettingsView imports forbidden modules: {forbidden}"


def test_update_center_modules_importable() -> None:
    """All Update Center modules can be imported without errors."""
    from services.update_center_service import (
        GitHubRelease,
        UpdateCenterService,
        UpdateCheckError,
        UpdateCheckResult,
    )
    assert GitHubRelease is not None
    assert UpdateCenterService is not None
    assert UpdateCheckError is not None
    assert UpdateCheckResult is not None
