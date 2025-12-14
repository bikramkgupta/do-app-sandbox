"""App Platform deployment management.

This module handles creating, deleting, and managing App Platform
applications using doctl CLI commands.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Union

from .exceptions import SandboxCreationError, SandboxNotFoundError
from .types import AppInfo

# Environment variables for GHCR configuration
ENV_GHCR_OWNER = "GHCR_OWNER"        # Image owner/namespace (default: bikramkgupta)

# Image repository names
IMAGE_REPOS = {
    "python": "sandbox-python",
    "node": "sandbox-node",
}

# Default image tags (override with env APP_SANDBOX_PYTHON_TAG / APP_SANDBOX_NODE_TAG)
IMAGE_TAGS = {
    "python": os.environ.get("APP_SANDBOX_PYTHON_TAG", "latest"),
    "node": os.environ.get("APP_SANDBOX_NODE_TAG", "latest"),
}

# Defaults for GHCR-backed images
DEFAULT_IMAGE_OWNER = os.environ.get(ENV_GHCR_OWNER, "bikramkgupta")
DEFAULT_REGISTRY_HOST = os.environ.get("GHCR_REGISTRY", "ghcr.io")

# Service spec template - exposes HTTP port 8080
# Health check is on port 9090 (/sandbox_health) - handled by sandbox health server.
# Users do NOT need to implement a health endpoint in their apps.
SERVICE_SPEC_TEMPLATE = """name: {sandbox_name}
region: {region}
services:
  - name: sandbox
    image:
      registry_type: {registry_type}
      registry: {registry}
      repository: {repository}
      tag: {tag}
    instance_count: 1
    instance_size_slug: {instance_size}
    http_port: 8080
    internal_ports:
      - 9090
    health_check:
      http_path: /sandbox_health
      port: 9090
      initial_delay_seconds: 10
      period_seconds: 10
      timeout_seconds: 5
      success_threshold: 1
      failure_threshold: 3
"""

# Worker spec template - no HTTP endpoint, process-based health
# Workers run the internal health server but don't expose any HTTP port.
WORKER_SPEC_TEMPLATE = """name: {sandbox_name}
region: {region}
workers:
  - name: sandbox
    image:
      registry_type: {registry_type}
      registry: {registry}
      repository: {repository}
      tag: {tag}
    instance_count: 1
    instance_size_slug: {instance_size}
