# Trackora UI Specification

Version: 1.1

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
4. Charts
5. Settings
6. Support Center

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

# Support Center Screen

Purpose:

Central hub for user support interactions.

## Navigation

Internal tabs (top bar):

1. Report Bug
2. Suggest Feature
3. General Feedback
4. Upcoming Updates

Form submission implemented via GitHub Issues REST API.

Each form page has a Submit button. On submit:
1. Form data is validated (title/description required).
2. BugReport / FeatureRequest / FeedbackReport model is created.
3. Report is stored locally.
4. If GitHub is configured, report is submitted as a GitHub Issue.
5. Result is shown inline (green for success, red for error).
6. GitHub submission errors are user-friendly (auth, rate limit, not found).

---

## Report Bug Page

Fields:

* Title
* Description
* Steps to Reproduce
* Expected Behavior
* Actual Behavior
* Severity (low / medium / high / critical)

---

## Suggest Feature Page

Fields:

* Title
* Description
* Use Case
* Priority (low / medium / high)

---

## General Feedback Page

Fields:

* Subject
* Message
* Category (general / praise / complaint)
* Contact Permission (checkbox)

---

## Upcoming Updates Page

Displays:

* Feature title
* Description
* Version number
* Published status

Data sourced from SupportService (static roadmap, no GitHub integration yet).

---

# Error Messages

Requirements:

* Clear
* Human readable
* Actionable

Never display raw Python exceptions.