"""Integration tests for Pool + Snapshot operations.

These tests require real DigitalOcean credentials and Spaces.
Set environment variables:
- DIGITALOCEAN_TOKEN
- SPACES_BUCKET, SPACES_REGION, SPACES_ACCESS_KEY, SPACES_SECRET_KEY
"""

import pytest

from tests.integration.conftest import requires_all_credentials


@pytest.mark.integration
@requires_all_credentials
class TestManagerWithSnapshots:
    """Tests for SandboxManager with snapshot operations."""

    @pytest.mark.timeout(180)
    def test_acquire_with_snapshot(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Pool acquire + restore (~20s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.manager import SandboxManager
        from do_app_sandbox.snapshot import SnapshotManager

        # First create a snapshot to restore from
        setup_sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(setup_sandbox)

        # Create identifiable content
        setup_sandbox.exec("echo 'pool-snapshot-test' > /workspace/marker.txt")
        metadata = setup_sandbox.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        # Now use manager to acquire with snapshot
        manager = SandboxManager(
            pool_sizes={"python": 1},
            api_token=do_token,
            spaces_config=spaces_config
        )

        try:
            sandbox = manager.acquire_with_snapshot_sync(
                "python",
                metadata.snapshot_id,
                timeout=120
            )
            cleanup_sandboxes(sandbox)

            # Verify content was restored
            result = sandbox.exec("cat /workspace/marker.txt")
            assert "pool-snapshot-test" in result.stdout

        finally:
            manager.shutdown_sync()

    @pytest.mark.timeout(180)
    def test_wake_hibernated_via_pool(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """wake_hibernated() with pool (~20s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.manager import SandboxManager
        from do_app_sandbox.types import HibernatedSandbox

        # Create and hibernate a sandbox
        original = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )

        original.exec("echo 'hibernated-pool-test' > /workspace/hib.txt")
        hibernated = original.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        # Wake using manager
        manager = SandboxManager(
            pool_sizes={"python": 1},
            api_token=do_token,
            spaces_config=spaces_config
        )

        try:
            sandbox = manager.wake_hibernated_sync(hibernated, timeout=120)
            cleanup_sandboxes(sandbox)

            # Verify content was restored
            result = sandbox.exec("cat /workspace/hib.txt")
            assert "hibernated-pool-test" in result.stdout

        finally:
            manager.shutdown_sync()


@pytest.mark.integration
@requires_all_credentials
class TestManagerSnapshotErrors:
    """Tests for snapshot error handling in manager."""

    @pytest.mark.timeout(30)
    def test_acquire_snapshot_not_found(self, do_token, spaces_config):
        """Error on missing snapshot (~5s)."""
        from do_app_sandbox.manager import SandboxManager
        from do_app_sandbox.exceptions import SnapshotNotFoundError

        manager = SandboxManager(
            pool_sizes={"python": 0},  # No pooling
            api_token=do_token,
            spaces_config=spaces_config
        )

        try:
            with pytest.raises(SnapshotNotFoundError):
                manager.acquire_with_snapshot_sync(
                    "python",
                    "nonexistent-snapshot-xyz",
                    timeout=30
                )
        finally:
            manager.shutdown_sync()

    @pytest.mark.timeout(10)
    def test_acquire_spaces_not_configured(self, do_token):
        """Error without Spaces config (~2s)."""
        from do_app_sandbox.manager import SandboxManager
        from do_app_sandbox.exceptions import SpacesNotConfiguredError

        manager = SandboxManager(
            pool_sizes={"python": 0},
            api_token=do_token,
            spaces_config=None  # No Spaces
        )

        try:
            with pytest.raises((SpacesNotConfiguredError, AttributeError)):
                manager.acquire_with_snapshot_sync(
                    "python",
                    "any-snapshot",
                    timeout=30
                )
        finally:
            manager.shutdown_sync()
