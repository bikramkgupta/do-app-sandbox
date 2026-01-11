"""Pytest configuration and fixtures for container API tests.

These tests validate the FastAPI server that runs inside service-mode containers.
Can be run locally with Docker or against a deployed container.

Environment variables (in order of precedence):
1. SANDBOX_API_URL + SANDBOX_API_TOKEN: Explicit API endpoint and token
2. SHARED_SERVICE_SANDBOX_ID: Auto-detect from shared service sandbox (via `make test-setup`)
3. Local Docker: Run against local container

To run with shared sandbox:
    make test-setup       # Creates shared sandboxes, sets SANDBOX_API_URL
    make test-api         # Runs API tests

To run locally with Docker:
    docker build -t sandbox-api-test -f images/sandbox-python-service/Dockerfile images/
    docker run -p 8080:8080 -e SANDBOX_API_TOKEN=test-token sandbox-api-test
    SANDBOX_API_URL=http://localhost:8080 SANDBOX_API_TOKEN=test-token pytest tests/api/
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
    config.addinivalue_line("markers", "api: mark test as container API test")


def has_container_api() -> bool:
    """Check if container API is available (explicit or via shared sandbox)."""
    # Check explicit config first
    url = os.environ.get("SANDBOX_API_URL")
    token = os.environ.get("SANDBOX_API_TOKEN")
    if url and token:
        return True

    # Check for shared service sandbox
    shared_id = os.environ.get("SHARED_SERVICE_SANDBOX_ID")
    if shared_id:
        return True

    return False


requires_container_api = pytest.mark.skipif(
    not has_container_api(),
    reason="SANDBOX_API_URL/TOKEN not set. Run 'make test-setup' or provide credentials.",
)


def _get_shared_sandbox_api_info():
    """Get API URL and token from shared service sandbox if available."""
    shared_id = os.environ.get("SHARED_SERVICE_SANDBOX_ID")
    if not shared_id:
        return None, None

    # First check if explicit URL/token are set (they take precedence)
    url = os.environ.get("SANDBOX_API_URL")
    token = os.environ.get("SANDBOX_API_TOKEN")
    if url and token:
        return url, token

    # Try to get from the sandbox object
    try:
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.get_from_id(shared_id)
        url = sandbox.get_url()
        token = sandbox._service_token
        return url, token
    except Exception:
        return None, None


@pytest.fixture
def api_url():
    """Get API URL from environment or shared sandbox."""
    # Check explicit URL first
    url = os.environ.get("SANDBOX_API_URL")
    if url:
        return url.rstrip("/")

    # Try shared sandbox
    url, _ = _get_shared_sandbox_api_info()
    if url:
        return url.rstrip("/")

    pytest.skip("SANDBOX_API_URL not set. Run 'make test-setup' first.")


@pytest.fixture
def api_token():
    """Get API token from environment or shared sandbox."""
    # Check explicit token first
    token = os.environ.get("SANDBOX_API_TOKEN")
    if token:
        return token

    # Try shared sandbox
    _, token = _get_shared_sandbox_api_info()
    if token:
        return token

    pytest.skip("SANDBOX_API_TOKEN not set. Run 'make test-setup' first.")


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
