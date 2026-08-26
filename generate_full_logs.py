"""generate_full_logs.py — Generates complete, untruncated, and safe test execution logs."""

from __future__ import annotations

import platform
import sys
import time
from typing import Dict, List

import pytest


def main() -> int:
    records: List[str] = []
    counts: Dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}

    class SafeLogCollector:
        def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
            if report.when == "call" or (report.when in ("setup", "teardown") and report.failed):
                outcome = report.outcome.lower()
                if outcome in counts:
                    counts[outcome] += 1
                else:
                    counts["error"] += 1

                status_str = report.outcome.upper()
                node = report.nodeid
                if report.when != "call":
                    node = f"{node} ({report.when})"
                records.append(f"{node:<95} {status_str:<8} [{report.duration:.3f}s]")

    t0 = time.perf_counter()
    ret = pytest.main(["tests/", "-q", "--timeout=30"], plugins=[SafeLogCollector()])
    elapsed = time.perf_counter() - t0

    total_tests = len(records)
    passed_count = counts["passed"]
    failed_count = counts["failed"] + counts["error"]
    skipped_count = counts["skipped"]
    pass_rate = (passed_count / total_tests * 100.0) if total_tests > 0 else 0.0

    sys_platform_str = f"{platform.system()} {platform.release()} ({platform.machine()}) [{platform.platform()}]"
    python_ver_str = f"{platform.python_version()} ({platform.python_implementation()})"

    header = (
        "=" * 115 + "\n"
        "============================= PLUMA FULL TEST SUITE EXECUTION =============================\n"
        f"Platform: {sys_platform_str} | Python: {python_ver_str}\n"
        f"Total Tests: {total_tests} | Passed: {passed_count} | Failed: {failed_count} | Skipped: {skipped_count} | Elapsed: {elapsed:.2f}s\n"
        + "=" * 115
        + "\n"
    )

    footer = (
        "\n"
        + "=" * 115
        + f"\nFINAL RESULT: {passed_count} passed, {failed_count} failed, {skipped_count} skipped in {elapsed:.2f}s ({pass_rate:.1f}% PASS RATE)\n"
        + "=" * 115
        + "\n"
    )

    full_text = header + "\n".join(records) + footer

    with open("test_run_raw.log", "w", encoding="utf-8") as f:
        f.write(full_text)
    with open("ACCEPTANCE_TEST_RAW_LOG.txt", "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"Generated complete logs: {passed_count} passed, {failed_count} failed, {skipped_count} skipped ({pass_rate:.1f}%) in {elapsed:.2f}s.")
    return int(ret)


if __name__ == "__main__":
    sys.exit(main())
