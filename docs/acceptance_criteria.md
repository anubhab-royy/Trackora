# GameTracker Acceptance Criteria

Version: 1.0

## AC-001: Add Game

Given:

User opens Game Management

When:

User selects a valid executable

Then:

* Game is added to database
* Process name is detected
* Game appears in game list
* No duplicate game is created

Pass Condition:

Game visible after application restart.

---

## AC-002: Track Game Session

Given:

Tracked game exists

When:

User launches game

Then:

* GameTracker detects process
* Active session created
* Session start time recorded

Pass Condition:

Session visible in active_sessions.

---

## AC-003: End Game Session

Given:

Game is being tracked

When:

Game process exits

Then:

* Session closes
* Duration calculated
* Session saved

Pass Condition:

Session appears in session history.

---

## AC-004: Lifetime Statistics

Given:

Sessions exist

When:

User opens dashboard

Then:

Lifetime playtime equals sum of all sessions.

Pass Condition:

Value matches database calculations.

---

## AC-005: Daily Statistics

Given:

Today's sessions exist

When:

Dashboard loads

Then:

Today's playtime displayed correctly.

Pass Condition:

Matches database records.

---

## AC-006: Weekly Statistics

Given:

Current week contains sessions

Then:

Weekly totals and averages are correct.

---

## AC-007: Monthly Statistics

Given:

Current month contains sessions

Then:

Monthly totals and averages are correct.

---

## AC-008: Crash Recovery

Given:

GameTracker terminates unexpectedly

When:

Application restarts

Then:

* Active session recovered
* No session data lost

Pass Condition:

Recovered session duration reasonable.

---

## AC-009: CSV Export

When:

User exports CSV

Then:

* File created
* Sessions included
* Format valid

Pass Condition:

CSV opens correctly in Excel.

---

## AC-010: JSON Backup

When:

User creates backup

Then:

Backup file contains:

* Games
* Sessions
* Settings

Pass Condition:

Backup can be restored.

---

## AC-011: Start With Windows

Given:

Option enabled

When:

User logs into Windows

Then:

GameTracker launches automatically.

Pass Condition:

Tray icon appears.

---

## AC-012: System Tray

When:

Main window closed

Then:

Application minimizes to tray.

Pass Condition:

Tracking continues.

---

## AC-013: Dark Mode

When:

User enables dark mode

Then:

Entire UI switches theme.

Pass Condition:

Theme persists after restart.

---

## AC-014: Performance

Idle State:

CPU < 1%

Memory < 100 MB

Pass Condition:

Measured during testing.

---

## AC-015: Release Readiness

All tests pass.

No critical bugs.

Installer builds successfully.

Application starts successfully.