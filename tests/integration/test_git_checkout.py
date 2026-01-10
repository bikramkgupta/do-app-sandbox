"""Integration tests for Git Operations.

These tests require real DigitalOcean credentials.
Set DIGITALOCEAN_TOKEN environment variable.
"""

import pytest

from tests.integration.conftest import requires_do_token


@pytest.mark.integration
@requires_do_token
class TestGitCheckoutPublic:
    """Tests for cloning public repositories."""

    @pytest.mark.timeout(120)
    def test_git_checkout_public_repo(self, do_token, cleanup_sandboxes):
        """Clone public GitHub repo (~15s)."""
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.create(image="python", api_token=do_token, wait_ready=True)
        cleanup_sandboxes(sandbox)

        # Clone a small public repo
        result = sandbox.git_checkout(url="https://github.com/octocat/Hello-World.git", path="/workspace/hello-world")

        assert result.success or result.exit_code == 0

        # Verify files exist
        ls_result = sandbox.exec("ls /workspace/hello-world")
        assert "README" in ls_result.stdout

    @pytest.mark.timeout(120)
    def test_git_checkout_branch(self, do_token, cleanup_sandboxes):
        """Clone specific branch (~15s)."""
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.create(image="python", api_token=do_token, wait_ready=True)
        cleanup_sandboxes(sandbox)

        # Clone a specific branch
        result = sandbox.git_checkout(
            url="https://github.com/octocat/Hello-World.git",
            path="/workspace/hw-master",
            branch="master",
        )

        assert result.success or result.exit_code == 0

        # Verify correct branch
        branch_result = sandbox.exec("cd /workspace/hw-master && git branch")
        assert "master" in branch_result.stdout

    @pytest.mark.timeout(90)
    def test_git_checkout_shallow(self, do_token, cleanup_sandboxes):
        """Shallow clone (depth=1) (~10s)."""
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.create(image="python", api_token=do_token, wait_ready=True)
        cleanup_sandboxes(sandbox)

        result = sandbox.git_checkout(
            url="https://github.com/octocat/Hello-World.git", path="/workspace/shallow", depth=1
        )

        assert result.success or result.exit_code == 0

        # Verify shallow clone
        log_result = sandbox.exec("cd /workspace/shallow && git log --oneline | wc -l")
        commit_count = int(log_result.stdout.strip())
        assert commit_count == 1  # Shallow clone has 1 commit

    @pytest.mark.timeout(120)
    def test_git_checkout_custom_path(self, do_token, cleanup_sandboxes):
        """Clone to custom path (~15s)."""
        from do_app_sandbox import Sandbox

        sandbox = Sandbox.create(image="python", api_token=do_token, wait_ready=True)
        cleanup_sandboxes(sandbox)

        custom_path = "/workspace/projects/my-repo"

        result = sandbox.git_checkout(url="https://github.com/octocat/Hello-World.git", path=custom_path)

        assert result.success or result.exit_code == 0

        # Verify path
        check = sandbox.exec(f"test -d {custom_path}/.git && echo exists")
        assert "exists" in check.stdout


@pytest.mark.integration
@requires_do_token
class TestGitCheckoutAuth:
    """Tests for authenticated git operations.

    Note: These tests require a GitHub PAT to be set as GITHUB_TOKEN.
    Skip if not available.
    """

    @pytest.mark.skip(reason="Requires GITHUB_TOKEN for private repo access")
    @pytest.mark.timeout(120)
    def test_git_checkout_with_token(self, do_token, cleanup_sandboxes):
        """Clone with PAT (private repo) (~15s)."""
        import os

        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import GitCredentials

        github_token = os.environ.get("GITHUB_TOKEN")
        if not github_token:
            pytest.skip("GITHUB_TOKEN not set")

        sandbox = Sandbox.create(image="python", api_token=do_token, wait_ready=True)
        cleanup_sandboxes(sandbox)

        credentials = GitCredentials(username="git", token=github_token)

        # This would need a real private repo URL
        result = sandbox.git_checkout(
            url="https://github.com/your-org/private-repo.git",
            path="/workspace/private",
            credentials=credentials,
        )

        # If the repo exists and token is valid, this should succeed
        assert result.exit_code == 0
