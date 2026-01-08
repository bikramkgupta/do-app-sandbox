"""Tests for service_client.py - HTTP Client Tests."""

import json
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Mock httpx before importing service_client
httpx_mock = MagicMock()


class TestSandboxServiceClient:
    """Tests for synchronous SandboxServiceClient."""

    @pytest.fixture
    def mock_httpx(self):
        """Fixture to mock httpx module."""
        with patch.dict("sys.modules", {"httpx": httpx_mock}):
            # Re-import to get mocked version
            from do_app_sandbox import service_client
            # Reload to pick up the mock
            import importlib
            importlib.reload(service_client)
            yield httpx_mock
            # Restore
            importlib.reload(service_client)

    def test_client_initialization(self):
        """Client stores base_url and token."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="test-token-123",
                timeout=60.0
            )

            assert client._base_url == "https://sandbox.example.com"
            assert client._token == "test-token-123"
            assert client._timeout == 60.0

    def test_client_strips_trailing_slash(self):
        """Client strips trailing slash from base_url."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com/",
                token="token"
            )

            assert client._base_url == "https://sandbox.example.com"

    def test_client_headers_set(self):
        """Authorization header is set correctly."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="my-secret-token"
            )

            assert client._headers == {"Authorization": "Bearer my-secret-token"}

    def test_exec_request_format(self):
        """exec() sends correct JSON payload."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient

            # Setup mock response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "stdout": "output",
                "stderr": "",
                "exit_code": 0
            }
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.request.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_httpx.Client.return_value = mock_client_instance

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="token"
            )

            result = client.exec(
                command="echo hello",
                env={"FOO": "bar"},
                cwd="/app",
                timeout=30
            )

            # Verify request was made with correct payload
            mock_client_instance.request.assert_called_once()
            call_args = mock_client_instance.request.call_args
            assert call_args.kwargs["method"] == "POST"
            assert "/api/exec" in call_args.kwargs["url"]
            assert call_args.kwargs["json"]["command"] == "echo hello"
            assert call_args.kwargs["json"]["env"] == {"FOO": "bar"}
            assert call_args.kwargs["json"]["cwd"] == "/app"
            assert call_args.kwargs["json"]["timeout"] == 30

    def test_exec_response_parsing(self):
        """exec() parses CommandResult correctly."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient
            from do_app_sandbox.types import CommandResult

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "stdout": "Hello, World!",
                "stderr": "warning message",
                "exit_code": 0
            }
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.request.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_httpx.Client.return_value = mock_client_instance

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="token"
            )

            result = client.exec("test command")

            assert isinstance(result, CommandResult)
            assert result.stdout == "Hello, World!"
            assert result.stderr == "warning message"
            assert result.exit_code == 0

    def test_exec_background_returns_pid(self):
        """exec_background() returns process ID."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient

            mock_response = MagicMock()
            mock_response.json.return_value = {"pid": 12345}
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.request.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_httpx.Client.return_value = mock_client_instance

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="token"
            )

            pid = client.exec_background("python server.py")

            assert pid == 12345

    def test_list_processes_parsing(self):
        """list_processes() parses response correctly."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient
            from do_app_sandbox.types import ProcessInfo

            mock_response = MagicMock()
            mock_response.json.return_value = [
                {"pid": 123, "command": "python app.py", "status": "running"},
                {"pid": 456, "command": "node server.js", "status": "stopped"}
            ]
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.request.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_httpx.Client.return_value = mock_client_instance

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="token"
            )

            processes = client.list_processes()

            assert len(processes) == 2
            assert all(isinstance(p, ProcessInfo) for p in processes)
            assert processes[0].pid == 123
            assert processes[0].command == "python app.py"
            assert processes[1].status == "stopped"

    def test_session_create_response(self):
        """create_session() returns session info."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "session_id": "my-session",
                "cwd": "/workspace",
                "created_at": time.time()
            }
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.request.return_value = mock_response
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_httpx.Client.return_value = mock_client_instance

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="token"
            )

            result = client.create_session(
                session_id="my-session",
                env={"PATH": "/usr/bin"},
                cwd="/workspace"
            )

            assert result["session_id"] == "my-session"


class TestAsyncSandboxServiceClient:
    """Tests for asynchronous AsyncSandboxServiceClient."""

    def test_async_client_initialization(self):
        """AsyncSandboxServiceClient stores correct values."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import AsyncSandboxServiceClient

            client = AsyncSandboxServiceClient(
                base_url="https://async.example.com",
                token="async-token",
                timeout=90.0
            )

            assert client._base_url == "https://async.example.com"
            assert client._token == "async-token"
            assert client._timeout == 90.0
            assert client._headers == {"Authorization": "Bearer async-token"}


class TestSSEEventParsing:
    """Tests for SSE event parsing in exec_stream."""

    def test_parse_stdout_event(self):
        """Correctly parses stdout SSE events."""
        # This tests the parsing logic conceptually
        from do_app_sandbox.types import StreamEvent

        # Simulated event data
        event_type = "stdout"
        event_data = {"line": "Hello, World!", "timestamp": 1234567890.0}

        event = StreamEvent(
            type=event_type,
            data=event_data.get("line", ""),
            timestamp=event_data.get("timestamp", time.time())
        )

        assert event.type == "stdout"
        assert event.data == "Hello, World!"
        assert event.is_output is True

    def test_parse_stderr_event(self):
        """Correctly parses stderr SSE events."""
        from do_app_sandbox.types import StreamEvent

        event = StreamEvent(
            type="stderr",
            data="Error: file not found",
            timestamp=time.time()
        )

        assert event.type == "stderr"
        assert event.is_output is True

    def test_parse_exit_event(self):
        """Correctly parses exit SSE events."""
        from do_app_sandbox.types import StreamEvent

        event = StreamEvent(
            type="exit",
            data="0",
            timestamp=time.time()
        )

        assert event.type == "exit"
        assert event.is_complete is True

    def test_parse_error_event(self):
        """Correctly parses error SSE events."""
        from do_app_sandbox.types import StreamEvent

        event = StreamEvent(
            type="error",
            data="Command execution failed",
            timestamp=time.time()
        )

        assert event.type == "error"
        assert event.is_complete is True


class TestServiceClientErrors:
    """Tests for error handling in service client."""

    def test_connection_error_handling(self):
        """ServiceConnectionError raised on connect failure."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient
            from do_app_sandbox.exceptions import ServiceConnectionError

            # Setup mock to raise ConnectError
            mock_httpx.ConnectError = Exception
            mock_client_instance = MagicMock()
            mock_client_instance.request.side_effect = mock_httpx.ConnectError("Connection refused")
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_httpx.Client.return_value = mock_client_instance

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="token"
            )

            with pytest.raises(ServiceConnectionError):
                client.exec("test")

    def test_timeout_error_handling(self):
        """CommandTimeoutError raised on timeout."""
        with patch("do_app_sandbox.service_client.httpx") as mock_httpx:
            from do_app_sandbox.service_client import SandboxServiceClient
            from do_app_sandbox.exceptions import CommandTimeoutError

            # Setup mock to raise TimeoutException
            mock_httpx.TimeoutException = Exception
            mock_httpx.ConnectError = type("ConnectError", (Exception,), {})
            mock_client_instance = MagicMock()
            mock_client_instance.request.side_effect = mock_httpx.TimeoutException("Timed out")
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_httpx.Client.return_value = mock_client_instance

            client = SandboxServiceClient(
                base_url="https://sandbox.example.com",
                token="token"
            )

            with pytest.raises(CommandTimeoutError):
                client.exec("long running command")
