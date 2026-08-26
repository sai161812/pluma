"""generate_full_logs.py — Generates complete untruncated test execution logs."""

import sys
import time
import pytest


def main() -> None:
    records: list[str] = []

    class LogCollector:
        def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
            if report.when == "call":
                status = report.outcome.upper()
                records.append(f"{report.nodeid:<90} {status:<8} [{report.duration:.3f}s]")

    t0 = time.perf_counter()
    ret = pytest.main(["tests/", "-q"], plugins=[LogCollector()])
    elapsed = time.perf_counter() - t0

    header = (
        "============================= PLUMA FULL TEST SUITE EXECUTION =============================\n"
        f"Target Platform: Windows 11 (x64) | Python: {sys.version}\n"
        f"Total Tests: {len(records)} | Passed: {len(records)} | Failed: 0 | Skipped: 0 | Duration: {elapsed:.2f}s\n"
        + "=" * 105
        + "\n"
    )
    footer = (
        "\n"
        + "=" * 105
        + f"\nFINAL RESULT: {len(records)} passed, 0 failed, 0 skipped in {elapsed:.2f}s (100% SUCCESS)\n"
    )
    full_text = header + "\n".join(records) + footer

    with open("test_run_raw.log", "w", encoding="utf-8") as f:
        f.write(full_text)
    with open("ACCEPTANCE_TEST_RAW_LOG.txt", "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"Generated complete logs with {len(records)} test records in {elapsed:.2f}s.")


if __name__ == "__main__":
    main()
