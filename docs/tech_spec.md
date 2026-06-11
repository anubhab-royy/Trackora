# Trackora Technical Specification

Version: 1.0

## Purpose

This document defines the technical implementation details of Trackora Version 1.0.

This document serves as the engineering blueprint for development.

---

# Technology Stack

Language:

Python 3.13+

Frameworks:

* PyQt6
* PyQtGraph

Libraries:

* psutil
* sqlite3
* pathlib
* logging
* csv
* json

Testing:

* pytest

Packaging:

* PyInstaller

Installer:

* Inno Setup

---

# Project Structure

Trackora/

├── tracker/
├── database/
├── statistics/
├── ui/
├── services/

---

# Database Layer

## Database Engine

SQLite

Configuration:

* WAL mode enabled
* Foreign keys enabled

Database File:

database/tracker.db

---

# Repository Pattern

Every database table must have a repository.

Repositories:

* GamesRepository
* SessionsRepository
* SettingsRepository
* ActiveSessionsRepository

Rules:

* UI cannot access repositories directly.
* SQL must remain inside repositories.

---

# Tracker Layer

## Process Monitor

Responsibilities:

* Scan active Windows processes every 5 seconds.
* Detect tracked games.
* Detect process start.
* Detect process stop.

Dependencies:

* psutil

---

## Session Manager

Responsibilities:

* Create sessions.
* Close sessions.
* Calculate durations.
* Save sessions.

---

## Recovery Manager

Responsibilities:

* Restore active sessions.
* Handle crashes.
* Handle unexpected shutdowns.

---

# Statistics Layer

## Statistics Service

Must expose:

get_lifetime_stats()

get_daily_stats()

get_weekly_stats()

get_monthly_stats()

get_most_played_game()

get_longest_session()

---

## Trend Analyzer

Must provide:

* monthly change %
* weekly change %
* playtime comparisons

---

# UI Layer

Framework:

PyQt6

Pattern:

View + Controller

Rules:

* No business logic in UI.
* No SQL in UI.
* No filesystem operations in UI.

---

# Services Layer

## Tray Service

Responsibilities:

* System tray icon
* Open dashboard
* Pause tracking
* Resume tracking
* Exit

---

## Startup Service

Responsibilities:

* Windows startup registration
* Startup validation

---

## Export Service

Supported Formats:

* CSV
* JSON

---

## Logging Service

Location:

logs/

Format:

YYYY-MM-DD.log

Levels:

* INFO
* WARNING
* ERROR

---

# Performance Targets

CPU Usage:

< 1%

Memory Usage:

< 100 MB

Database Query:

< 50 ms

Startup Time:

< 3 seconds

---

# Error Handling

All errors must:

* be logged
* not crash application
* display user-friendly messages

---

# Security

Requirements:

* Local-only by default
* No telemetry
* No external network calls
* User owns all data

---

# Coding Standards

Requirements:

* Type hints required
* Dataclasses preferred
* PEP8 compliance
* pytest coverage > 80%

No exceptions.