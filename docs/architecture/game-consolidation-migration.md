# Game Consolidation — Migration Report

## Date
2026-06-21

## Summary
Merged eFootball (legacy ID=1) into eFootball™ (steam-discovered ID=10). Valorant (ID=2→12) deferred for manual review.

## Merge Performed

### eFootball (ID=1 → ID=10)

| Operation | Details |
|-----------|---------|
| **Confidence** | HIGH — same normalized name, same Steam app folder |
| **Sessions moved** | 8 sessions (64621 seconds / 17.95 hours) |
| **Active sessions moved** | 0 (none existed on legacy) |
| **Statistics cache moved** | 0 (cache was empty) |
| **Surviving record updated** | process_name → `eFootball.exe`, executable_path → legacy binary (`.../eFootball/Binaries/Win64/eFootball.exe`), first_played preserved, last_played preserved, platform/ID stays `steam`/`1665460` |
| **Legacy record** | Deleted (ID=1) |

### SQL Logic
```sql
-- Step 1: Move sessions
UPDATE sessions SET game_id = 10 WHERE game_id = 1;

-- Step 2: Update surviving record with legacy metadata
UPDATE games
SET process_name = 'eFootball.exe',
    executable_path = 'E:/.../eFootball.exe',
    first_played = CASE WHEN ? IS NOT NULL AND (? < first_played) THEN ? ELSE first_played END,
    last_played = CASE WHEN ? IS NOT NULL AND (? > last_played) THEN ? ELSE last_played END,
    updated_at = ?
WHERE id = 10;

-- Step 3: Delete legacy
DELETE FROM games WHERE id = 1;
```

### Valorant (ID=2 → ID=12) — DEFERRED, Manual Review Required

| Item | Detail |
|------|--------|
| **Reason** | Suspicious process_name `Trackora.exe` |
| **Sessions at risk** | 3 sessions, 9908s (2.75h) — may be Trackora uptime, not Valorant |
| **Active session** | ID=15 with process_id=2924 — needs cleanup |
| **Recommendation** | Fix process_name to `VALORANT.exe`, executable to Riot path, verify sessions are real, then delete legacy record |

## Future Protection (Phase F)

Added to `GameService.import_discovered_games()` in `services/game_service.py`:

1. **Normalized name check**: Before creating a new discovered game, legacy games (empty `platform`) with matching normalized names are **updated** with discovered platform info instead of creating a separate record.
2. **Normalization function**: `_normalize_name()` strips trademark symbols (™, ®, ©) and lowercases.
3. **Existing checks preserved**: executable_path and (platform, platform_id) checks still run first.

This prevents duplicates like eFootball/eFootball™ from recurring in future scans.

### Normalization Logic
```python
@staticmethod
def _normalize_name(name: str) -> str:
    return (
        name.replace("\u2122", "")
        .replace("\u00AE", "")
        .replace("\u00A9", "")
        .strip()
        .lower()
    )
```

### Legacy Match Detection
```python
def _find_legacy_by_normalized_name(self, name, existing_games):
    norm = self._normalize_name(name)
    for game in existing_games:
        if not game.platform and self._normalize_name(game.name) == norm:
            return game
    return None
```

### Duplicate Prevention Priority (per candidate)
1. Skip if `executable_path` exists in any game
2. Skip if `(platform, platform_id)` exists in any game
3. If legacy game (empty platform) matches by `_normalize_name()` — **update legacy** with discovered info
4. Otherwise — create new game
