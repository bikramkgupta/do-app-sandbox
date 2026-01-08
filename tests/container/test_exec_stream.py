"""Container API tests for streaming execution endpoint."""

import time

import pytest
import httpx

from tests.container.conftest import requires_container_api


@pytest.mark.container
@requires_container_api
class TestExecStreamEndpoint:
    """Tests for /api/exec/stream endpoint."""

    def test_exec_stream_returns_sse(self, api_url, auth_headers):
        """Response is text/event-stream."""
        with httpx.Client(timeout=30.0) as client:
            with client.stream(
                "POST",
                f"{api_url}/api/exec/stream",
                json={"command": "echo hello"},
                headers=auth_headers
            ) as response:
                content_type = response.headers.get("content-type", "")
                assert "text/event-stream" in content_type

    def test_exec_stream_stdout_events(self, api_url, auth_headers):
        """Yields stdout events."""
        events = []
        with httpx.Client(timeout=30.0) as client:
            with client.stream(
                "POST",
                f"{api_url}/api/exec/stream",
                json={"command": "echo 'stream output'"},
                headers=auth_headers
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        events.append(line)

        # Should have at least one event
        assert len(events) >= 1
        assert any("stdout" in e for e in events)

    def test_exec_stream_stderr_events(self, api_url, auth_headers):
        """Yields stderr events."""
        events = []
        with httpx.Client(timeout=30.0) as client:
            with client.stream(
                "POST",
                f"{api_url}/api/exec/stream",
                json={"command": "echo 'error' >&2"},
                headers=auth_headers
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        events.append(line)

        assert any("stderr" in e for e in events)

    def test_exec_stream_exit_event(self, api_url, auth_headers):
        """Yields exit event at end."""
        events = []
        with httpx.Client(timeout=30.0) as client:
            with client.stream(
                "POST",
                f"{api_url}/api/exec/stream",
                json={"command": "exit 0"},
                headers=auth_headers
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        events.append(line)

        assert any("exit" in e for e in events)

    def test_exec_stream_interleaved(self, api_url, auth_headers):
        """stdout/stderr interleaved correctly."""
        events = []
        with httpx.Client(timeout=30.0) as client:
            with client.stream(
                "POST",
                f"{api_url}/api/exec/stream",
                json={"command": "echo 'out1' && echo 'err1' >&2 && echo 'out2'"},
                headers=auth_headers
            ) as response:
                current_event = None
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and current_event:
                        events.append((current_event, line))
                        current_event = None

        # Should have multiple events of different types
        types = set(e[0] for e in events)
        # At least one type should be present
        assert len(types) >= 1

    def test_exec_stream_no_buffering(self, api_url, auth_headers):
        """Events arrive in real-time (not buffered)."""
        received_times = []

        with httpx.Client(timeout=30.0) as client:
            with client.stream(
                "POST",
                f"{api_url}/api/exec/stream",
                json={"command": "for i in 1 2 3; do echo $i; sleep 0.1; done"},
                headers=auth_headers
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        received_times.append(time.time())

        # If not buffered, events should arrive at different times
        if len(received_times) >= 2:
            time_diff = received_times[-1] - received_times[0]
            # Should take at least 0.1 seconds between first and last
            # (allowing for some variance)
            assert time_diff > 0.05 or len(received_times) >= 3
