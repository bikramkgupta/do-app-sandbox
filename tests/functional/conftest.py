"""Pytest configuration and fixtures for functional tests.

Functional tests validate complete end-to-end workflows using real
DigitalOcean infrastructure. They require:
- DIGITALOCEAN_TOKEN
- SPACES_* credentials (for file transfer tests)
"""

import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports (root conftest.py does this too, but be safe)
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "functional: mark test as functional/E2E test")


@pytest.fixture(scope="session")
def ensure_do_token():
    """Ensure DIGITALOCEAN_TOKEN is set for the session."""
    token = os.environ.get("DIGITALOCEAN_TOKEN")
    if not token:
        pytest.skip("DIGITALOCEAN_TOKEN not set - skipping functional tests")
    return token


@pytest.fixture
def cleanup_sandboxes():
    """Track and cleanup sandboxes created during tests.

    Usage:
        def test_workflow(cleanup_sandboxes):
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


@pytest.fixture
def test_results_dir():
    """Get or create directory for test results."""
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    return results_dir
