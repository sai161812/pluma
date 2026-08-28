# -*- mode: python ; coding: utf-8 -*-
"""pluma.spec — PyInstaller bundle specification for PLUMA standalone executable.

Spec §25: Windows startup launches only the resident core.
Zero heavy ML loaded at startup.
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
project_dir = Path(SPECPATH).resolve()

datas = [
    (str(project_dir / "pluma" / "config" / "defaults.yaml"), "pluma/config"),
    (str(project_dir / "pluma" / "config" / "tool_policy.yaml"), "pluma/config"),
    (str(project_dir / "pluma" / "memory" / "migrations" / "*.sql"), "pluma/memory/migrations"),
]

hiddenimports = [
    "pluma",
    "pluma.app",
    "pluma.core.resident",
    "pluma.core.ipc",
    "pluma.core.task_supervisor",
    "pluma.core.orchestrator",
    "pluma.core.multi_step",
    "pluma.core.ownership",
    "pluma.core.job_object",
    "pluma.tools.registry",
    "pluma.tools.apps",
    "pluma.tools.audio",
    "pluma.tools.clipboard",
    "pluma.tools.files",
    "pluma.tools.system",
    "pluma.tools.ui",
    "pluma.tools.windows",
    "pluma.policy.engine",
    "pluma.memory.activity",
    "pluma.memory.db",
    "pluma.memory.redaction",
    "pluma.rollback.engine",
    "pluma.rollback.recipes",
]

a = Analysis(
    ["pluma/app.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "scipy"],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
