# GameTracker UI Specification

Version: 1.0

## Design Philosophy

The interface should feel:

* Clean
* Fast
* Lightweight
* Professional

Inspired by:

* Windows 11
* Discord settings layout
* Steam statistics pages

No flashy animations.

No unnecessary visual effects.

---

# Main Navigation

Sections:

1. Dashboard
2. Games
3. History
4. Settings

Navigation:

Left Sidebar

---

# Dashboard Screen

Purpose:

Display important statistics immediately.

## Statistics Cards

Display:

* Total Playtime
* Today's Playtime
* Weekly Playtime
* Monthly Playtime

Each card shows:

* Value
* Label

---

## Most Played Game Section

Display:

* Game Icon
* Game Name
* Total Hours

---

## Charts Section

Charts:

* Daily Activity
* Monthly Trend
* Game Distribution

---

# Games Screen

Purpose:

Manage tracked games.

Columns:

* Icon
* Name
* Process Name
* Tracking Enabled

Actions:

* Add Game
* Edit Game
* Delete Game

---

## Add Game Dialog

Fields:

* Game Name
* Executable Path

Buttons:

* Browse
* Save
* Cancel

---

# History Screen

Purpose:

Display session history.

Columns:

* Date
* Game
* Start Time
* End Time
* Duration

Features:

* Search
* Filter
* Sort

---

# Settings Screen

Sections:

## General

* Start With Windows
* Minimize To Tray

---

## Appearance

* Dark Mode
* Light Mode

---

## Data

* Export CSV
* Export JSON
* Create Backup

---

# System Tray

Right Click Menu:

* Open Dashboard
* Pause Tracking
* Resume Tracking
* Exit

---

# Theme Requirements

Dark Theme:

Default

Light Theme:

Optional

Theme must persist after restart.

---

# Error Messages

Requirements:

* Clear
* Human readable
* Actionable

Never display raw Python exceptions.