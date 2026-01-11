"""Integration tests for Git Operations.

These tests require real DigitalOcean credentials.
Set DIGITALOCEAN_TOKEN environment variable.

Uses shared_worker_sandbox fixture for efficiency.
Run `make test-setup` first for fastest execution.
"""

import os

import pytest

from tests.integration.conftest import requires_do_token


@pytest.mark.integration
@requires_do_token
class TestGitCheckoutPublic:
    """Tests for cloning public repositories.

    All tests use the shared_worker_sandbox fixture for efficiency.
    Each test clones to a different path to avoid conflicts.
    """

    @pytest.mark.timeout(120)
    def test_git_checkout_public_repo(self, shared_worker_sandbox):
        """Clone public GitHub repo (~15s)."""
        sandbox = shared_worker_sandbox

        # Clone a small public repo
        result = sandbox.git_checkout(
            url="https://github.com/octocat/Hello-World.git", path="/home/sandbox/app/hello-world"
        )

        assert result.success or result.exit_code == 0

        # Verify files exist
        ls_result = sandbox.exec("ls /home/sandbox/app/hello-world")
        assert "README" in ls_result.stdout

    @pytest.mark.timeout(120)
    def test_git_checkout_branch(self, shared_worker_sandbox):
        """Clone specific branch (~15s)."""
        sandbox = shared_worker_sandbox

        # Clone a specific branch
        result = sandbox.git_checkout(
            url="https://github.com/octocat/Hello-World.git",
            path="/home/sandbox/app/hw-master",
            branch="master",
        )

        assert result.success or result.exit_code == 0

        # Verify correct branch
        branch_result = sandbox.exec("cd /home/sandbox/app/hw-master && git branch")
        assert "master" in branch_result.stdout

    @pytest.mark.timeout(90)
    def test_git_checkout_shallow(self, shared_worker_sandbox):
        """Shallow clone (depth=1) (~10s)."""
        sandbox = shared_worker_sandbox

        result = sandbox.git_checkout(
            url="https://github.com/octocat/Hello-World.git", path="/home/sandbox/app/shallow", depth=1
        )

        assert result.success or result.exit_code == 0

        # Verify shallow clone
        log_result = sandbox.exec("cd /home/sandbox/app/shallow && git log --oneline | wc -l")
        commit_count = int(log_result.stdout.strip())
        assert commit_count == 1  # Shallow clone has 1 commit

    @pytest.mark.timeout(120)
    def test_git_checkout_custom_path(self, shared_worker_sandbox):
        """Clone to custom path (~15s)."""
        sandbox = shared_worker_sandbox

        custom_path = "/home/sandbox/app/projects/my-repo"

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

    @pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="Requires GITHUB_TOKEN for authenticated git access",
    )
    @pytest.mark.timeout(120)
    def test_git_checkout_with_token(self, shared_worker_sandbox):
        """Clone with PAT using credentials (~15s).

        Uses GITHUB_PRIVATE_REPO env var if set, otherwise tests with a public repo
        to verify the credentials flow works.
        """
        from do_app_sandbox.types import GitCredentials

        sandbox = shared_worker_sandbox
        github_token = os.environ.get("GITHUB_TOKEN")

        credentials = GitCredentials(username="git", token=github_token)

        # Use private repo from env, or fall back to public repo to test credentials flow
        repo_url = os.environ.get(
            "GITHUB_PRIVATE_REPO",
            "https://github.com/octocat/Hello-World.git",  # Public fallback
        )

        result = sandbox.git_checkout(
            url=repo_url,
            path="/home/sandbox/app/auth-clone",
            credentials=credentials,
        )

        assert result.success or result.exit_code == 0

        # Verify clone worked
        check = sandbox.exec("test -d /home/sandbox/app/auth-clone/.git && echo exists")
        assert "exists" in check.stdout
