"""Integration tests for Snapshot E2E.

These tests require real DigitalOcean credentials and Spaces.
Set environment variables:
- DIGITALOCEAN_TOKEN
- SPACES_BUCKET, SPACES_REGION, SPACES_ACCESS_KEY, SPACES_SECRET_KEY

Test categories:
- TestSnapshotShared: Tests that CAN use a shared sandbox (non-destructive)
- TestSnapshotIsolated: Tests that MUST have their own sandbox (restore, node image)
- TestSnapshotErrors: Tests that need no sandbox (pure Spaces operations)
"""

import time

import pytest

from tests.integration.conftest import requires_all_credentials

# ---------------------------------------------------------------------------
# Fixture for snapshot tests that can share
# ---------------------------------------------------------------------------


@pytest.fixture
def snapshot_sandbox(shared_worker_sandbox, spaces_config):
    """Provide a sandbox for snapshot tests that can share.

    Uses shared_worker_sandbox (from `make test-setup` or session fallback).
    Adds spaces_config to the sandbox for snapshot operations.
    """
    # Add spaces_config if not already present (needed for snapshot operations)
    if not hasattr(shared_worker_sandbox, "_spaces_config") or shared_worker_sandbox._spaces_config is None:
        shared_worker_sandbox._spaces_config = spaces_config
    yield shared_worker_sandbox


# ---------------------------------------------------------------------------
# Tests that CAN use a shared sandbox
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_all_credentials
class TestSnapshotShared:
    """Snapshot tests that can use a shared sandbox.

    These tests:
    - Create files in unique paths to avoid conflicts
    - Create snapshots (non-destructive read operation)
    - List/filter snapshots from Spaces

    Run with: `make test-snapshot` after `make test-setup`
    """

    @pytest.mark.timeout(120)
    def test_create_snapshot_basic(self, snapshot_sandbox, spaces_config, cleanup_snapshots):
        """Create snapshot of /home/sandbox/app (~30s)."""
        from do_app_sandbox.types import SnapshotMetadata

        # Use unique path to avoid conflicts with other tests
        unique_id = f"basic_{int(time.time())}"
        test_dir = f"/home/sandbox/app/test_{unique_id}"

        snapshot_sandbox.exec(f"mkdir -p {test_dir}")
        snapshot_sandbox.exec(f"echo 'test content' > {test_dir}/test.txt")

        # Create snapshot with unique ID
        snapshot_id = f"snap-basic-{unique_id}"
        metadata = snapshot_sandbox.create_snapshot(snapshot_id=snapshot_id, description="Test snapshot")
        cleanup_snapshots(metadata.snapshot_id)

        assert isinstance(metadata, SnapshotMetadata)
        assert metadata.snapshot_id == snapshot_id
        assert metadata.sandbox_image == "python"
        assert metadata.size_bytes > 0

        # Cleanup test files
        snapshot_sandbox.exec(f"rm -rf {test_dir}")

    @pytest.mark.timeout(120)
    def test_create_snapshot_custom_paths(self, snapshot_sandbox, spaces_config, cleanup_snapshots):
        """Snapshot with custom paths (~30s)."""
        # Use unique path
        unique_id = f"paths_{int(time.time())}"
        test_dir = f"/home/sandbox/app/src_{unique_id}"

        snapshot_sandbox.exec(f"mkdir -p {test_dir}")
        snapshot_sandbox.exec(f"echo 'code' > {test_dir}/main.py")

        snapshot_id = f"snap-paths-{unique_id}"
        metadata = snapshot_sandbox.create_snapshot(
            snapshot_id=snapshot_id, paths=[test_dir], description="Source code only"
        )
        cleanup_snapshots(metadata.snapshot_id)

        assert metadata.paths == [test_dir]

        # Cleanup
        snapshot_sandbox.exec(f"rm -rf {test_dir}")

    @pytest.mark.timeout(30)
    def test_snapshot_metadata_stored(self, snapshot_sandbox, spaces_config, cleanup_snapshots):
        """Metadata retrievable from Spaces (~5s after creation)."""
        from do_app_sandbox.snapshot import SnapshotManager

        unique_id = f"meta_{int(time.time())}"
        snapshot_id = f"snap-meta-{unique_id}"

        metadata = snapshot_sandbox.create_snapshot(snapshot_id=snapshot_id)
        cleanup_snapshots(metadata.snapshot_id)

        # Retrieve metadata from Spaces
        manager = SnapshotManager(spaces_config=spaces_config)
        retrieved = manager.get_snapshot(metadata.snapshot_id)

        assert retrieved is not None
        assert retrieved.snapshot_id == metadata.snapshot_id
        assert retrieved.sandbox_image == metadata.sandbox_image

    @pytest.mark.timeout(30)
    def test_list_snapshots(self, snapshot_sandbox, spaces_config, cleanup_snapshots):
        """List returns created snapshots (~5s)."""
        from do_app_sandbox.snapshot import SnapshotManager

        # Create snapshot with unique prefix
        snapshot_id = f"snap-list-test-{int(time.time())}"
        metadata = snapshot_sandbox.create_snapshot(snapshot_id=snapshot_id)
        cleanup_snapshots(metadata.snapshot_id)

        # List and verify
        manager = SnapshotManager(spaces_config=spaces_config)
        snapshots = manager.list_snapshots()

        assert any(s.snapshot_id == snapshot_id for s in snapshots)

    @pytest.mark.timeout(30)
    def test_list_snapshots_filter_image(self, snapshot_sandbox, spaces_config, cleanup_snapshots):
        """Filter snapshots by image (~5s)."""
        from do_app_sandbox.snapshot import SnapshotManager

        unique_id = f"filter_{int(time.time())}"
        snapshot_id = f"snap-filter-{unique_id}"

        metadata = snapshot_sandbox.create_snapshot(snapshot_id=snapshot_id)
        cleanup_snapshots(metadata.snapshot_id)

        manager = SnapshotManager(spaces_config=spaces_config)
        python_snapshots = manager.list_snapshots(image="python")

        assert all(s.sandbox_image == "python" for s in python_snapshots)

    @pytest.mark.timeout(30)
    def test_delete_snapshot(self, snapshot_sandbox, spaces_config):
        """Delete removes from Spaces (~5s)."""
        from do_app_sandbox.snapshot import SnapshotManager

        unique_id = f"delete_{int(time.time())}"
        snapshot_id = f"snap-delete-{unique_id}"

        metadata = snapshot_sandbox.create_snapshot(snapshot_id=snapshot_id)

        manager = SnapshotManager(spaces_config=spaces_config)

        # Verify exists
        assert manager.snapshot_exists(snapshot_id)

        # Delete
        result = manager.delete_snapshot(snapshot_id)
        assert result is True

        # Verify deleted
        assert not manager.snapshot_exists(snapshot_id)


