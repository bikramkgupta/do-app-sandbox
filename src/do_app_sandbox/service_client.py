"""HTTP client for service-mode sandboxes.

This module provides sync and async clients for communicating with
sandboxes deployed in service mode via HTTP/SSE.
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

try:
    import httpx
except ImportError:
    httpx = None  # Optional dependency

from .exceptions import (
    CommandExecutionError,
    CommandTimeoutError,
    ServiceConnectionError,
)
from .types import CommandResult, ProcessInfo, StreamEvent


class SandboxServiceClient:
    """Synchronous HTTP client for service-mode sandboxes."""

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        """Initialize the service client.

        Args:
            base_url: Base URL of the sandbox service (e.g., https://app-xxx.ondigitalocean.app)
            token: API token for authentication
            timeout: Default timeout for requests in seconds
        """
        if httpx is None:
            raise ImportError(
                "httpx is required for service mode. Install with: pip install httpx"
            )

        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._headers = {"Authorization": f"Bearer {token}"}

    def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Make an HTTP request to the sandbox service."""
        url = f"{self._base_url}{path}"
        timeout = timeout or self._timeout

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Failed to connect to sandbox: {e}")
        except httpx.TimeoutException as e:
            raise CommandTimeoutError(f"Request timed out: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ServiceConnectionError("Invalid API token")
            elif e.response.status_code == 403:
                raise ServiceConnectionError("Access denied")
            elif e.response.status_code == 408:
                raise CommandTimeoutError("Command timed out")
            else:
                raise CommandExecutionError(f"HTTP error {e.response.status_code}: {e}")

    def health(self) -> Dict[str, Any]:
        """Check sandbox health.

        Returns:
            Health status dict
        """
        response = self._request("GET", "/health", timeout=10.0)
        return response.json()

    def exec(
        self,
        command: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace",
        timeout: int = 120,
    ) -> CommandResult:
        """Execute a command and return the result.

        Args:
            command: Shell command to execute
            env: Environment variables
            cwd: Working directory
            timeout: Command timeout in seconds

        Returns:
            CommandResult with stdout, stderr, exit_code
        """
        response = self._request(
            "POST",
            "/api/exec",
            json_data={
                "command": command,
                "env": env,
                "cwd": cwd,
                "timeout": timeout,
            },
            timeout=timeout + 10,  # Extra buffer for HTTP overhead
        )
        data = response.json()
        return CommandResult(
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", -1),
        )

    def exec_stream(
        self,
        command: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace",
        timeout: int = 120,
    ) -> Generator[StreamEvent, None, None]:
        """Execute a command with streaming output via SSE.

        Args:
            command: Shell command to execute
            env: Environment variables
            cwd: Working directory
            timeout: Command timeout in seconds

        Yields:
            StreamEvent objects for stdout, stderr, exit, error
        """
        url = f"{self._base_url}/api/exec/stream"

        try:
            with httpx.Client(timeout=None) as client:
                with client.stream(
                    "POST",
                    url,
                    json={
                        "command": command,
                        "env": env,
                        "cwd": cwd,
                        "timeout": timeout,
                    },
                    headers=self._headers,
                ) as response:
                    response.raise_for_status()

                    event_type = "stdout"
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if line.startswith("event: "):
                            event_type = line[7:].strip()
                        elif line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                yield StreamEvent(
                                    type=event_type,
                                    data=data.get("line", data.get("code", "")),
                                    timestamp=data.get("timestamp", time.time()),
                                )
                            except json.JSONDecodeError:
                                pass
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Failed to connect to sandbox: {e}")
        except httpx.HTTPStatusError as e:
            raise CommandExecutionError(f"Streaming failed: {e}")

    def exec_background(
        self,
        command: str,
        cwd: str = "/workspace",
        env: Optional[Dict[str, str]] = None,
    ) -> int:
        """Start a background process.

        Args:
            command: Shell command to execute
            cwd: Working directory
            env: Environment variables

        Returns:
            Process ID (PID)
        """
        response = self._request(
            "POST",
            "/api/exec/background",
            json_data={"command": command, "cwd": cwd, "env": env},
        )
        data = response.json()
        return data.get("pid", 0)

    def list_processes(self) -> List[ProcessInfo]:
        """List tracked background processes.

        Returns:
            List of ProcessInfo objects
        """
        response = self._request("GET", "/api/processes")
        data = response.json()
        return [
            ProcessInfo(
                pid=p.get("pid", 0),
                command=p.get("command", ""),
                status=p.get("status", "unknown"),
            )
            for p in data
        ]

    def get_process_logs(self, pid: int, tail: Optional[int] = None) -> str:
        """Get logs from a background process.

        Args:
            pid: Process ID
            tail: Only return last N lines

        Returns:
            Log content
        """
        params = f"?tail={tail}" if tail else ""
        response = self._request("GET", f"/api/processes/{pid}/logs{params}")
        data = response.json()
        return data.get("logs", "")

    def stream_process_logs(self, pid: int) -> Generator[str, None, None]:
        """Stream logs from a background process.

        Args:
            pid: Process ID

        Yields:
            Log lines
        """
        url = f"{self._base_url}/api/processes/{pid}/logs/stream"

        try:
            with httpx.Client(timeout=None) as client:
                with client.stream("GET", url, headers=self._headers) as response:
                    response.raise_for_status()

                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                yield data.get("line", "")
                            except json.JSONDecodeError:
                                pass
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Failed to connect to sandbox: {e}")

    def kill_process(self, pid: int, signal: int = 15) -> bool:
        """Kill a background process.

        Args:
            pid: Process ID
            signal: Signal to send (default: SIGTERM)

        Returns:
            True if successful
        """
        response = self._request(
            "POST",
            f"/api/processes/{pid}/kill",
            json_data={"signal": signal},
        )
        data = response.json()
        return data.get("success", False)

    # Session management

    def create_session(
        self,
        session_id: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace",
    ) -> Dict[str, Any]:
        """Create a new persistent session.

        Args:
            session_id: Unique session identifier
            env: Initial environment variables
            cwd: Initial working directory

        Returns:
            Session info dict
        """
        response = self._request(
            "POST",
            "/api/sessions",
            json_data={"session_id": session_id, "env": env, "cwd": cwd},
        )
        return response.json()

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session info.

        Args:
            session_id: Session identifier

        Returns:
            Session info dict
        """
        response = self._request("GET", f"/api/sessions/{session_id}")
        return response.json()

    def session_exec(
        self, session_id: str, command: str, timeout: int = 120
    ) -> Dict[str, Any]:
        """Execute command in a session.

        Args:
            session_id: Session identifier
            command: Command to execute
            timeout: Command timeout

        Returns:
            Execution result dict
        """
        response = self._request(
            "POST",
            f"/api/sessions/{session_id}/exec",
            json_data={"command": command, "timeout": timeout},
            timeout=timeout + 10,
        )
        return response.json()

    def close_session(self, session_id: str) -> bool:
        """Close a session.

        Args:
            session_id: Session identifier

        Returns:
            True if successful
        """
        response = self._request("DELETE", f"/api/sessions/{session_id}")
        data = response.json()
        return data.get("success", False)


class AsyncSandboxServiceClient:
    """Asynchronous HTTP client for service-mode sandboxes."""

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        """Initialize the async service client.

        Args:
            base_url: Base URL of the sandbox service
            token: API token for authentication
            timeout: Default timeout for requests in seconds
        """
        if httpx is None:
            raise ImportError(
                "httpx is required for service mode. Install with: pip install httpx"
            )

        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Make an async HTTP request to the sandbox service."""
        url = f"{self._base_url}{path}"
        timeout = timeout or self._timeout

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    headers=self._headers,
                )
                response.raise_for_status()
                return response
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Failed to connect to sandbox: {e}")
        except httpx.TimeoutException as e:
            raise CommandTimeoutError(f"Request timed out: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ServiceConnectionError("Invalid API token")
            elif e.response.status_code == 403:
                raise ServiceConnectionError("Access denied")
            elif e.response.status_code == 408:
                raise CommandTimeoutError("Command timed out")
            else:
                raise CommandExecutionError(f"HTTP error {e.response.status_code}: {e}")

    async def health(self) -> Dict[str, Any]:
        """Check sandbox health."""
        response = await self._request("GET", "/health", timeout=10.0)
        return response.json()

    async def exec(
        self,
        command: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace",
        timeout: int = 120,
    ) -> CommandResult:
        """Execute a command and return the result."""
        response = await self._request(
            "POST",
            "/api/exec",
            json_data={
                "command": command,
                "env": env,
                "cwd": cwd,
                "timeout": timeout,
            },
            timeout=timeout + 10,
        )
        data = response.json()
        return CommandResult(
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", -1),
        )

    async def exec_stream(
        self,
        command: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace",
        timeout: int = 120,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute a command with streaming output via SSE."""
        url = f"{self._base_url}/api/exec/stream"

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    url,
                    json={
                        "command": command,
                        "env": env,
                        "cwd": cwd,
                        "timeout": timeout,
                    },
                    headers=self._headers,
                ) as response:
                    response.raise_for_status()

                    event_type = "stdout"
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("event: "):
                            event_type = line[7:].strip()
                        elif line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                yield StreamEvent(
                                    type=event_type,
                                    data=data.get("line", data.get("code", "")),
                                    timestamp=data.get("timestamp", time.time()),
                                )
                            except json.JSONDecodeError:
                                pass
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Failed to connect to sandbox: {e}")
        except httpx.HTTPStatusError as e:
            raise CommandExecutionError(f"Streaming failed: {e}")

    async def exec_background(
        self,
        command: str,
        cwd: str = "/workspace",
        env: Optional[Dict[str, str]] = None,
    ) -> int:
        """Start a background process."""
        response = await self._request(
            "POST",
            "/api/exec/background",
            json_data={"command": command, "cwd": cwd, "env": env},
        )
        data = response.json()
        return data.get("pid", 0)

    async def list_processes(self) -> List[ProcessInfo]:
        """List tracked background processes."""
        response = await self._request("GET", "/api/processes")
        data = response.json()
        return [
            ProcessInfo(
                pid=p.get("pid", 0),
                command=p.get("command", ""),
                status=p.get("status", "unknown"),
            )
            for p in data
        ]

    async def get_process_logs(self, pid: int, tail: Optional[int] = None) -> str:
        """Get logs from a background process."""
        params = f"?tail={tail}" if tail else ""
        response = await self._request("GET", f"/api/processes/{pid}/logs{params}")
        data = response.json()
        return data.get("logs", "")

    async def stream_process_logs(self, pid: int) -> AsyncGenerator[str, None]:
        """Stream logs from a background process."""
        url = f"{self._base_url}/api/processes/{pid}/logs/stream"

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url, headers=self._headers) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                yield data.get("line", "")
                            except json.JSONDecodeError:
                                pass
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Failed to connect to sandbox: {e}")

    async def kill_process(self, pid: int, signal: int = 15) -> bool:
        """Kill a background process."""
        response = await self._request(
            "POST",
            f"/api/processes/{pid}/kill",
            json_data={"signal": signal},
        )
        data = response.json()
        return data.get("success", False)

    async def create_session(
        self,
        session_id: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace",
    ) -> Dict[str, Any]:
        """Create a new persistent session."""
        response = await self._request(
            "POST",
            "/api/sessions",
            json_data={"session_id": session_id, "env": env, "cwd": cwd},
        )
        return response.json()

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session info."""
        response = await self._request("GET", f"/api/sessions/{session_id}")
        return response.json()

    async def session_exec(
        self, session_id: str, command: str, timeout: int = 120
    ) -> Dict[str, Any]:
        """Execute command in a session."""
        response = await self._request(
            "POST",
            f"/api/sessions/{session_id}/exec",
            json_data={"command": command, "timeout": timeout},
            timeout=timeout + 10,
        )
        return response.json()

    async def close_session(self, session_id: str) -> bool:
        """Close a session."""
        response = await self._request("DELETE", f"/api/sessions/{session_id}")
        data = response.json()
        return data.get("success", False)
