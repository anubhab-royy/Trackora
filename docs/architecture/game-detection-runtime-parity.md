# Game Detection Runtime Parity

## Parity Matrix

```
Platform             Source Runtime Count    Executable Count    Difference
──────               ─────────────────────    ───────────────    ──────────
Steam                2                       2                   0
Epic                 0                       0                   0
Riot                 1                       1                   0
Ubisoft              0                       0                   0
EA                   0                       0                   0
Battle.net           0                       0                   0
Folder               0                       0                   0
──────────────────────────────────────────────────────────────────────────
Total                3                       3                   0
```

## Validation Method

1. Run `python -m trackora` via diagnostic script → dump results to JSON
2. Build `Trackora.exe` via `pyinstaller Trackora.spec`
3. Run `Trackora.exe --discovery-diagnostic` → dump results to JSON
4. Compare `total`, `platforms`, `games`, `errors` across both outputs
5. Repeat executable test 3 times to verify consistency

## Frozen Runtime Compatibility

All `tracker/discovery/` modules were audited for PyInstaller frozen-runtime compatibility:

| Check | Result |
|-------|--------|
| `__file__` usage | None found ✅ |
| `sys.frozen` / `sys._MEIPASS` | None found ✅ |
| Relative paths | None found ✅ |
| `winreg` import | Local import in `steam_detector.py` — works ✅ |
| `sqlite3` import | Module-level import in `battlenet_detector.py` — hook processes it ✅ |
| C extension modules | `_sqlite3` handled by PyInstaller hook ✅ |
| `os.scandir` / `Path` | Works in frozen mode ✅ |

## Packaging Verification

- `Trackora.spec` hidden imports include `tracker.discovery` and `tracker.discovery.detectors`
- No discovery-related modules excluded
- External launcher metadata files read from system paths (not bundled)
- `hook-sqlite3.py` standard hook processes `sqlite3` module
- Only warning: `pyqtgraph.opengl` missing `OpenGL` (unrelated to discovery)

## Conclusion

**Full parity confirmed.** No executable-specific issues, no hidden imports failures, no frozen path problems, no registry access regressions. Discovery behavior in `Trackora.exe` is identical to `python -m trackora`.
