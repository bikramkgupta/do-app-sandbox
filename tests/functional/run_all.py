#!/usr/bin/env python3
"""
Run all functional tests for do-app-sandbox

Usage:
    python tests/functional/run_all.py              # Run all tests
    python tests/functional/run_all.py --skip 1    # Skip test 1
    python tests/functional/run_all.py --only 3 4  # Run only tests 3 and 4
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def run_test(test_num: int, test_file: str) -> dict:
    """Run a single test and return results."""
    print(f"\n{'=' * 60}")
    print(f"RUNNING TEST {test_num}: {test_file}")
    print(f"{'=' * 60}\n")

    result = {
        "test_num": test_num,
        "test_file": test_file,
        "status": "unknown",
        "exit_code": -1,
        "output": "",
    }

    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(script_dir, test_file)],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        result["exit_code"] = proc.returncode
        result["output"] = proc.stdout + proc.stderr
        result["status"] = "PASS" if proc.returncode == 0 else "FAIL"

        # Print output
        print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)

    except subprocess.TimeoutExpired:
        result["status"] = "TIMEOUT"
        result["output"] = "Test timed out after 600 seconds"
        print(f"ERROR: Test {test_num} timed out")

    except Exception as e:
        result["status"] = "ERROR"
        result["output"] = str(e)
        print(f"ERROR: {e}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Run functional tests")
    parser.add_argument("--skip", type=int, nargs="+", default=[], help="Tests to skip")
    parser.add_argument("--only", type=int, nargs="+", default=[], help="Only run these tests")
    args = parser.parse_args()

    tests = [
        (1, "test_01_existing_app.py"),
        (2, "test_02_benchmark.py"),
        (3, "test_03_basic_sdk.py"),
        (4, "test_04_manager.py"),
    ]

    # Filter tests
    if args.only:
        tests = [(n, f) for n, f in tests if n in args.only]
    tests = [(n, f) for n, f in tests if n not in args.skip]

    print("=" * 60)
    print("DO-APP-SANDBOX v0.1.4 FUNCTIONAL TESTS")
    print("=" * 60)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Tests to run: {[n for n, _ in tests]}")
    print("=" * 60)

    results = []
    for test_num, test_file in tests:
        result = run_test(test_num, test_file)
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] in ("ERROR", "TIMEOUT"))

    for r in results:
        icon = "✓" if r["status"] == "PASS" else "✗"
        print(f"  {icon} Test {r['test_num']}: {r['status']}")

    print(f"\nTotal: {len(results)} | Passed: {passed} | Failed: {failed} | Errors: {errors}")

    # Save summary
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "results": results,
    }

    summary_file = os.path.join(results_dir, "summary.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary saved to: {summary_file}")

    return 0 if failed == 0 and errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
