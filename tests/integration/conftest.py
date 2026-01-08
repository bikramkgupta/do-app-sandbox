"""Pytest configuration and fixtures for integration tests.

These tests require real DigitalOcean credentials and Spaces configuration.
Set the following environment variables:
- DIGITALOCEAN_TOKEN: DO API token
- SPACES_BUCKET: DO Spaces bucket name
- SPACES_REGION: DO Spaces region (e.g., nyc3)
- SPACES_ACCESS_KEY: Spaces access key
- SPACES_SECRET_KEY: Spaces secret key
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
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring real credentials"
    )


def has_do_credentials() -> bool:
    """Check if DigitalOcean credentials are available."""
    return bool(os.environ.get("DIGITALOCEAN_TOKEN"))


def has_spaces_credentials() -> bool:
    """Check if Spaces credentials are available."""
    return all([
        os.environ.get("SPACES_BUCKET"),
        os.environ.get("SPACES_REGION"),
        os.environ.get("SPACES_ACCESS_KEY"),
        os.environ.get("SPACES_SECRET_KEY"),
    ])


# Skip markers for missing credentials
requires_do_token = pytest.mark.skipif(
    not has_do_credentials(),
    reason="DIGITALOCEAN_TOKEN not set"
)

requires_spaces = pytest.mark.skipif(
    not has_spaces_credentials(),
    reason="Spaces credentials not configured"
)

requires_all_credentials = pytest.mark.skipif(
    not (has_do_credentials() and has_spaces_credentials()),
    reason="Full credentials not configured"
)


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

    return SpacesConfig(
        bucket=bucket,
        region=region,
        access_key=access_key,
        secret_key=secret_key
    )


@pytest.fixture
def cleanup_sandboxes():
    """Track and cleanup sandboxes created during tests."""
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
def cleanup_snapshots(spaces_config):
    """Track and cleanup snapshots created during tests."""
    from do_app_sandbox.snapshot import SnapshotManager

    created_snapshots = []
    manager = None

    try:
        manager = SnapshotManager(spaces_config=spaces_config)
    except Exception:
        pytest.skip("Could not initialize SnapshotManager")

    def track(snapshot_id):
        created_snapshots.append(snapshot_id)
        return snapshot_id

    yield track

    # Cleanup all created snapshots
    if manager:
        for snapshot_id in created_snapshots:
            try:
                manager.delete_snapshot(snapshot_id)
            except Exception:
                pass
