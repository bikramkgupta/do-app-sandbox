#!/usr/bin/env python3
"""
Test 1: Connect to Existing App and Troubleshoot

Tests the SDK's ability to connect to an existing App Platform app
and run diagnostic commands, as described in docs/troubleshooting_existing_apps.md
"""

import sys
import os
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from do_app_sandbox import Sandbox


@dataclass
class TestResult:
    """Result of the existing app connection test."""
    test_name: str = "Connect to Existing App"
    app_id: str = ""
    component: str = ""
    connected: bool = False
    whoami: Optional[str] = None
    pwd: Optional[str] = None
    uname: Optional[str] = None
    ps_aux: Optional[str] = None
    df_h: Optional[str] = None
    env_count: Optional[int] = None
    file_list: Optional[list] = None
    error: Optional[str] = None
    timestamp: str = ""


def run_test(app_id: str, component: str = "sandbox") -> TestResult:
    """
    Connect to an existing app and run diagnostic commands.

    Args:
        app_id: The App Platform app ID to connect to
        component: Component name (default "sandbox" for SDK-created sandboxes)

    Returns:
        TestResult with diagnostic information
    """
    result = TestResult(
        app_id=app_id,
        component=component,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    try:
        print(f"Connecting to app: {app_id}, component: {component}")
        app = Sandbox.get_from_id(app_id=app_id, component=component)
        result.connected = True
        print("Connected successfully!")

        # Run diagnostic commands
        print("\nRunning diagnostics...")

        # whoami
        try:
            res = app.exec("whoami", timeout=30)
            result.whoami = res.stdout.strip()
            print(f"  whoami: {result.whoami}")
        except Exception as e:
            print(f"  whoami failed: {e}")

        # pwd
        try:
            res = app.exec("pwd", timeout=30)
            result.pwd = res.stdout.strip()
            print(f"  pwd: {result.pwd}")
        except Exception as e:
            print(f"  pwd failed: {e}")

        # uname -a
        try:
            res = app.exec("uname -a", timeout=30)
            result.uname = res.stdout.strip()
            print(f"  uname: {result.uname[:80]}...")
        except Exception as e:
            print(f"  uname failed: {e}")

        # ps aux (first 5 lines)
        try:
            res = app.exec("ps aux | head -5", timeout=30)
            result.ps_aux = res.stdout.strip()
            print(f"  ps aux: {len(result.ps_aux)} chars")
        except Exception as e:
            print(f"  ps aux failed: {e}")

        # df -h
        try:
            res = app.exec("df -h", timeout=30)
            result.df_h = res.stdout.strip()
            print(f"  df -h: {len(result.df_h)} chars")
        except Exception as e:
            print(f"  df -h failed: {e}")

        # env count
        try:
            res = app.exec("env | wc -l", timeout=30)
            result.env_count = int(res.stdout.strip())
            print(f"  env vars: {result.env_count}")
        except Exception as e:
            print(f"  env count failed: {e}")

        # List files via filesystem API
        try:
            files = app.filesystem.list_dir("/app")
            result.file_list = [f.name for f in files[:10]]
            print(f"  /app files: {result.file_list}")
        except Exception as e:
            print(f"  list_dir failed: {e}")

    except Exception as e:
        result.error = str(e)
        print(f"ERROR: {e}")

    return result


def main():
    """Main entry point for Test 1."""
    # Default app ID from user request
    app_id = "4dd0ff44-45c6-4b63-8218-5b8d38d0a1f1"
    component = "sandbox"  # Default for SDK-created sandboxes

    # Allow override from command line
    if len(sys.argv) > 1:
        app_id = sys.argv[1]
    if len(sys.argv) > 2:
        component = sys.argv[2]

    print("=" * 60)
    print("TEST 1: Connect to Existing App and Troubleshoot")
    print("=" * 60)
    print(f"App ID: {app_id}")
    print(f"Component: {component}")
    print("=" * 60)

    result = run_test(app_id, component)

    print("\n" + "=" * 60)
    print("TEST RESULT")
    print("=" * 60)

    if result.connected:
        print("STATUS: PASS - Connected successfully")
    else:
        print(f"STATUS: FAIL - {result.error}")

    # Save result to JSON
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    output_file = os.path.join(results_dir, "test_01_result.json")
    with open(output_file, "w") as f:
        json.dump(asdict(result), f, indent=2)
    print(f"\nResults saved to: {output_file}")

    return 0 if result.connected else 1


if __name__ == "__main__":
    sys.exit(main())
