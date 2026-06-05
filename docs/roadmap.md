# GameTracker Architecture

Version: 1.0

---

# System Overview

GameTracker consists of five major layers:

1. Tracking Layer
2. Database Layer
3. Statistics Layer
4. UI Layer
5. System Services Layer

---

# High-Level Architecture

Windows OS

↓

Process Detection Service

↓

Session Manager

↓

SQLite Database

↓

Statistics Engine

↓

Dashboard UI

↓

User

---

# Tracking Layer

Responsibility:

Detect gaming activity.

Modules:

tracker/process_monitor.py

tracker/session_manager.py

Functions:

* Detect process start
* Detect process stop
* Track active sessions
* Handle crash recovery

Dependencies:

* psutil

---

# Database Layer

Responsibility:

Persist all data.

Modules:

database/database_manager.py

database/repositories/

Functions:

* Store games
* Store sessions
* Store settings
* Recovery state

Dependencies:

* SQLite

---

# Statistics Layer

Responsibility:

Generate analytics.

Modules:

statistics/statistics_service.py

Functions:

* Lifetime statistics
* Daily statistics
* Weekly statistics
* Monthly statistics
* Session counts
* Trends

---

# UI Layer

Responsibility:

User interaction.

Framework:

PyQt6

Modules:

ui/dashboard/

ui/settings/

ui/history/

ui/games/

Features:

* Dashboard
* Charts
* History
* Settings
* Game Management

---

# System Services Layer

Modules:

services/tray_service.py

services/startup_service.py

services/export_service.py

Responsibilities:

* System tray
* Windows startup
* Data export
* Notifications

---

# Error Handling

Every module writes logs.

logs/

yyyy-mm-dd.log

Log Levels:

* INFO
* WARNING
* ERROR

---

# Recovery Strategy

Application Crash

↓

Read active_sessions

↓

Restore tracking state

↓

Continue monitoring

---

# Performance Targets

CPU Usage:

< 1%

Memory Usage:

< 100 MB

Startup Time:

< 3 Seconds

Database Response:

< 50 ms

---

# Security Model

* No user account required
* No mandatory cloud storage
* Local-only by default
* User-controlled exports