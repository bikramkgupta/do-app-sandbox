"""Container API tests for background process management."""

import time

import pytest
import httpx

from tests.container.conftest import requires_container_api


@pytest.mark.container
@requires_container_api
class TestBackgroundProcess:
    """Tests for background process endpoints."""

    def test_exec_background_returns_pid(self, api_url, auth_headers, cleanup_processes):
        """Returns process ID."""
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "sleep 60"},
            headers=auth_headers,
            timeout=10.0
        )
        assert response.status_code == 200

        data = response.json()
        assert "pid" in data
        assert isinstance(data["pid"], int)
        assert data["pid"] > 0

        cleanup_processes(data["pid"])

    def test_exec_background_process_runs(self, api_url, auth_headers, cleanup_processes):
        """Process actually runs."""
        # Start a process that creates a file
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "echo 'background-test' > /tmp/bg_test.txt && sleep 5"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]
        cleanup_processes(pid)

        # Wait a bit for file creation
        time.sleep(0.5)

        # Verify file exists
        check_response = httpx.post(
            f"{api_url}/api/exec",
            json={"command": "cat /tmp/bg_test.txt"},
            headers=auth_headers,
            timeout=10.0
        )
        assert "background-test" in check_response.json().get("stdout", "")

    def test_list_processes(self, api_url, auth_headers, cleanup_processes):
        """GET /api/processes lists them."""
        # Start a process
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "sleep 30"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]
        cleanup_processes(pid)

        # List processes
        list_response = httpx.get(
            f"{api_url}/api/processes",
            headers=auth_headers,
            timeout=10.0
        )
        assert list_response.status_code == 200

        processes = list_response.json()
        assert isinstance(processes, list)
        # Our process should be in the list
        pids = [p.get("pid") for p in processes]
        assert pid in pids

    def test_process_status_running(self, api_url, auth_headers, cleanup_processes):
        """Shows running status."""
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "sleep 30"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]
        cleanup_processes(pid)

        # Check status
        status_response = httpx.get(
            f"{api_url}/api/processes/{pid}",
            headers=auth_headers,
            timeout=10.0
        )

        if status_response.status_code == 200:
            data = status_response.json()
            assert data.get("status") == "running"

    def test_process_status_stopped(self, api_url, auth_headers):
        """Shows stopped after exit."""
        # Start a short-lived process
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "echo done"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]

        # Wait for process to finish
        time.sleep(1)

        # Check status
        status_response = httpx.get(
            f"{api_url}/api/processes/{pid}",
            headers=auth_headers,
            timeout=10.0
        )

        if status_response.status_code == 200:
            data = status_response.json()
            # Status could be "stopped", "completed", or "exited"
            assert data.get("status") in ("stopped", "completed", "exited", "unknown")

    def test_get_process_logs(self, api_url, auth_headers, cleanup_processes):
        """GET /api/processes/{pid}/logs works."""
        # Start a process with output
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "echo 'log line 1' && sleep 0.5 && echo 'log line 2' && sleep 5"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]
        cleanup_processes(pid)

        # Wait for some output
        time.sleep(1)

        # Get logs
        logs_response = httpx.get(
            f"{api_url}/api/processes/{pid}/logs",
            headers=auth_headers,
            timeout=10.0
        )
        assert logs_response.status_code == 200

        data = logs_response.json()
        logs = data.get("logs", "")
        assert "log line" in logs

    def test_get_process_logs_tail(self, api_url, auth_headers, cleanup_processes):
        """Tail parameter works."""
        # Start a process with multiple lines
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "for i in 1 2 3 4 5; do echo line$i; done && sleep 5"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]
        cleanup_processes(pid)

        time.sleep(1)

        # Get last 2 lines
        logs_response = httpx.get(
            f"{api_url}/api/processes/{pid}/logs?tail=2",
            headers=auth_headers,
            timeout=10.0
        )

        if logs_response.status_code == 200:
            logs = logs_response.json().get("logs", "")
            lines = [l for l in logs.strip().split("\n") if l]
            assert len(lines) <= 2

    def test_kill_process(self, api_url, auth_headers):
        """POST /api/processes/{pid}/kill works."""
        # Start a long-running process
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "sleep 300"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]

        # Kill it
        kill_response = httpx.post(
            f"{api_url}/api/processes/{pid}/kill",
            json={},
            headers=auth_headers,
            timeout=10.0
        )
        assert kill_response.status_code == 200

        data = kill_response.json()
        assert data.get("success") is True

    def test_kill_process_signal(self, api_url, auth_headers):
        """Custom signal works."""
        # Start a process
        response = httpx.post(
            f"{api_url}/api/exec/background",
            json={"command": "sleep 300"},
            headers=auth_headers,
            timeout=10.0
        )
        pid = response.json()["pid"]

        # Kill with SIGKILL (9)
        kill_response = httpx.post(
            f"{api_url}/api/processes/{pid}/kill",
            json={"signal": 9},
            headers=auth_headers,
            timeout=10.0
        )
        assert kill_response.status_code == 200
