# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.0.x   | ✅ Active |
| < 2.0   | ❌ Not supported |

## Reporting a Vulnerability

Trackora takes security seriously. If you discover a security vulnerability, please follow responsible disclosure practices.

### How to Report

1. **Do not** create a public GitHub issue
2. Send details to the maintainers via email or private contact
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Affected versions
   - Potential impact
   - Suggested fix (if available)

### What to Expect

- **Acknowledgment** within 48 hours
- **Initial assessment** within 5 business days
- **Fix timeline** communicated based on severity

### Severity Classification

| Severity | Response Time | Fix Timeline |
|----------|---------------|--------------|
| Critical | 24 hours | 7 days |
| High | 48 hours | 14 days |
| Medium | 5 business days | 30 days |
| Low | Next release | Next release |

## Security Practices

### For Users

- Trackora stores all data locally in SQLite — no cloud accounts required
- No telemetry or analytics data is collected
- Internet access is used only for: update checks, crash report submission, and optional MongoDB support
- Credentials (MongoDB URI, GitHub tokens) are stored in environment variables or `.env` files — never in source code

### For Developers

- No secrets in source code — use environment variables for all credentials
- `.env` is gitignored and must never be committed
- Code signing certificates stored securely, never in the repository
- Dependencies are pinned in `requirements.txt` and audited via CI
- Pull requests require review before merging to `main`

## Scope

This security policy covers:
- The Trackora application source code
- Build and packaging scripts
- CI/CD configuration

Out of scope:
- Third-party dependencies (report issues to their maintainers)
- MongoDB Atlas or Supabase infrastructure
- Operating system security
