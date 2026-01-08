"""Integration tests for Hibernate/Wake E2E.

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
class TestHibernate:
    """Hibernation operation tests."""

    @pytest.mark.timeout(180)
    def test_hibernate_creates_snapshot(
        self, do_token, spaces_config, cleanup_snapshots
    ):
        """hibernate() creates snapshot (~45s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.snapshot import SnapshotManager
        from do_app_sandbox.types import HibernatedSandbox

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )

        # Create some state
        sandbox.exec("echo 'hibernation test' > /workspace/state.txt")

        # Hibernate (this deletes the sandbox)
        hibernated = sandbox.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        assert isinstance(hibernated, HibernatedSandbox)
        assert hibernated.snapshot_id.startswith("hibernate-")

        # Verify snapshot exists
        manager = SnapshotManager(spaces_config=spaces_config)
        assert manager.snapshot_exists(hibernated.snapshot_id)

    @pytest.mark.timeout(180)
    def test_hibernate_deletes_sandbox(
        self, do_token, spaces_config, cleanup_snapshots
    ):
        """hibernate() deletes the app (~10s after hibernate)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.exceptions import SandboxNotFoundError

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        app_id = sandbox.app_id

        hibernated = sandbox.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        # Try to get the sandbox - should be deleted
        with pytest.raises(SandboxNotFoundError):
            Sandbox.get_from_id(app_id, api_token=do_token)

    @pytest.mark.timeout(30)
    def test_hibernate_returns_reference(
        self, do_token, spaces_config, cleanup_snapshots
    ):
        """Returns HibernatedSandbox (~2s verification)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import HibernatedSandbox, SandboxMode

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )

        hibernated = sandbox.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        assert isinstance(hibernated, HibernatedSandbox)
        assert hibernated.image == "python"
        assert hibernated.mode == SandboxMode.WORKER
        assert hibernated.hibernated_at > 0


@pytest.mark.integration
@requires_all_credentials
class TestWake:
    """Wake operation tests."""

    @pytest.mark.timeout(300)
    def test_wake_creates_new_sandbox(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """wake() creates new sandbox (~60s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxState

        # Create and hibernate
        sandbox1 = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        sandbox1.exec("echo 'wake test' > /workspace/wake.txt")

        hibernated = sandbox1.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        # Wake - creates new sandbox
        sandbox2 = Sandbox.wake(
            hibernated,
            api_token=do_token,
            spaces_config=spaces_config
        )
        cleanup_sandboxes(sandbox2)

        assert sandbox2.app_id != sandbox1.app_id  # Different app
        assert sandbox2.state == SandboxState.ACTIVE

    @pytest.mark.timeout(300)
    def test_wake_restores_state(
        self, do_token, spaces_config, cleanup_sandboxes, cleanup_snapshots
    ):
        """wake() restores files (~30s verification)."""
        from do_app_sandbox import Sandbox

        unique_content = f"unique-{int(time.time())}"

        # Create and hibernate
        sandbox1 = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )
        sandbox1.exec(f"echo '{unique_content}' > /workspace/restore-test.txt")

        hibernated = sandbox1.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        # Wake
        sandbox2 = Sandbox.wake(
            hibernated,
            api_token=do_token,
            spaces_config=spaces_config
        )
        cleanup_sandboxes(sandbox2)

        # Verify content restored
        result = sandbox2.exec("cat /workspace/restore-test.txt")
        assert unique_content in result.stdout


@pytest.mark.integration
@requires_all_credentials
class TestHibernationErrors:
    """Hibernation error handling tests."""

    @pytest.mark.timeout(30)
    def test_double_hibernate_error(
        self, do_token, spaces_config, cleanup_snapshots
    ):
        """Can't hibernate twice (~2s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.exceptions import SandboxHibernatedError

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )

        hibernated = sandbox.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        # Second hibernate should fail
        with pytest.raises(SandboxHibernatedError):
            sandbox.hibernate()

    @pytest.mark.timeout(30)
    def test_exec_on_hibernated_error(
        self, do_token, spaces_config, cleanup_snapshots
    ):
        """exec() on hibernated raises (~2s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.exceptions import SandboxHibernatedError

        sandbox = Sandbox.create(
            image="python",
            api_token=do_token,
            spaces_config=spaces_config,
            wait_ready=True
        )

        hibernated = sandbox.hibernate()
        cleanup_snapshots(hibernated.snapshot_id)

        # exec should fail on hibernated sandbox
        with pytest.raises(SandboxHibernatedError):
            sandbox.exec("echo test")
