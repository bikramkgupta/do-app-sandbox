#!/usr/bin/env python3
"""Show status of shared test sandboxes.

This script:
1. Checks if sandbox IDs are set in environment
2. Verifies sandboxes exist and are healthy
3. Tests connectivity to service sandbox

Usage:
    cd tests && make test-status
    # or directly:
    python tests/scripts/test_status.py
"""

import os
import sys
from pathlib import Path

# Add src to path (tests/scripts -> tests -> root -> src)
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

# Load existing .env (override=True ensures .env takes precedence over shell exports)
load_dotenv(override=True)


def check_worker_sandbox(sandbox_id: str) -> tuple[bool, str]:
    """Check if worker sandbox is healthy."""
    from do_app_sandbox import Sandbox
    from do_app_sandbox.exceptions import SandboxNotFoundError

    try:
        sandbox = Sandbox.get_from_id(sandbox_id)
        status = sandbox.status

        if status != "ACTIVE":
            return False, f"Status: {status} (expected ACTIVE)"

        # Try a simple exec
        result = sandbox.exec("echo health_check")
        if "health_check" not in result.stdout:
            return False, "exec() failed"

        return True, f"Status: {status}, exec() works"
    except SandboxNotFoundError:
        return False, "Sandbox not found (deleted?)"
    except Exception as e:
        return False, f"Error: {e}"


def check_service_sandbox(sandbox_id: str, api_url: str, api_token: str) -> tuple[bool, str]:
    """Check if service sandbox is healthy."""
    from do_app_sandbox import Sandbox
    from do_app_sandbox.exceptions import SandboxNotFoundError
    from do_app_sandbox.service_client import SandboxServiceClient

    try:
        sandbox = Sandbox.get_from_id(sandbox_id)
        status = sandbox.status

        if status != "ACTIVE":
            return False, f"Status: {status} (expected ACTIVE)"

        # Try HTTP connectivity using SandboxServiceClient directly
        # (get_from_id doesn't have the service token, so we create the client ourselves)
        if api_url and api_token:
            import httpx

            try:
                client = SandboxServiceClient(base_url=api_url, token=api_token)
                result = client.exec("echo health_check", timeout=30)
                if "health_check" not in result.stdout:
                    return False, "HTTP API exec() failed"
                return True, f"Status: {status}, HTTP API works"
            except httpx.ConnectError:
                return False, "HTTP endpoint not reachable"
            except Exception as e:
                return False, f"HTTP API error: {e}"
        elif api_url:
            return False, f"Status: {status}, but SANDBOX_API_TOKEN not set"
        else:
            return True, f"Status: {status} (no API URL to test)"

    except SandboxNotFoundError:
        return False, "Sandbox not found (deleted?)"
    except Exception as e:
        return False, f"Error: {e}"


def main():
    """Show status of shared test sandboxes."""
    print("=" * 60)
    print("  Shared Test Sandbox Status")
    print("=" * 60)

    worker_id = os.environ.get("SHARED_WORKER_SANDBOX_ID")
    service_id = os.environ.get("SHARED_SERVICE_SANDBOX_ID")
    api_url = os.environ.get("SANDBOX_API_URL")
    api_token = os.environ.get("SANDBOX_API_TOKEN")
    test_app_id = os.environ.get("TEST_APP_ID")

    # Show environment state
    print("\nEnvironment Variables:")
    print(f"  SHARED_WORKER_SANDBOX_ID: {worker_id or '(not set)'}")
    print(f"  SHARED_SERVICE_SANDBOX_ID: {service_id or '(not set)'}")
    print(f"  SANDBOX_API_URL: {api_url or '(not set)'}")
    print(f"  SANDBOX_API_TOKEN: {'***' + api_token[-8:] if api_token else '(not set)'}")
    print(f"  TEST_APP_ID: {test_app_id or '(not set)'}")

    if not worker_id and not service_id:
        print("\n" + "=" * 60)
        print("  No Shared Sandboxes Configured")
        print("=" * 60)
        print("\nRun 'make test-setup' to create shared sandboxes.")
        return

    all_healthy = True

    # Check worker sandbox
    print("\nWorker Sandbox:")
    if worker_id:
        healthy, message = check_worker_sandbox(worker_id)
        status_icon = "OK" if healthy else "FAIL"
        print(f"  [{status_icon}] {worker_id}")
        print(f"       {message}")
        if not healthy:
            all_healthy = False
    else:
        print("  [SKIP] Not configured")

    # Check service sandbox
    print("\nService Sandbox:")
    if service_id:
        healthy, message = check_service_sandbox(service_id, api_url, api_token)
        status_icon = "OK" if healthy else "FAIL"
        print(f"  [{status_icon}] {service_id}")
        print(f"       {message}")
        if api_url:
            print(f"       URL: {api_url}")
        if not healthy:
            all_healthy = False
    else:
        print("  [SKIP] Not configured")

    # Summary
    print("\n" + "=" * 60)
    if all_healthy:
        print("  All Sandboxes Healthy")
        print("=" * 60)
        print("\nReady for testing. Example commands:")
        print("  make test-git       # Run git checkout tests")
        print("  make test-service   # Run service mode tests")
        print("  make test-api       # Run API tests")
    else:
        print("  Some Sandboxes Unhealthy")
        print("=" * 60)
        print("\nRun 'make test-teardown' then 'make test-setup' to recreate.")
        sys.exit(1)


if __name__ == "__main__":
    main()
