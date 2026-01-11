"""Pytest configuration and fixtures for integration tests.

These tests require real DigitalOcean credentials and optionally Spaces configuration.

Required environment variables:
- DIGITALOCEAN_TOKEN: DO API token

Optional for snapshots/hibernation:
- SPACES_BUCKET: DO Spaces bucket name
- SPACES_REGION: DO Spaces region (e.g., nyc3)
- SPACES_ACCESS_KEY: Spaces access key
- SPACES_SECRET_KEY: Spaces secret key

Shared sandbox support:
- Run `make test-setup` to create shared sandboxes before running tests
- This sets SHARED_WORKER_SANDBOX_ID and SHARED_SERVICE_SANDBOX_ID
- Tests using shared_worker_sandbox or shared_service_sandbox fixtures will reuse them
"""

import pytest

# Import skip markers from root conftest (they're also available via pytest discovery)
from tests.conftest import (
    requires_all_credentials,
    requires_do_token,
    requires_spaces,
)

# Re-export for convenience (tests import from here)
__all__ = ["requires_do_token", "requires_spaces", "requires_all_credentials"]


# ---------------------------------------------------------------------------
# Integration-specific fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cleanup_snapshots(spaces_config):
    """Track and cleanup snapshots created during tests.

    Usage:
        def test_snapshot(cleanup_snapshots):
            metadata = sandbox.create_snapshot()
            cleanup_snapshots(metadata.snapshot_id)
            # snapshot will be deleted on teardown
    """
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
