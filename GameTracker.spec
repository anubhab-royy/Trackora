# -*- mode: python ; coding: utf-8 -*-
#
# GameTracker.spec — PyInstaller spec file (production)
#
# Build:
#     pyinstaller GameTracker.spec
#
# Output:
#     dist/GameTracker.exe
#

# Version — keep in sync with gametracker/__init__.py
version = "1.0.0"
BLOCK_CIPHER_LIST = None

a = Analysis(
    ["gametracker/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("ui/themes", "ui/themes"),
        ("ui/icons", "ui/icons"),
    ],
    hiddenimports=[
        "PyQt6.QtSvg",
        "pyqtgraph",
        "psutil",
        "database",
        "database.models",
        "database.repositories",
        "services",
        "services.update_service",
        "statistics",
        "tracker",
        "ui",
        "ui.dashboard",
        "ui.games",
        "ui.history",
        "ui.settings",
        "ui.themes",
        "ui.widgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # --- unused GUI frameworks ---
        "tkinter",
        "PyQt5",
        "PySide2",
        "PySide6",
        # --- matplotlib (large, not directly used) ---
        "matplotlib",
        "mpl_toolkits",
        # --- test / dev ---
        "test",
        "unittest",
        "distutils",
        "setuptools",
        "pip",
        "pytest",
        "_pytest",
        "tests",
        # --- unused pyqtgraph optional deps ---
        "scipy",
        "cupy",
        "h5py",
        "numba",
        "bottleneck",
        "colorcet",
        # --- other unused ---
        "tornado",
        "jinja2",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GameTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["ui/icons/app_icon.ico"],
    version="version_info.txt",
)
