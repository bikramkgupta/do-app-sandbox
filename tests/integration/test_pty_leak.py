"""Test for PTY file descriptor leak in Executor._disconnect().

This test verifies that PTY file descriptors are properly released after
command execution, preventing resource exhaustion in long-running applications.

GitHub Issue: https://github.com/bikramkgupta/do-app-sandbox/issues/6
"""

import os
import subprocess
import time

from do_app_sandbox import Sandbox

# Existing test sandbox - no creation needed
TEST_APP_ID = "057623bb-7434-4706-bb76-af6834681f33"
TEST_COMPONENT = "debug"

# Number of iterations for leak test
ITERATIONS = 50


def count_pty_fds(pid: int) -> int:
    """Count open PTY file descriptors for a process.

    On macOS, PTY master file descriptors appear as 'ptmx' in lsof output.

    Args:
        pid: Process ID to check

    Returns:
        Number of open PTY file descriptors
    """
    result = subprocess.run(
        ["lsof", "-p", str(pid)],
        capture_output=True,
        text=True,
    )
    # Count lines containing 'ptmx' (PTY master) or 'pty' (generic)
    count = 0
    for line in result.stdout.split("\n"):
        line_lower = line.lower()
        if "ptmx" in line_lower or "pty" in line_lower:
            count += 1
    return count


def test_no_pty_leak_after_multiple_executions():
    """Verify PTY file descriptors are released after command execution.

    This test:
    1. Records baseline PTY FD count
    2. Runs 50 command executions
    3. Checks FD count every 10 iterations
    4. Verifies no net accumulation of PTY FDs

    If this test fails, it indicates a PTY file descriptor leak in the
    Executor._disconnect() method.
    """
    pid = os.getpid()
    baseline = count_pty_fds(pid)
    print(f"\nBaseline PTY FDs: {baseline}")

    # Connect to existing test sandbox
    sandbox = Sandbox.get_from_id(TEST_APP_ID, component=TEST_COMPONENT)
    print(f"Connected to sandbox: {TEST_APP_ID}")

    fd_counts = [baseline]

    for i in range(ITERATIONS):
        result = sandbox.exec("echo test")
        assert result.success, f"Iteration {i}: command failed with {result.stderr}"

        # Check FD count every 10 iterations
        if (i + 1) % 10 == 0:
            current = count_pty_fds(pid)
            fd_counts.append(current)
            accumulated = current - baseline
            print(f"After {i + 1} iterations: {current} PTY FDs (accumulated: {accumulated})")

    # Allow brief cleanup time
    time.sleep(1)

    # Final check
    final_count = count_pty_fds(pid)
    fd_counts.append(final_count)
    total_accumulated = final_count - baseline

    print(f"\nFinal PTY FDs: {final_count}")
    print(f"Total accumulated: {total_accumulated}")
    print(f"FD progression: {fd_counts}")

    # Should not accumulate PTY FDs
    # Allow small margin (+2) for transient FDs
    assert final_count <= baseline + 2, (
        f"PTY leak detected: {total_accumulated} FDs accumulated after {ITERATIONS} iterations. "
        f"FD progression: {fd_counts}"
    )


if __name__ == "__main__":
    # Allow running directly for manual testing
    test_no_pty_leak_after_multiple_executions()
    print("\nTest passed!")
