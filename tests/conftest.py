"""Root pytest configuration for all tests.

This conftest.py provides:
- Centralized path configuration
- All pytest marker registrations
- Common credential checking utilities
- Shared fixtures available to all test types
"""

import os
import sys
from pathlib import Path

import pytest

# Load .env file from project root if it exists
# Use override=True so .env values take precedence over stale shell exports
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_file, override=True)

# Add src to path for imports (done once at root level)
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def pytest_configure(config):
    """Register all custom markers."""
    markers = [
        "unit: Fast tests with mocked dependencies, no network",
        "api: Tests for container API endpoints (requires SANDBOX_API_*)",
        "integration: Tests with real DigitalOcean infrastructure",
        "functional: End-to-end feature tests",
        "stress: Long-running load and stress tests",
        "slow: Tests that take more than 60 seconds",
        "container: Alias for api marker (container API tests)",
        "timeout: Set a timeout for the test (requires pytest-timeout)",
        "requires_own_sandbox: Test needs its own sandbox (cannot share)",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)


# ---------------------------------------------------------------------------
# Credential checking utilities
# ---------------------------------------------------------------------------


def has_do_credentials() -> bool:
    """Check if DigitalOcean credentials are available."""
    return bool(os.environ.get("DIGITALOCEAN_TOKEN"))


def has_spaces_credentials() -> bool:
    """Check if Spaces credentials are available."""
    return all(
        [
            os.environ.get("SPACES_BUCKET"),
            os.environ.get("SPACES_REGION"),
            os.environ.get("SPACES_ACCESS_KEY"),
            os.environ.get("SPACES_SECRET_KEY"),
        ]
    )


def has_container_api() -> bool:
    """Check if container API is available."""
    url = os.environ.get("SANDBOX_API_URL")
    token = os.environ.get("SANDBOX_API_TOKEN")
    return bool(url and token)


# Skip markers (available to all tests)
requires_do_token = pytest.mark.skipif(not has_do_credentials(), reason="DIGITALOCEAN_TOKEN not set")

requires_spaces = pytest.mark.skipif(not has_spaces_credentials(), reason="Spaces credentials not configured")

requires_all_credentials = pytest.mark.skipif(
    not (has_do_credentials() and has_spaces_credentials()),
    reason="Full credentials not configured",
)

requires_container_api = pytest.mark.skipif(
    not has_container_api(), reason="SANDBOX_API_URL and SANDBOX_API_TOKEN not set"
)


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def do_token():
    """Get DigitalOcean token from environment."""
    token = os.environ.get("DIGITALOCEAN_TOKEN")
    if not token:
        pytest.skip("DIGITALOCEAN_TOKEN not set")
    return token


@pytest.fixture
def spaces_config():
    """Get Spaces configuration from environment."""
    from do_app_sandbox.types import SpacesConfig

    bucket = os.environ.get("SPACES_BUCKET")
    region = os.environ.get("SPACES_REGION")
    access_key = os.environ.get("SPACES_ACCESS_KEY")
    secret_key = os.environ.get("SPACES_SECRET_KEY")

    if not all([bucket, region, access_key, secret_key]):
        pytest.skip("Spaces credentials not configured")

    return SpacesConfig(bucket=bucket, region=region, access_key=access_key, secret_key=secret_key)


@pytest.fixture
def cleanup_sandboxes():
    """Track and cleanup sandboxes created during tests.

    Usage:
        def test_something(cleanup_sandboxes):
            sandbox = Sandbox.create(...)
            cleanup_sandboxes(sandbox)
            # sandbox will be deleted on teardown
    """
    created_sandboxes = []

    def track(sandbox):
        created_sandboxes.append(sandbox)
        return sandbox

    yield track

    # Cleanup all created sandboxes
    for sandbox in created_sandboxes:
        try:
            sandbox.delete()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Shared Sandbox Fixtures
# ---------------------------------------------------------------------------
#
# These fixtures provide shared sandboxes for tests that can reuse them.
# Use `make test-setup` to create shared sandboxes before running tests.
# If no shared sandbox is available, a new one is created (slower).
#
# Usage:
#     def test_something(shared_worker_sandbox):
#         result = shared_worker_sandbox.exec("echo hello")
#         assert result.exit_code == 0


def _get_spaces_config_from_env():
    """Get Spaces configuration from environment if available."""
    from do_app_sandbox.types import SpacesConfig

    bucket = os.environ.get("SPACES_BUCKET")
    region = os.environ.get("SPACES_REGION")
    access_key = os.environ.get("SPACES_ACCESS_KEY")
    secret_key = os.environ.get("SPACES_SECRET_KEY")

    if all([bucket, region, access_key, secret_key]):
        return SpacesConfig(bucket=bucket, region=region, access_key=access_key, secret_key=secret_key)
    return None


