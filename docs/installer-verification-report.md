# Trackora Installer Verification Report

**Version:** 1.0.0
**Date:** 2026-06-09
**Status:** CONFIGURATION VALIDATED

---

## Installer Configuration

| Parameter | Value |
|-----------|-------|
| Installer Tool | Inno Setup 6+ |
| Script | `installer/Trackora.iss` |
| Output | `installer/Output/Trackora-Setup-1.0.0.exe` |
| App ID | `{{8E3B5C1A-2D4F-4E6A-9B7C-1D2E3F4A5B6C}}` |
| Compression | lzma2/max (maximum) |
| Architecture | 64-bit Windows |

---

## Validation Checks

### 1. Installation Directory
- Default: `{autopf}\Trackora` (Program Files)
- Configurable via wizard: **YES**

### 2. Start Menu Shortcuts
- `Trackora` application shortcut: **YES**
- `Uninstall Trackora` shortcut: **YES**

### 3. Desktop Shortcut
- Optional, controlled by `desktopicon` task: **YES**

### 4. Startup Registration
- Optional, controlled by `startup` task: **YES**
- Registry key: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

### 5. Uninstall Support
- Windows Programs & Features entry: **YES**
- Uninstall icon: Application icon
- Display name: `Trackora 1.0.0`

### 6. Upgrade Support
- App ID persistent across versions: **YES**
- Existing install detected and replaced: **YES**
- User data in APPDATA preserved: **YES** (no files outside executable)

### 7. No Registry Pollution
- Allowed entries (only):
  - Uninstall entry (created by Inno Setup automatically)
  - Optional startup (only if user selects)

### 8. Code Signing Ready
- Installer supports future code signing: **YES**
- Script structure accommodates signed executable

---

## How to Build Installer

**Prerequisites:** Inno Setup 6+ installed

```bash
iscc installer/Trackora.iss
```

Output: `installer/Output/Trackora-Setup-1.0.0.exe`

---

## Installation Flow

1. User runs `Trackora-Setup-1.0.0.exe`
2. Welcome screen
3. Select installation directory (default: Program Files\Trackora)
4. Select components:
   - Desktop shortcut (optional)
   - Start with Windows (optional)
5. Install
6. Optional: Launch Trackora immediately

---

## Manual Verification Checklist (Post-Installation)

| Check | Expected Result |
|-------|----------------|
| Installation completes | Wizard finishes without errors |
| Start Menu entry | Trackora appears in Start Menu |
| Launch from Start Menu | Application starts |
| System tray icon | Trackora icon appears in tray |
| Database created | `%APPDATA%\Trackora\Trackora.db` exists |
| Logs created | `%APPDATA%\Trackora\logs\trackora.log` exists |
| Uninstall works | Remove from Programs & Features |
| No files left after uninstall | Only AppData remains (user data) |

---

## Verdict

**INSTALLER CONFIGURATION VALIDATED** — All configuration checks pass.

The Inno Setup script is complete and ready for use. Build the installer with `iscc installer/Trackora.iss` after installing Inno Setup 6+.
