"""
T-242: Installer Testing — Automated Validation Suite

Validates the complete Trackora v2.0.1 Windows installer at the source level.

Tests cover:
    - Inno Setup script structure and correctness
    - Version consistency across all artifacts
    - File layout in spec and installer
    - Registry configuration
    - Upgrade / data-preservation logic
    - Uninstall behavior (data preservation)
    - Shortcut configuration
    - Process termination hooks
    - AppID consistency
    - Startup / launch configuration
    - Installer UX configuration (wizard style, icons)
    - Binary artifact presence (dist/ and installer/Output/)
    - Executable metadata consistency
    - Code section correctness (Code block in .iss)

Does NOT:
    - Execute the installer (requires physical Windows environment + admin)
    - Execute PyInstaller (already done)
    - Modify any installer scripts
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ISS_PATH = REPO_ROOT / "installer" / "Trackora.iss"
VERSION_ISS_PATH = REPO_ROOT / "installer" / "version.iss"
SPEC_PATH = REPO_ROOT / "Trackora.spec"
VERSION_INFO_PATH = REPO_ROOT / "version_info.txt"
INIT_PATH = REPO_ROOT / "trackora" / "__init__.py"
DIST_EXE = REPO_ROOT / "dist" / "Trackora.exe"
INSTALLER_EXE = REPO_ROOT / "installer" / "Output" / "Trackora-Setup-2.0.1.exe"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iss() -> str:
    """Return the full text of Trackora.iss."""
    return ISS_PATH.read_text(encoding="utf-8", errors="replace")


def _app_version() -> str:
    """Read __version__ from the single source of truth."""
    src = INIT_PATH.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', src)
    assert m, "Cannot parse __version__ from trackora/__init__.py"
    return m.group(1)


# ---------------------------------------------------------------------------
# 1. Installer script existence and parseability
# ---------------------------------------------------------------------------


class TestInstallerScriptExists:
    """Verify installer artifacts exist and are readable."""

    def test_trackora_iss_exists(self):
        assert ISS_PATH.is_file(), f"Trackora.iss not found: {ISS_PATH}"

    def test_version_iss_exists(self):
        assert VERSION_ISS_PATH.is_file(), f"version.iss not found: {VERSION_ISS_PATH}"

    def test_dist_exe_exists(self):
        """dist/Trackora.exe must exist (PyInstaller output)."""
        assert DIST_EXE.is_file(), (
            f"Packaged executable not found: {DIST_EXE}. "
            "Run: pyinstaller Trackora.spec"
        )

    def test_installer_exe_exists(self):
        """installer/Output/Trackora-Setup-{version}.exe must exist."""
        version = _app_version()
        installer = REPO_ROOT / "installer" / "Output" / f"Trackora-Setup-{version}.exe"
        assert installer.is_file(), (
            f"Installer executable not found: {installer}. "
            "Run: iscc installer/Trackora.iss"
        )

    def test_dist_exe_nonzero_size(self):
        """Executable must be a non-trivial size (>10 MB)."""
        assert DIST_EXE.stat().st_size > 10 * 1024 * 1024, (
            "dist/Trackora.exe appears too small — may be corrupt"
        )

    def test_installer_exe_nonzero_size(self):
        """Installer must be a non-trivial size (>10 MB)."""
        version = _app_version()
        installer = REPO_ROOT / "installer" / "Output" / f"Trackora-Setup-{version}.exe"
        assert installer.stat().st_size > 10 * 1024 * 1024, (
            "Installer executable appears too small — may be corrupt"
        )


# ---------------------------------------------------------------------------
# 2. Version consistency — all artifacts must agree
# ---------------------------------------------------------------------------


class TestVersionConsistency:
    """All version references must agree with trackora/__init__.py."""

    def test_version_iss_matches_init(self):
        version = _app_version()
        text = VERSION_ISS_PATH.read_text(encoding="utf-8")
        m = re.search(r'#define MyAppVersion\s+"(\d+\.\d+\.\d+)"', text)
        assert m, "MyAppVersion not found in version.iss"
        assert m.group(1) == version, (
            f"version.iss says '{m.group(1)}' but __init__.py says '{version}'"
        )

    def test_installer_output_filename_matches_version(self):
        version = _app_version()
        installer = REPO_ROOT / "installer" / "Output" / f"Trackora-Setup-{version}.exe"
        assert installer.is_file(), (
            f"Installer output filename does not match version {version}: "
            f"expected {installer.name}"
        )

    def test_version_info_txt_filevers_matches(self):
        version = _app_version()
        text = VERSION_INFO_PATH.read_text(encoding="utf-8")
        major, minor, patch = version.split(".")
        # filevers must be (major, minor, patch, 0)
        m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+)", text)
        assert m, "filevers not found in version_info.txt"
        assert (m.group(1), m.group(2), m.group(3)) == (major, minor, patch), (
            f"version_info.txt filevers {m.group(1)}.{m.group(2)}.{m.group(3)} "
            f"!= {version}"
        )

    def test_version_info_txt_prodvers_matches(self):
        version = _app_version()
        text = VERSION_INFO_PATH.read_text(encoding="utf-8")
        major, minor, patch = version.split(".")
        m = re.search(r"prodvers=\((\d+),\s*(\d+),\s*(\d+)", text)
        assert m, "prodvers not found in version_info.txt"
        assert (m.group(1), m.group(2), m.group(3)) == (major, minor, patch)

    def test_version_info_txt_string_fileversion_matches(self):
        version = _app_version()
        text = VERSION_INFO_PATH.read_text(encoding="utf-8")
        m = re.search(r"StringStruct\(u'FileVersion', u'(\d+\.\d+\.\d+)'\)", text)
        assert m, "FileVersion StringStruct not found"
        assert m.group(1) == version

    def test_version_info_txt_string_productversion_matches(self):
        version = _app_version()
        text = VERSION_INFO_PATH.read_text(encoding="utf-8")
        m = re.search(r"StringStruct\(u'ProductVersion', u'(\d+\.\d+\.\d+)'\)", text)
        assert m, "ProductVersion StringStruct not found"
        assert m.group(1) == version

    def test_installer_uninstall_display_name_contains_version(self):
        """UninstallDisplayName must include the version number."""
        version = _app_version()
        iss = _iss()
        m = re.search(r"UninstallDisplayName\s*=\s*(.+)", iss)
        assert m, "UninstallDisplayName not found in Trackora.iss"
        display = m.group(1).strip()
        assert "{#MyAppVersion}" in display or version in display, (
            f"UninstallDisplayName '{display}' does not reference version"
        )


# ---------------------------------------------------------------------------
# 3. Installer structure — required sections
# ---------------------------------------------------------------------------


class TestInstallerStructure:
    """Inno Setup script must contain all required sections."""

    def test_setup_section_present(self):
        assert "[Setup]" in _iss()

    def test_languages_section_present(self):
        assert "[Languages]" in _iss()

    def test_files_section_present(self):
        assert "[Files]" in _iss()

    def test_icons_section_present(self):
        assert "[Icons]" in _iss()

    def test_registry_section_present(self):
        assert "[Registry]" in _iss()

    def test_run_section_present(self):
        assert "[Run]" in _iss()

    def test_uninstall_run_section_present(self):
        assert "[UninstallRun]" in _iss()

    def test_uninstall_delete_section_present(self):
        assert "[UninstallDelete]" in _iss()

    def test_code_section_present(self):
        assert "[Code]" in _iss()

    def test_tasks_section_present(self):
        assert "[Tasks]" in _iss()


# ---------------------------------------------------------------------------
# 4. App ID and identity
# ---------------------------------------------------------------------------


class TestAppIdentity:
    """AppId must be stable and well-formed for upgrade detection."""

    EXPECTED_APP_ID = "{8E3B5C1A-2D4F-4E6A-9B7C-1D2E3F4A5B6C}"

    def test_app_id_present(self):
        assert "AppId=" in _iss(), "AppId not defined in installer"

    def test_app_id_is_guid(self):
        iss = _iss()
        # Inno Setup uses {{GUID} — double-brace is the preprocessor escape for {
        m = re.search(r"AppId=\{?\{([0-9A-Fa-f\-]{36})\}", iss)
        assert m, "AppId is not a valid GUID format"

    def test_app_id_stable(self):
        """AppId must match the known stable GUID."""
        iss = _iss()
        assert self.EXPECTED_APP_ID in iss, (
            f"AppId changed from expected {self.EXPECTED_APP_ID}"
        )

    def test_app_name_is_trackora(self):
        iss = _iss()
        assert "AppName={#MyAppName}" in iss or 'AppName="Trackora"' in iss

    def test_publisher_set(self):
        assert "AppPublisher=" in _iss()

    def test_publisher_url_set(self):
        assert "AppPublisherURL=" in _iss()


# ---------------------------------------------------------------------------
# 5. Installation directory and file layout
# ---------------------------------------------------------------------------


class TestInstallationLayout:
    """Installation directory defaults and file specifications."""

    def test_default_dir_is_program_files(self):
        iss = _iss()
        assert "DefaultDirName={autopf}" in iss, (
            "Installer does not default to Program Files"
        )

    def test_trackora_exe_in_files(self):
        iss = _iss()
        assert "Trackora.exe" in iss or "{#MyAppExeName}" in iss, (
            "Trackora.exe not referenced in [Files] section"
        )

    def test_exe_source_is_dist_folder(self):
        iss = _iss()
        assert "..\\dist\\" in iss or "../dist/" in iss, (
            "Installer does not pull executable from dist/"
        )

    def test_ignoreversion_flag_set(self):
        """Prevents version mismatch errors during upgrade."""
        assert "ignoreversion" in _iss()

    def test_no_appdata_files_in_files_section(self):
        """Installer must not install any files into AppData."""
        iss = _iss()
        files_start = iss.find("[Files]")
        files_end = iss.find("[", files_start + 1)
        files_section = iss[files_start:files_end]
        # APPDATA paths must not appear as install destinations
        assert "{userappdata}" not in files_section.lower(), (
            "Installer is deploying files into APPDATA — user data must not be preloaded"
        )
        assert "{commonappdata}" not in files_section.lower()

    def test_installation_to_app_dir(self):
        """Files must be installed to {app}."""
        iss = _iss()
        files_start = iss.find("[Files]")
        files_end = iss.find("[", files_start + 1)
        files_section = iss[files_start:files_end]
        assert "DestDir: \"{app}\"" in files_section, (
            "Installer does not install to {app} directory"
        )


# ---------------------------------------------------------------------------
# 6. Shortcut configuration
# ---------------------------------------------------------------------------


class TestShortcutConfiguration:
    """Verify Start Menu, Desktop, and Uninstall shortcuts are configured."""

    def test_start_menu_shortcut_present(self):
        iss = _iss()
        icons_start = iss.find("[Icons]")
        icons_end = iss.find("[", icons_start + 1)
        icons_section = iss[icons_start:icons_end]
        assert "{group}" in icons_section, "No Start Menu ({group}) shortcut defined"

    def test_uninstall_shortcut_in_start_menu(self):
        iss = _iss()
        assert "{uninstallexe}" in iss, "Uninstall shortcut not configured"

    def test_desktop_shortcut_optional(self):
        """Desktop shortcut must be conditional on 'desktopicon' task."""
        iss = _iss()
        icons_start = iss.find("[Icons]")
        icons_end = iss.find("[", icons_start + 1)
        icons_section = iss[icons_start:icons_end]
        assert "Tasks: desktopicon" in icons_section, (
            "Desktop shortcut must be conditional on desktopicon task"
        )
        assert "{autodesktop}" in icons_section, (
            "Desktop shortcut not using {autodesktop}"
        )

    def test_desktopicon_task_defined(self):
        iss = _iss()
        tasks_start = iss.find("[Tasks]")
        tasks_end = iss.find("[", tasks_start + 1)
        tasks_section = iss[tasks_start:tasks_end]
        assert "desktopicon" in tasks_section, (
            "desktopicon task not defined in [Tasks]"
        )

    def test_desktop_shortcut_checked_once(self):
        """Desktop shortcut task should not default-check on upgrades."""
        iss = _iss()
        # 'checkedonce' means it defaults checked on first install, not upgrades
        assert "checkedonce" in iss

    def test_startup_task_defined(self):
        iss = _iss()
        tasks_start = iss.find("[Tasks]")
        tasks_end = iss.find("[", tasks_start + 1)
        tasks_section = iss[tasks_start:tasks_end]
        assert "startup" in tasks_section, (
            "startup task not defined in [Tasks]"
        )


# ---------------------------------------------------------------------------
# 7. Registry configuration
# ---------------------------------------------------------------------------


class TestRegistryConfiguration:
    """Verify registry entries are minimal and correct."""

    def test_startup_registry_key_is_hkcu_run(self):
        iss = _iss()
        reg_start = iss.find("[Registry]")
        reg_end = iss.find("[", reg_start + 1)
        reg_section = iss[reg_start:reg_end]
        assert "Software\\Microsoft\\Windows\\CurrentVersion\\Run" in reg_section, (
            "Startup registry key not in HKCU Run"
        )

    def test_startup_registry_conditional_on_task(self):
        iss = _iss()
        reg_start = iss.find("[Registry]")
        reg_end = iss.find("[", reg_start + 1)
        reg_section = iss[reg_start:reg_end]
        assert "Tasks: startup" in reg_section, (
            "Startup registry entry must be conditional on 'startup' task"
        )

    def test_startup_registry_uninstallable(self):
        """Startup key must be removed on uninstall."""
        iss = _iss()
        reg_start = iss.find("[Registry]")
        reg_end = iss.find("[", reg_start + 1)
        reg_section = iss[reg_start:reg_end]
        assert "uninsdeletevalue" in reg_section, (
            "Startup registry entry not marked uninsdeletevalue"
        )

    def test_old_gametracker_run_value_cleaned(self):
        """Installer must clean up legacy GameTracker Run registry value."""
        iss = _iss()
        assert "GameTracker" in iss or "OldAppName" in iss, (
            "No reference to cleaning old GameTracker registry value"
        )
        assert "deletevalue" in iss, (
            "Old GameTracker Run value not flagged for deletion"
        )

    def test_no_excessive_registry_entries(self):
        """Installer must not pollute HKLM Software or HKCU Software."""
        iss = _iss()
        reg_start = iss.find("[Registry]")
        reg_end = iss.find("[", reg_start + 1)
        reg_section = iss[reg_start:reg_end]
        # Must not write to HKLM\Software\Trackora or HKCU\Software\Trackora
        assert "HKCU; Subkey: \"Software\\Trackora\"" not in reg_section, (
            "Installer polluting HKCU\\Software\\Trackora"
        )
        assert "HKLM; Subkey: \"Software\\Trackora\"" not in reg_section, (
            "Installer polluting HKLM\\Software\\Trackora"
        )


# ---------------------------------------------------------------------------
# 8. Uninstall — data preservation
# ---------------------------------------------------------------------------


class TestUninstallDataPreservation:
    """Uninstall must clean up Program Files but preserve AppData."""

    def test_uninstall_delete_targets_app_dir_only(self):
        """[UninstallDelete] must only reference {app}, not {userappdata}."""
        iss = _iss()
        ud_start = iss.find("[UninstallDelete]")
        ud_end = iss.find("[", ud_start + 1)
        ud_section = iss[ud_start:ud_end]
        assert "{app}" in ud_section, "{app} not in [UninstallDelete]"
        # Must NOT delete AppData
        assert "{userappdata}" not in ud_section, (
            "Uninstaller deletes AppData — this would destroy user data!"
        )
        assert "{commonappdata}" not in ud_section

    def test_no_appdata_deletion_in_code_section(self):
        """[Code] section must not contain logic to delete AppData."""
        iss = _iss()
        code_start = iss.find("[Code]")
        code_section = iss[code_start:]
        # Should not delete the new AppData location
        assert "userappdata" not in code_section.lower() or (
            "MigrateAppData" in code_section
        ), "Code section references AppData unexpectedly"

    def test_appdata_preservation_comment_present(self):
        """Installer must document that AppData is intentionally preserved."""
        iss = _iss()
        assert "AppData" in iss and ("preserved" in iss.lower() or "intentionally" in iss.lower()), (
            "No documentation that AppData is preserved on uninstall"
        )

    def test_uninstall_run_kills_process_before_uninstall(self):
        """Uninstaller must terminate the app before removing files."""
        iss = _iss()
        uninstall_run_start = iss.find("[UninstallRun]")
        # There should be a KillAppProcesses call in InitializeUninstall
        assert "InitializeUninstall" in iss, "InitializeUninstall not defined"
        assert "KillAppProcesses" in iss or "KillProcessByName" in iss, (
            "Uninstaller does not kill app process before removal"
        )


# ---------------------------------------------------------------------------
# 9. Upgrade logic
# ---------------------------------------------------------------------------


class TestUpgradeLogic:
    """Upgrade from previous versions must be handled correctly."""

    def test_upgrade_processes_killed_on_setup_start(self):
        """InitializeSetup must kill old processes."""
        iss = _iss()
        assert "InitializeSetup" in iss, "InitializeSetup function not defined"
        assert "KillAppProcesses" in iss, "KillAppProcesses not called in InitializeSetup"

    def test_old_gametracker_exe_killed(self):
        """Installer must kill old GameTracker.exe (legacy process name)."""
        iss = _iss()
        assert "GameTracker.exe" in iss or "OldExeNameConst" in iss, (
            "Old GameTracker.exe not targeted for process termination"
        )

    def test_old_program_dir_cleaned_up(self):
        """Post-install must remove old GameTracker program directory."""
        iss = _iss()
        assert "RemoveOldProgramDir" in iss, (
            "RemoveOldProgramDir not called in CurStepChanged"
        )

    def test_old_shortcuts_removed(self):
        """Post-install must remove old GameTracker shortcuts."""
        iss = _iss()
        assert "RemoveOldShortcuts" in iss, (
            "RemoveOldShortcuts not called in post-install"
        )

    def test_appdata_migration_implemented(self):
        """GameTracker → Trackora AppData migration must be implemented."""
        iss = _iss()
        assert "MigrateAppData" in iss, "MigrateAppData function not found"

    def test_appdata_migration_only_if_old_exists(self):
        """Migration must check if old AppData exists before migrating."""
        iss = _iss()
        code_start = iss.find("[Code]")
        code_section = iss[code_start:]
        # The function should have a conditional check
        assert "DirExists(OldDataDir)" in code_section or "DirExists" in code_section, (
            "AppData migration does not check if old path exists"
        )

    def test_migration_skipped_if_new_exists(self):
        """Migration must be skipped if new AppData already exists."""
        iss = _iss()
        assert "DirExists(NewDataDir)" in iss, (
            "AppData migration does not check if new path already exists"
        )

    def test_usepreviousappdir_disabled(self):
        """
        UsePreviousAppDir=no ensures upgrade always installs to new Trackora
        directory, not the old GameTracker directory.
        """
        iss = _iss()
        assert "UsePreviousAppDir=no" in iss, (
            "UsePreviousAppDir should be 'no' to force correct install directory"
        )

    def test_postinstall_step_triggered(self):
        """CurStepChanged must handle ssPostInstall."""
        iss = _iss()
        assert "ssPostInstall" in iss, "ssPostInstall not handled in CurStepChanged"

    def test_xcopy_fallback_for_migration(self):
        """Migration must have xcopy fallback if rename fails."""
        iss = _iss()
        assert "xcopy" in iss, (
            "AppData migration has no fallback for cross-drive rename failure"
        )


# ---------------------------------------------------------------------------
# 10. Launch configuration
# ---------------------------------------------------------------------------


class TestLaunchConfiguration:
    """Post-install launch and startup configuration."""

    def test_postinstall_launch_option(self):
        """User must be given option to launch after install."""
        iss = _iss()
        run_start = iss.find("[Run]")
        run_end = iss.find("[", run_start + 1)
        run_section = iss[run_start:run_end]
        assert "postinstall" in run_section, "No postinstall launch option"
        assert "skipifsilent" in run_section, "Launch must be skipped in silent mode"

    def test_startup_task_writes_run_key(self):
        """If user selects auto-start, registry Run key must be written."""
        iss = _iss()
        assert "CurrentVersion\\Run" in iss

    def test_startup_registry_uses_app_dir(self):
        """Startup Run key must point to {app}\\Trackora.exe."""
        iss = _iss()
        assert "{app}\\{#MyAppExeName}" in iss or "{app}\\Trackora.exe" in iss, (
            "Startup registry value does not reference app executable"
        )


# ---------------------------------------------------------------------------
# 11. Installer UX configuration
# ---------------------------------------------------------------------------


class TestInstallerUX:
    """Installer wizard and UI configuration."""

    def test_wizard_style_modern(self):
        assert "WizardStyle=modern" in _iss(), "Installer not using modern wizard style"

    def test_compression_is_lzma2(self):
        assert "lzma2" in _iss(), "Installer not using lzma2 compression"

    def test_solid_compression_enabled(self):
        assert "SolidCompression=yes" in _iss()

    def test_setup_icon_referenced(self):
        iss = _iss()
        assert "SetupIconFile=" in iss, "No setup icon configured"

    def test_uninstall_display_icon_set(self):
        assert "UninstallDisplayIcon=" in _iss()

    def test_admin_privileges_required(self):
        assert "PrivilegesRequired=admin" in _iss(), (
            "Installer should require admin for Program Files installation"
        )

    def test_close_applications_enabled(self):
        """Inno Setup should close applications before overwriting files."""
        assert "CloseApplications=yes" in _iss()

    def test_restart_applications_disabled(self):
        """App should not auto-restart after install (user controls this)."""
        assert "RestartApplications=no" in _iss()

    def test_output_dir_set(self):
        assert "OutputDir=" in _iss()

    def test_output_filename_includes_version(self):
        iss = _iss()
        m = re.search(r"OutputBaseFilename\s*=\s*(.+)", iss)
        assert m, "OutputBaseFilename not defined"
        assert "{#MyAppVersion}" in m.group(1), (
            "OutputBaseFilename does not include version"
        )


# ---------------------------------------------------------------------------
# 12. Code section logic validation
# ---------------------------------------------------------------------------


class TestCodeSectionLogic:
    """Validate the Pascal code section of the installer."""

    def test_kill_by_name_function_exists(self):
        assert "KillProcessByName" in _iss()

    def test_kill_app_processes_function_exists(self):
        assert "KillAppProcesses" in _iss()

    def test_old_run_value_check_function_exists(self):
        assert "OldRunValueExists" in _iss()

    def test_get_old_install_path_function_exists(self):
        assert "GetOldInstallPath" in _iss()

    def test_remove_old_program_dir_function_exists(self):
        assert "RemoveOldProgramDir" in _iss()

    def test_remove_old_shortcuts_function_exists(self):
        assert "RemoveOldShortcuts" in _iss()

    def test_remove_old_desktop_shortcut_function_exists(self):
        assert "RemoveOldDesktopShortcut" in _iss()

    def test_migrate_appdata_function_exists(self):
        assert "MigrateAppData" in _iss()

    def test_initialize_setup_function_exists(self):
        assert "function InitializeSetup" in _iss()

    def test_cur_step_changed_function_exists(self):
        assert "procedure CurStepChanged" in _iss()

    def test_initialize_uninstall_function_exists(self):
        assert "function InitializeUninstall" in _iss()

    def test_cur_uninstall_step_changed_function_exists(self):
        assert "procedure CurUninstallStepChanged" in _iss()

    def test_kill_uses_taskkill(self):
        """Process termination must use taskkill.exe."""
        iss = _iss()
        assert "taskkill.exe" in iss, "KillProcessByName should use taskkill.exe"

    def test_kill_uses_force_flag(self):
        """Must use /f flag to force-terminate even unresponsive processes."""
        assert "/f" in _iss()

    def test_migration_uses_rename_file(self):
        """AppData migration must attempt RenameFile for efficiency."""
        assert "RenameFile" in _iss()

    def test_log_statements_present(self):
        """Installer must log significant operations for diagnosability."""
        iss = _iss()
        log_count = iss.count("Log(")
        assert log_count >= 10, (
            f"Installer only has {log_count} Log() calls — add more for diagnosability"
        )


# ---------------------------------------------------------------------------
# 13. PyInstaller spec consistency with installer
# ---------------------------------------------------------------------------


class TestSpecInstallerConsistency:
    """Cross-validate PyInstaller spec against installer script."""

    def test_spec_exe_name_matches_installer(self):
        """Spec must produce Trackora.exe which installer references."""
        spec = SPEC_PATH.read_text(encoding="utf-8")
        iss = _iss()
        # Spec must produce Trackora.exe
        assert 'name="Trackora"' in spec, "Spec does not produce Trackora.exe"
        # Installer must reference Trackora.exe
        assert "Trackora.exe" in iss or "{#MyAppExeName}" in iss

    def test_spec_icon_matches_installer_icon(self):
        """Both spec and installer must reference the same icon file."""
        spec = SPEC_PATH.read_text(encoding="utf-8")
        iss = _iss()
        # Both reference app_icon.ico
        assert "app_icon.ico" in spec
        assert "app_icon.ico" in iss

    def test_spec_themes_data_present(self):
        """Themes directory must be bundled by PyInstaller."""
        spec = SPEC_PATH.read_text(encoding="utf-8")
        assert "ui/themes" in spec

    def test_spec_icons_data_present(self):
        """Icons directory must be bundled by PyInstaller."""
        spec = SPEC_PATH.read_text(encoding="utf-8")
        assert "ui/icons" in spec

    def test_spec_windowed_mode(self):
        """Executable must be windowed (no console window)."""
        spec = SPEC_PATH.read_text(encoding="utf-8")
        assert "console=False" in spec, "Spec must set console=False for GUI app"

    def test_spec_no_debug_mode(self):
        """Production spec must have debug=False."""
        spec = SPEC_PATH.read_text(encoding="utf-8")
        assert "debug=False" in spec

    def test_psutil_in_hidden_imports(self):
        spec = SPEC_PATH.read_text(encoding="utf-8")
        assert '"psutil"' in spec, "psutil missing from hidden imports"

    def test_pymongo_in_hidden_imports(self):
        spec = SPEC_PATH.read_text(encoding="utf-8")
        assert '"pymongo"' in spec, "pymongo missing from hidden imports"


# ---------------------------------------------------------------------------
# 14. File and resource existence checks
# ---------------------------------------------------------------------------


class TestRequiredFilesExist:
    """All files referenced by installer and spec must exist on disk."""

    def test_app_icon_exists(self):
        icon = REPO_ROOT / "ui" / "icons" / "app_icon.ico"
        assert icon.is_file(), f"App icon not found: {icon}"

    def test_themes_directory_exists(self):
        themes = REPO_ROOT / "ui" / "themes"
        assert themes.is_dir(), f"Themes directory not found: {themes}"

    def test_icons_directory_exists(self):
        icons = REPO_ROOT / "ui" / "icons"
        assert icons.is_dir(), f"Icons directory not found: {icons}"

    def test_version_info_txt_exists(self):
        assert VERSION_INFO_PATH.is_file(), f"version_info.txt not found: {VERSION_INFO_PATH}"

    def test_main_entry_point_exists(self):
        main = REPO_ROOT / "trackora" / "__main__.py"
        assert main.is_file(), f"Entry point not found: {main}"

    def test_installer_iss_references_existing_source(self):
        """Trackora.iss [Files] Source must point to existing executable."""
        # The .iss source references ../dist/Trackora.exe
        dist_exe = REPO_ROOT / "dist" / "Trackora.exe"
        assert dist_exe.is_file(), (
            f"Installer source file not found: {dist_exe}. "
            "Run: pyinstaller Trackora.spec"
        )
