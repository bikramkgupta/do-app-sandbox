"""Main Sandbox class for the App Platform Sandbox SDK.

This module provides the primary interface for creating and managing
sandbox environments on DigitalOcean App Platform.
"""

import json
import os
import subprocess
import time
import uuid
import shutil
from typing import Dict, Optional, Union

from .deployer import DEFAULT_IMAGE_OWNER, DEFAULT_INSTANCE_SIZE, DEFAULT_REGION, Deployer
from .exceptions import SandboxCreationError, SandboxNotFoundError, SandboxNotReadyError
from .executor import Executor
from .filesystem import FileSystem
from .process import ProcessManager
from .spaces import SpacesClient, create_spaces_config_from_env
from .types import CommandResult, ProcessInfo, SpacesConfig

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
    - Executing commands
    - File system operations
    - Process management
    - Accessing the public URL

    Example usage:
        >>> sandbox = Sandbox.create(image="python", name="my-sandbox")
        >>> sandbox.filesystem.write_file("/app/script.py", "print('hello')")
        >>> result = sandbox.exec("python /app/script.py")
        >>> print(result.stdout)
        hello
        >>> sandbox.delete()
    """

    def __init__(
        self,
        app_id: str,
        component: str = "sandbox",
        api_token: Optional[str] = None,
        spaces_config: Optional[Union[SpacesConfig, Dict]] = None,
        _deployer: Optional[Deployer] = None,
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
        """
        self._app_id = app_id
        self._component = component
        self._api_token = api_token
        self._deployer = _deployer
        self._executor = Executor(app_id, component)
        self._url: Optional[str] = None

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
        self._filesystem = FileSystem(
            self._executor,
            spaces_client=self._spaces_client,
            sandbox_id=app_id,
        )
        self._process = ProcessManager(self._executor)

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
        component_type: str = "service",
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
            component_type: "service" for HTTP endpoint (default), "worker" for
                background process without HTTP. Workers are useful for long-running
                tasks that don't need a public URL.
            registry: Optional registry host. If not provided, uses public
                GHCR images from ghcr.io/bikramkgupta/.
            api_token: DigitalOcean API token (uses DIGITALOCEAN_TOKEN env if not set)
            wait_ready: If True, wait for the sandbox to be ready before returning
            timeout: Maximum time to wait for ready state (in seconds)
            spaces_config: Optional SpacesConfig or dict for large file transfers.
                          Required for files >= 5MB. Dict should have keys:
                          "bucket", "region", and optionally "access_key", "secret_key".

        Returns:
            A Sandbox instance connected to the new environment

        Raises:
            SandboxCreationError: If sandbox creation fails
            ValueError: If an invalid image or component_type is specified

        Example:
            >>> # Simple creation with public GHCR images
            >>> sandbox = Sandbox.create(image="python")
            >>> print(sandbox.app_id)
            abc123-def456

            >>> # Create a worker (no HTTP endpoint)
            >>> worker = Sandbox.create(image="node", component_type="worker")

            >>> # With Spaces for large files
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

        # Validate component_type
        valid_component_types = ("service", "worker")
        if component_type not in valid_component_types:
            raise ValueError(f"Invalid component_type '{component_type}'. Must be one of: {valid_component_types}")

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

        app_info = deployer.create_app(name, image, component_type=component_type)

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

        Example:
            >>> result = sandbox.exec("python --version")
            >>> print(result.stdout)
            Python 3.13.0
            >>> print(result.exit_code)
            0
        """
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
        return f"Sandbox(app_id={self._app_id!r}, component={self._component!r})"

    def __enter__(self) -> "Sandbox":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - deletes the sandbox."""
        self.delete()
