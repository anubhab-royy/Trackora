"""
tests/test_silent_startup.py

T-201: Silent Startup

Covers:
  - _get_startup_command() appends --silent
  - Windows registry write uses command with --silent
  - Linux .desktop Exec= uses command with --silent
  - _parse_silent_flag() detects --silent in sys.argv
  - _parse_silent_flag() returns False when --silent absent
  - Architecture: StartupService has no UI / no SQL
  - Architecture: __main__._parse_silent_flag is pure (no side-effects)
"""

from __future__ import annotations

import sys
import platform
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_startup_module():
    """Return a fresh import of services.startup_service.

    Module-level constants (_DESKTOP_FILE, _REG_VALUE) are computed at import
    time, so we import once and patch the internal helpers instead.
    """
    import services.startup_service as m
    return m


# ============================================================================
# TestGetStartupCommand
# ============================================================================

class TestGetStartupCommand:
    """_get_startup_command() must always end with ' --silent'."""

    def test_ends_with_silent_flag(self) -> None:
        from services.startup_service import _get_startup_command
        cmd = _get_startup_command()
        assert cmd.endswith(" --silent"), (
            f"Expected command to end with ' --silent', got: {cmd!r}"
        )

    def test_contains_app_path(self) -> None:
        from services.startup_service import _get_app_path, _get_startup_command
        cmd = _get_startup_command()
        app_path = _get_app_path()
        assert app_path in cmd

    def test_format_is_path_space_flag(self) -> None:
        """Command must be '<path> --silent' with exactly one space."""
        from services.startup_service import _get_startup_command
        cmd = _get_startup_command()
        parts = cmd.rsplit(" ", 1)
        assert len(parts) == 2
        assert parts[1] == "--silent"

    def test_frozen_build_uses_executable(self) -> None:
        """In a frozen (PyInstaller) build the registered path is sys.executable.

        We verify the command ends with '--silent' and contains the executable
        filename.  The exact path representation varies by platform (Path.resolve
        normalises separators), so we match on the final path component only.
        """
        fake_exe = str(Path(sys.executable).parent / "FakeTrackora")
        with patch.object(sys, "executable", fake_exe), \
             patch.object(sys, "frozen", True, create=True):
            from services.startup_service import _get_startup_command
            cmd = _get_startup_command()
        # The command must include the executable's stem and end with --silent
        assert "FakeTrackora" in cmd
        assert cmd.endswith("--silent")

    def test_development_build_uses_interpreter(self) -> None:
        """Without sys.frozen the interpreter path is used."""
        # Remove frozen attribute if present
        was_frozen = hasattr(sys, "frozen")
        if was_frozen:
            orig = sys.frozen  # type: ignore[attr-defined]
            del sys.frozen  # type: ignore[attr-defined]
        try:
            from services.startup_service import _get_startup_command
            cmd = _get_startup_command()
            assert cmd.endswith("--silent")
        finally:
            if was_frozen:
                sys.frozen = orig  # type: ignore[attr-defined]

    def test_return_type_is_str(self) -> None:
        from services.startup_service import _get_startup_command
        assert isinstance(_get_startup_command(), str)


# ============================================================================
# TestWindowsRegisterSilent
# ============================================================================

class TestWindowsRegisterSilent:
    """Windows registry write must use _get_startup_command(), not _get_app_path()."""

    def test_registry_value_includes_silent_flag(self) -> None:
        """The value written to winreg must end with --silent."""
        captured: list[str] = []

        fake_winreg = MagicMock()

        def fake_set_value_ex(key, name, reserved, type_, data):
            captured.append(data)

        fake_winreg.SetValueEx.side_effect = fake_set_value_ex
        fake_winreg.OpenKey.return_value.__enter__ = lambda s: s
        fake_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        fake_winreg.HKEY_CURRENT_USER = 0x80000001
        fake_winreg.KEY_SET_VALUE = 0x0002
        fake_winreg.REG_SZ = 1

        with patch.dict("sys.modules", {"winreg": fake_winreg}):
            from services.startup_service import _windows_register
            result = _windows_register()

        assert result is True
        assert captured, "SetValueEx was never called"
        assert captured[0].endswith("--silent"), (
            f"Registry value does not end with --silent: {captured[0]!r}"
        )

    def test_register_success_returns_true(self) -> None:
        fake_winreg = MagicMock()
        fake_winreg.OpenKey.return_value.__enter__ = lambda s: s
        fake_winreg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        fake_winreg.HKEY_CURRENT_USER = 0x80000001
        fake_winreg.KEY_SET_VALUE = 0x0002
        fake_winreg.REG_SZ = 1

        with patch.dict("sys.modules", {"winreg": fake_winreg}):
            from services.startup_service import _windows_register
            assert _windows_register() is True

    def test_register_failure_returns_false(self) -> None:
        fake_winreg = MagicMock()
        fake_winreg.OpenKey.side_effect = OSError("access denied")
        fake_winreg.HKEY_CURRENT_USER = 0x80000001
        fake_winreg.KEY_SET_VALUE = 0x0002

        with patch.dict("sys.modules", {"winreg": fake_winreg}):
            from services.startup_service import _windows_register
            assert _windows_register() is False


# ============================================================================
# TestLinuxRegisterSilent
# ============================================================================

