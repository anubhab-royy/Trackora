; Trackora Inno Setup Installer
; Requires Inno Setup 6+ (https://jrsoftware.org/isdl.php)
;
; Build: iscc installer/Trackora.iss
;
; Upgrade behavior:
;   1. Detects old GameTracker installation via AppId + registry lookup
;   2. Kills running GameTracker.exe / Trackora.exe before anything
;   3. Silently runs old uninstaller (same AppId triggers this automatically)
;   4. Removes leftover old program directory and registry cruft
;   5. Migrates %APPDATA%\GameTracker\ → %APPDATA%\Trackora\ if needed
;   6. Installs fresh to {autopf}\Trackora
;
; NEVER deletes user data (SQLite DB in AppData) unless explicitly migrated.

#define MyAppName "Trackora"
#define MyAppShortName "Trackora"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Trackora"
#define MyAppURL "https://github.com/yourusername/trackora"
#define MyAppExeName "Trackora.exe"
#define MyAppAssocName "Trackora Data"

; Old names used for upgrade detection / cleanup
#define OldAppName "GameTracker"
#define OldExeName "GameTracker.exe"

[Setup]
; Same AppId so Windows treats upgrades as the same product
AppId={{8E3B5C1A-2D4F-4E6A-9B7C-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Always default to new Trackora directory, even if old was GameTracker
DefaultDirName={autopf}\{#MyAppShortName}
UsePreviousAppDir=no
DisableProgramGroupPage=yes
DisableDirPage=auto
DefaultGroupName={#MyAppName}

; Always create a fresh Start Menu group (old "GameTracker" group stays gone)
UsePreviousGroup=no

AllowNoIcons=yes
LicenseFile=
PrivilegesRequired=admin
OutputDir=Output
OutputBaseFilename=Trackora-Setup-{#MyAppVersion}
SetupIconFile=..\ui\icons\app_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

; Inno Setup will close files it is about to overwrite, but since we install
; to a *new* directory during upgrade, the old exe won't be detected automatically.
; We kill the old process in [Code] — InitializeSetup.
CloseApplications=yes
RestartApplications=no

; Show the user what is happening during an upgrade
ShowUndisplayableLanguages=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "startup"; Description: "Start &Trackora when Windows starts"; GroupDescription: "Startup options:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Ensure no files are installed in AppData — runtime data is created on first launch

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Only modify uninstall and optional startup — no other registry pollution
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppShortName}"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletevalue; Tasks: startup

; Clean up old GameTracker Run value (in case old uninstaller missed it)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "{#OldAppName}"; Flags: deletevalue; Check: OldRunValueExists

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--uninstall"; Flags: runhidden

; On uninstall, leave AppData alone (user data preserved)
; Only clean up program files
[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; ---------------------------------------------------------------------------
; [Code] — Upgrade / migration / cleanup logic
; ---------------------------------------------------------------------------

[Code]

// ---------------------------------------------------------------------------
// Constants for old-version detection
// ---------------------------------------------------------------------------
const
  OldAppNameConst = '{#OldAppName}';
  OldExeNameConst = '{#OldExeName}';

// ---------------------------------------------------------------------------
// Kill any running instances of a given executable name (fire-and-forget)
// ---------------------------------------------------------------------------
procedure KillProcessByName(const ExeName: string);
var
  DummyCode: Integer;
begin
  Log('Killing process: ' + ExeName);
  Exec('taskkill.exe', '/f /im ' + ExeName, '', SW_HIDE, ewWaitUntilTerminated, DummyCode);
  // Give the process a moment to release file handles
  Sleep(500);
end;

// ---------------------------------------------------------------------------
// Kill both old (GameTracker.exe) and new (Trackora.exe) instances
// ---------------------------------------------------------------------------
procedure KillAppProcesses;
begin
  KillProcessByName(OldExeNameConst);
  KillProcessByName('{#MyAppExeName}');
end;

// ---------------------------------------------------------------------------
// Check if the old GameTracker Run registry value still exists
// ---------------------------------------------------------------------------
function OldRunValueExists: Boolean;
var
  Value: string;
begin
  Result := RegQueryStringValue(
    HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run',
    OldAppNameConst, Value
  );
  if Result then
    Log('Found old Run value: GameTracker = ' + Value);
end;

// ---------------------------------------------------------------------------
// Get the old GameTracker install directory from the old uninstall key,
// or fall back to the default Program Files path.
// ---------------------------------------------------------------------------
function GetOldInstallPath: string;
var
  UninstallKey: string;
begin
  Result := '';
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';

  if RegQueryStringValue(HKLM, UninstallKey, 'Inno Setup: App Path', Result) then
  begin
    Log('Found old install path from HKLM: ' + Result);
    Exit;
  end;

  if RegQueryStringValue(HKCU, UninstallKey, 'Inno Setup: App Path', Result) then
  begin
    Log('Found old install path from HKCU: ' + Result);
    Exit;
  end;

  // Fallback: default location for old GameTracker
  Result := ExpandConstant('{autopf}') + '\' + OldAppNameConst;
  Log('Using default old install path: ' + Result);
end;

// ---------------------------------------------------------------------------
// Delete the old program directory and all its contents.
// Only called after the old uninstaller has already removed files.
// ---------------------------------------------------------------------------
procedure RemoveOldProgramDir;
var
  OldDir: string;
begin
  OldDir := GetOldInstallPath;
  if not DirExists(OldDir) then
  begin
    Log('Old program dir does not exist — nothing to clean: ' + OldDir);
    Exit;
  end;

  Log('Removing old program directory: ' + OldDir);
  if DelTree(OldDir, True, True, True) then
    Log('  Successfully removed old program dir.')
  else
    Log('  WARNING: Could not fully remove old program dir.');
end;

// ---------------------------------------------------------------------------
// Remove old Start Menu shortcut group "GameTracker" if it still exists
// ---------------------------------------------------------------------------
procedure RemoveOldShortcuts;
var
  OldGroupDir: string;
begin
  OldGroupDir := ExpandConstant('{commonprograms}') + '\' + OldAppNameConst;
  if DirExists(OldGroupDir) then
  begin
    Log('Removing old Start Menu group: ' + OldGroupDir);
    if DelTree(OldGroupDir, True, True, True) then
      Log('  Removed old shortcuts.')
    else
      Log('  WARNING: Could not remove old shortcuts.');
  end
  else
    Log('Old Start Menu group not found.');
end;

// ---------------------------------------------------------------------------
// Remove old desktop shortcut if it exists
// ---------------------------------------------------------------------------
procedure RemoveOldDesktopShortcut;
var
  OldDesktopLink: string;
begin
  OldDesktopLink := ExpandConstant('{autodesktop}') + '\' + OldAppNameConst + '.lnk';
  if FileExists(OldDesktopLink) then
  begin
    Log('Removing old desktop shortcut: ' + OldDesktopLink);
    if DeleteFile(OldDesktopLink) then
      Log('  Removed.')
    else
      Log('  WARNING: Could not remove desktop shortcut.');
  end;
end;

// ---------------------------------------------------------------------------
// Migrate user data from %APPDATA%\GameTracker to %APPDATA%\Trackora
// Only migrates if old path exists and new path does not.
// ---------------------------------------------------------------------------
procedure MigrateAppData;
var
  OldDataDir, NewDataDir, Quote: string;
  ResultCode: Integer;
begin
  Quote := '"';
  OldDataDir := ExpandConstant('{userappdata}\' + OldAppNameConst);
  NewDataDir := ExpandConstant('{userappdata}\{#MyAppShortName}');

  if not DirExists(OldDataDir) then
  begin
    Log('No old AppData to migrate: ' + OldDataDir);
    Exit;
  end;

  if DirExists(NewDataDir) then
  begin
    Log('New AppData already exists, skipping migration.');
    Exit;
  end;

  Log('Migrating data: ' + OldDataDir + ' -> ' + NewDataDir);

  if RenameFile(OldDataDir, NewDataDir) then
  begin
    Log('Migration successful (RenameFile).');
  end
  else
  begin
    Log('RenameFile failed. Trying xcopy fallback...');
    if Exec(ExpandConstant('{cmd}'), '/c xcopy ' + Quote + OldDataDir + '\*' + Quote + ' ' + Quote + NewDataDir + '\' + Quote + ' /e /i /h /k /y', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
    begin
      Log('xcopy succeeded. Removing old directory...');
      Exec(ExpandConstant('{cmd}'), '/c rmdir /s /q ' + Quote + OldDataDir + Quote, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Log('Migration completed via xcopy.');
    end
    else
      Log('WARNING: Migration failed. Old data preserved at: ' + OldDataDir);
  end;
end;

// ---------------------------------------------------------------------------
// InitializeSetup — called when the installer starts
// ---------------------------------------------------------------------------
function InitializeSetup: Boolean;
var
  OldPath: string;
begin
  Result := True;

  // Kill any running instances of the app (old or new)
  KillAppProcesses;

  // Detect old installation
  OldPath := GetOldInstallPath;
  if DirExists(OldPath) then
  begin
    Log('Old GameTracker installation detected at: ' + OldPath);
    Log('Inno Setup will run the old uninstaller automatically (same AppId).');
  end
  else
    Log('No old GameTracker installation detected — performing fresh install.');
end;

// ---------------------------------------------------------------------------
// CurStepChanged — called at various stages of installation
// ---------------------------------------------------------------------------
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('');
    Log('=== Post-Install Phase ===');

    // 1. Migrate user data from old AppData path to new
    MigrateAppData;

    // 2. Clean up old program files left by old uninstaller
    RemoveOldProgramDir;

    // 3. Clean up old shortcuts
    RemoveOldShortcuts;
    RemoveOldDesktopShortcut;

    Log('=== Post-Install Complete ===');
    Log('');
  end;
end;

// ---------------------------------------------------------------------------
// InitializeUninstall — called when the uninstaller starts
// ---------------------------------------------------------------------------
function InitializeUninstall: Boolean;
begin
  // Kill the app before uninstalling
  KillAppProcesses;
  Result := True;
end;

// ---------------------------------------------------------------------------
// CurUninstallStepChanged — called at various stages of uninstallation
// ---------------------------------------------------------------------------
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Log('Uninstall complete.');
    // Note: AppData is intentionally NOT deleted to preserve user data.
    // The user can manually remove %APPDATA%\Trackora if desired.
  end;
end;