# ---------------------------------------------------------------------------
# Tests that MUST have their own sandbox
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.requires_own_sandbox
@requires_all_credentials
class TestSnapshotIsolated:
    """Snapshot tests that require their own sandbox.

    These tests either:
    - Restore snapshots (overwrites sandbox state)
    - Use a different image (node)
    - Need pristine sandbox state

    Always create dedicated sandboxes via cleanup_sandboxes fixture.
    """

    @pytest.mark.timeout(180)
    def test_create_snapshot_with_deps(self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots):
        """Snapshot includes node_modules (~45s).

        Uses node image, so cannot share python sandbox.
        """
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.create(image="node", api_token=do_token, spaces_config=spaces_config, wait_ready=True)
        cleanup_sandboxes(sandbox)

        # Install a small package
        sandbox.exec("cd /home/sandbox/app && npm init -y && npm install is-odd")

        # Create snapshot
        metadata = sandbox.create_snapshot(description="With dependencies")
        cleanup_snapshots(metadata.snapshot_id)

        # node_modules should be included (size should be > minimal)
        assert metadata.size_bytes > 1000  # Should be larger with deps

    @pytest.mark.timeout(180)
    def test_restore_snapshot_basic(self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots):
        """Restore snapshot to new sandbox (~30s)."""
        from do_app_sandbox import Sandbox

        # Create first sandbox with content
        sandbox1 = Sandbox.create(image="python", api_token=do_token, spaces_config=spaces_config, wait_ready=True)
        cleanup_sandboxes(sandbox1)

        sandbox1.exec("echo 'original content' > /home/sandbox/app/data.txt")
        metadata = sandbox1.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        # Create second sandbox and restore
        sandbox2 = Sandbox.create(image="python", api_token=do_token, spaces_config=spaces_config, wait_ready=True)
        cleanup_sandboxes(sandbox2)

        success = sandbox2.restore_snapshot(metadata.snapshot_id)
        assert success is True

    @pytest.mark.timeout(180)
    def test_restore_preserves_files(self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots):
        """Restored files match original (~10s after restore)."""
        from do_app_sandbox import Sandbox

        # Create sandbox with specific content
        sandbox1 = Sandbox.create(image="python", api_token=do_token, spaces_config=spaces_config, wait_ready=True)
        cleanup_sandboxes(sandbox1)

        test_content = "unique-test-content-12345"
        sandbox1.exec(f"echo '{test_content}' > /home/sandbox/app/verify.txt")
        metadata = sandbox1.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        # Restore to new sandbox
        sandbox2 = Sandbox.create(image="python", api_token=do_token, spaces_config=spaces_config, wait_ready=True)
        cleanup_sandboxes(sandbox2)

        sandbox2.restore_snapshot(metadata.snapshot_id)

        # Verify content
        result = sandbox2.exec("cat /home/sandbox/app/verify.txt")
        assert test_content in result.stdout


# ---------------------------------------------------------------------------
# Tests that don't need any sandbox
# ---------------------------------------------------------------------------


@pytest.mark.integration
@requires_all_credentials
class TestSnapshotErrors:
    """Snapshot error handling tests.

    These tests only use SnapshotManager - no sandbox needed.
    """

    @pytest.mark.timeout(10)
    def test_snapshot_not_found(self, spaces_config):
        """Restore non-existent raises error (~2s)."""
        from do_app_sandbox.exceptions import SnapshotNotFoundError
        from do_app_sandbox.snapshot import SnapshotManager

        manager = SnapshotManager(spaces_config=spaces_config)

        with pytest.raises(SnapshotNotFoundError):
            manager.get_snapshot_download_url("nonexistent-snapshot-xyz")
