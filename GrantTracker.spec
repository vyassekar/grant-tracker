# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the desktop-packaged app (see desktop.py). Builds a
onedir bundle on every platform; on macOS that onedir is additionally wrapped in a
.app via BUNDLE. On Windows, the resulting dist/GrantTracker/ folder (containing
GrantTracker.exe) is the distributable -- zip it or wrap it with an installer
(Inno Setup/NSIS) as a later step, not handled here.

Run from the repo root: pyinstaller GrantTracker.spec
(add --noconfirm to skip the overwrite prompt on rebuilds).
"""
import sys

block_cipher = None

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("schema.sql", "."),
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GrantTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # no terminal window -- this is a GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GrantTracker",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="GrantTracker.app",
        icon=None,
        bundle_identifier="edu.cmu.granttracker",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "1.0.0",
        },
    )