"""

# Default values - region must include datacenter number (e.g., atl1, nyc1, sfo3)
DEFAULT_REGION = "atl1"
DEFAULT_INSTANCE_SIZE = "apps-s-1vcpu-1gb"


class Deployer:
    """Manages App Platform deployment operations."""

    def __init__(
        self,
        registry: Optional[str] = None,
        registry_type: str = "GHCR",
        owner: Optional[str] = None,
        region: str = DEFAULT_REGION,
        instance_size: str = DEFAULT_INSTANCE_SIZE,
        api_token: Optional[str] = None,
    ):
        """Initialize the deployer.

        Args:
            registry: Registry name/owner (GHCR: owner/namespace; DOCR: registry name)
            registry_type: "GHCR" (default) or "DOCR"
            owner: Image owner/namespace (default: GHCR_OWNER env or "bikramkgupta")
            region: App Platform region (e.g., "atl1", "nyc", "sfo3")
            instance_size: Instance size slug (e.g., "apps-s-1vcpu-1gb")
            api_token: DigitalOcean API token. Optional - doctl uses its own auth if not set.
        """
        self.registry = registry or owner or DEFAULT_IMAGE_OWNER
        self.registry_type = registry_type
        self.owner = owner or DEFAULT_IMAGE_OWNER
        self.region = region
        self.instance_size = instance_size
        # Token is optional - doctl uses its own auth if not provided
        self.api_token = api_token or os.environ.get("DIGITALOCEAN_TOKEN")

    def _run_doctl(
        self, args: list[str], timeout: int = 120, capture_json: bool = True
    ) -> tuple[int, str, str]:
        """Run a doctl command.

        Args:
            args: Command arguments (after 'doctl')
            timeout: Command timeout in seconds
            capture_json: If True, add --output json flag

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = ["doctl"]
        cmd.extend(args)

        if capture_json and "--output" not in args:
            cmd.extend(["--output", "json"])

        env = os.environ.copy()
        # Only override token if explicitly provided; otherwise doctl uses its own auth
        if self.api_token:
            env["DIGITALOCEAN_ACCESS_TOKEN"] = self.api_token

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

    def _generate_app_spec(
        self,
        name: str,
        image: str,
        component_type: str = "service",
    ) -> str:
        """Generate an app spec YAML for a sandbox.

        Args:
            name: The sandbox name
            image: The image type ("python" or "node")
            component_type: "service" for HTTP endpoint, "worker" for background process

        Returns:
            The app spec YAML string
        """
        repository = IMAGE_REPOS.get(image, IMAGE_REPOS["python"])
        tag = IMAGE_TAGS.get(image, "latest")
        registry_value = self.registry or self.owner
        repository_path = repository

        # Select template based on component type
        template = SERVICE_SPEC_TEMPLATE if component_type == "service" else WORKER_SPEC_TEMPLATE

        spec = template.format(
            sandbox_name=name,
            registry_type=self.registry_type,
            registry=registry_value,
            repository=repository_path,
            tag=tag,
            region=self.region,
            instance_size=self.instance_size,
        )

        return spec

    def create_app(
        self,
        name: str,
        image: str = "python",
        component_type: str = "service",
    ) -> AppInfo:
        """Create a new App Platform application.

        Args:
            name: The app name
            image: The image type ("python" or "node")
            component_type: "service" for HTTP endpoint, "worker" for background process

        Returns:
            AppInfo with the created app details

        Raises:
            SandboxCreationError: If app creation fails
        """
        # Generate app spec
        spec = self._generate_app_spec(name, image, component_type)

        # Write spec to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(spec)
            spec_path = f.name

        try:
            # Create the app
            code, stdout, stderr = self._run_doctl(
                ["apps", "create", "--spec", spec_path],
                timeout=60,
            )

            if code != 0:
                # Provide detailed error - stderr may be empty
                error_detail = stderr.strip() or stdout.strip() or f"exit code {code}"
                raise SandboxCreationError(f"Failed to create app: {error_detail}")

            # Parse the response
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    data = data[0]

                return AppInfo(
                    app_id=data.get("id", ""),
                    name=data.get("spec", {}).get("name", name),
                    status=data.get("active_deployment", {}).get("phase", "PENDING"),
                    url=data.get("live_url"),
                    region=data.get("region", {}).get("slug"),
                    created_at=data.get("created_at"),
                    updated_at=data.get("updated_at"),
                )
            except json.JSONDecodeError as e:
                raise SandboxCreationError(f"Failed to parse response: {e}")

        finally:
            # Clean up temp file
            Path(spec_path).unlink(missing_ok=True)

    def delete_app(self, app_id: str) -> bool:
        """Delete an App Platform application.

        Args:
            app_id: The app ID to delete

        Returns:
            True if deletion was successful

        Raises:
            SandboxNotFoundError: If the app doesn't exist
        """
        code, stdout, stderr = self._run_doctl(
            ["apps", "delete", app_id, "--force"],
            capture_json=False,
        )

        if code != 0:
            if "not found" in stderr.lower():
                raise SandboxNotFoundError(f"App {app_id} not found")
            # Force delete usually succeeds, ignore errors
            pass

        return True

    def get_app(self, app_id: str) -> AppInfo:
        """Get information about an app.

        Args:
            app_id: The app ID

        Returns:
            AppInfo with app details

        Raises:
            SandboxNotFoundError: If the app doesn't exist
        """
        code, stdout, stderr = self._run_doctl(["apps", "get", app_id])

        if code != 0:
            if "not found" in stderr.lower():
                raise SandboxNotFoundError(f"App {app_id} not found")
            # Provide detailed error - stderr may be empty
            error_detail = stderr.strip() or stdout.strip() or f"exit code {code}"
            raise SandboxNotFoundError(f"Failed to get app: {error_detail}")

        try:
            data = json.loads(stdout)
            if isinstance(data, list):
                data = data[0]

            # Get deployment status
            active_deployment = data.get("active_deployment", {})
            phase = active_deployment.get("phase", "UNKNOWN")

            return AppInfo(
                app_id=data.get("id", app_id),
                name=data.get("spec", {}).get("name", ""),
                status=phase,
                url=data.get("live_url"),
                region=data.get("region", {}).get("slug"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
            )
        except json.JSONDecodeError as e:
            raise SandboxNotFoundError(f"Failed to parse app info: {e}")

    def wait_ready(
        self,
        app_id: str,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> AppInfo:
        """Wait for an app to become ready.

        Args:
            app_id: The app ID
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            AppInfo when the app is ready

        Raises:
            SandboxCreationError: If the app fails to become ready
            SandboxNotFoundError: If the app doesn't exist
        """
        start = time.time()
        last_status = None

        while time.time() - start < timeout:
            app_info = self.get_app(app_id)
            status = app_info.status

            if status != last_status:
                last_status = status

            if status == "ACTIVE":
                return app_info

            if status in ("ERROR", "FAILED"):
                raise SandboxCreationError(
                    f"App deployment failed with status: {status}"
                )

            time.sleep(poll_interval)

        raise SandboxCreationError(
            f"Timed out waiting for app to be ready after {timeout}s. Last status: {last_status}"
        )

    def get_app_url(self, app_id: str) -> str:
        """Get the public URL for an app.

        Args:
            app_id: The app ID

        Returns:
            The public URL

        Raises:
            SandboxNotFoundError: If the app doesn't exist
        """
        app_info = self.get_app(app_id)
        if app_info.url:
            return app_info.url

        # Construct URL from app name if not available
        return f"https://{app_info.name}.ondigitalocean.app"
