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
    def test_acquire_with_snapshot(self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots):
        """Pool acquire + restore (~20s)."""
        from do_app_sandbox import PoolConfig, Sandbox
        from do_app_sandbox.manager import SandboxManager

        # First create a snapshot to restore from
        setup_sandbox = Sandbox.create(image="python", api_token=do_token, spaces_config=spaces_config, wait_ready=True)
        cleanup_sandboxes(setup_sandbox)

        # Create identifiable content
        setup_sandbox.exec("echo 'pool-snapshot-test' > /home/sandbox/app/marker.txt")
        metadata = setup_sandbox.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        # Now use manager to acquire with snapshot
        manager = SandboxManager(
            pools={"python": PoolConfig(target_ready=1)},
            sandbox_defaults={"api_token": do_token, "spaces_config": spaces_config},
        )

        try:
            manager.start_sync()
            sandbox = manager.acquire_with_snapshot_sync("python", metadata.snapshot_id, timeout=120)
            cleanup_sandboxes(sandbox)

            # Verify content was restored
            result = sandbox.exec("cat /home/sandbox/app/marker.txt")
            assert "pool-snapshot-test" in result.stdout

        finally:
            manager.shutdown_sync()

    @pytest.mark.timeout(180)
    def test_wake_hibernated_via_pool(self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots):
        """wake_hibernated() with pool (~20s)."""
        from do_app_sandbox import PoolConfig, Sandbox
        from do_app_sandbox.manager import SandboxManager

        # Create and hibernate a sandbox
        original = Sandbox.create(image="python", api_token=do_token, spaces_config=spaces_config, wait_ready=True)

        original.exec("echo 'hibernated-pool-test' > /home/sandbox/app/hib.txt")
        hibernated = original.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        # Wake using manager
        manager = SandboxManager(
            pools={"python": PoolConfig(target_ready=1)},
            sandbox_defaults={"api_token": do_token, "spaces_config": spaces_config},
        )

        try:
            manager.start_sync()
            sandbox = manager.wake_hibernated_sync(hibernated, timeout=120)
            cleanup_sandboxes(sandbox)

            # Verify content was restored
            result = sandbox.exec("cat /home/sandbox/app/hib.txt")
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
        from do_app_sandbox import PoolConfig
        from do_app_sandbox.exceptions import SnapshotNotFoundError
        from do_app_sandbox.manager import SandboxManager

        manager = SandboxManager(
            pools={"python": PoolConfig(target_ready=0)},  # No pooling
            sandbox_defaults={"api_token": do_token, "spaces_config": spaces_config},
        )

        try:
            manager.start_sync()
            with pytest.raises(SnapshotNotFoundError):
                manager.acquire_with_snapshot_sync("python", "nonexistent-snapshot-xyz", timeout=30)
        finally:
            manager.shutdown_sync()

    @pytest.mark.timeout(10)
    def test_acquire_spaces_not_configured(self, do_token):
        """Error without Spaces config (~2s)."""
        from do_app_sandbox import PoolConfig
        from do_app_sandbox.exceptions import SpacesNotConfiguredError
        from do_app_sandbox.manager import SandboxManager

        manager = SandboxManager(
            pools={"python": PoolConfig(target_ready=0)},
            sandbox_defaults={"api_token": do_token, "spaces_config": None},  # No Spaces
        )

        try:
            manager.start_sync()
            with pytest.raises((SpacesNotConfiguredError, AttributeError)):
                manager.acquire_with_snapshot_sync("python", "any-snapshot", timeout=30)
        finally:
            manager.shutdown_sync()
