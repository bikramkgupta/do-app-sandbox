"""Integration tests for Snapshot E2E.

These tests require real DigitalOcean credentials and Spaces.
Set environment variables:
- DIGITALOCEAN_TOKEN
- SPACES_BUCKET, SPACES_REGION, SPACES_ACCESS_KEY, SPACES_SECRET_KEY
"""

import time

import pytest

from tests.integration.conftest import requires_all_credentials


@pytest.mark.integration
@requires_all_credentials
class TestSnapshotBasic:
    """Basic snapshot creation and restoration tests."""

    @pytest.mark.timeout(120)
    def test_create_snapshot_basic(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Create snapshot of /workspace (~30s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SnapshotMetadata

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        # Create some content
        sandbox.exec("echo 'test content' > /workspace/test.txt")

        # Create snapshot
        metadata = sandbox.create_snapshot(
            description="Test snapshot"
        )
        cleanup_snapshots(metadata.snapshot_id)

        assert isinstance(metadata, SnapshotMetadata)
        assert metadata.snapshot_id.startswith("snap-")
        assert metadata.sandbox_image == "python"
        assert metadata.size_bytes > 0

    @pytest.mark.timeout(120)
    def test_create_snapshot_custom_paths(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Snapshot with custom paths (~30s)."""
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        # Create content in specific paths
        sandbox.exec("mkdir -p /workspace/src && echo 'code' > /workspace/src/main.py")

        metadata = sandbox.create_snapshot(
            paths=["/workspace/src"],
            description="Source code only"
        )
        cleanup_snapshots(metadata.snapshot_id)

        assert metadata.paths == ["/workspace/src"]

    @pytest.mark.timeout(180)
    def test_create_snapshot_with_deps(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Snapshot includes node_modules (~45s)."""
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.create(
            image="node",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        # Install a small package
        sandbox.exec("cd /workspace && npm init -y && npm install is-odd")

        # Create snapshot
        metadata = sandbox.create_snapshot(
            description="With dependencies"
        )
        cleanup_snapshots(metadata.snapshot_id)

        # node_modules should be included (size should be > minimal)
        assert metadata.size_bytes > 1000  # Should be larger with deps

    @pytest.mark.timeout(30)
    def test_snapshot_metadata_stored(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Metadata retrievable from Spaces (~5s after creation)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.snapshot import SnapshotManager

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        metadata = sandbox.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        # Retrieve metadata from Spaces
        manager = SnapshotManager(spaces_config=spaces_config)
        retrieved = manager.get_snapshot(metadata.snapshot_id)

        assert retrieved is not None
        assert retrieved.snapshot_id == metadata.snapshot_id
        assert retrieved.sandbox_image == metadata.sandbox_image


@pytest.mark.integration
@requires_all_credentials
class TestSnapshotRestore:
    """Snapshot restoration tests."""

    @pytest.mark.timeout(180)
    def test_restore_snapshot_basic(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Restore snapshot to new sandbox (~30s)."""
        from do_app_sandbox import Sandbox

        # Create first sandbox with content
        sandbox1 = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox1)

        sandbox1.exec("echo 'original content' > /workspace/data.txt")
        metadata = sandbox1.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        # Create second sandbox and restore
        sandbox2 = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox2)

        success = sandbox2.restore_snapshot(metadata.snapshot_id)
        assert success is True

    @pytest.mark.timeout(180)
    def test_restore_preserves_files(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Restored files match original (~10s after restore)."""
        from do_app_sandbox import Sandbox

        # Create sandbox with specific content
        sandbox1 = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox1)

        test_content = "unique-test-content-12345"
        sandbox1.exec(f"echo '{test_content}' > /workspace/verify.txt")
        metadata = sandbox1.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        # Restore to new sandbox
        sandbox2 = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox2)

        sandbox2.restore_snapshot(metadata.snapshot_id)

        # Verify content
        result = sandbox2.exec("cat /workspace/verify.txt")
        assert test_content in result.stdout


@pytest.mark.integration
@requires_all_credentials
class TestSnapshotList:
    """Snapshot listing and filtering tests."""

    @pytest.mark.timeout(30)
    def test_list_snapshots(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """List returns created snapshots (~5s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.snapshot import SnapshotManager

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        # Create snapshot with unique prefix
        snapshot_id = f"snap-list-test-{int(time.time())}"
        metadata = sandbox.create_snapshot(snapshot_id=snapshot_id)
        cleanup_snapshots(metadata.snapshot_id)

        # List and verify
        manager = SnapshotManager(spaces_config=spaces_config)
        snapshots = manager.list_snapshots()

        assert any(s.snapshot_id == snapshot_id for s in snapshots)

    @pytest.mark.timeout(30)
    def test_list_snapshots_filter_image(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """Filter snapshots by image (~5s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.snapshot import SnapshotManager

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        metadata = sandbox.create_snapshot()
        cleanup_snapshots(metadata.snapshot_id)

        manager = SnapshotManager(spaces_config=spaces_config)
        python_snapshots = manager.list_snapshots(image="python")

        assert all(s.sandbox_image == "python" for s in python_snapshots)

    @pytest.mark.timeout(30)
    def test_delete_snapshot(
        self, do_token, spaces_config, cleanup_sandboxes
    ):
        """Delete removes from Spaces (~5s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.snapshot import SnapshotManager

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        metadata = sandbox.create_snapshot()
        snapshot_id = metadata.snapshot_id

        manager = SnapshotManager(spaces_config=spaces_config)

        # Verify exists
        assert manager.snapshot_exists(snapshot_id)

        # Delete
        result = manager.delete_snapshot(snapshot_id)
        assert result is True

        # Verify deleted
        assert not manager.snapshot_exists(snapshot_id)


@pytest.mark.integration
@requires_all_credentials
class TestSnapshotErrors:
    """Snapshot error handling tests."""

    @pytest.mark.timeout(10)
    def test_snapshot_not_found(self, spaces_config):
        """Restore non-existent raises error (~2s)."""
        from do_app_sandbox.snapshot import SnapshotManager
        from do_app_sandbox.exceptions import SnapshotNotFoundError

        manager = SnapshotManager(spaces_config=spaces_config)

        with pytest.raises(SnapshotNotFoundError):
            manager.get_snapshot_download_url("nonexistent-snapshot-xyz")
