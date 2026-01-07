#!/usr/bin/env python3
"""
Test 3: Basic Sandbox SDK Functionality

Tests the core SDK features:
- Create sandbox
- Execute commands
- File operations
- Process management
- Delete sandbox
"""

import sys
import os
import json
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from do_app_sandbox import Sandbox


@dataclass
class TestCase:
    """Individual test case result."""
    name: str
    passed: bool
    duration_s: float = 0.0
    details: str = ""
    error: Optional[str] = None


@dataclass
class TestResult:
    """Overall test result."""
    test_name: str = "Basic Sandbox SDK"
    app_id: Optional[str] = None
    url: Optional[str] = None
    image: str = "python"
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    duration_s: float = 0.0
    test_cases: List[dict] = field(default_factory=list)
    timestamp: str = ""


def run_test_case(name: str, func) -> TestCase:
    """Run a single test case and capture result."""
    start = time.time()
    try:
        result = func()
        return TestCase(
            name=name,
            passed=True,
            duration_s=time.time() - start,
            details=str(result) if result else "OK",
        )
    except Exception as e:
        return TestCase(
            name=name,
            passed=False,
            duration_s=time.time() - start,
            error=str(e),
        )


def run_tests(image: str = "python") -> TestResult:
    """Run all basic SDK tests."""
    result = TestResult(
        image=image,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    test_cases = []

    print("=" * 60)
    print("TEST 3: BASIC SANDBOX SDK")
    print("=" * 60)
    print(f"Image: {image}")
    print("=" * 60)

    sandbox = None
    overall_start = time.time()

    try:
        # Test 1: Create sandbox
        print("\n[1/10] Creating sandbox...")
        tc = run_test_case("create_sandbox", lambda: Sandbox.create(
            image=image,
            name=f"func-test-{int(time.time())}",
            wait_ready=True,
            timeout=300,
        ))
        if tc.passed:
            sandbox = tc.details if isinstance(tc.details, Sandbox) else None
            # Re-run to get sandbox object
            sandbox = Sandbox.create(
                image=image,
                name=f"func-test-{int(time.time())}",
                wait_ready=True,
                timeout=300,
            )
            tc.details = f"app_id: {sandbox.app_id}"
            result.app_id = sandbox.app_id
            result.url = sandbox.get_url()
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        if not sandbox:
            print("Cannot continue without sandbox")
            return result

        # Test 2: Basic exec
        print("\n[2/10] Testing exec...")
        tc = run_test_case("exec_echo", lambda: sandbox.exec("echo 'hello world'"))
        if tc.passed:
            res = sandbox.exec("echo 'hello world'")
            tc.details = f"stdout: {res.stdout.strip()}, exit_code: {res.exit_code}"
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 3: Exec with exit code
        print("\n[3/10] Testing exec exit codes...")
        tc = run_test_case("exec_exit_code", lambda: None)
        try:
            res = sandbox.exec("exit 42")
            tc.passed = res.exit_code == 42
            tc.details = f"exit_code: {res.exit_code} (expected 42)"
        except Exception as e:
            tc.passed = False
            tc.error = str(e)
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 4: Runtime version
        print("\n[4/10] Testing runtime version...")
        version_cmd = "python3 --version" if image == "python" else "node --version"
        tc = run_test_case("runtime_version", lambda: sandbox.exec(version_cmd))
        res = sandbox.exec(version_cmd)
        tc.details = res.stdout.strip()
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 5: Write file
        print("\n[5/10] Testing write_file...")
        test_content = "Hello from functional test!"
        tc = run_test_case("write_file", lambda: sandbox.filesystem.write_file(
            "/tmp/test.txt", test_content
        ))
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 6: Read file
        print("\n[6/10] Testing read_file...")
        tc = run_test_case("read_file", lambda: sandbox.filesystem.read_file("/tmp/test.txt"))
        if tc.passed:
            content = sandbox.filesystem.read_file("/tmp/test.txt")
            tc.passed = content.strip() == test_content
            tc.details = f"content matches: {tc.passed}"
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 7: List directory
        print("\n[7/10] Testing list_dir...")
        tc = run_test_case("list_dir", lambda: sandbox.filesystem.list_dir("/tmp"))
        if tc.passed:
            files = sandbox.filesystem.list_dir("/tmp")
            tc.details = f"found {len(files)} files"
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 8: File exists
        print("\n[8/10] Testing exists...")
        tc = run_test_case("file_exists", lambda: sandbox.filesystem.exists("/tmp/test.txt"))
        if tc.passed:
            exists = sandbox.filesystem.exists("/tmp/test.txt")
            tc.passed = exists is True
            tc.details = f"exists: {exists}"
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 9: Remove file
        print("\n[9/10] Testing rm...")
        tc = run_test_case("rm_file", lambda: sandbox.filesystem.rm("/tmp/test.txt"))
        if tc.passed:
            exists_after = sandbox.filesystem.exists("/tmp/test.txt")
            tc.passed = exists_after is False
            tc.details = f"file removed: {not exists_after}"
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

        # Test 10: Delete sandbox
        print("\n[10/10] Testing delete...")
        tc = run_test_case("delete_sandbox", lambda: sandbox.delete())
        test_cases.append(tc)
        print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")
        sandbox = None  # Mark as deleted

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        # Cleanup if sandbox still exists
        if sandbox:
            try:
                print("\nCleaning up...")
                sandbox.delete()
            except Exception:
                pass

    # Compile results
    result.duration_s = time.time() - overall_start
    result.test_cases = [asdict(tc) for tc in test_cases]
    result.total_tests = len(test_cases)
    result.passed = sum(1 for tc in test_cases if tc.passed)
    result.failed = result.total_tests - result.passed

    return result


def main():
    """Main entry point for Test 3."""
    image = os.getenv("TEST_IMAGE", "python")
    if len(sys.argv) > 1:
        image = sys.argv[1]

    result = run_tests(image)

    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"Total: {result.total_tests}")
    print(f"Passed: {result.passed}")
    print(f"Failed: {result.failed}")
    print(f"Duration: {result.duration_s:.1f}s")

    # Save result to JSON
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    output_file = os.path.join(results_dir, "test_03_result.json")
    with open(output_file, "w") as f:
        json.dump(asdict(result), f, indent=2)
    print(f"\nResults saved to: {output_file}")

    print("\n" + "=" * 60)
    status = "PASS" if result.failed == 0 else "FAIL"
    print(f"STATUS: {status}")
    print("=" * 60)

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
