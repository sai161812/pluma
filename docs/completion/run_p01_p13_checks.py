"""Reproduce one E73 regression selection in isolated storage on Windows.

Native microphone, physical focus/audio/power and release tests are not selected.
Selections reuse the checked-in P12 manifest plus the remaining P13 modules.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
MODES = ("prerequisites", "catalog", "contracts", "p12", "native", "p13")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    mode = parser.parse_args().mode
    out = ROOT / "output/p01-p13-audit"
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "docs/completion/p12_check_manifest.json").read_text(encoding="utf-8"))
    manifest["p13"] = ["-m", "pytest", "tests/unit/test_brain_llama_cpp_adapter.py",
        "tests/unit/test_planner_target_admission.py", "tests/unit/test_planner_route_replan.py", "-q"]
    command = [sys.executable, *manifest[mode], "--runxfail", "-o", "junit_family=xunit1",
        "-W", "error::pytest.PytestUnhandledThreadExceptionWarning", "--junitxml=" + str(out / (mode + "-final.xml"))]
    env = {key: value for key, value in os.environ.items() if not key.startswith("PLUMA_")}
    private = Path(tempfile.mkdtemp(prefix="pluma-audit-" + mode + "-"))
    for key in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        directory = private / key
        directory.mkdir()
        env[key] = str(directory)
    env["PYTHONIOENCODING"] = "utf-8"
    metadata = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "mode": mode, "command": command, "windows": platform.platform(), "python": sys.version.split()[0],
        "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for directory in ("pluma", "tests") for path in (ROOT / directory).rglob("*.py")}}
    started = time.monotonic()
    try:
        with (out / (mode + "-final.txt")).open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        metadata["exit"] = result.returncode
        metadata["junit"] = [node.attrib for node in ET.parse(out / (mode + "-final.xml")).getroot().iter("testsuite")]
        if any(int(suite.get("skipped", 0)) for suite in metadata["junit"]):
            metadata["exit"] = 1
    except subprocess.TimeoutExpired:
        metadata.update(exit=124, error="AUDIT_SUITE_TIMEOUT")
    metadata["wall_seconds"] = round(time.monotonic() - started, 3)
    (out / (mode + "-final.json")).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in metadata.items() if key not in ("source_hashes", "command")}))
    return metadata["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
