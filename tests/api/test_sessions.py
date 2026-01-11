"""Container API tests for session management."""

import httpx
import pytest

from tests.api.conftest import requires_container_api


@pytest.mark.container
@requires_container_api
class TestSessions:
    """Tests for session management endpoints."""

    def test_create_session(self, api_url, auth_headers, cleanup_sessions):
        """POST /api/sessions creates session."""
        response = httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "test-session-1"},
            headers=auth_headers,
            timeout=10.0,
        )
        assert response.status_code == 200

        data = response.json()
        assert data.get("session_id") == "test-session-1"
        cleanup_sessions("test-session-1")

    def test_create_session_with_env(self, api_url, auth_headers, cleanup_sessions):
        """Session has custom env vars."""
        response = httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "env-session", "env": {"CUSTOM_VAR": "custom-value"}},
            headers=auth_headers,
            timeout=10.0,
        )
        assert response.status_code == 200
        cleanup_sessions("env-session")

        # Execute and check env
        exec_response = httpx.post(
            f"{api_url}/api/sessions/env-session/exec",
            json={"command": "echo $CUSTOM_VAR"},
            headers=auth_headers,
            timeout=10.0,
        )
        output = exec_response.json().get("output", exec_response.json().get("stdout", ""))
        assert "custom-value" in output

    def test_create_session_with_cwd(self, api_url, auth_headers, cleanup_sessions):
        """Session has custom cwd."""
        response = httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "cwd-session", "cwd": "/tmp"},
            headers=auth_headers,
            timeout=10.0,
        )
        assert response.status_code == 200
        cleanup_sessions("cwd-session")

        # Execute and check cwd
        exec_response = httpx.post(
            f"{api_url}/api/sessions/cwd-session/exec",
            json={"command": "pwd"},
            headers=auth_headers,
            timeout=10.0,
        )
        output = exec_response.json().get("output", exec_response.json().get("stdout", ""))
        assert "/tmp" in output

    def test_list_sessions(self, api_url, auth_headers, cleanup_sessions):
        """GET /api/sessions lists all."""
        # Create a session first
        httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "list-test-session"},
            headers=auth_headers,
            timeout=10.0,
        )
        cleanup_sessions("list-test-session")

        # List sessions
        response = httpx.get(f"{api_url}/api/sessions", headers=auth_headers, timeout=10.0)
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        session_ids = [s.get("session_id") for s in data]
        assert "list-test-session" in session_ids

    def test_get_session(self, api_url, auth_headers, cleanup_sessions):
        """GET /api/sessions/{id} returns info."""
        httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "get-test-session"},
            headers=auth_headers,
            timeout=10.0,
        )
        cleanup_sessions("get-test-session")

        response = httpx.get(f"{api_url}/api/sessions/get-test-session", headers=auth_headers, timeout=10.0)
        assert response.status_code == 200

        data = response.json()
        assert data.get("session_id") == "get-test-session"

    def test_session_exec(self, api_url, auth_headers, cleanup_sessions):
        """POST /api/sessions/{id}/exec runs in session."""
        httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "exec-session"},
            headers=auth_headers,
            timeout=10.0,
        )
        cleanup_sessions("exec-session")

        response = httpx.post(
            f"{api_url}/api/sessions/exec-session/exec",
            json={"command": "echo 'session exec test'"},
            headers=auth_headers,
            timeout=10.0,
        )
        assert response.status_code == 200

        output = response.json().get("output", response.json().get("stdout", ""))
        assert "session exec test" in output

    def test_session_state_persists(self, api_url, auth_headers, cleanup_sessions):
        """cd in session persists."""
        httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "state-session"},
            headers=auth_headers,
            timeout=10.0,
        )
        cleanup_sessions("state-session")

        # Change directory
        httpx.post(
            f"{api_url}/api/sessions/state-session/exec",
            json={"command": "cd /tmp"},
            headers=auth_headers,
            timeout=10.0,
        )

        # Check pwd persists
        response = httpx.post(
            f"{api_url}/api/sessions/state-session/exec",
            json={"command": "pwd"},
            headers=auth_headers,
            timeout=10.0,
        )
        output = response.json().get("output", response.json().get("stdout", ""))
        assert "/tmp" in output

    def test_session_env_persists(self, api_url, auth_headers, cleanup_sessions):
        """export in session persists."""
        httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "env-persist-session"},
            headers=auth_headers,
            timeout=10.0,
        )
        cleanup_sessions("env-persist-session")

        # Export variable
        httpx.post(
            f"{api_url}/api/sessions/env-persist-session/exec",
            json={"command": "export MY_PERSIST_VAR=persistent-value"},
            headers=auth_headers,
            timeout=10.0,
        )

        # Check variable persists
        response = httpx.post(
            f"{api_url}/api/sessions/env-persist-session/exec",
            json={"command": "echo $MY_PERSIST_VAR"},
            headers=auth_headers,
            timeout=10.0,
        )
        output = response.json().get("output", response.json().get("stdout", ""))
        assert "persistent-value" in output

    def test_close_session(self, api_url, auth_headers):
        """DELETE /api/sessions/{id} closes."""
        # Create session
        httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "close-session"},
            headers=auth_headers,
            timeout=10.0,
        )

        # Close it
        response = httpx.delete(f"{api_url}/api/sessions/close-session", headers=auth_headers, timeout=10.0)
        assert response.status_code == 200

        data = response.json()
        assert data.get("success") is True

        # Verify closed - should return 404
        get_response = httpx.get(f"{api_url}/api/sessions/close-session", headers=auth_headers, timeout=10.0)
        assert get_response.status_code == 404

    def test_duplicate_session_error(self, api_url, auth_headers, cleanup_sessions):
        """Can't create same ID twice."""
        # Create first
        httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "duplicate-session"},
            headers=auth_headers,
            timeout=10.0,
        )
        cleanup_sessions("duplicate-session")

        # Try to create again
        response = httpx.post(
            f"{api_url}/api/sessions",
            json={"session_id": "duplicate-session"},
            headers=auth_headers,
            timeout=10.0,
        )
        # Should return 409 Conflict or 400 Bad Request
        assert response.status_code in (400, 409)
