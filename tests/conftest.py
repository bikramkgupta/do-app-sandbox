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
