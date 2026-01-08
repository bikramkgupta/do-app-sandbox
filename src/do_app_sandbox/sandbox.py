"""Main Sandbox class for the App Platform Sandbox SDK.

This module provides the primary interface for creating and managing
sandbox environments on DigitalOcean App Platform.

Supports two deployment modes:
- WORKER (default): Uses doctl console for command execution
- SERVICE: HTTP API with streaming support, port exposure, sessions
"""

import json
import os
import subprocess
import time
import uuid
import shutil
from typing import Dict, Generator, List, Optional, TYPE_CHECKING, Union
from urllib.parse import urlparse, urlunparse

from .deployer import DEFAULT_IMAGE_OWNER, DEFAULT_INSTANCE_SIZE, DEFAULT_REGION, Deployer
from .exceptions import (
    SandboxCreationError,
    SandboxNotFoundError,
    SandboxNotReadyError,
    SandboxHibernatedError,
    ServiceNotAvailableError,
    SnapshotError,
)
from .executor import Executor
from .filesystem import FileSystem
from .process import ProcessManager
from .spaces import SpacesClient, create_spaces_config_from_env
from .types import (
    CommandResult,
    ExposedPort,
    GitCredentials,
    HibernatedSandbox,
    HibernationConfig,
    ProcessInfo,
    SandboxMode,
    SandboxState,
    ServiceConfig,
    SnapshotMetadata,
    SpacesConfig,
    StreamEvent,
)

if TYPE_CHECKING:
    from .manager import SandboxManager

# Environment variable names
ENV_REGISTRY = "APP_SANDBOX_REGISTRY"
ENV_REGION = "APP_SANDBOX_REGION"


