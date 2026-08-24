# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os
from pathlib import Path
import platform
import tomllib


PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
APP_NAME = "DJI Gyro Fix"
with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
    APP_VERSION = tomllib.load(project_file)["project"]["version"]
BUNDLE_IDENTIFIER = "kr.dronefriends.djigyrofix"
TARGET_ARCH = os.environ.get("DJI_GYRO_FIX_ARCH", platform.machine())
CODESIGN_IDENTITY = os.environ.get("DJI_GYRO_FIX_CODESIGN_IDENTITY") or None

if TARGET_ARCH not in {"arm64", "x86_64", "universal2"}:
    raise ValueError(f"Unsupported macOS target architecture: {TARGET_ARCH}")


analysis = Analysis(
    [str(PROJECT_ROOT / "app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=TARGET_ARCH,
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=None,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    collection,
    name=f"{APP_NAME}.app",
    icon=str(PROJECT_ROOT / "packaging" / "macos" / "app_icon_1024.png"),
    bundle_identifier=BUNDLE_IDENTIFIER,
    version=APP_VERSION,
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "LSApplicationCategoryType": "public.app-category.video",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 dronefriends.kr",
    },
)
