"""tests.unit.test_job_object — Tests for WindowsJobObject wrapper."""

import subprocess
import sys
import time

import pytest

from pluma.core.job_object import WindowsJobObject, JobObjectError


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Objects require win32")
class TestWindowsJobObject:
    def test_job_object_creation_and_limits(self) -> None:
        """Verify the job object creates successfully and doesn't raise."""
        with WindowsJobObject(name="pluma-test-job-1") as job:
            assert job._handle is not None

    def test_job_object_process_assignment_and_terminate(self) -> None:
        """Verify we can assign a subprocess and terminate it."""
        with WindowsJobObject() as job:
            # Spawn the deterministic fixture app to spin indefinitely
            proc = subprocess.Popen(
                [sys.executable, "tests/fixtures/fixture_app.py", "spin"]
            )
            try:
                # Assign to job
                job.assign_process(proc)
                
                # Check it's alive
                assert proc.poll() is None
                
                # Terminate the job
                job.terminate(exit_code=99)
                
                # Wait briefly for Windows to kill the process
                time.sleep(0.1)
                
                # Check it's dead
                assert proc.poll() is not None
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def test_job_object_kill_on_close(self) -> None:
        """Verify processes are killed when the job handle closes (KILL_ON_JOB_CLOSE)."""
        proc = subprocess.Popen(
            [sys.executable, "tests/fixtures/fixture_app.py", "spin"]
        )
        try:
            job = WindowsJobObject()
            job.assign_process(proc)
            
            assert proc.poll() is None
            
            # Close the job handle. The process should die.
            job.close()
            time.sleep(0.1)
            
            assert proc.poll() is not None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
