"""Build an isolated PLUMA backend bundle without cleaning the checkout.

This legacy builder produces a backend-only bundle. It is not the unified,
signed Core + WinUI release required by P28.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT_DIR / "output"
PRODUCT_SCOPE = (
    "PLUMA backend-only bundle. This artifact does not contain the WinUI shell, "
    "a complete offline dependency set, or a release signature. It is not a "
    "P28-complete production release.\n"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_environment(output_dir: Path) -> dict[str, str]:
    temp_dir = output_dir / "temporary"
    cache_dir = output_dir / "pip-cache"
    pyinstaller_config_dir = output_dir / "pyinstaller-config"
    temp_dir.mkdir(exist_ok=True)
    cache_dir.mkdir(exist_ok=True)
    pyinstaller_config_dir.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "PIP_CACHE_DIR": str(cache_dir),
            "PYINSTALLER_CONFIG_DIR": str(pyinstaller_config_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return environment


def _new_output_dir(requested: Path | None) -> Path:
    if requested is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        candidate = OUTPUT_ROOT / f"release-backend-{stamp}"
    else:
        candidate = requested
        if not candidate.is_absolute():
            candidate = ROOT_DIR / candidate

    candidate = candidate.resolve()
    try:
        candidate.relative_to(ROOT_DIR)
    except ValueError as exc:
        raise ValueError("Release output must remain inside the PLUMA checkout.") from exc
    if candidate == ROOT_DIR or candidate.exists():
        raise FileExistsError(f"Refusing to reuse existing release output: {candidate}")
    candidate.mkdir(parents=True)
    return candidate


def build_wheel(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    output_dir = destination.parent
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(destination),
            str(ROOT_DIR),
        ],
        cwd=ROOT_DIR,
        env=_build_environment(output_dir),
        check=True,
    )
    wheels = sorted(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected exactly one wheel in {destination}; found {len(wheels)}.")
    return wheels[0]


def build_executable(output_dir: Path) -> Path:
    work_dir = output_dir / "pyinstaller-work"
    dist_dir = output_dir / "executable"
    work_dir.mkdir()
    dist_dir.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--workpath",
            str(work_dir),
            "--distpath",
            str(dist_dir),
            str(ROOT_DIR / "pluma.spec"),
        ],
        cwd=ROOT_DIR,
        env=_build_environment(output_dir),
        check=True,
    )
    exe_path = dist_dir / "pluma.exe"
    if not exe_path.is_file():
        raise RuntimeError(f"Expected backend executable was not produced: {exe_path}")
    return exe_path


def _release_files(wheel_path: Path, exe_path: Path, output_dir: Path) -> dict[str, Path]:
    scope_path = output_dir / "PRODUCT_SCOPE.txt"
    scope_path.write_text(PRODUCT_SCOPE, encoding="utf-8", newline="\n")
    files: dict[str, Path] = {
        f"packages/{wheel_path.name}": wheel_path,
        "pluma.exe": exe_path,
        "PRODUCT_SCOPE.txt": scope_path,
    }
    fixed_paths = (
        "install.ps1",
        "uninstall.ps1",
        "README.md",
        "pyproject.toml",
        "pluma.spec",
        "pluma/config/defaults.yaml",
        "pluma/config/tool_policy.yaml",
    )
    for relative in fixed_paths:
        source = ROOT_DIR / relative
        if not source.is_file():
            raise FileNotFoundError(f"Required release input is missing: {source}")
        files[relative] = source
    return files


def create_release_zip(wheel_path: Path, exe_path: Path, output_dir: Path) -> Path:
    archive_path = output_dir / "pluma-backend-only-windows-x64.zip"
    files = _release_files(wheel_path, exe_path, output_dir)
    manifest = "".join(f"{_sha256_file(source)}  {name}\n" for name, source in sorted(files.items()))
    (output_dir / "SHA256SUMS.txt").write_text(manifest, encoding="utf-8", newline="\n")
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, source in sorted(files.items()):
            archive.write(source, arcname=name)
        archive.writestr("SHA256SUMS.txt", manifest.encode("utf-8"))
    return archive_path


def verify_zip_cleanliness(archive_path: Path) -> None:
    forbidden_segments = {".git", "__pycache__", ".pytest_cache", "bin", "obj"}
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Release archive contains duplicate paths.")
        for name in names:
            parts = Path(name).parts
            if Path(name).is_absolute() or ".." in parts or forbidden_segments.intersection(parts):
                raise ValueError(f"Release archive contains an unsafe or generated path: {name}")
            if name.endswith(".pyc"):
                raise ValueError(f"Release archive contains bytecode: {name}")

        try:
            manifest_bytes = archive.read("SHA256SUMS.txt")
        except KeyError as exc:
            raise ValueError("Release archive is missing its integrity manifest.") from exc
        expected: dict[str, str] = {}
        for line in manifest_bytes.decode("utf-8").splitlines():
            digest, separator, name = line.partition("  ")
            if not separator or len(digest) != 64 or name in expected:
                raise ValueError("Release integrity manifest is malformed.")
            expected[name] = digest
        actual_names = set(names) - {"SHA256SUMS.txt"}
        if set(expected) != actual_names:
            raise ValueError("Release integrity manifest does not cover the archive contents.")
        for name, digest in expected.items():
            member_digest = hashlib.sha256()
            with archive.open(name, "r") as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b""):
                    member_digest.update(chunk)
            if member_digest.hexdigest() != digest:
                raise ValueError(f"Release integrity check failed for {name}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="new, unused output directory under the PLUMA checkout (default: ignored output/)",
    )
    args = parser.parse_args()

    output_dir = _new_output_dir(args.output_dir)
    wheel_path = build_wheel(output_dir / "packages")
    exe_path = build_executable(output_dir)
    archive_path = create_release_zip(wheel_path, exe_path, output_dir)
    verify_zip_cleanliness(archive_path)
    print(f"Backend-only bundle created: {archive_path}")
    print("This is not the signed, unified Core + WinUI P28 release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
