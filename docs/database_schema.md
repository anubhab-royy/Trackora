# GameTracker Database Schema

Version: 1.0

Database Engine: SQLite

---

# Design Principles

* Local-first
* Fast queries
* Reliable recovery
* Future scalability
* Human-readable structure

---

# Table: games

Stores all tracked games.

| Field           | Type                |
| --------------- | ------------------- |
| id              | INTEGER PRIMARY KEY |
| name            | TEXT                |
| process_name    | TEXT                |
| executable_path | TEXT                |
| icon_path       | TEXT                |
| is_enabled      | INTEGER             |
| first_played    | DATETIME            |
| last_played     | DATETIME            |
| created_at      | DATETIME            |
| updated_at      | DATETIME            |

---

# Table: sessions

Stores all completed gaming sessions.

| Field            | Type                |
| ---------------- | ------------------- |
| id               | INTEGER PRIMARY KEY |
| game_id          | INTEGER             |
| start_time       | DATETIME            |
| end_time         | DATETIME            |
| duration_seconds | INTEGER             |
| created_at       | DATETIME            |

Foreign Key:

sessions.game_id → games.id

---

# Table: active_sessions

Stores currently running sessions.

Purpose:

Crash recovery and shutdown recovery.

| Field      | Type                |
| ---------- | ------------------- |
| id         | INTEGER PRIMARY KEY |
| game_id    | INTEGER             |
| process_id | INTEGER             |
| start_time | DATETIME            |
| created_at | DATETIME            |

---

# Table: settings

Application settings.

| Field      | Type             |
| ---------- | ---------------- |
| key        | TEXT PRIMARY KEY |
| value      | TEXT             |
| updated_at | DATETIME         |

Examples:

* dark_mode
* start_with_windows
* backup_enabled

---

# Table: statistics_cache

Optional future optimization.

| Field         | Type                |
| ------------- | ------------------- |
| id            | INTEGER PRIMARY KEY |
| game_id       | INTEGER             |
| period_type   | TEXT                |
| period_key    | TEXT                |
| value_seconds | INTEGER             |

Examples:

* daily
* weekly
* monthly

---

# Future Tables

Version 2.0

* goals
* reports
* achievements
* cloud_sync
* tags

---

# Indexes

games.process_name

sessions.game_id

sessions.start_time

sessions.end_time

active_sessions.game_id

---

# Data Retention

Default:

Unlimited

All session history remains unless deleted by user.

---

# Backup Strategy

Manual Export:

* CSV
* JSON

Future:

* Automatic backup
* Cloud backup