# Trackora v2.0.1 Known Limitations

This document lists the low-priority, non-blocking limitations identified during the Trackora v2.0.1 release cycle. These items do not impact core tracking reliability or data safety and are deferred to future releases.

---

## 1. Unsigned Windows Installer
- **Description**: The compiled setup executable `Trackora-Setup-2.0.1.exe` is not signed with a trusted digital certificate.
- **Symptom**: Windows Defender SmartScreen may show a warning dialog ("Windows protected your PC") on first execution.
- **Workaround**: Users must click "More info" and select "Run anyway" to proceed with installation.
- **Resolution Plan**: Code signing integration is planned for the v2.1.0 release.

---

## 2. Setup Wizard License Agreement Rendering
- **Description**: The Inno Setup installation wizard does not render a License Agreement checkbox step.
- **Symptom**: The installer installs files directly without presenting the MIT license text.
- **Workaround**: The license is fully documented in `LICENSE.md` in the installation directory and the GitHub repository.
- **Resolution Plan**: The `LicenseFile` parameter will be added to the Inno Setup script in the next minor version.

---

## 3. GitHub API Rate Limiting on Update Checks
- **Description**: Verification queries to the GitHub Releases API are subject to rate limiting controls for unauthenticated client IP addresses.
- **Symptom**: If the user checks for updates repeatedly, GitHub may return HTTP 403 Forbidden.
- **Mitigation**: Trackora caches the update results for 1 hour locally. If rate limits are exceeded, the app falls back gracefully without interrupting operations or crashing.
- **Resolution Plan**: Out-of-scope. Standard GitHub API behavior.

---

## 4. Playtime Analytics Resolution for Very Long Sessions
- **Description**: If a game runs continuously for more than 24 hours, the dashboard charts calculate playtime against the calendar day when the session ended, rather than partitioning it hour-by-hour across days.
- **Symptom**: Heatmaps may display playtime spikes on the day of session closure.
- **Workaround**: None required. Overall lifetime playtime calculations remain fully accurate.
- **Resolution Plan**: Playtime partitioning algorithms will be refactored in v2.1.0 as part of analytics enhancements.
