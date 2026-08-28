"""build_release.py — Clean release artifact builder for PLUMA.

Spec §25: Build clean wheel package and release distribution ZIP with 0 build/cache artifacts.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).parent.resolve()
DIST_DIR = ROOT_DIR / "dist"
RELEASE_DIR = ROOT_DIR / "release"


def clean_artifacts() -> None:
    """Clean all Python caches and previous build artifacts."""
    print("[1/4] Cleaning build artifacts and __pycache__ trees...")
    for pattern in ["build", "dist", "release", "*.egg-info", ".pytest_cache"]:
        for p in ROOT_DIR.glob(pattern):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                p.unlink(missing_ok=True)

    for p in ROOT_DIR.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

    for p in ROOT_DIR.rglob("*.pyc"):
        p.unlink(missing_ok=True)


def build_wheel() -> Path:
    """Build Python wheel package."""
    print("[2/4] Building clean Python wheel package...")
    res = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(DIST_DIR), str(ROOT_DIR)],
        capture_output=True,
        text=True,
        check=True,
    )
    wheels = list(DIST_DIR.glob("*.whl"))
    if not wheels:
        raise RuntimeError(f"No wheel produced in {DIST_DIR}")
    print(f"  -> Built wheel: {wheels[0].name}")
    return wheels[0]


def create_release_zip(wheel_path: Path) -> Path:
    """Create a pristine release ZIP containing the wheel, installer scripts, configs, docs, and SHA-256 manifest."""
    print("[3/4] Packaging pristine release ZIP archive...")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RELEASE_DIR / "pluma-0.1.0-windows-x64-release.zip"

    # Compute wheel SHA-256
    import hashlib
    def hash_file(p: Path) -> str:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
        
    # Build EXE with PyInstaller
    print("[3/5] Building EXE with PyInstaller...")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "pluma.spec"], check=True)
    exe_path = ROOT_DIR / "dist" / "pluma.exe"
    if not exe_path.exists():
        raise RuntimeError("pluma.exe was not built!")

    print("[4/5] Packaging pristine release ZIP archive...")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RELEASE_DIR / "pluma-0.1.0-windows-x64-release.zip"

    manifest_lines = [
        f"{hash_file(wheel_path)}  packages/{wheel_path.name}",
        f"{hash_file(exe_path)}  pluma.exe",
    ]

    manifest_path = RELEASE_DIR / "SHA256SUMS.txt"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(manifest_lines) + "\n")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include wheel and exe
        zf.write(wheel_path, arcname=f"packages/{wheel_path.name}")
        zf.write(exe_path, arcname="pluma.exe")
        
        # Include install and uninstall scripts
        for script_name in ["install.ps1", "uninstall.ps1"]:
            script_path = ROOT_DIR / script_name
            if script_path.exists():
                zf.write(script_path, arcname=script_name)

        # Include configs
        cfg_dir = ROOT_DIR / "pluma" / "config"
        for cfg in ["defaults.yaml", "tool_policy.yaml"]:
            cp = cfg_dir / cfg
            if cp.exists():
                zf.write(cp, arcname=f"config/{cfg}")

        # Include documentation and manifest
        for doc_name in ["README.md", "pyproject.toml", "PHASE_13_5_COMPLETION_REPORT.md", "pluma.spec"]:
            doc_path = ROOT_DIR / doc_name
            if doc_path.exists():
                zf.write(doc_path, arcname=doc_name)

        zf.write(manifest_path, arcname="SHA256SUMS.txt")

    print(f"  -> Pristine release archive created: {zip_path.name} ({zip_path.stat().st_size / 1024:.1f} KB)")
    return zip_path



def verify_zip_cleanliness(zip_path: Path) -> None:
    """Verify that the release ZIP contains ZERO cache, git, or compiler artifacts."""
    print("[4/4] Verifying release archive cleanliness...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        entries = zf.namelist()
        forbidden = [e for e in entries if any(bad in e for bad in ["__pycache__", ".git", ".pytest_cache", ".pyc"])]
        if forbidden:
            raise ValueError(f"Found forbidden cache artifacts in release ZIP: {forbidden}")
        print(f"  -> Verified: {len(entries)} clean production files, 0 cache artifacts.")


def main() -> None:
    clean_artifacts()
    wheel_path = build_wheel()
    zip_path = create_release_zip(wheel_path)
    verify_zip_cleanliness(zip_path)
    print("\nRELEASE BUILD COMPLETED SUCCESSFULLY.")


if __name__ == "__main__":
    main()
