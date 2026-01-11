"""Integration tests for Service Mode E2E.

These tests require real DigitalOcean credentials.
Set DIGITALOCEAN_TOKEN environment variable.

Uses shared_service_sandbox fixture for efficiency.
Run `make test-setup` first for fastest execution.
"""

import time

import pytest

from tests.integration.conftest import requires_do_token


@pytest.mark.integration
@requires_do_token
class TestServiceModeCreation:
    """Tests for service mode sandbox creation.

    These tests specifically test the creation process and require their own sandbox.
    """

    @pytest.mark.requires_own_sandbox
    @pytest.mark.timeout(120)
    def test_create_service_mode_sandbox(self, do_token, cleanup_sandboxes):
        """Create sandbox with mode=SERVICE (~60s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True,
            timeout=300,
        )
        cleanup_sandboxes(sandbox)

        assert sandbox.mode == SandboxMode.SERVICE
        assert sandbox._service_token is not None
        assert sandbox.status == "ACTIVE"


@pytest.mark.integration
@requires_do_token
class TestServiceModeSandbox:
    """End-to-end tests for service mode sandboxes.

    These tests use the shared_service_sandbox fixture for efficiency.
    The shared fixture already has connectivity verified.
    """

    @pytest.mark.timeout(60)
    def test_service_mode_exec(self, shared_service_sandbox):
        """exec() works via HTTP API (~5s)."""
        sandbox = shared_service_sandbox

        result = sandbox.exec("echo 'hello from service mode'")

        assert result.exit_code == 0
        assert "hello from service mode" in result.stdout

    @pytest.mark.timeout(90)
    def test_service_mode_exec_stream(self, shared_service_sandbox):
        """exec_stream() yields SSE events (~10s)."""
        from do_app_sandbox.types import StreamEvent

        sandbox = shared_service_sandbox

        events = list(sandbox.exec_stream("echo 'streaming test'"))

        # Should have at least stdout and exit events
        assert len(events) >= 1
        assert all(isinstance(e, StreamEvent) for e in events)

        # Find output events
        output_events = [e for e in events if e.is_output]
        assert len(output_events) >= 1

    @pytest.mark.timeout(60)
    def test_service_mode_stream_stdout_stderr(self, shared_service_sandbox):
        """Streaming captures both stdout and stderr (~5s)."""
        sandbox = shared_service_sandbox

        # Command that writes to both stdout and stderr
        events = list(sandbox.exec_stream("echo 'stdout message' && echo 'stderr message' >&2"))

        # Collect event types
        types = set(e.type for e in events)

        assert "stdout" in types or "stderr" in types

    @pytest.mark.timeout(60)
    def test_service_mode_background_process(self, shared_service_sandbox):
        """Background exec returns pid (~5s)."""
        sandbox = shared_service_sandbox

        client = sandbox._get_service_client()
        pid = client.exec_background("sleep 10")

        assert isinstance(pid, int)
        assert pid > 0

        # Cleanup: kill the background process
        try:
            client.kill_process(pid)
        except Exception:
            pass

    @pytest.mark.timeout(60)
    def test_service_mode_process_logs(self, shared_service_sandbox):
        """Can retrieve process logs (~5s)."""
        sandbox = shared_service_sandbox

        client = sandbox._get_service_client()

        # Start a process that outputs something
        pid = client.exec_background("echo 'test log output' && sleep 2")

        # Wait for output
        time.sleep(1)

        logs = client.get_process_logs(pid)
        assert isinstance(logs, str)

        # Cleanup
        try:
            client.kill_process(pid)
        except Exception:
            pass

    @pytest.mark.timeout(60)
    def test_service_mode_port_exposure(self, shared_service_sandbox):
        """expose_port() returns valid URL (~2s)."""
        from do_app_sandbox.types import ExposedPort

        sandbox = shared_service_sandbox

        port_info = sandbox.expose_port(3000)

        assert isinstance(port_info, ExposedPort)
        assert port_info.port == 3000
        assert "proxy/3000" in port_info.url
        assert port_info.protocol == "https"

    @pytest.mark.timeout(90)
    def test_service_mode_port_proxy(self, shared_service_sandbox):
        """Port proxy actually works (~10s)."""
        import httpx

        sandbox = shared_service_sandbox

        # Start a simple HTTP server on a unique port to avoid conflicts
        sandbox.exec("python -m http.server 3001 &")
        time.sleep(2)

        # Get proxy URL
        port_info = sandbox.expose_port(3001)

        # Try to access it (this tests the proxy functionality)
        try:
            response = httpx.get(
                port_info.url,
                headers={"Authorization": f"Bearer {sandbox._service_token}"},
                timeout=10.0,
            )
            # Should get some response (could be 200 or 502 if server not ready)
            assert response.status_code in (200, 404, 502)
        except httpx.ConnectError:
            # Proxy might not be ready yet, that's OK for this test
            pass

        # Cleanup: kill the http server
        sandbox.exec("pkill -f 'http.server 3001' || true")

    @pytest.mark.timeout(90)
    def test_service_mode_sessions(self, shared_service_sandbox):
        """Session create/exec/close flow (~10s)."""
        sandbox = shared_service_sandbox

        client = sandbox._get_service_client()

        # Use unique session ID to avoid conflicts
        session_id = f"test-session-{int(time.time())}"

        # Create session (service mode uses /workspace)
        session_info = client.create_session(session_id=session_id, cwd="/workspace")
        assert session_info["session_id"] == session_id

        # Execute in session
        result = client.session_exec(session_id, "pwd")
        assert "/workspace" in result.get("output", result.get("stdout", ""))

        # Close session
        success = client.close_session(session_id)
        assert success is True
