# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller packaging specification for PLUMA.

Spec §20, §25:
- Packages the resident core, Win32 adapters, database migrations, and config defaults.
- Models and SQLite databases reside outside the binary (%LOCALAPPDATA%\Pluma\).
- Zero ML workers bundled as startup services.
"""

from pathlib import Path
import sys

block_cipher = None

repo_root = Path.cwd()

datas = [
    (str(repo_root / "pluma" / "config" / "defaults.yaml"), "pluma/config"),
    (str(repo_root / "pluma" / "config" / "tool_policy.yaml"), "pluma/config"),
    (str(repo_root / "pluma" / "memory" / "migrations"), "pluma/memory/migrations"),
]

hiddenimports = [
    "pluma.adapters.win32",
    "pluma.adapters.powershell",
    "pluma.adapters.input",
    "pluma.adapters.uia",
    "pluma.adapters.screen",
    "pluma.tools.apps",
    "pluma.tools.files",
    "pluma.tools.windows",
    "pluma.tools.processes",
    "pluma.tools.audio",
    "pluma.tools.system",
    "pluma.tools.clipboard",
    "pluma.tools.ui",
    "pluma.policy.engine",
    "pluma.policy.rules",
    "pluma.policy.elevation_broker",
    "pluma.ui.confirmations",
]

a = Analysis(
    [str(repo_root / "pluma" / "app.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "transformers",
        "scipy",
        "matplotlib",
        "IPython",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="pluma",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Resident background process
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
