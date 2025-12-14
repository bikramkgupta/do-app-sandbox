"""Asynchronous Sandbox class for the App Platform Sandbox SDK.

This module provides an async interface that wraps the synchronous
Sandbox class using asyncio.to_thread for non-blocking operations.
"""

import asyncio
from typing import Callable, Dict, Optional, Union

from .sandbox import Sandbox
from .types import CommandResult, ProcessInfo, SpacesConfig


class AsyncFileSystem:
    """Async wrapper for file system operations."""

    def __init__(self, sync_sandbox: Sandbox):
        self._sync_sandbox = sync_sandbox

    async def read_file(self, path: str, binary: bool = False) -> str | bytes:
        """Read a file from the sandbox asynchronously."""
        return await asyncio.to_thread(
            self._sync_sandbox.filesystem.read_file, path, binary
        )

    async def write_file(
        self, path: str, content: str | bytes, binary: bool = False
    ) -> None:
        """Write content to a file asynchronously."""
        await asyncio.to_thread(
            self._sync_sandbox.filesystem.write_file, path, content, binary
        )

    async def append_file(self, path: str, content: str) -> None:
        """Append content to a file asynchronously."""
        await asyncio.to_thread(self._sync_sandbox.filesystem.append_file, path, content)

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a local file to the sandbox asynchronously."""
        await asyncio.to_thread(
            self._sync_sandbox.filesystem.upload_file, local_path, remote_path
        )

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the sandbox asynchronously."""
        await asyncio.to_thread(
            self._sync_sandbox.filesystem.download_file, remote_path, local_path
        )

    async def list_dir(self, path: str = ".") -> list:
        """List directory contents asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.filesystem.list_dir, path)

    async def mkdir(self, path: str, recursive: bool = True) -> None:
        """Create a directory asynchronously."""
        await asyncio.to_thread(self._sync_sandbox.filesystem.mkdir, path, recursive)

    async def rm(self, path: str, recursive: bool = False, force: bool = True) -> None:
        """Remove a file or directory asynchronously."""
        await asyncio.to_thread(
            self._sync_sandbox.filesystem.rm, path, recursive, force
        )

    async def exists(self, path: str) -> bool:
        """Check if a path exists asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.filesystem.exists, path)

    async def is_file(self, path: str) -> bool:
        """Check if a path is a file asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.filesystem.is_file, path)

    async def is_dir(self, path: str) -> bool:
        """Check if a path is a directory asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.filesystem.is_dir, path)

    async def copy(self, src: str, dst: str, recursive: bool = False) -> None:
        """Copy a file or directory asynchronously."""
        await asyncio.to_thread(self._sync_sandbox.filesystem.copy, src, dst, recursive)

    async def move(self, src: str, dst: str) -> None:
        """Move a file or directory asynchronously."""
        await asyncio.to_thread(self._sync_sandbox.filesystem.move, src, dst)

    async def chmod(self, path: str, mode: str) -> None:
        """Change file permissions asynchronously."""
        await asyncio.to_thread(self._sync_sandbox.filesystem.chmod, path, mode)

    async def get_size(self, path: str) -> int:
        """Get file size asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.filesystem.get_size, path)

    async def upload_large(
        self,
        local_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        cleanup: bool = False,
    ) -> None:
        """Upload a large file to the sandbox via DO Spaces asynchronously.

        For files >= 5MB, this uses Spaces as an intermediary.
        For smaller files, falls back to regular upload.

        Args:
            local_path: Path to local file
            remote_path: Destination path on sandbox
            progress_callback: Optional callback(bytes_transferred) for progress
            cleanup: If True, delete Spaces object after transfer (default: False)

        Raises:
            SpacesNotConfiguredError: If Spaces is not configured for large files
            FileOperationError: If the transfer fails
        """
        await asyncio.to_thread(
            self._sync_sandbox.filesystem.upload_large,
            local_path,
            remote_path,
            progress_callback,
            cleanup,
        )

    async def download_large(
        self,
        remote_path: str,
        local_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        cleanup: bool = False,
    ) -> None:
        """Download a large file from the sandbox via DO Spaces asynchronously.

        For files >= 5MB, this uses Spaces as an intermediary.
        For smaller files, falls back to regular download.

        Args:
            remote_path: Path to file on sandbox
            local_path: Destination path locally
            progress_callback: Optional callback(bytes_transferred) for progress
            cleanup: If True, delete Spaces object after transfer (default: False)

        Raises:
            SpacesNotConfiguredError: If Spaces is not configured for large files
            FileOperationError: If the transfer fails
        """
        await asyncio.to_thread(
            self._sync_sandbox.filesystem.download_large,
            remote_path,
            local_path,
            progress_callback,
            cleanup,
        )

    @property
    def has_spaces(self) -> bool:
        """Check if Spaces is configured for large file transfers."""
        return self._sync_sandbox.filesystem.has_spaces


class AsyncSandbox:
    """Async sandbox environment running on DigitalOcean App Platform.

    This class provides an async interface that wraps the synchronous
    Sandbox class. All methods are non-blocking.

    Example usage:
        >>> sandbox = await AsyncSandbox.create(image="python")
        >>> await sandbox.filesystem.write_file("/app/script.py", "print('hello')")
        >>> result = await sandbox.exec("python /app/script.py")
        >>> print(result.stdout)
        hello
        >>> await sandbox.delete()
    """

    def __init__(self, sync_sandbox: Sandbox):
        """Initialize an AsyncSandbox wrapper.

        Generally, you should use AsyncSandbox.create() or AsyncSandbox.get_from_id()
        instead of this constructor directly.

        Args:
            sync_sandbox: The underlying synchronous Sandbox instance
        """
        self._sync_sandbox = sync_sandbox
        self._filesystem = AsyncFileSystem(sync_sandbox)

    @classmethod
    async def create(
        cls,
        registry: Optional[str] = None,
        *,
        image: str,
        name: Optional[str] = None,
        region: Optional[str] = None,
        instance_size: Optional[str] = None,
        component_type: str = "service",
        api_token: Optional[str] = None,
        wait_ready: bool = True,
        timeout: int = 600,
        spaces_config: Optional[Union[SpacesConfig, Dict]] = None,
    ) -> "AsyncSandbox":
        """Create a new sandbox environment asynchronously.

        Args:
            registry: DOCR registry name. Falls back to APP_SANDBOX_REGISTRY env var.
            image: The sandbox image to use ("python" or "node"). Required.
            name: Optional name for the sandbox
            region: App Platform region (e.g., "nyc", "sfo3", "syd1").
                Falls back to APP_SANDBOX_REGION env var, then "nyc".
            instance_size: Instance size slug (e.g., "apps-s-1vcpu-1gb").
            component_type: "service" for HTTP endpoint (default), "worker" for
                background process without HTTP.
            api_token: DigitalOcean API token
            wait_ready: If True, wait for the sandbox to be ready
            timeout: Maximum time to wait for ready state
            spaces_config: Optional SpacesConfig or dict for large file transfers.
                          Required for files >= 5MB.

        Returns:
            An AsyncSandbox instance

        Example:
            >>> sandbox = await AsyncSandbox.create(registry="my-registry", image="python")

            >>> # Create a worker
            >>> worker = await AsyncSandbox.create(image="node", component_type="worker")

            >>> # With Spaces for large files
            >>> sandbox = await AsyncSandbox.create(
            ...     registry="my-registry",
            ...     image="python",
            ...     spaces_config={"bucket": "my-bucket", "region": "nyc3"}
            ... )
        """
        sync_sandbox = await asyncio.to_thread(
            Sandbox.create,
            registry=registry,
            image=image,
            name=name,
            region=region,
            instance_size=instance_size,
            component_type=component_type,
            api_token=api_token,
            wait_ready=wait_ready,
            timeout=timeout,
            spaces_config=spaces_config,
        )
        return cls(sync_sandbox)

    @classmethod
    async def get_from_id(
        cls,
        app_id: str,
        registry: Optional[str] = None,
        component: str = "sandbox",
        api_token: Optional[str] = None,
        spaces_config: Optional[Union[SpacesConfig, Dict]] = None,
    ) -> "AsyncSandbox":
        """Connect to an existing sandbox asynchronously.

        Args:
            app_id: The App Platform application ID
            registry: DOCR registry name. Falls back to APP_SANDBOX_REGISTRY env var.
                Optional - only needed for operations like delete() that require deployer.
            component: The component/service name
            api_token: DigitalOcean API token
            spaces_config: Optional SpacesConfig or dict for large file transfers.

        Returns:
            An AsyncSandbox instance

        Example:
            >>> sandbox = await AsyncSandbox.get_from_id("abc123-def456")
        """
        sync_sandbox = await asyncio.to_thread(
            Sandbox.get_from_id,
            app_id=app_id,
            registry=registry,
            component=component,
            api_token=api_token,
            spaces_config=spaces_config,
        )
        return cls(sync_sandbox)

    @property
    def app_id(self) -> str:
        """The App Platform application ID."""
        return self._sync_sandbox.app_id

    @property
    def component(self) -> str:
        """The component/service name."""
        return self._sync_sandbox.component

    @property
    def filesystem(self) -> AsyncFileSystem:
        """Async file system operations interface."""
        return self._filesystem

    async def get_status(self) -> str:
        """Get the current deployment status asynchronously."""
        return await asyncio.to_thread(lambda: self._sync_sandbox.status)

    async def exec(
        self,
        command: str,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: int = 120,
    ) -> CommandResult:
        """Execute a command asynchronously.

        Args:
            command: The command to execute
            env: Environment variables to set
            cwd: Working directory
            timeout: Command timeout in seconds

        Returns:
            CommandResult with stdout, stderr, and exit_code

        Example:
            >>> result = await sandbox.exec("python --version")
            >>> print(result.stdout)
        """
        return await asyncio.to_thread(
            self._sync_sandbox.exec,
            command,
            env=env,
            cwd=cwd,
            timeout=timeout,
        )

    async def launch_process(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> int:
        """Launch a background process asynchronously.

        Args:
            command: The command to run
            cwd: Working directory
            env: Environment variables

        Returns:
            The process ID (PID)
        """
        return await asyncio.to_thread(
            self._sync_sandbox.launch_process,
            command,
            cwd=cwd,
            env=env,
        )

    async def list_processes(self, pattern: Optional[str] = None) -> list[ProcessInfo]:
        """List running processes asynchronously."""
        return await asyncio.to_thread(
            self._sync_sandbox.list_processes, pattern
        )

    async def kill_process(self, pid: int) -> bool:
        """Kill a process asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.kill_process, pid)

    async def kill_all_processes(self) -> int:
        """Kill all launched processes asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.kill_all_processes)

    async def get_url(self) -> str:
        """Get the public URL asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.get_url)

    async def delete(self) -> None:
        """Delete the sandbox asynchronously."""
        await asyncio.to_thread(self._sync_sandbox.delete)

    async def is_ready(self) -> bool:
        """Check if the sandbox is ready asynchronously."""
        return await asyncio.to_thread(self._sync_sandbox.is_ready)

    async def wait_ready(self, timeout: int = 600) -> None:
        """Wait for the sandbox to be ready asynchronously."""
        await asyncio.to_thread(self._sync_sandbox.wait_ready, timeout)

    def __repr__(self) -> str:
        return f"AsyncSandbox(app_id={self.app_id!r}, component={self.component!r})"

    async def __aenter__(self) -> "AsyncSandbox":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - deletes the sandbox."""
        await self.delete()
