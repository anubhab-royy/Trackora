# Game Consolidation — Discovery Audit

## Date
2026-06-21

## Inventory

| ID | Name | Platform | Platform ID | Process Name | Executable Path | Sessions | Total (s) | Status |
|----|------|----------|-------------|-------------|----------------|----------|-----------|--------|
| 1 | eFootball | *NULL* | *NULL* | eFootball.exe | `.../eFootball/Binaries/Win64/eFootball.exe` | 8 | 64621 | Legacy (manual) |
| 2 | Valorant | *NULL* | *NULL* | **Trackora.exe** | `.../dist/Trackora.exe` | 3 | 9908 | Legacy (suspicious) |
| 10 | eFootball™ | steam | 1665460 | Settings.exe | `.../eFootball/Settings.exe` | 0 | 0 | Auto-discovered |
| 11 | Wallpaper Engine | steam | 431960 | installer.exe | `.../installer.exe` | 0 | 0 | Auto-discovered |
| 12 | Valorant | riot | riot_valorant | VALORANT.exe | `.../VALORANT/live/VALORANT.exe` | 0 | 0 | Auto-discovered |

## Duplicate Candidates

### Pair 1: eFootball / eFootball™
- **Normalized name match**: `efootball`
- **Legacy ID**: 1 (name=`eFootball`, platform=NULL)
- **Discovered ID**: 10 (name=`eFootball™`, platform=`steam`, platform_id=`1665460`)
- **Sessions on legacy**: 8 (64621s = 17.95h)
- **Sessions on discovered**: 0
- **Confidence**: **HIGH** — same normalized name, same Steam app folder (`steamapps/common/eFootball/`), legacy executable is actual game binary

### Pair 2: Valorant / Valorant
- **Normalized name match**: `valorant`
- **Legacy ID**: 2 (name=`Valorant`, platform=NULL, process_name=`Trackora.exe`)
- **Discovered ID**: 12 (name=`Valorant`, platform=`riot`, platform_id=`riot_valorant`)
- **Sessions on legacy**: 3 (9908s = 2.75h)
- **Sessions on discovered**: 0
- **Confidence**: **MANUAL REVIEW REQUIRED** — legacy process_name=Trackora.exe indicates misconfiguration

## Confidence Scoring

| Level | Criteria | Action |
|-------|----------|--------|
| **High** | Same normalized name AND (same executable path OR same platform/app folder) | Auto-merge |
| **Medium** | Same normalized name, similar install folders but different executables | Manual review |
| **Low** | Only normalized name matches | Report only, no merge |

| Pair | Normalized Name | Executable Path | Platform ID | Install Folder | Confidence |
|------|----------------|----------------|-------------|----------------|------------|
| eFootball (1→10) | ✅ Match | Different (same app) | — | ✅ Same Steam app | **HIGH** |
| Valorant (2→12) | ✅ Match | Different | — | Different | **MANUAL** |

## Corruption Audit

### Suspicious Records

**ID=2 — Valorant (Legacy)**
- **Process Name**: `Trackora.exe` — this is Trackora's own executable, not Valorant
- **Executable Path**: `E:/Code&Programs/GitHub/Trackora/dist/Trackora.exe` — points to Trackora's own installer
- **Root Cause**: User (or test) manually added Trackora's own exe as a game named "Valorant"
- **Effect**: Process monitor detects Trackora.exe running and logs sessions under "Valorant"
- **Recommendation**: Do not auto-merge. Investigate whether the 3 sessions (2.75h) represent real Valorant time or Trackora uptime. If real, manually correct process_name to `VALORANT.exe` and executable to Riot path.

### Clean Records
- ID=1 (eFootball legacy): Clean — process_name matches executable basename, executable exists on disk
- ID=10 (eFootball™ discovered): Correct — proper platform, platform_id, realized executable path
- ID=11 (Wallpaper Engine): Clean — single record, no duplicate
- ID=12 (Valorant discovered): Correct — proper platform, platform_id

## Active Sessions
- **ID=15**: game_id=2 (Valorant legacy), process_id=2924, started 2026-06-21T20:12:10
- This active session is associated with the suspicious Valorant record — do not migrate

## Statistics Cache
- Table exists with columns: `id, game_id, period_type, period_key, value_seconds`
- Currently **empty** (0 rows) — no migration needed
