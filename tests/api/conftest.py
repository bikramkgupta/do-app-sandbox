"""Pytest configuration and fixtures for container API tests.

These tests validate the FastAPI server that runs inside service-mode containers.
Can be run locally with Docker or against a deployed container.

Required environment variables:
- SANDBOX_API_URL: Base URL of the sandbox API (e.g., http://localhost:8080)
- SANDBOX_API_TOKEN: API token for authentication

To run locally:
    docker build -t sandbox-api-test -f images/sandbox-python-service/Dockerfile images/
    docker run -p 8080:8080 -e SANDBOX_API_TOKEN=test-token sandbox-api-test
    SANDBOX_API_URL=http://localhost:8080 SANDBOX_API_TOKEN=test-token pytest tests/container/
"""

import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "container: mark test as container API test")


def has_container_api() -> bool:
    """Check if container API is available."""
    url = os.environ.get("SANDBOX_API_URL")
    token = os.environ.get("SANDBOX_API_TOKEN")
    return bool(url and token)


requires_container_api = pytest.mark.skipif(
    not has_container_api(), reason="SANDBOX_API_URL and SANDBOX_API_TOKEN not set"
)


@pytest.fixture
def api_url():
    """Get API URL from environment."""
    url = os.environ.get("SANDBOX_API_URL")
    if not url:
        pytest.skip("SANDBOX_API_URL not set")
    return url.rstrip("/")


@pytest.fixture
def api_token():
    """Get API token from environment."""
    token = os.environ.get("SANDBOX_API_TOKEN")
    if not token:
        pytest.skip("SANDBOX_API_TOKEN not set")
    return token


@pytest.fixture
def auth_headers(api_token):
    """Get authorization headers."""
    return {"Authorization": f"Bearer {api_token}"}


@pytest.fixture
def api_client(api_url, api_token):
    """Create a SandboxServiceClient for testing."""
    from do_app_sandbox.service_client import SandboxServiceClient

    return SandboxServiceClient(base_url=api_url, token=api_token)


@pytest.fixture
def cleanup_sessions(api_client):
    """Track and cleanup sessions created during tests."""
    created_sessions = []

    def track(session_id):
        created_sessions.append(session_id)
        return session_id

    yield track

    for session_id in created_sessions:
        try:
            api_client.close_session(session_id)
        except Exception:
            pass


@pytest.fixture
def cleanup_processes(api_client):
    """Track and cleanup processes created during tests."""
    created_pids = []

    def track(pid):
        created_pids.append(pid)
        return pid

    yield track

    for pid in created_pids:
        try:
            api_client.kill_process(pid)
        except Exception:
            pass
