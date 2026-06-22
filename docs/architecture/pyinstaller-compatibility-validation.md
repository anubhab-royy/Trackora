# PyInstaller Compatibility Validation: pymongo + dnspython

## Summary

**Risk: LOW.** Both `pymongo` and `dnspython` bundle correctly with PyInstaller 6.x. No custom hooks or binary patches are required.

## Validation by Layer

### 1. pymongo (v4.17.0)

| Artifact | Status | Mechanism |
|----------|--------|-----------|
| Pure-Python modules | ✅ Discovered via static analysis | Standard `import` statements in our code (`from pymongo import MongoClient`) are visible to PyInstaller's `Analysis` phase |
| C extension (`_cmessage.*.so`) | ✅ Collected automatically | `.so` files are detected by `Analysis` as binaries and included in `a.binaries` |
| Dynamic `importlib` usage | ✅ None found | pymongo 4.17.0 uses only `importlib.metadata` (stdlib) — no `import_module()` or `__import__()` calls |

### 2. dnspython (v2.8.0)

| Artifact | Status | Mechanism |
|----------|--------|-----------|
| Pure-Python modules | ✅ Discovered as dependency | pymongo imports `dns` internally for SRV URI resolution; transitive dependencies are scanned |
| Dynamic `dns.rdtypes.*` loading | ✅ Handled by existing hook | `hook-dns.rdata.py` exists in `_pyinstaller_hooks_contrib/stdhooks/` and calls `collect_submodules('dns.rdtypes')` to gather all dynamically-loaded rdtype modules |
| Dynamic `dns.rdtypes.ANY.*` loading | ✅ Handled by existing hook | Same hook collects the `ANY` sub-package |

### 3. SSL / TLS

| Concern | Status | Notes |
|---------|--------|-------|
| Python `ssl` module | ✅ Stdlib — always included | PyInstaller bundles all stdlib modules unless explicitly excluded |
| `certifi` / CA bundle | ✅ Transitive dependency | pymongo uses system CA store; `certifi` is an optional extra, not a hard dependency |

## Required .spec Changes

Add two entries to the `hiddenimports` list in `Trackora.spec`:

```python
hiddenimports=[
    ...
    "pymongo",        # ensure top-level package is collected
    "dns",            # ensure top-level package is collected
]
```

These are **defensive** — PyInstaller would likely discover both packages via static analysis since our code directly imports them. Adding them explicitly prevents edge cases where indirect imports through `__init__.py` re-exports are missed in a `--onefile` build.

**No other .spec changes are required.** The existing `hook-dns.rdata.py` is activated automatically by PyInstaller when it encounters `import dns`.

## Not Required

- ❌ Custom hook file (`hook-pymongo.py`) — pymongo has no hidden imports
- ❌ Binary path collection — C extensions are auto-discovered
- ❌ Data file collection — pymongo/dnspython have no runtime data files
- ❌ Runtime hooks — no need to customize bootloader behavior
- ❌ Excluding unused C extension variants — PyInstaller only collects the `.so` matching the build Python version

## Build Verification

After implementation, validate with:

```bash
pyinstaller Trackora.spec --clean --noconfirm 2>&1 | tail -20
# Then run the built binary:
./dist/Trackora/Trackora --help
# If MongoDB is available, test a real connection:
MONGODB_URI="mongodb://localhost:27017/trackora_support" ./dist/Trackora/Trackora
```

Expected outcomes:
- Build succeeds without warnings about missing pymongo/dns modules
- Binary starts and reports "MongoDB reporting: connected" or "not available" based on environment
- No `ImportError` or `ModuleNotFoundError` at startup

## References

- PyInstaller `hook-dns.rdata.py`: `.venv/lib/python3.12/site-packages/_pyinstaller_hooks_contrib/stdhooks/hook-dns.rdata.py`
- PyInstaller hidden imports docs: https://pyinstaller.org/en/stable/when-things-go-wrong.html#listing-hidden-imports
- PyInstaller hooks docs: https://pyinstaller.org/en/stable/hooks.html
