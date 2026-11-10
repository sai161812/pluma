"""Build an isolated PLUMA Core + WinUI package candidate without cleaning the checkout."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import secrets
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT_DIR / "output"
PRODUCT_SCOPE = (
    "PLUMA Core + WinUI x64 package candidate. It includes the Python Core wheel "
    "and resolved Windows runtime wheels, plus a self-contained WinUI publish. "
    "Local inference/OCR models are intentionally external. The archive and its "
    "executables are not release-signed; this candidate is not a P28-complete "
    "production release until authorized signing and exact-build acceptance pass.\n"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_environment(output_dir: Path) -> dict[str, str]:
    temp_dir = output_dir / "temporary"
    temp_dir.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "DOTNET_CLI_HOME": str(output_dir / "dotnet-cli-home"),
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "NUGET_PACKAGES": str(output_dir / "nuget-packages"),
        }
    )
    return environment


def _new_output_dir(requested: Path | None) -> Path:
    if requested is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        candidate = OUTPUT_ROOT / f"release-{stamp}-{secrets.token_hex(4)}"
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


def build_wheelhouse(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    output_dir = destination.parent
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--only-binary=:all:",
            "--no-cache-dir",
            "--index-url",
            "https://pypi.org/simple",
            "--wheel-dir",
            str(destination),
            f"{ROOT_DIR}[windows,media,stt,ocr]",
        ],
        cwd=ROOT_DIR,
        env=_build_environment(output_dir),
        check=True,
    )
    wheels = sorted(destination.glob("*.whl"))
    core_wheels = [path for path in wheels if path.name.lower().startswith("pluma-")]
    if not wheels or len(core_wheels) != 1:
        raise RuntimeError(
            f"Expected a complete wheelhouse with exactly one PLUMA wheel in {destination}; "
            f"found {len(wheels)} wheels and {len(core_wheels)} PLUMA wheels."
        )
    return core_wheels[0]


def build_ui(output_dir: Path) -> Path:
    project = ROOT_DIR / "PLUMA.UI" / "PLUMA.UI" / "PLUMA.UI.csproj"
    publish_dir = output_dir / "ui-publish"
    intermediate_dir = output_dir / "ui-intermediate"
    lock_path = output_dir / "ui-packages.lock.json"
    publish_dir.mkdir()
    intermediate_dir.mkdir()
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise FileNotFoundError("The .NET SDK is required to publish the PLUMA WinUI shell.")
    shared_properties = [
        "-m:1",
        f"-p:BaseIntermediateOutputPath={intermediate_dir}",
        f"-p:NuGetLockFilePath={lock_path}",
        "-p:RestorePackagesWithLockFile=true",
        "-p:WindowsPackageType=None",
        "-p:WindowsAppSDKSelfContained=true",
        "-p:UseSharedCompilation=false",
        "-p:BuildInParallel=false",
        "-p:ContinuousIntegrationBuild=true",
    ]
    subprocess.run(
        [
            dotnet,
            "restore",
            str(project),
            "--runtime", "win-x64",
            "--source", "https://api.nuget.org/v3/index.json",
            "--packages", str(output_dir / "nuget-packages"),
            *shared_properties,
        ],
        cwd=ROOT_DIR,
        env=_build_environment(output_dir),
        check=True,
    )
    subprocess.run(
        [
            dotnet,
            "publish",
            str(project),
            "--configuration", "Release",
            "--runtime", "win-x64",
            "--self-contained", "true",
            "--output", str(publish_dir),
            "--no-restore",
            "-p:PublishSingleFile=false",
            "-p:PublishTrimmed=false",
            "-p:PublishReadyToRun=false",
            *shared_properties,
        ],
        cwd=ROOT_DIR,
        env=_build_environment(output_dir),
        check=True,
    )
    executable = publish_dir / "PLUMA.UI.exe"
    if not executable.is_file():
        raise RuntimeError(f"WinUI publish did not produce the expected executable: {executable}")
    if not lock_path.is_file():
        raise RuntimeError("WinUI restore did not produce the isolated NuGet lock file.")
    return publish_dir


def _release_files(
    wheelhouse: Path, ui_dir: Path, output_dir: Path
) -> dict[str, Path]:
    scope_path = output_dir / "PRODUCT_SCOPE.txt"
    scope_path.write_text(PRODUCT_SCOPE, encoding="utf-8", newline="\n")
    files: dict[str, Path] = {
        "PRODUCT_SCOPE.txt": scope_path,
    }
    for wheel in sorted(wheelhouse.glob("*.whl")):
        files[f"packages/{wheel.name}"] = wheel
    if not any(Path(name).name.lower().startswith("pluma-") for name in files if name.startswith("packages/")):
        raise FileNotFoundError("The complete wheelhouse does not contain the PLUMA Core wheel.")
    python_lock = output_dir / "python-wheelhouse.lock.txt"
    python_wheels = sorted(wheelhouse.glob("*.whl"))
    python_lock.write_text(
        "".join(f"{_sha256_file(wheel)}  {wheel.name}\n" for wheel in python_wheels),
        encoding="utf-8",
        newline="\n",
    )
    files["build-inputs/python-wheelhouse.lock.txt"] = python_lock
    ui_executable = ui_dir / "PLUMA.UI.exe"
    if not ui_executable.is_file():
        raise FileNotFoundError(f"Required WinUI executable is missing: {ui_executable}")
    for source in sorted(path for path in ui_dir.rglob("*") if path.is_file()):
        files[f"ui/{source.relative_to(ui_dir).as_posix()}"] = source
    lock_path = output_dir / "ui-packages.lock.json"
    if not lock_path.is_file():
        raise FileNotFoundError(f"Retained NuGet package lock is missing: {lock_path}")
    files["build-inputs/ui-packages.lock.json"] = lock_path
    nuget_cache = output_dir / "nuget-packages"
    if not nuget_cache.is_dir():
        raise FileNotFoundError("Isolated NuGet package cache is missing.")
    nuget_packages = sorted(path for path in nuget_cache.glob("*/*/*.nupkg") if path.is_file())
    if not nuget_packages:
        raise FileNotFoundError("No retained NuGet packages were produced for the WinUI build.")
    for source in nuget_packages:
        files[f"build-inputs/nuget/{source.name}"] = source
    fixed_paths = (
        "install.ps1",
        "uninstall.ps1",
        "README.md",
        "pyproject.toml",
        "pluma/config/defaults.yaml",
        "pluma/config/tool_policy.yaml",
    )
    for relative in fixed_paths:
        source = ROOT_DIR / relative
        if not source.is_file():
            raise FileNotFoundError(f"Required release input is missing: {source}")
        files[relative] = source
    return files


def create_release_zip(wheelhouse: Path, ui_dir: Path, output_dir: Path) -> Path:
    archive_path = output_dir / "pluma-core-winui-windows-x64-candidate.zip"
    files = _release_files(wheelhouse, ui_dir, output_dir)
    manifest = "".join(f"{_sha256_file(source)}  {name}\n" for name, source in sorted(files.items()))
    (output_dir / "SHA256SUMS.txt").write_text(manifest, encoding="utf-8", newline="\n")
    # The wheel/NuGet packages and published binaries are already compressed or
    # incompressible. Store them directly to avoid a CPU-heavy second compression.
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_STORED) as archive:
        for name, source in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            with source.open("rb") as input_file, archive.open(info, "w") as output_file:
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        info = zipfile.ZipInfo("SHA256SUMS.txt", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, manifest.encode("utf-8"))
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

    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("The PLUMA x64 Windows release candidate must be built on Windows x64.")
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or newer is required for the declared runtime dependencies.")

    output_dir = _new_output_dir(args.output_dir)
    wheelhouse = output_dir / "packages"
    build_wheelhouse(wheelhouse)
    ui_dir = build_ui(output_dir)
    archive_path = create_release_zip(wheelhouse, ui_dir, output_dir)
    verify_zip_cleanliness(archive_path)
    print(f"Core + WinUI package candidate created: {archive_path}")
    print("This candidate is unsigned and is not a P28-complete production release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
