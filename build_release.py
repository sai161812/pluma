"""Build an isolated PLUMA Core + WinUI package candidate without cleaning the checkout."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
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


def _verify_retained_candidate(root: Path, expected_source_commit: str) -> dict[str, Path]:
    root = root.resolve()
    manifest_path = root / "SHA256SUMS.txt"
    if not manifest_path.is_file():
        raise FileNotFoundError("Offline build inputs are missing SHA256SUMS.txt.")
    files: dict[str, Path] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([A-Za-z0-9._/+\-]+)", line)
        if match is None:
            raise ValueError("Retained package integrity manifest is malformed.")
        digest, relative_name = match.groups()
        relative = Path(relative_name)
        if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
            raise ValueError(f"Unsafe retained package path: {relative_name}")
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Retained package path escapes its root: {relative_name}") from exc
        if relative_name in files or not candidate.is_file():
            raise FileNotFoundError(f"Retained package file is missing or duplicated: {relative_name}")
        if _sha256_file(candidate).lower() != digest.lower():
            raise ValueError(f"Retained package hash mismatch: {relative_name}")
        files[relative_name] = candidate
    required = {
        "build-inputs/python-wheelhouse.lock.txt",
        "build-inputs/python-build-constraints.txt",
        "build-inputs/build-provenance.json",
        "build-inputs/ui-packages.lock.json",
        "install.ps1",
        "uninstall.ps1",
        "pyproject.toml",
    }
    missing = required - files.keys()
    if missing:
        raise FileNotFoundError("Offline package is missing retained build inputs: " + ", ".join(sorted(missing)))
    provenance = json.loads(files["build-inputs/build-provenance.json"].read_text(encoding="utf-8"))
    if (provenance.get("schema_version") != 1 or
            provenance.get("source_commit") != expected_source_commit or
            provenance.get("tracked_source_clean") is not True):
        raise ValueError("Offline inputs were not built from this exact committed PLUMA source revision.")
    if not any(name.startswith("build-inputs/nuget/") and name.endswith(".nupkg") for name in files):
        raise FileNotFoundError("Offline package is missing retained NuGet package inputs.")
    return files


def _verify_wheelhouse(root: Path, lock_path: Path) -> list[Path]:
    if not lock_path.is_file():
        raise FileNotFoundError(f"Retained Python wheelhouse lock is missing: {lock_path}")
    expected: dict[str, str] = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([A-Za-z0-9._+\-]+\.whl)", line)
        if match is None:
            raise ValueError("Retained Python wheelhouse lock is malformed.")
        digest, name = match.groups()
        if name in expected:
            raise ValueError(f"Duplicate retained wheelhouse entry: {name}")
        expected[name] = digest.lower()
    wheels = sorted(root.glob("*.whl"))
    if not wheels or {wheel.name for wheel in wheels} != expected.keys():
        raise ValueError("Retained wheelhouse contents do not exactly match its hash lock.")
    for wheel in wheels:
        if _sha256_file(wheel).lower() != expected[wheel.name]:
            raise ValueError(f"Retained wheel hash mismatch: {wheel.name}")
    return wheels


def _python_build_constraints(wheels: list[Path]) -> str:
    selected: dict[str, set[str]] = {"setuptools": set(), "wheel": set()}
    for wheel in wheels:
        parts = wheel.name.split("-", 2)
        if len(parts) < 3:
            continue
        distribution = parts[0].lower().replace("_", "-")
        if distribution in selected:
            selected[distribution].add(parts[1])
    if any(len(versions) != 1 for versions in selected.values()):
        raise ValueError("The retained wheelhouse must contain exactly one setuptools and wheel version.")
    return "".join(f"{name}=={next(iter(versions))}\n" for name, versions in sorted(selected.items()))


def _verified_source_commit() -> str:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("Git is required to record exact release build provenance.")
    source_commit = subprocess.run(
        [git, "rev-parse", "--verify", "HEAD"], cwd=ROOT_DIR, text=True,
        capture_output=True, check=True,
    ).stdout.strip()
    tracked_changes = subprocess.run(
        [git, "status", "--porcelain", "--untracked-files=no"], cwd=ROOT_DIR,
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    if tracked_changes:
        raise RuntimeError("Release packaging requires a committed, clean tracked source tree.")
    return source_commit


def _dotnet_sdk_version() -> str:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise FileNotFoundError("The .NET SDK is required to record exact release build provenance.")
    return subprocess.run(
        [dotnet, "--version"], cwd=ROOT_DIR, text=True,
        capture_output=True, timeout=15, check=True,
    ).stdout.strip()


def _verify_offline_toolchain(provenance: dict[str, object], dotnet_version: str) -> None:
    current = {
        "python_version": platform.python_version(),
        "pip_version": importlib.metadata.version("pip"),
        "dotnet_sdk_version": dotnet_version,
    }
    mismatches = [name for name, value in current.items() if provenance.get(name) != value]
    if mismatches:
        raise ValueError(
            "Offline rebuild toolchain does not match retained provenance: " + ", ".join(mismatches)
        )


def _write_build_provenance(
    output_dir: Path, offline: bool, source_commit: str, dotnet_version: str
) -> Path:
    pip_version = importlib.metadata.version("pip")
    payload = {
        "schema_version": 1,
        "source_commit": source_commit,
        "tracked_source_clean": True,
        "build_mode": "offline" if offline else "online_dependency_resolution",
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "pip_version": pip_version,
        "dotnet_sdk_version": dotnet_version,
    }
    path = output_dir / "build-provenance.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path


def build_wheelhouse(destination: Path, offline_inputs: Path | None = None) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    output_dir = destination.parent
    constraints = output_dir / "python-build-constraints.txt"
    if offline_inputs is None:
        subprocess.run(
            [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--no-cache-dir",
             "--index-url", "https://pypi.org/simple", "--dest", str(destination), "setuptools", "wheel"],
            cwd=ROOT_DIR, env=_build_environment(output_dir), check=True,
        )
        support_wheels = sorted(path for path in destination.glob("*.whl")
                                if path.name.lower().startswith(("setuptools-", "wheel-")))
        constraints.write_text(_python_build_constraints(support_wheels), encoding="utf-8", newline="\n")
        find_links = destination
        index_args = ["--index-url", "https://pypi.org/simple"]
    else:
        offline_inputs = offline_inputs.resolve()
        retained_wheelhouse = offline_inputs / "packages"
        retained_lock = offline_inputs / "build-inputs" / "python-wheelhouse.lock.txt"
        retained_constraints = offline_inputs / "build-inputs" / "python-build-constraints.txt"
        retained_wheels = _verify_wheelhouse(retained_wheelhouse, retained_lock)
        expected_constraints = _python_build_constraints(retained_wheels)
        if retained_constraints.read_text(encoding="utf-8") != expected_constraints:
            raise ValueError("Retained Python build constraints do not match the hashed build-support wheels.")
        constraints.write_text(expected_constraints, encoding="utf-8", newline="\n")
        for wheel in retained_wheels:
            if wheel.name.lower().startswith(("setuptools-", "wheel-")):
                shutil.copy2(wheel, destination / wheel.name)
        find_links = retained_wheelhouse
        index_args = ["--no-index"]

    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--only-binary=:all:", "--no-cache-dir",
         *index_args, "--find-links", str(find_links), "--constraint", str(constraints),
         "--wheel-dir", str(destination), f"{ROOT_DIR}[windows,media,stt,ocr]"],
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


def build_ui(output_dir: Path, offline_inputs: Path | None = None) -> Path:
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
    restore_inputs = [
        "--source", "https://api.nuget.org/v3/index.json",
        "--packages", str(output_dir / "nuget-packages"),
    ]
    if offline_inputs is not None:
        retained_lock = offline_inputs / "build-inputs" / "ui-packages.lock.json"
        retained_feed = offline_inputs / "build-inputs" / "nuget"
        if not retained_lock.is_file() or not retained_feed.is_dir():
            raise FileNotFoundError("Retained offline NuGet lock or package feed is missing.")
        shutil.copy2(retained_lock, lock_path)
        restore_inputs = [
            "--source", str(retained_feed),
            "--packages", str(output_dir / "nuget-packages"),
            "--locked-mode",
        ]
    subprocess.run(
        [
            dotnet,
            "restore",
            str(project),
            "--runtime", "win-x64",
            *restore_inputs,
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
    python_constraints = output_dir / "python-build-constraints.txt"
    if not python_constraints.is_file():
        raise FileNotFoundError("Retained Python build constraints are missing.")
    files["build-inputs/python-build-constraints.txt"] = python_constraints
    provenance = output_dir / "build-provenance.json"
    if not provenance.is_file():
        raise FileNotFoundError("Build provenance was not recorded.")
    files["build-inputs/build-provenance.json"] = provenance
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
    nuget_packages = sorted(path for path in nuget_cache.rglob("*.nupkg") if path.is_file())
    if not nuget_packages:
        raise FileNotFoundError("No retained NuGet packages were produced for the WinUI build.")
    for source in nuget_packages:
        files[f"build-inputs/nuget/{source.relative_to(nuget_cache).as_posix()}"] = source
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
    parser.add_argument(
        "--offline-inputs",
        type=Path,
        help="extracted prior candidate root with hash-locked Python and NuGet build inputs",
    )
    args = parser.parse_args()

    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("The PLUMA x64 Windows release candidate must be built on Windows x64.")
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12 or newer is required for the declared runtime dependencies.")

    source_commit = _verified_source_commit()
    offline_inputs = args.offline_inputs.resolve() if args.offline_inputs is not None else None
    offline_files = None
    if offline_inputs is not None:
        offline_files = _verify_retained_candidate(offline_inputs, source_commit)
    dotnet_version = _dotnet_sdk_version()
    if offline_files is not None:
        retained_provenance = json.loads(
            offline_files["build-inputs/build-provenance.json"].read_text(encoding="utf-8")
        )
        _verify_offline_toolchain(retained_provenance, dotnet_version)
    output_dir = _new_output_dir(args.output_dir)
    _write_build_provenance(
        output_dir, args.offline_inputs is not None, source_commit, dotnet_version
    )
    wheelhouse = output_dir / "packages"
    build_wheelhouse(wheelhouse, offline_inputs)
    ui_dir = build_ui(output_dir, offline_inputs)
    archive_path = create_release_zip(wheelhouse, ui_dir, output_dir)
    verify_zip_cleanliness(archive_path)
    print(f"Core + WinUI package candidate created: {archive_path}")
    print("This candidate is unsigned and is not a P28-complete production release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
