"""Container API tests for command execution endpoint."""

import httpx
import pytest

from tests.api.conftest import requires_container_api


@pytest.mark.container
@requires_container_api
class TestExecEndpoint:
    """Tests for /api/exec endpoint."""

    def test_exec_simple_command(self, api_url, auth_headers):
        """POST /api/exec runs command."""
        response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo hello"},
            headers=auth_headers,
            timeout=30.0,
        )
        assert response.status_code == 200

    def test_exec_returns_stdout(self, api_url, auth_headers):
        """Captures stdout correctly."""
        response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo 'test output'"},
            headers=auth_headers,
            timeout=30.0,
        )
        data = response.json()

        assert "stdout" in data
        assert "test output" in data["stdout"]

    def test_exec_returns_stderr(self, api_url, auth_headers):
        """Captures stderr correctly."""
        response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo 'error message' >&2"},
            headers=auth_headers,
            timeout=30.0,
        )
        data = response.json()

        assert "stderr" in data
        assert "error message" in data["stderr"]

    def test_exec_returns_exit_code(self, api_url, auth_headers):
        """Returns correct exit code."""
        # Successful command
        response = httpx.post(f"{api_url}/api/exec", json={"command": "exit 0"}, headers=auth_headers, timeout=30.0)
        assert response.json().get("exit_code") == 0

        # Failed command
        response = httpx.post(f"{api_url}/api/exec", json={"command": "exit 42"}, headers=auth_headers, timeout=30.0)
        assert response.json().get("exit_code") == 42

    def test_exec_with_env(self, api_url, auth_headers):
        """Environment variables work."""
        response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo $MY_VAR", "env": {"MY_VAR": "custom-value-123"}},
            headers=auth_headers,
            timeout=30.0,
        )
        data = response.json()

        assert "custom-value-123" in data.get("stdout", "")

    def test_exec_with_cwd(self, api_url, auth_headers):
        """Working directory works."""
        response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "pwd", "cwd": "/tmp"},
            headers=auth_headers,
            timeout=30.0,
        )
        data = response.json()

        assert "/tmp" in data.get("stdout", "")

    def test_exec_timeout(self, api_url, auth_headers):
        """Times out long commands."""
        response = httpx.post(
            f"{api_url}/api/exec",
            json={
                "command": "sleep 10",
                "timeout": 1,  # 1 second timeout
            },
            headers=auth_headers,
            timeout=30.0,
        )

        # Should either timeout (408) or return error
        assert response.status_code in (200, 408)
        if response.status_code == 200:
            data = response.json()
            # Either exit_code is non-zero or there's an error
            assert data.get("exit_code", 0) != 0 or "timeout" in data.get("stderr", "").lower()

    def test_exec_requires_auth(self, api_url):
        """Returns 401 without token."""
        response = httpx.post(f"{api_url}/api/exec", json={"command": "echo test"}, timeout=10.0)
        assert response.status_code in (401, 403)

    def test_exec_invalid_token(self, api_url):
        """Returns 403 with bad token."""
        response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "echo test"},
            headers={"Authorization": "Bearer invalid-token-xyz"},
            timeout=10.0,
        )
        assert response.status_code in (401, 403)