class TestLinuxRegisterSilent:
    """Linux .desktop Exec= must use _get_startup_command()."""

    def test_desktop_exec_includes_silent_flag(self, tmp_path: Path) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"

        with patch("services.startup_service._AUTOSTART_DIR", autostart_dir), \
             patch("services.startup_service._DESKTOP_FILE", desktop_file):
            from services.startup_service import _linux_register
            result = _linux_register()

        assert result is True
        assert desktop_file.is_file()
        content = desktop_file.read_text(encoding="utf-8")
        exec_lines = [ln for ln in content.splitlines() if ln.startswith("Exec=")]
        assert exec_lines, ".desktop file has no Exec= line"
        assert "--silent" in exec_lines[0], (
            f"Exec= line does not contain --silent: {exec_lines[0]!r}"
        )

    def test_desktop_file_still_contains_trackora(self, tmp_path: Path) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"

        with patch("services.startup_service._AUTOSTART_DIR", autostart_dir), \
             patch("services.startup_service._DESKTOP_FILE", desktop_file):
            from services.startup_service import _linux_register
            _linux_register()

        content = desktop_file.read_text(encoding="utf-8")
        assert "Trackora" in content

    def test_desktop_file_created_in_correct_dir(self, tmp_path: Path) -> None:
        autostart_dir = tmp_path / ".config" / "autostart"
        desktop_file = autostart_dir / "Trackora.desktop"

        with patch("services.startup_service._AUTOSTART_DIR", autostart_dir), \
             patch("services.startup_service._DESKTOP_FILE", desktop_file):
            from services.startup_service import _linux_register
            _linux_register()

        assert desktop_file.parent == autostart_dir
        assert desktop_file.is_file()


# ============================================================================
# TestParseSilentFlag
# ============================================================================

class TestParseSilentFlag:
    """_parse_silent_flag() reads sys.argv without side-effects."""

    def test_returns_true_when_silent_present(self) -> None:
        with patch.object(sys, "argv", ["trackora", "--silent"]):
            from trackora.__main__ import _parse_silent_flag
            assert _parse_silent_flag() is True

    def test_returns_false_when_silent_absent(self) -> None:
        with patch.object(sys, "argv", ["trackora"]):
            from trackora.__main__ import _parse_silent_flag
            assert _parse_silent_flag() is False

    def test_returns_false_for_empty_argv(self) -> None:
        with patch.object(sys, "argv", []):
            from trackora.__main__ import _parse_silent_flag
            assert _parse_silent_flag() is False

    def test_other_flags_do_not_trigger_silent(self) -> None:
        with patch.object(sys, "argv", ["trackora", "--verbose", "--debug"]):
            from trackora.__main__ import _parse_silent_flag
            assert _parse_silent_flag() is False

    def test_silent_among_other_flags(self) -> None:
        with patch.object(sys, "argv", ["trackora", "--verbose", "--silent", "--debug"]):
            from trackora.__main__ import _parse_silent_flag
            assert _parse_silent_flag() is True

    def test_partial_silent_word_does_not_match(self) -> None:
        with patch.object(sys, "argv", ["trackora", "--silently"]):
            from trackora.__main__ import _parse_silent_flag
            assert _parse_silent_flag() is False

    def test_return_type_is_bool(self) -> None:
        with patch.object(sys, "argv", ["trackora", "--silent"]):
            from trackora.__main__ import _parse_silent_flag
            result = _parse_silent_flag()
            assert isinstance(result, bool)


# ============================================================================
# TestSilentFlagConstant
# ============================================================================

class TestSilentFlagConstant:
    """The module-level constant _SILENT_FLAG must be exactly '--silent'."""

    def test_silent_flag_value(self) -> None:
        from trackora.__main__ import _SILENT_FLAG
        assert _SILENT_FLAG == "--silent"

    def test_silent_flag_type(self) -> None:
        from trackora.__main__ import _SILENT_FLAG
        assert isinstance(_SILENT_FLAG, str)


# ============================================================================
# TestArchitectureConstraints
# ============================================================================

class TestArchitectureConstraints:
    """Verify T-201 changes do not introduce layer violations."""

    def test_startup_service_has_no_ui_import(self) -> None:
        """StartupService must not import anything from the ui package."""
        import ast
        import importlib.util

        spec = importlib.util.find_spec("services.startup_service")
        assert spec is not None
        assert spec.origin is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("ui"), (
                        f"StartupService imports from ui: {node.module}"
                    )

    def test_startup_service_has_no_sql_import(self) -> None:
        """StartupService must not import database repositories directly."""
        import ast
        import importlib.util

        spec = importlib.util.find_spec("services.startup_service")
        assert spec is not None
        assert spec.origin is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("database.repositories"), (
                    f"StartupService imports repository: {node.module}"
                )

    def test_get_startup_command_is_pure_function(self) -> None:
        """_get_startup_command must not raise and must return a non-empty string."""
        from services.startup_service import _get_startup_command
        result = _get_startup_command()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_parse_silent_flag_is_pure_function(self) -> None:
        """_parse_silent_flag must not raise and must return a bool."""
        with patch.object(sys, "argv", []):
            from trackora.__main__ import _parse_silent_flag
            result = _parse_silent_flag()
        assert isinstance(result, bool)

    def test_startup_command_distinct_from_app_path(self) -> None:
        """The startup command must differ from the raw app path (contains --silent)."""
        from services.startup_service import _get_app_path, _get_startup_command
        assert _get_startup_command() != _get_app_path()
        assert "--silent" in _get_startup_command()
        assert "--silent" not in _get_app_path()