def _run_doctl(
    args: list[str],
    timeout: int = 120,
    api_token: Optional[str] = None,
) -> tuple[int, str, str]:
    """Run a doctl command without requiring Deployer.

    Args:
        args: Command arguments (after 'doctl')
        timeout: Command timeout in seconds
        api_token: Optional API token (uses doctl auth if not provided)

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    cmd = ["doctl"] + args + ["--output", "json"]

    env = os.environ.copy()
    token = api_token or os.environ.get("DIGITALOCEAN_TOKEN")
    if token:
        env["DIGITALOCEAN_ACCESS_TOKEN"] = token

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"
    except Exception as e:
        return -1, "", str(e)


def _get_app_info(app_id: str, api_token: Optional[str] = None) -> dict:
    """Get app info directly via doctl without requiring Deployer.

    Args:
        app_id: The App Platform application ID
        api_token: Optional API token

    Returns:
        Dict with app info including 'url' and 'status'

    Raises:
        SandboxNotFoundError: If the app doesn't exist
    """
    code, stdout, stderr = _run_doctl(["apps", "get", app_id], api_token=api_token)

    if code != 0:
        if "not found" in stderr.lower():
            raise SandboxNotFoundError(f"App {app_id} not found")
        error_detail = stderr.strip() or stdout.strip() or f"exit code {code}"
        raise SandboxNotFoundError(f"Failed to get app: {error_detail}")

    try:
        data = json.loads(stdout)
        if isinstance(data, list):
            data = data[0]

        active_deployment = data.get("active_deployment", {})
        phase = active_deployment.get("phase", "UNKNOWN")

        return {
            "app_id": data.get("id", app_id),
            "name": data.get("spec", {}).get("name", ""),
            "status": phase,
            "url": data.get("live_url"),
        }
    except json.JSONDecodeError as e:
        raise SandboxNotFoundError(f"Failed to parse app info: {e}")


def _delete_app(app_id: str, api_token: Optional[str] = None) -> bool:
    """Delete an app directly via doctl without requiring Deployer.

    Args:
        app_id: The App Platform application ID
        api_token: Optional API token

    Returns:
        True if deletion was successful

    Raises:
        SandboxNotFoundError: If the app doesn't exist
    """
    code, stdout, stderr = _run_doctl(
        ["apps", "delete", app_id, "--force"],
        api_token=api_token,
    )

    if code != 0:
        if "not found" in stderr.lower():
            raise SandboxNotFoundError(f"App {app_id} not found")
        # Force delete usually succeeds, ignore other errors
        pass

    return True


def _ensure_doctl_available() -> None:
    """Ensure doctl is installed; raise if missing."""
    if shutil.which("doctl") is None:
        raise SandboxCreationError(
            "doctl is required for sandbox operations. Install doctl and run 'doctl auth init'. "
            "See https://docs.digitalocean.com/reference/doctl/how-to/install/"
        )


class Sandbox:
    """A sandbox environment running on DigitalOcean App Platform.

    The Sandbox class provides a complete interface for:
    - Creating and deleting sandbox containers
    - Executing commands (with optional streaming in service mode)
    - File system operations
    - Process management
    - Port exposure and preview URLs (service mode)
    - Hibernation (snapshot + delete for cost savings)

    Deployment Modes:
        - WORKER (default): Uses doctl console for execution. Simple but no streaming.
        - SERVICE: HTTP API with SSE streaming, port exposure, sessions.

    Example usage:
        >>> # Worker mode (default)
        >>> sandbox = Sandbox.create(image="python", name="my-sandbox")
        >>> result = sandbox.exec("python --version")
        >>> sandbox.delete()

        >>> # Service mode with streaming
        >>> sandbox = Sandbox.create(
        ...     image="python",
        ...     mode=SandboxMode.SERVICE
        ... )
        >>> for event in sandbox.exec_stream("pip install requests"):
        ...     print(event.data, end="")
        >>> sandbox.delete()
    """

    def __init__(
        self,
        app_id: str,
        component: str = "sandbox",
        api_token: Optional[str] = None,
        spaces_config: Optional[Union[SpacesConfig, Dict]] = None,
        _deployer: Optional[Deployer] = None,
        _mode: SandboxMode = SandboxMode.WORKER,
        _service_config: Optional[ServiceConfig] = None,
        _service_token: Optional[str] = None,
        _image: str = "python",
        _hibernation_config: Optional[HibernationConfig] = None,
    ):
        """Initialize a Sandbox instance.

        Generally, you should use Sandbox.create() or Sandbox.get_from_id()
        instead of this constructor directly.

        Args:
            app_id: The App Platform application ID
            component: The component/service name
            api_token: DigitalOcean API token
            spaces_config: Optional SpacesConfig or dict for large file transfers.
                          If not provided, will try to load from environment variables.
            _deployer: Internal deployer instance (for testing)
            _mode: Sandbox mode (WORKER or SERVICE)
            _service_config: Configuration for service mode
            _service_token: Auth token for service mode API
            _image: Image type used (python, node)
            _hibernation_config: Hibernation settings
        """
        self._app_id = app_id
        self._component = component
        self._api_token = api_token
        self._deployer = _deployer
        self._url: Optional[str] = None

        # Mode and service configuration
        self._mode = _mode
        self._service_config = _service_config
        self._service_token = _service_token
        self._image = _image
        self._hibernation_config = _hibernation_config or HibernationConfig()

        # State tracking
        self._state = SandboxState.ACTIVE
        self._last_activity = time.time()
        self._active_streams = 0

        # Service client (lazy initialized for service mode)
        self._service_client = None

        # Worker mode: use doctl console executor
        if _mode == SandboxMode.WORKER:
            self._executor = Executor(app_id, component)
        else:
            self._executor = None  # Service mode uses HTTP client

        # Initialize Spaces client if configured
        self._spaces_client: Optional[SpacesClient] = None
        self._spaces_config = self._resolve_spaces_config(spaces_config)
        if self._spaces_config:
            try:
                self._spaces_client = SpacesClient(self._spaces_config)
            except Exception:
                # Spaces is optional - don't fail if not configured properly
                pass

        # Initialize filesystem with optional Spaces support
        if self._executor:
            self._filesystem = FileSystem(
                self._executor,
                spaces_client=self._spaces_client,
                sandbox_id=app_id,
            )
            self._process = ProcessManager(self._executor)
        else:
            # Service mode - filesystem/process via HTTP
            self._filesystem = None
            self._process = None

    def _resolve_spaces_config(
        self, config: Optional[Union[SpacesConfig, Dict]]
    ) -> Optional[SpacesConfig]:
        """Resolve SpacesConfig from parameter, dict, or environment.

        Args:
            config: SpacesConfig, dict with config, or None

        Returns:
            SpacesConfig if available, None otherwise
        """
        if config is None:
            # Try to load from environment
            return create_spaces_config_from_env()

        if isinstance(config, SpacesConfig):
            return config

        if isinstance(config, dict):
            return SpacesConfig(
                bucket=config.get("bucket", ""),
                region=config.get("region", ""),
                access_key=config.get("access_key"),
                secret_key=config.get("secret_key"),
                endpoint=config.get("endpoint"),
            )

        return None

    @classmethod
    def create(
        cls,
        *,
        image: str,
        name: Optional[str] = None,
        region: Optional[str] = None,
        instance_size: Optional[str] = None,
        mode: SandboxMode = SandboxMode.WORKER,
        service_config: Optional[ServiceConfig] = None,
        hibernation_config: Optional[HibernationConfig] = None,
        registry: Optional[str] = None,
        api_token: Optional[str] = None,
        wait_ready: bool = True,
        timeout: int = 600,
        spaces_config: Optional[Union[SpacesConfig, Dict]] = None,
    ) -> "Sandbox":
        """Create a new sandbox environment.

        This deploys a new container to App Platform using the specified image.
        The sandbox will be ready for commands once this method returns.

        Args:
            image: The sandbox image to use ("python" or "node"). Required.
            name: Optional name for the sandbox (auto-generated if not provided)
            region: App Platform region (e.g., "atl1", "sfo3", "nyc").
                Falls back to APP_SANDBOX_REGION env var, then "atl1".
            instance_size: Instance size slug (e.g., "apps-s-1vcpu-1gb").
                Defaults to "apps-s-1vcpu-1gb".
            mode: SandboxMode.WORKER (default) for doctl console execution,
                SandboxMode.SERVICE for HTTP API with streaming support.
            service_config: Configuration for service mode (API port, proxy ports, etc.)
            hibernation_config: Configuration for auto-hibernation behavior
            registry: Optional registry host. If not provided, uses public
                GHCR images from ghcr.io/bikramkgupta/.
            api_token: DigitalOcean API token (uses DIGITALOCEAN_TOKEN env if not set)
            wait_ready: If True, wait for the sandbox to be ready before returning
            timeout: Maximum time to wait for ready state (in seconds)
            spaces_config: Optional SpacesConfig or dict for large file transfers.
                          Required for files >= 5MB and for snapshots/hibernation.

        Returns:
            A Sandbox instance connected to the new environment

        Raises:
            SandboxCreationError: If sandbox creation fails
            ValueError: If an invalid image is specified

        Example:
            >>> # Simple creation (worker mode, default)
            >>> sandbox = Sandbox.create(image="python")
            >>> result = sandbox.exec("python --version")
            >>> sandbox.delete()

            >>> # Service mode with streaming
            >>> sandbox = Sandbox.create(
            ...     image="python",
            ...     mode=SandboxMode.SERVICE
            ... )
            >>> for event in sandbox.exec_stream("pip install requests"):
            ...     print(event.data, end="")

            >>> # With Spaces for snapshots
            >>> sandbox = Sandbox.create(
            ...     image="python",
            ...     spaces_config={"bucket": "my-bucket", "region": "nyc3"}
            ... )
        """
        _ensure_doctl_available()

        # Determine registry owner (GHCR by default)
        resolved_registry = registry or os.environ.get(ENV_REGISTRY) or DEFAULT_IMAGE_OWNER

        # Resolve region (param > env var > default)
        resolved_region = (region or os.environ.get(ENV_REGION) or DEFAULT_REGION).lower()

        # Resolve instance size (param > default)
        resolved_instance_size = instance_size or DEFAULT_INSTANCE_SIZE

        # Validate image
        valid_images = ("python", "node")
        if image not in valid_images:
            raise ValueError(f"Invalid image '{image}'. Must be one of: {valid_images}")

        # Generate name if not provided
        if not name:
            name = f"sandbox-{uuid.uuid4().hex[:8]}"

        # Create deployer and deploy
        deployer = Deployer(
            registry=resolved_registry,
            region=resolved_region,
            instance_size=resolved_instance_size,
            api_token=api_token,
        )

        # Determine component type based on mode
        component_type = "worker" if mode == SandboxMode.WORKER else "service"

        # Create the app
        app_info, service_token = deployer.create_app(
            name,
            image,
            component_type=component_type,
            mode=mode,
            service_config=service_config
        )

        # Wait for ready if requested
        if wait_ready:
            app_info = deployer.wait_ready(app_info.app_id, timeout=timeout)

        # Create and return the Sandbox instance
        sandbox = cls(
            app_id=app_info.app_id,
            component="sandbox",
            api_token=api_token,
            spaces_config=spaces_config,
            _deployer=deployer,
            _mode=mode,
            _service_config=service_config,
            _service_token=service_token,
            _image=image,
            _hibernation_config=hibernation_config,
        )
        sandbox._url = app_info.url

        return sandbox

    @classmethod
    def get_from_id(
        cls,
        app_id: str,
        component: str = "sandbox",
        api_token: Optional[str] = None,
        spaces_config: Optional[Union[SpacesConfig, Dict]] = None,
    ) -> "Sandbox":
        """Connect to an existing sandbox by app ID.

        Use this to reconnect to a sandbox that was previously created.
        Registry is NOT required - all operations work with just the app_id.

        Args:
            app_id: The App Platform application ID
            component: The component/service name
            api_token: DigitalOcean API token
            spaces_config: Optional SpacesConfig or dict for large file transfers.

        Returns:
            A Sandbox instance connected to the existing environment

        Raises:
            SandboxNotFoundError: If the sandbox doesn't exist

        Example:
            >>> sandbox = Sandbox.get_from_id("abc123-def456")
            >>> result = sandbox.exec("whoami")
        """
        _ensure_doctl_available()

        # Verify the app exists and get initial info
        app_info = _get_app_info(app_id, api_token=api_token)

        sandbox = cls(
            app_id=app_id,
            component=component,
            api_token=api_token,
            spaces_config=spaces_config,
        )
        sandbox._url = app_info.get("url")

        return sandbox

    @property
    def app_id(self) -> str:
        """The App Platform application ID."""
        return self._app_id

    @property
    def component(self) -> str:
        """The component/service name within the app."""
        return self._component

    @property
    def filesystem(self) -> FileSystem:
        """File system operations interface."""
        return self._filesystem

    @property
    def status(self) -> str:
        """Get the current deployment status."""
        try:
            app_info = _get_app_info(self._app_id, api_token=self._api_token)
            return app_info.get("status", "UNKNOWN")
        except SandboxNotFoundError:
            return "DELETED"

    def exec(
        self,
        command: str,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: int = 120,
    ) -> CommandResult:
        """Execute a command in the sandbox.

        Args:
            command: The command to execute
            env: Environment variables to set for this command
            cwd: Working directory for the command
            timeout: Command timeout in seconds

        Returns:
            CommandResult with stdout, stderr, and exit_code

        Raises:
            SandboxHibernatedError: If sandbox is hibernated

        Example:
            >>> result = sandbox.exec("python --version")
            >>> print(result.stdout)
            Python 3.13.0
            >>> print(result.exit_code)
            0
        """
        self._ensure_awake()
        self._record_activity()

        if self._mode == SandboxMode.SERVICE:
            client = self._get_service_client()
            return client.exec(command, env=env, cwd=cwd or "/workspace", timeout=timeout)
        else:
            return self._executor.execute(command, env=env, cwd=cwd, timeout=timeout)

    def launch_process(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> int:
        """Launch a background process.

        The process runs detached from the console session, allowing
        long-running processes like web servers.

        Args:
            command: The command to run
            cwd: Working directory for the process
            env: Environment variables to set

        Returns:
            The process ID (PID)

        Example:
            >>> pid = sandbox.launch_process("python -m http.server 9000", cwd="/app")
            >>> print(f"Server running with PID {pid}")
        """
        return self._process.launch(command, cwd=cwd, env=env)

    def list_processes(self, pattern: Optional[str] = None) -> list[ProcessInfo]:
        """List running processes.

        Args:
            pattern: Optional pattern to filter processes

        Returns:
            List of ProcessInfo objects
        """
        return self._process.list_processes(pattern)

    def kill_process(self, pid: int) -> bool:
        """Kill a process by PID.

        Args:
            pid: The process ID

        Returns:
            True if the signal was sent
        """
        return self._process.kill(pid)

    def kill_all_processes(self) -> int:
        """Kill all processes launched by this sandbox.

        Returns:
            Number of processes killed
        """
        return self._process.kill_all_launched()

    def get_url(self) -> str:
        """Get the public URL for this sandbox.

        Returns:
            The public HTTPS URL

        Raises:
            SandboxNotFoundError: If the sandbox doesn't exist

        Example:
            >>> url = sandbox.get_url()
            >>> print(url)
            https://my-sandbox.ondigitalocean.app
        """
        if not self._url:
            app_info = _get_app_info(self._app_id, api_token=self._api_token)
            self._url = app_info.get("url")
            if not self._url:
                # Construct URL from app name if not available
                name = app_info.get("name", "")
                if name:
                    self._url = f"https://{name}.ondigitalocean.app"
        return self._url

    def delete(self) -> None:
        """Delete this sandbox and all its resources.

        This permanently removes the App Platform application.
        The Sandbox instance should not be used after calling this method.

        Raises:
            SandboxNotFoundError: If the sandbox doesn't exist

        Example:
            >>> sandbox.delete()
            >>> # sandbox is now destroyed
        """
        _delete_app(self._app_id, api_token=self._api_token)

    def is_ready(self) -> bool:
        """Check if the sandbox is ready for commands.

        Returns:
            True if the sandbox is active and ready
        """
        return self.status == "ACTIVE"

    def wait_ready(self, timeout: int = 600, poll_interval: int = 10) -> None:
        """Wait for the sandbox to be ready.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Raises:
            SandboxNotReadyError: If the sandbox fails to become ready
            SandboxNotFoundError: If the sandbox doesn't exist
        """
        start = time.time()
        last_status = None

        while time.time() - start < timeout:
            app_info = _get_app_info(self._app_id, api_token=self._api_token)
            status = app_info.get("status", "UNKNOWN")

            if status != last_status:
                last_status = status

            if status == "ACTIVE":
                # Update cached URL
                self._url = app_info.get("url")
                return

            if status in ("ERROR", "FAILED"):
                raise SandboxNotReadyError(
                    f"Sandbox deployment failed with status: {status}"
                )

            time.sleep(poll_interval)

        raise SandboxNotReadyError(
            f"Timed out waiting for sandbox to be ready after {timeout}s. "
            f"Last status: {last_status}"
        )

    def __repr__(self) -> str:
        mode_str = self._mode.value if self._mode else "worker"
        return f"Sandbox(app_id={self._app_id!r}, mode={mode_str!r})"

    def __enter__(self) -> "Sandbox":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - deletes the sandbox."""
        self.delete()

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get_service_client(self):
        """Get or create the service client for HTTP API mode."""
        if self._service_client is None:
            from .service_client import SandboxServiceClient
            base_url = self.get_url()
            if not self._service_token:
                raise ServiceNotAvailableError(
                    "Service token not available. Sandbox may not be in service mode."
                )
            self._service_client = SandboxServiceClient(
                base_url=base_url,
                token=self._service_token
            )
        return self._service_client

    def _ensure_awake(self) -> None:
        """Ensure sandbox is not hibernated before operations."""
        if self._state == SandboxState.HIBERNATED:
            raise SandboxHibernatedError(
                "Sandbox is hibernated. Use Sandbox.wake() to restore it."
            )

    def _record_activity(self) -> None:
        """Record activity to reset the idle timer."""
        self._last_activity = time.time()

    def _is_idle(self) -> bool:
        """Check if sandbox is idle (ready to hibernate).

        Returns:
            True if no activity for sleep_after seconds and no active streams
        """
        if self._active_streams > 0:
            return False
        idle_time = time.time() - self._last_activity
        return idle_time > self._hibernation_config.sleep_after

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def mode(self) -> SandboxMode:
        """The sandbox deployment mode (WORKER or SERVICE)."""
        return self._mode

    @property
    def state(self) -> SandboxState:
        """The sandbox lifecycle state."""
        return self._state

    @property
    def image(self) -> str:
        """The sandbox image type (python, node)."""
        return self._image

    # =========================================================================
    # Streaming execution (service mode)
    # =========================================================================

    def exec_stream(
        self,
        command: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace",
        timeout: int = 120,
    ) -> Generator[StreamEvent, None, None]:
        """Execute a command with streaming output.

        Streams stdout/stderr in real-time via SSE. Requires service mode.

        Args:
            command: Command to execute
            env: Environment variables
            cwd: Working directory
            timeout: Command timeout in seconds

        Yields:
            StreamEvent objects with type (stdout/stderr/exit/error) and data

        Raises:
            ServiceNotAvailableError: If not in service mode
            SandboxHibernatedError: If sandbox is hibernated

        Example:
            >>> for event in sandbox.exec_stream("pip install requests"):
            ...     if event.type == "stdout":
            ...         print(event.data, end="", flush=True)
            ...     elif event.type == "exit":
            ...         print(f"\\nExited with code: {event.data}")
        """
        if self._mode != SandboxMode.SERVICE:
            raise ServiceNotAvailableError(
                "exec_stream() requires service mode. "
                "Create sandbox with mode=SandboxMode.SERVICE"
            )

        self._ensure_awake()
        self._active_streams += 1

        try:
            self._record_activity()
            client = self._get_service_client()
            for event in client.exec_stream(command, env=env, cwd=cwd, timeout=timeout):
                self._record_activity()
                yield event
        finally:
            self._active_streams -= 1
            self._record_activity()

    # =========================================================================
    # Port exposure (service mode)
    # =========================================================================

    def expose_port(self, port: int) -> ExposedPort:
        """Get a public URL for an internal port.

        The sandbox API proxies requests to the specified internal port,
        allowing you to access services running inside the sandbox.

        Requires service mode.

        Args:
            port: Internal port number to expose

        Returns:
            ExposedPort with public URL

        Raises:
            ServiceNotAvailableError: If not in service mode

        Example:
            >>> sandbox.exec("python -m http.server 3000 &")
            >>> port_info = sandbox.expose_port(3000)
            >>> print(port_info.url)
            https://sandbox-xxx.ondigitalocean.app/proxy/3000
        """
        if self._mode != SandboxMode.SERVICE:
            raise ServiceNotAvailableError(
                "Port exposure requires service mode. "
                "Create sandbox with mode=SandboxMode.SERVICE"
            )

        base_url = self.get_url()
        proxy_url = f"{base_url}/proxy/{port}"

        return ExposedPort(
            port=port,
            url=proxy_url,
            protocol="https",
            created_at=time.time()
        )

    # =========================================================================
    # Git operations
    # =========================================================================

    def git_checkout(
        self,
        url: str,
        path: str = "/workspace",
        branch: Optional[str] = None,
        depth: int = 1,
        credentials: Optional[GitCredentials] = None,
    ) -> CommandResult:
        """Clone a git repository into the sandbox.

        Args:
            url: Repository URL (HTTPS or SSH)
            path: Destination path (default: /workspace)
            branch: Branch to checkout (default: default branch)
            depth: Clone depth (default: 1 for shallow clone)
            credentials: Optional credentials for private repos

        Returns:
            CommandResult from the git clone command

        Example:
            >>> result = sandbox.git_checkout("https://github.com/user/repo.git")
            >>> if result.success:
            ...     print("Clone successful")

            >>> # Private repo with token
            >>> creds = GitCredentials(token="ghp_xxx")
            >>> sandbox.git_checkout(
            ...     "https://github.com/user/private-repo.git",
            ...     credentials=creds
            ... )
        """
        self._ensure_awake()

        cmd_parts = ["git", "clone"]

        if depth:
            cmd_parts.extend(["--depth", str(depth)])
        if branch:
            cmd_parts.extend(["--branch", branch])

        clone_url = url
        env = None

        if credentials:
            if credentials.ssh_key:
                # Write SSH key temporarily
                key_path = "/tmp/git_key"
                self.filesystem.write_file(key_path, credentials.ssh_key)
                self.exec(f"chmod 600 {key_path}")
                env = {
                    "GIT_SSH_COMMAND": f"ssh -i {key_path} -o StrictHostKeyChecking=no"
                }
            elif credentials.token:
                # Embed token in HTTPS URL
                parsed = urlparse(url)
                auth = f"{credentials.username or 'git'}:{credentials.token}"
                clone_url = urlunparse(
                    parsed._replace(netloc=f"{auth}@{parsed.netloc}")
                )

        cmd_parts.extend([clone_url, path])
        result = self.exec(" ".join(cmd_parts), env=env)

        # Cleanup SSH key if used
        if credentials and credentials.ssh_key:
            self.exec("rm -f /tmp/git_key")

        return result

    # =========================================================================
    # Snapshots
    # =========================================================================

    def create_snapshot(
        self,
        snapshot_id: Optional[str] = None,
        paths: Optional[List[str]] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        timeout: int = 600,
    ) -> SnapshotMetadata:
        """Create a snapshot of sandbox filesystem state.

        Snapshots are stored in DO Spaces and include dependencies
        (node_modules, .venv) for rapid restoration.

        Requires Spaces to be configured.

        Args:
            snapshot_id: Optional ID (auto-generated if not provided)
            paths: Paths to include (default: ["/workspace"])
            description: Optional human-readable description
            tags: Optional key-value tags
            timeout: Timeout for archive/upload in seconds

        Returns:
            SnapshotMetadata with snapshot details

        Raises:
            SpacesNotConfiguredError: If Spaces is not configured
            SnapshotError: If snapshot creation fails

        Example:
            >>> meta = sandbox.create_snapshot(
            ...     description="After installing dependencies"
            ... )
            >>> print(f"Snapshot: {meta.snapshot_id}, Size: {meta.size_bytes}")
        """
        self._ensure_awake()

        from .snapshot import SnapshotManager
        snapshot_mgr = SnapshotManager(self._spaces_config)
        return snapshot_mgr.create_snapshot(
            sandbox=self,
            snapshot_id=snapshot_id,
            paths=paths,
            description=description,
            tags=tags,
            timeout=timeout
        )

    def restore_snapshot(
        self,
        snapshot_id: str,
        target_path: str = "/",
        timeout: int = 600,
    ) -> bool:
        """Restore a snapshot to this sandbox.

        Args:
            snapshot_id: ID of snapshot to restore
            target_path: Base path for extraction
            timeout: Timeout for download/extract in seconds

        Returns:
            True if restoration succeeded

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
            SnapshotRestoreError: If restoration fails
        """
        self._ensure_awake()

        from .snapshot import SnapshotManager
        snapshot_mgr = SnapshotManager(self._spaces_config)
        return snapshot_mgr.restore_snapshot(
            sandbox=self,
            snapshot_id=snapshot_id,
            target_path=target_path,
            timeout=timeout
        )

    # =========================================================================
    # Hibernation
    # =========================================================================

    def hibernate(self) -> HibernatedSandbox:
        """Hibernate the sandbox: snapshot state and delete sandbox.

        This creates a snapshot of the sandbox filesystem, then deletes
        the sandbox entirely for cost savings. The sandbox can be restored
        later using Sandbox.wake().

        Cost comparison:
        - Running sandbox: ~$5/month
        - Hibernated (Spaces storage only): ~$0.02/month

        Requires Spaces to be configured.

        Returns:
            HibernatedSandbox reference for later wake()

        Raises:
            SandboxHibernatedError: If already hibernated
            SpacesNotConfiguredError: If Spaces not configured

        Example:
            >>> hibernated = sandbox.hibernate()
            >>> print(f"Hibernated. Cost: ~$0.02/mo for {hibernated.snapshot_id}")
            >>>
            >>> # Later: wake the sandbox
            >>> sandbox = Sandbox.wake(hibernated)
        """
        if self._state == SandboxState.HIBERNATED:
            raise SandboxHibernatedError("Sandbox is already hibernated")

        # Create hibernation snapshot
        snapshot_id = f"hibernate-{self._app_id}-{int(time.time())}"
        self.create_snapshot(
            snapshot_id=snapshot_id,
            paths=["/workspace", "/home", "/tmp"],
            description=f"Hibernation snapshot for {self._app_id}"
        )

        # Store metadata for restoration
        hibernated = HibernatedSandbox(
            snapshot_id=snapshot_id,
            image=self._image,
            mode=self._mode,
            service_config=self._service_config,
            hibernated_at=time.time(),
            metadata={"app_id": self._app_id}
        )

        # Delete the sandbox (not just scale to 0)
        self.delete()

        self._state = SandboxState.HIBERNATED
        return hibernated

    @classmethod
    def wake(
        cls,
        hibernated: HibernatedSandbox,
        pool: Optional["SandboxManager"] = None,
        **create_kwargs
    ) -> "Sandbox":
        """Wake a hibernated sandbox.

        Creates a new sandbox and restores the hibernation snapshot.
        If a pool is provided, acquires from the pool for faster startup.

        Args:
            hibernated: HibernatedSandbox reference from hibernate()
            pool: Optional SandboxManager for fast pool acquisition
            **create_kwargs: Additional arguments for Sandbox.create()

        Returns:
            New Sandbox with restored state

        Example:
            >>> # Wake without pool (slower, ~60s)
            >>> sandbox = Sandbox.wake(hibernated)
            >>>
            >>> # Wake with pool (faster, ~5-15s)
            >>> manager = SandboxManager(...)
            >>> sandbox = Sandbox.wake(hibernated, pool=manager)
        """
        # Acquire new sandbox
        if pool:
            sandbox = pool.acquire_sync(hibernated.image)
        else:
            sandbox = cls.create(
                image=hibernated.image,
                mode=hibernated.mode,
                service_config=hibernated.service_config,
                **create_kwargs
            )

        # Restore snapshot
        sandbox.restore_snapshot(hibernated.snapshot_id)

        return sandbox
