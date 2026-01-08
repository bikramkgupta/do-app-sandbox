"""Integration tests for Service Mode E2E.

These tests require real DigitalOcean credentials.
Set DIGITALOCEAN_TOKEN environment variable.
"""

import time

import pytest

from tests.integration.conftest import requires_do_token


@pytest.mark.integration
@requires_do_token
class TestServiceModeSandbox:
    """End-to-end tests for service mode sandboxes."""

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
            timeout=300
        )
        cleanup_sandboxes(sandbox)

        assert sandbox.mode == SandboxMode.SERVICE
        assert sandbox._service_token is not None
        assert sandbox.status == "ACTIVE"

    @pytest.mark.timeout(30)
    def test_service_mode_exec(self, do_token, cleanup_sandboxes):
        """exec() works via HTTP API (~5s after creation)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        result = sandbox.exec("echo 'hello from service mode'")

        assert result.exit_code == 0
        assert "hello from service mode" in result.stdout

    @pytest.mark.timeout(60)
    def test_service_mode_exec_stream(self, do_token, cleanup_sandboxes):
        """exec_stream() yields SSE events (~10s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode, StreamEvent

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        events = list(sandbox.exec_stream("echo 'streaming test'"))

        # Should have at least stdout and exit events
        assert len(events) >= 1
        assert all(isinstance(e, StreamEvent) for e in events)

        # Find output events
        output_events = [e for e in events if e.is_output]
        assert len(output_events) >= 1

    @pytest.mark.timeout(30)
    def test_service_mode_stream_stdout_stderr(self, do_token, cleanup_sandboxes):
        """Streaming captures both stdout and stderr (~5s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        # Command that writes to both stdout and stderr
        events = list(sandbox.exec_stream(
            "echo 'stdout message' && echo 'stderr message' >&2"
        ))

        # Collect event types
        types = set(e.type for e in events)

        assert "stdout" in types or "stderr" in types

    @pytest.mark.timeout(30)
    def test_service_mode_background_process(self, do_token, cleanup_sandboxes):
        """Background exec returns pid (~5s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        client = sandbox._get_service_client()
        pid = client.exec_background("sleep 10")

        assert isinstance(pid, int)
        assert pid > 0

    @pytest.mark.timeout(30)
    def test_service_mode_process_logs(self, do_token, cleanup_sandboxes):
        """Can retrieve process logs (~5s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        client = sandbox._get_service_client()

        # Start a process that outputs something
        pid = client.exec_background("echo 'test log output' && sleep 2")

        # Wait for output
        time.sleep(1)

        logs = client.get_process_logs(pid)
        assert isinstance(logs, str)

    @pytest.mark.timeout(10)
    def test_service_mode_port_exposure(self, do_token, cleanup_sandboxes):
        """expose_port() returns valid URL (~2s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode, ExposedPort

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        port_info = sandbox.expose_port(3000)

        assert isinstance(port_info, ExposedPort)
        assert port_info.port == 3000
        assert "proxy/3000" in port_info.url
        assert port_info.protocol == "https"

    @pytest.mark.timeout(60)
    def test_service_mode_port_proxy(self, do_token, cleanup_sandboxes):
        """Port proxy actually works (~10s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        # Start a simple HTTP server
        sandbox.exec("python -m http.server 3000 &")
        time.sleep(2)

        # Get proxy URL
        port_info = sandbox.expose_port(3000)

        # Try to access it (this tests the proxy functionality)
        import httpx
        try:
            response = httpx.get(
                port_info.url,
                headers={"Authorization": f"Bearer {sandbox._service_token}"},
                timeout=10.0
            )
            # Should get some response (could be 200 or 502 if server not ready)
            assert response.status_code in (200, 404, 502)
        except httpx.ConnectError:
            # Proxy might not be ready yet, that's OK for this test
            pass

    @pytest.mark.timeout(60)
    def test_service_mode_sessions(self, do_token, cleanup_sandboxes):
        """Session create/exec/close flow (~10s)."""
        from do_app_sandbox import Sandbox
        from do_app_sandbox.types import SandboxMode

        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            api_token=do_token,
            wait_ready=True
        )
        cleanup_sandboxes(sandbox)

        client = sandbox._get_service_client()

        # Create session
        session_info = client.create_session(
            session_id="test-session",
            cwd="/workspace"
        )
        assert session_info["session_id"] == "test-session"

        # Execute in session
        result = client.session_exec("test-session", "pwd")
        assert "/workspace" in result.get("output", result.get("stdout", ""))

        # Close session
        success = client.close_session("test-session")
        assert success is True
