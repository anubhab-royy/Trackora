# Building Trackora

Build a standalone Windows executable using PyInstaller and create an installer with Inno Setup.

## Prerequisites

### Windows Build Environment

1. **Python 3.13+** — [python.org](https://www.python.org/downloads/)
2. **Visual C++ Redistributable** — required by PyQt6
3. **Inno Setup 6+** — [jrsoftware.org](https://jrsoftware.org/isdl.php) (for installer only)
4. **Windows SDK** — for code signing via `signtool` (optional)

### Python Dependencies

```bash
pip install -r requirements.txt
pip install pyinstaller
```

## Application Entry Point

The entry point is `trackora/__main__.py`, invoked as:

```bash
python -m trackora
```

For PyInstaller builds the spec file (`Trackora.spec`) targets this entry point directly.

## PyInstaller Build

### Recommended Build (Spec File)

```bash
pyinstaller Trackora.spec
```

The spec file handles all hidden imports, data files, version metadata, and exclusions automatically.

### Quick Build (Command Line)

```bash
pyinstaller --onefile --windowed `
    --name "Trackora" `
    --icon "ui/icons/app_icon.ico" `
    --add-data "ui/themes;ui/themes" `
    --add-data "ui/icons;ui/icons" `
    --hidden-import "PyQt6.QtSvg" `
    --hidden-import "pyqtgraph" `
    --hidden-import "psutil" `
    --collect-submodules "database" `
    --collect-submodules "tracker" `
    --collect-submodules "trackora_stats" `
    --collect-submodules "services" `
    --collect-submodules "ui" `
    trackora/__main__.py
```

### Output

```
dist/Trackora.exe  (~52 MB)
```

## Runtime Paths

When packaged, Trackora stores data at:

| Data        | Windows Path                            |
|-------------|-----------------------------------------|
| Database    | `%APPDATA%\Trackora\trackora.db`        |
| Logs        | `%APPDATA%\Trackora\logs\trackora.log` |

No data is stored next to the executable — the application is fully portable and respects Windows conventions.

## Inno Setup Installer

After building `dist/Trackora.exe`, create the installer:

```bash
iscc installer/Trackora.iss
```

The installer is created at:

```
installer/Output/Trackora-Setup-1.0.0.exe
```

## Code Signing

Trackora includes a helper script for code signing:

```powershell
# Create a self-signed certificate and sign the executable:
.\scripts\sign-code.ps1
```

For production, obtain a certificate from a trusted CA (DigiCert, Sectigo, etc.):
- Prices range from free (self-signed for testing) to ~$200-500/year (trusted)
- Open-source projects can get free certificates via [Azure Trusted Signing](https://learn.microsoft.com/en-us/azure/trusted-signing/)

Manual signing with a purchased certificate:

```bash
signtool sign /fd SHA256 /a /f "certificate.pfx" /p "password" /tr http://timestamp.digicert.com /td SHA256 dist/Trackora.exe
```

## CI/CD Pipeline

A GitHub Actions workflow is configured at `.github/workflows/ci.yml`:

| Trigger | Action |
|---------|--------|
| Push/PR to `main` | Run tests |
| Tag push `v*` | Build executable + Create GitHub Release |

To trigger a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Automatic Updates

Trackora includes an `UpdateService` that checks GitHub Releases for newer versions. To integrate it:

```python
from services import UpdateService

updater = UpdateService("yourusername/trackora")
info = updater.check_for_updates()
if updater.update_available:
    print(f"Update available: {info.latest_version}")
    print(f"Download: {info.download_url}")
```

The service uses the GitHub Releases API and respects rate limits.

## Performance Optimizations

The spec file excludes unused packages to minimize binary size:

| Excluded Package | Reason | Size Saved |
|------------------|--------|------------|
| matplotlib | Not directly used by Trackora | ~15 MB |
| scipy, cupy, h5py | Optional pyqtgraph deps | ~5 MB |
| PyQt5, PySide2/6 | Alternative Qt bindings | ~3 MB |
| tkinter | Unused GUI framework | ~2 MB |

## Troubleshooting

### Missing Modules

Add `--hidden-import` for any dynamic imports:

```bash
--hidden-import "PyQt6.QtSvg"
--hidden-import "pyqtgraph"
--hidden-import "psutil"
```

### Theme / Resource Files Not Found

Verify `--add-data` paths use the correct separator:
- **Windows**: `source;dest`
- **Linux/macOS**: `source:dest`

### Database or Log Errors

If the application fails to create the database or log files, check:

1. `%APPDATA%\Trackora\` exists and is writable
2. Antivirus is not blocking file creation in AppData
3. The application is not running from a read-only location

### Windows Defender / Antivirus False Positives

PyInstaller-packaged executables may trigger false positives. To mitigate:

1. Code-sign the executable (see [Code Signing](#code-signing) above)
2. Submit the executable to Microsoft Defender portal
3. Use the Inno Setup installer (creates a proper installed application)
4. Add an exclusion in Windows Security for the installation folder

### Icon Not Showing in System Tray

The tray icon loads from the bundled `ui/icons/tray_icon.png`. If missing:

1. Verify `ui/icons/tray_icon.png` exists
2. Rebuild with `--add-data "ui/icons;ui/icons"`
3. Ensure PyQt6 QtSvg plugin is available