@pytest.fixture(scope="session")
def shared_worker_sandbox():
    """Shared worker-mode sandbox for tests that can reuse.

    If SHARED_WORKER_SANDBOX_ID is set (via `make test-setup`), uses that sandbox.
    Otherwise, creates a new sandbox (slower but works without setup).

    The sandbox is NOT deleted at the end - use `make test-teardown` for cleanup.

    Usage:
        def test_something(shared_worker_sandbox):
            result = shared_worker_sandbox.exec("echo hello")
            assert result.exit_code == 0
    """
    from do_app_sandbox import Sandbox

    token = os.environ.get("DIGITALOCEAN_TOKEN")
    if not token:
        pytest.skip("DIGITALOCEAN_TOKEN not set")

    shared_id = os.environ.get("SHARED_WORKER_SANDBOX_ID")

    if shared_id:
        # Use pre-created shared sandbox (fast path)
        try:
            sandbox = Sandbox.get_from_id(shared_id)
            sandbox._is_shared = True  # Mark as shared so tests don't delete it
            yield sandbox
            return  # Don't delete shared sandbox
        except Exception as e:
            pytest.fail(f"Shared worker sandbox {shared_id} not accessible: {e}")

    # Fallback: create a new sandbox (slow path)
    spaces_config = _get_spaces_config_from_env()
    sandbox = Sandbox.create(image="python", api_token=token, spaces_config=spaces_config, wait_ready=True)
    sandbox._is_shared = False  # Not shared, will be cleaned up

    yield sandbox

    # Cleanup fallback sandbox
    try:
        sandbox.delete()
    except Exception:
        pass


@pytest.fixture(scope="session")
def shared_service_sandbox():
    """Shared service-mode sandbox for tests that can reuse.

    If SHARED_SERVICE_SANDBOX_ID is set (via `make test-setup`), uses that sandbox.
    Otherwise, creates a new sandbox (slower but works without setup).

    Includes connectivity verification for reliable HTTP API access.

    Usage:
        def test_something(shared_service_sandbox):
            result = shared_service_sandbox.exec("echo hello")
            assert result.exit_code == 0
    """
    import time

    import httpx

    from do_app_sandbox import Sandbox
    from do_app_sandbox.types import SandboxMode

    token = os.environ.get("DIGITALOCEAN_TOKEN")
    if not token:
        pytest.skip("DIGITALOCEAN_TOKEN not set")

    shared_id = os.environ.get("SHARED_SERVICE_SANDBOX_ID")

    if shared_id:
        # Use pre-created shared sandbox (fast path)
        # We need to configure service mode properties that get_from_id doesn't set
        api_url = os.environ.get("SANDBOX_API_URL")
        api_token = os.environ.get("SANDBOX_API_TOKEN")

        if not api_url or not api_token:
            pytest.fail(
                "Shared service sandbox requires SANDBOX_API_URL and SANDBOX_API_TOKEN. "
                "Run 'make test-setup' or set these environment variables."
            )

        try:
            sandbox = Sandbox.get_from_id(shared_id)
            sandbox._is_shared = True
            # Configure service mode properties (get_from_id doesn't set these)
            sandbox._mode = SandboxMode.SERVICE
            sandbox._service_token = api_token
            sandbox._url = api_url
            yield sandbox
            return  # Don't delete shared sandbox
        except Exception as e:
            pytest.fail(f"Shared service sandbox {shared_id} not accessible: {e}")

    # Fallback: create a new sandbox (slow path)
    spaces_config = _get_spaces_config_from_env()
    sandbox = Sandbox.create(
        image="python",
        mode=SandboxMode.SERVICE,
        api_token=token,
        spaces_config=spaces_config,
        wait_ready=True,
        timeout=300,
    )
    sandbox._is_shared = False

    # Wait for HTTP endpoint to be DNS-resolvable and reachable
    client = sandbox._get_service_client()
    for attempt in range(15):
        try:
            result = client.exec("echo connectivity_check", timeout=30)
            if "connectivity_check" in result.stdout:
                break
        except (httpx.ConnectError, Exception):
            if attempt < 14:
                time.sleep(3)
            else:
                sandbox.delete()
                pytest.fail("Service sandbox HTTP endpoint not reachable")

    yield sandbox

    # Cleanup fallback sandbox
    try:
        sandbox.delete()
    except Exception:
        pass
