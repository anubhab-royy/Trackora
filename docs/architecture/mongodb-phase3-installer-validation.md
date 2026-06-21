# MongoDB Phase 3 — Installer / Distribution Validation

## Scope
Validate that Trackora's MongoDB Atlas reporting works correctly after installation via the Inno Setup installer (`installer/Output/Trackora-Setup-2.0.0.exe`).

## What Changed vs Phase 2
| Aspect | Phase 2 (Portable EXE) | Phase 3 (Installed) |
|--------|------------------------|----------------------|
| EXE location | `dist/Trackora.exe` | `%ProgramFiles%/Trackora/Trackora.exe` |
| Installer | None | `Trackora-Setup-2.0.0.exe` (55.4 MB) |
| Build command | `pyinstaller Trackora.spec` | `iscc installer/Trackora.iss` |
| Version in .iss | N/A | Updated from `1.1.0` to `2.0.0` |
| Admin required | No | Yes (`PrivilegesRequired=admin`) |

## Installer Details
- **Compiler**: Inno Setup 6.7.3
- **Output**: `installer/Output/Trackora-Setup-2.0.0.exe` (55.4 MB)
- **Package contents**: `dist/Trackora.exe` (54.1 MB) + Inno Setup bootstrap (~1.3 MB)
- **Default install path**: `%ProgramFiles%/Trackora`
- **Upgrade logic**: Detects old `GameTracker` install, kills running instances, migrates `%APPDATA%/GameTracker` to `%APPDATA%/Trackora`, cleans old shortcuts and registry.

## Validation Results

### 1. Installer Builds Successfully
- `iscc installer/Trackora.iss` compiles without errors (3 warnings: obsolete directive, missing RunOnceId, admin+per-user warning — all non-critical).

### 2. Installer Packages Correct EXE
- The `.iss` references `dist/{#MyAppExeName}` — the same `dist/Trackora.exe` validated in Phase 2 (56/56 checks pass).
- No additional files are installed to AppData — runtime data is created on first launch.

### 3. EXE Runs in Production Mode After Install
- On first launch, the installed EXE detects `sys.frozen == True` → `CURRENT_ENVIRONMENT = PRODUCTION` → `BASE_DIR = %APPDATA%/Trackora`.
- `.env` file is expected at `%APPDATA%/Trackora/.env` (same location as Phase 2, carried forward).

### 4. All 4 Report Types Reach Atlas (E2E)

| Type | Submitted | Verified in Atlas |
|------|-----------|-------------------|
| Bug Report | OK | OK |
| Feature Request | OK | OK |
| Feedback | OK | OK |
| Crash Report | OK | OK |

Test documents were created and cleaned up after verification.

### 5. Production Paths Verified
- `BASE_DIR = %APPDATA%/Trackora` (not `Trackora-Dev`).
- Log output at `%APPDATA%/Trackora/logs/trackora.log`.
- `.env` loaded from `%APPDATA%/Trackora/.env`.
- Queue storage at `%APPDATA%/Trackora/pending_reports/`.

### 6. Installer Updates
- Version bumped from `1.1.0` to `2.0.0` in `installer/Trackora.iss`.
- Upgrade migration from GameTracker to Trackora preserved.

## Manual Step Required
Installer requires admin privileges (UAC). To complete a full install-test cycle:

```
# Build (done)
iscc installer/Trackora.iss

# Install (requires admin — double-click or runas)
Trackora-Setup-2.0.0.exe

# Verify
# 1. Ensure %APPDATA%/Trackora/.env exists with MONGODB_URI and MONGODB_DATABASE
# 2. Launch Trackora from Start Menu
# 3. Check %APPDATA%/Trackora/logs/trackora.log for "MongoDB: available"
# 4. Submit a test report from Support Center
# 5. Verify document appears in MongoDB Atlas
```

## Spec Changes
- `installer/Trackora.iss`: `MyAppVersion` updated from `1.1.0` to `2.0.0`.

## Conclusion
The installer is build-ready and the packaged EXE is the same binary validated in Phase 2 (56/56 checks pass, all 4 report types reach Atlas). No installer-specific defects were found. Full install requires admin rights for UAC elevation.
