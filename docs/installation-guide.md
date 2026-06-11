# Trackora Clean Windows Installation Guide

This guide walks you through installing Trackora on a **clean Windows 10/11** system that has no Python or developer tools installed.

---

## Option 1: Install via Installer (Recommended)

### Prerequisites

Your Windows system needs only:
- Windows 10 version 1809+ or Windows 11
- 64-bit system
- ~200 MB free disk space

### Installation Steps

1. **Download the installer**
   - Go to the [Releases page](https://github.com/yourusername/Trackora/releases)
   - Download `Trackora-Setup-1.0.0.exe`

2. **Run the installer**
   - Double-click `Trackora-Setup-1.0.0.exe`
   - If Windows Defender shows a warning, click **More info** → **Run anyway**
     - *(This happens because the executable is not yet code-signed. See the code signing section below.)*
   - Follow the installation wizard:
     - Accept the default installation directory (`C:\Program Files\Trackora`)
     - Optionally check **Create a desktop shortcut**
     - Optionally check **Start Trackora when Windows starts**
   - Click **Install**

3. **Launch Trackora**
   - After installation, check **Launch Trackora** and click **Finish**
   - Or launch from the **Start Menu** → **Trackora**

4. **Verify it's running**
   - The main window should appear with your statistics dashboard
   - A Trackora icon appears in the **system tray** (near the clock)
   - Right-click the tray icon to access the menu

### Runtime Data Locations

| Data | Windows Path |
|------|--------------|
| Database | `%APPDATA%\Trackora\Trackora.db` |
| Logs | `%APPDATA%\Trackora\logs\trackora.log` |

Your data is stored in your user folder, not in the Program Files directory. This means:
- Data survives application updates
- Data survives uninstallation (if you want to remove it, delete the `%APPDATA%\Trackora` folder manually)
- Different Windows users have separate data

---

## Option 2: Standalone Executable (Portable)

If you prefer not to use the installer:

1. Download `Trackora.exe` from the [Releases page](https://github.com/yourusername/Trackora/releases)
2. Place it anywhere (Desktop, a folder, USB drive)
3. Double-click to run
4. No installation required

---

## Option 3: Run from Source (Developers)

### Prerequisites

If you want to run from source code:

| Software | Why Needed | How to Get |
|----------|------------|------------|
| Python 3.13+ | Runtime | [python.org](https://www.python.org/downloads/) |
| Visual C++ Redistributable | PyQt6 dependency | Bundled with Python on Windows |
| Git | Clone the repo | [git-scm.com](https://git-scm.com/) |

### Step-by-Step

```powershell
# 1. Install Python 3.13+ from python.org (check "Add Python to PATH")

# 2. Open PowerShell and verify:
python --version

# 3. Clone the repository
git clone https://github.com/yourusername/Trackora.git
cd Trackora

# 4. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 5. Install dependencies
pip install -r requirements.txt

# 6. Run Trackora
python -m Trackora
```

### Building the Executable

```powershell
# Install PyInstaller
pip install pyinstaller

# Build
pyinstaller Trackora.spec

# Output: dist\Trackora.exe
```

### Building the Installer

```powershell
# Requires Inno Setup 6+ (https://jrsoftware.org/isdl.php)
iscc installer\Trackora.iss
```

---

## Managing Windows Defender

Since Trackora is built with PyInstaller, Windows Defender may initially flag it. This is a known false positive common to all PyInstaller-packaged applications.

### To resolve:

**Option A: Add an exclusion (quick)**
1. Open **Windows Security** → **Virus & threat protection**
2. Click **Manage settings** under "Virus & threat protection settings"
3. Scroll to **Exclusions** → **Add or remove exclusions**
4. Click **Add an exclusion** → **Folder**
5. Select `C:\Program Files\Trackora` (or wherever you installed)

**Option B: Code sign the executable (permanent)**
- See the [Code signing guide](../scripts/sign-code.ps1)
- A signed executable is trusted by Windows without exclusions

**Option C: Submit to Microsoft**
- Visit https://www.microsoft.com/en-us/wdsi/filesubmission
- Upload `Trackora.exe` to report it as a false positive
- Microsoft will whitelist it after review

---

## Updating Trackora

### Via the installer
1. Download the new `Trackora-Setup-X.X.X.exe`
2. Run it — it will automatically upgrade your existing installation
3. Your data in `%APPDATA%\Trackora` is preserved

### Via the standalone executable
1. Download the new `Trackora.exe`
2. Replace the old one
3. Restart the application

### Via automatic update check
1. From the application menu, select **Check for Updates**
2. If a new version is available, you'll be prompted to download it

---

## Troubleshooting

### "Application failed to start because Qt platform plugin could not be initialized"
- Install the **Visual C++ Redistributable** from Microsoft
- Download: https://aka.ms/vs/17/release/vc_redist.x64.exe

### "Database file could not be created"
- Ensure `%APPDATA%` is writable
- Check antivirus isn't blocking file creation
- Run as normal user (not administrator)

### "Logs folder could not be created"
- Same as above — `%APPDATA%\Trackora\logs` must be writable

### Application does not appear in system tray
- Some systems hide tray icons by default
- Click the **^** arrow near the clock to see hidden icons
- Drag the Trackora icon to the visible area if desired

### Uninstalling
- **Via installer**: Settings → Apps → Apps & features → Trackora → Uninstall
- **Portable**: Delete the executable and `%APPDATA%\Trackora` folder

---

## Windows Clean Install Prerequisites Checklist

Before installing Trackora, your Windows system needs:

| Requirement | Status | Action If Missing |
|-------------|--------|-------------------|
| Windows 10/11 64-bit | ✅ Built-in | Update Windows |
| 200 MB disk space | ✅ Almost always available | Free up space |
| Visual C++ Redistributable | ⚠️ Check | Download from Microsoft |
| Administrator rights | ✅ Usually have | Run installer as admin |
| Internet connection | ✅ For download | Connect to network |

### Visual C++ Redistributable

If Trackora fails to start with a "DLL not found" error:

1. Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
2. Run the installer
3. Restart Trackora

This is a one-time requirement — many applications already include it.
