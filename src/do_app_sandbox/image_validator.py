"""Background image validation for custom sandbox images."""

import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from .image_registry import ImageRegistry
from .types import ValidationResult


class ImageValidator:
    """Validates custom Docker images for sandbox compatibility."""

    HEALTH_CHECK_TIMEOUT = 60  # seconds to wait for health check
    HEALTH_CHECK_INTERVAL = 2  # seconds between health check attempts

    def __init__(self, registry: Optional[ImageRegistry] = None):
        """Initialize the validator.

        Args:
            registry: ImageRegistry instance. Creates default if not provided.
        """
        self.registry = registry or ImageRegistry()

    def validate_dockerfile(self, dockerfile_path: str) -> Tuple[bool, ValidationResult]:
        """Parse and validate Dockerfile requirements.

        Args:
            dockerfile_path: Path to Dockerfile

        Returns:
            Tuple of (success, ValidationResult)
        """
        result = ValidationResult()

        try:
            with open(dockerfile_path, "r") as f:
                content = f.read()
            result.dockerfile_parsed = True
        except Exception as e:
            result.error = f"Failed to read Dockerfile: {e}"
            return False, result

        # Check for EXPOSE 8080
        expose_pattern = r"^\s*EXPOSE\s+.*\b8080\b"
        if re.search(expose_pattern, content, re.MULTILINE | re.IGNORECASE):
            result.has_expose_8080 = True
        else:
            result.error = "Dockerfile must EXPOSE 8080"
            return False, result

        # Check for ENTRYPOINT or CMD
        entrypoint_pattern = r"^\s*(ENTRYPOINT|CMD)\s+"
        if re.search(entrypoint_pattern, content, re.MULTILINE | re.IGNORECASE):
            result.has_entrypoint = True
        else:
            result.error = "Dockerfile must have ENTRYPOINT or CMD"
            return False, result

        return True, result

    def build_image(
        self,
        dockerfile_path: str,
        image_url: str,
        log_file: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Build Docker image from Dockerfile.

        Args:
            dockerfile_path: Path to Dockerfile
            image_url: Target image URL (tag)
            log_file: Optional file to write build logs

        Returns:
            Tuple of (success, error_message)
        """
        dockerfile_dir = os.path.dirname(os.path.abspath(dockerfile_path))

        cmd = ["docker", "build", "-t", image_url, "-f", dockerfile_path, dockerfile_dir]

        try:
            if log_file:
                with open(log_file, "a") as f:
                    f.write(f"\n=== Building image: {image_url} ===\n")
                    f.write(f"Command: {' '.join(cmd)}\n\n")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for build
            )

            if log_file:
                with open(log_file, "a") as f:
                    f.write(result.stdout)
                    if result.stderr:
                        f.write(f"\nSTDERR:\n{result.stderr}")

            if result.returncode != 0:
                return False, f"Docker build failed: {result.stderr}"

            return True, ""

        except subprocess.TimeoutExpired:
            return False, "Docker build timed out after 10 minutes"
        except Exception as e:
            return False, f"Docker build error: {e}"

    def push_image(self, image_url: str, log_file: Optional[str] = None) -> Tuple[bool, str]:
        """Push image to registry.

        Args:
            image_url: Image URL to push
            log_file: Optional file to write push logs

        Returns:
            Tuple of (success, error_message)
        """
        cmd = ["docker", "push", image_url]

        try:
            if log_file:
                with open(log_file, "a") as f:
                    f.write(f"\n=== Pushing image: {image_url} ===\n")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for push
            )

            if log_file:
                with open(log_file, "a") as f:
                    f.write(result.stdout)
                    if result.stderr:
                        f.write(f"\nSTDERR:\n{result.stderr}")

            if result.returncode != 0:
                return False, f"Docker push failed: {result.stderr}"

            return True, ""

        except subprocess.TimeoutExpired:
            return False, "Docker push timed out after 5 minutes"
        except Exception as e:
            return False, f"Docker push error: {e}"

    def run_test_container(
        self,
        image_url: str,
        log_file: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """Run a test container and verify health endpoint.

        Args:
            image_url: Image URL to test
            log_file: Optional file to write test logs

        Returns:
            Tuple of (success, error_message, container_id)
        """
        container_name = f"sandbox-test-{os.getpid()}"

        # Start container
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            "18080:8080",  # Use high port to avoid conflicts
            image_url,
        ]

        try:
            if log_file:
                with open(log_file, "a") as f:
                    f.write(f"\n=== Starting test container ===\n")
                    f.write(f"Command: {' '.join(cmd)}\n")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return False, f"Failed to start container: {result.stderr}", None

            container_id = result.stdout.strip()

            if log_file:
                with open(log_file, "a") as f:
                    f.write(f"Container ID: {container_id}\n")

            # Wait for container to be running
            time.sleep(2)

            # Check if container is still running
            inspect_result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
                capture_output=True,
                text=True,
            )

            if inspect_result.stdout.strip() != "true":
                # Get logs for debugging
                logs = subprocess.run(
                    ["docker", "logs", container_id],
                    capture_output=True,
                    text=True,
                )
                if log_file:
                    with open(log_file, "a") as f:
                        f.write(f"\nContainer logs:\n{logs.stdout}\n{logs.stderr}\n")
                return False, "Container exited unexpectedly", container_id

            return True, "", container_id

        except subprocess.TimeoutExpired:
            return False, "Container start timed out", None
        except Exception as e:
            return False, f"Container error: {e}", None

    def check_health_endpoint(
        self,
        port: int = 18080,
        log_file: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Check if health endpoint responds.

        Args:
            port: Port to check
            log_file: Optional file to write logs

        Returns:
            Tuple of (success, error_message)
        """
        url = f"http://localhost:{port}/health"
        start_time = time.time()

        if log_file:
            with open(log_file, "a") as f:
                f.write(f"\n=== Checking health endpoint: {url} ===\n")

        while time.time() - start_time < self.HEALTH_CHECK_TIMEOUT:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        if log_file:
                            with open(log_file, "a") as f:
                                f.write(f"Health check passed! Status: {response.status}\n")
                        return True, ""
            except Exception as e:
                if log_file:
                    with open(log_file, "a") as f:
                        f.write(f"Health check attempt failed: {e}\n")

            time.sleep(self.HEALTH_CHECK_INTERVAL)

        return False, f"Health endpoint did not respond within {self.HEALTH_CHECK_TIMEOUT}s"

    def cleanup_container(self, container_id: str, log_file: Optional[str] = None) -> None:
        """Stop and remove test container.

        Args:
            container_id: Container ID to cleanup
            log_file: Optional file to write logs
        """
        if log_file:
            with open(log_file, "a") as f:
                f.write(f"\n=== Cleaning up container: {container_id} ===\n")

        try:
            subprocess.run(["docker", "stop", container_id], capture_output=True, timeout=30)
            subprocess.run(["docker", "rm", container_id], capture_output=True, timeout=10)
        except Exception:
            pass  # Best effort cleanup

    def validate_image(self, image_name: str) -> ValidationResult:
        """Run full validation for a registered image.

        This is designed to be run in a background process.

        Args:
            image_name: Name of registered image to validate

        Returns:
            ValidationResult with all checks
        """
        image = self.registry.get_image(image_name)
        if image is None:
            return ValidationResult(error=f"Image '{image_name}' not found in registry")

        log_file = image.validation_log
        result = ValidationResult()
        container_id = None

        try:
            # Initialize log file
            if log_file:
                with open(log_file, "w") as f:
                    f.write(f"=== Validation started for: {image_name} ===\n")
                    f.write(f"Dockerfile: {image.dockerfile_path}\n")
                    f.write(f"Image URL: {image.image_url}\n\n")

            # Step 1: Validate Dockerfile
            success, result = self.validate_dockerfile(image.dockerfile_path)
            if not success:
                self.registry.update_status(image_name, "failed", validation_results=result)
                return result

            # Step 2: Build image
            success, error = self.build_image(
                image.dockerfile_path, image.image_url, log_file
            )
            if success:
                result.image_built = True
            else:
                result.error = error
                self.registry.update_status(image_name, "failed", validation_results=result)
                return result

            # Step 3: Push image
            success, error = self.push_image(image.image_url, log_file)
            if not success:
                result.error = error
                self.registry.update_status(image_name, "failed", validation_results=result)
                return result

            # Step 4: Run test container
            success, error, container_id = self.run_test_container(
                image.image_url, log_file
            )
            if success:
                result.container_started = True
            else:
                result.error = error
                self.registry.update_status(image_name, "failed", validation_results=result)
                return result

            # Step 5: Check health endpoint
            success, error = self.check_health_endpoint(log_file=log_file)
            if success:
                result.health_check_passed = True
            else:
                result.error = error
                self.registry.update_status(image_name, "failed", validation_results=result)
                return result

            # All checks passed
            self.registry.update_status(image_name, "validated", validation_results=result)

            if log_file:
                with open(log_file, "a") as f:
                    f.write(f"\n=== Validation PASSED ===\n")

            return result

        finally:
            # Cleanup test container
            if container_id:
                self.cleanup_container(container_id, log_file)


def run_validation(image_name: str, config_dir: Optional[str] = None) -> None:
    """Entry point for background validation process.

    Args:
        image_name: Name of image to validate
        config_dir: Optional config directory path
    """
    registry = ImageRegistry(config_dir)
    validator = ImageValidator(registry)

    # Update status with our PID
    registry.update_status(image_name, "validating", validation_pid=os.getpid())

    # Run validation
    validator.validate_image(image_name)


if __name__ == "__main__":
    # Allow running as: python -m do_app_sandbox.image_validator IMAGE_NAME [CONFIG_DIR]
    if len(sys.argv) < 2:
        print("Usage: python -m do_app_sandbox.image_validator IMAGE_NAME [CONFIG_DIR]")
        sys.exit(1)

    image_name = sys.argv[1]
    config_dir = sys.argv[2] if len(sys.argv) > 2 else None
    run_validation(image_name, config_dir)
