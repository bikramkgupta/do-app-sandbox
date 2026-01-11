"""Integration tests for basic SDK operations.

Uses shared_worker_sandbox fixture for fast execution.
Run `make test-setup` first for best performance.
"""

import pytest

from tests.integration.conftest import requires_do_token


@pytest.mark.integration
@requires_do_token
class TestBasicWorkflow:
    """Basic SDK workflow tests using shared sandbox."""

    @pytest.mark.timeout(60)
    def test_exec_and_exit_codes(self, shared_worker_sandbox):
        """Test command execution and exit code capture."""
        sandbox = shared_worker_sandbox

        # Test successful command
        result = sandbox.exec("python3 --version")
        assert result.success, f"Python version command failed: {result.stderr}"
        assert "Python" in result.stdout

        # Test exit code capture for failed command
        result = sandbox.exec("ls /nonexistent_path_12345")
        assert result.exit_code != 0, "Should have non-zero exit code for missing path"

    @pytest.mark.timeout(60)
    def test_file_operations(self, shared_worker_sandbox):
        """Test file write, read, and script execution."""
        sandbox = shared_worker_sandbox

        # Write a test script
        test_content = "print('Hello from Sandbox SDK!')"
        sandbox.filesystem.write_file("/tmp/test_workflow_script.py", test_content)

        # Read it back
        read_content = sandbox.filesystem.read_file("/tmp/test_workflow_script.py")
        assert "Hello from Sandbox SDK" in read_content, "Content mismatch"

        # Execute it
        result = sandbox.exec("python3 /tmp/test_workflow_script.py")
        assert "Hello from Sandbox SDK" in result.stdout, "Script output mismatch"

        # Cleanup
        sandbox.exec("rm -f /tmp/test_workflow_script.py")

    @pytest.mark.timeout(60)
    def test_directory_operations(self, shared_worker_sandbox):
        """Test directory creation and listing."""
        sandbox = shared_worker_sandbox

        # Create nested directory
        sandbox.filesystem.mkdir("/tmp/test_workflow_dir/subdir", recursive=True)
        assert sandbox.filesystem.is_dir("/tmp/test_workflow_dir"), "Directory not created"

        # List directory
        files = sandbox.filesystem.list_dir("/tmp")
        assert len(files) >= 1, "Should have at least one item in /tmp"

        # Cleanup
        sandbox.exec("rm -rf /tmp/test_workflow_dir")
