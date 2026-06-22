# Contributing to Trackora

Thank you for considering contributing to Trackora. This document outlines the guidelines for contributing to the project.

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold its terms.

## How to Contribute

### Reporting Bugs

1. Check existing [issues](https://github.com/anomalyco/trackora/issues) for duplicates
2. Use the bug report template when creating an issue
3. Include: steps to reproduce, expected behavior, actual behavior, environment details

### Suggesting Features

1. Check existing issues and discussions for similar ideas
2. Describe the feature, its use case, and how it fits Trackora's scope
3. Be specific about the problem it solves

### Pull Requests

1. Fork the repository
2. Create a feature branch from `develop`: `git checkout -b feature/my-feature`
3. Write tests for new functionality
4. Ensure all tests pass: `python -m pytest`
5. Run linting: `ruff check .`
6. Run type checking: `mypy trackora database services tracker ui --explicit-package-bases --ignore-missing-imports`
7. Submit a PR against the `develop` branch

## Development Setup

### Prerequisites

- Windows 10/11 (primary target), Linux/macOS (limited support)
- Python 3.13+
- Git

### Setup

```bash
git clone https://github.com/anomalyco/trackora.git
cd trackora
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Running

```bash
python -m trackora
```

### Testing

```bash
python -m pytest
python -m pytest --cov=trackora --cov-report=term-missing
```

### Building

See [BUILD.md](BUILD.md) for PyInstaller and Inno Setup instructions.

## Project Architecture

Trackora follows a modular monolith architecture with 7 layers:

1. **Tracking Layer** — Game detection and session management
2. **Database Layer** — SQLite persistence via repositories
3. **Statistics Layer** — Playtime calculations and trend analysis
4. **UI Layer** — PyQt6 views and controllers
5. **System Services Layer** — Tray, startup, export
6. **Support Layer** — Bug reports, feature requests, feedback
7. **Crash Detection Layer** — Crash recovery and diagnostics

No SQL appears in UI code. No business logic appears in widget classes.

## Coding Standards

- Type hints required for all function signatures
- Snake_case for variables, functions, and modules
- PascalCase for classes
- UPPER_CASE for constants
- Docstrings for public modules, classes, and functions
- Tests required for new functionality

## Versioning

Trackora follows [Semantic Versioning](https://semver.org/). The current version is defined in `trackora/__init__.py`.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE.md).
