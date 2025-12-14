"""Command-line interface for App Platform Sandbox.

This module provides a CLI for managing sandbox environments on DigitalOcean App Platform.

Usage:
    sandbox setup --registry MY_REGISTRY    # Build and push images
    sandbox create --image python           # Create a new sandbox
    sandbox list                            # List all sandboxes
    sandbox delete NAME                     # Delete a sandbox
    sandbox exec NAME "command"             # Execute a command
"""

import argparse
import json
import os
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Optional

from .deployer import (
    DEFAULT_IMAGE_OWNER,
    DEFAULT_INSTANCE_SIZE,
    DEFAULT_REGION,
    DEFAULT_REGISTRY_HOST,
    Deployer,
    IMAGE_REPOS,
)
from .sandbox import ENV_REGION, ENV_REGISTRY, Sandbox
from .image_registry import ImageRegistry


def ensure_doctl_available() -> bool:
    """Check that doctl is installed and accessible."""
    if shutil.which("doctl") is None:
        print("Error: 'doctl' not found. Install doctl and run 'doctl auth init'.")
        print("See https://docs.digitalocean.com/reference/doctl/how-to/install/")
        return False
    return True


def get_images_dir() -> Path:
    """Get the path to the images directory.

    Returns the images directory bundled with the package, or looks for it
    relative to the package installation.
    """
    # Try package data location first
    package_dir = Path(__file__).parent
    images_dir = package_dir / "images"
    if images_dir.exists():
        return images_dir

    # Try relative to package (for development)
    repo_root = package_dir.parent.parent
    images_dir = repo_root / "images"
    if images_dir.exists():
        return images_dir

    raise FileNotFoundError(
        "Could not find images directory. "
        "Please ensure the package is installed correctly or run from the repository."
    )


def run_command(cmd: list[str], capture: bool = False) -> tuple[int, str, str]:
    """Run a shell command.

    Args:
        cmd: Command and arguments
        capture: Whether to capture output

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd)
            return result.returncode, "", ""
    except Exception as e:
        return -1, "", str(e)


def run_command_with_retry(
    cmd: list[str],
    max_retries: int = 3,
    retry_delay: int = 5,
    description: str = "command"
) -> tuple[int, str, str]:
    """Run a shell command with retry logic for transient failures.

    Args:
        cmd: Command and arguments
        max_retries: Maximum number of retry attempts
        retry_delay: Seconds to wait between retries
        description: Description for logging

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    import time

    for attempt in range(1, max_retries + 1):
        code, stdout, stderr = run_command(cmd)
        if code == 0:
            return code, stdout, stderr

        # Check for transient network errors worth retrying
        error_text = stderr.lower() if stderr else ""
        transient_errors = [
            "connection reset",
            "connection refused",
            "network",
            "timeout",
            "closed network connection",
            "eof",
            "broken pipe",
        ]

        is_transient = any(err in error_text for err in transient_errors)

        if is_transient and attempt < max_retries:
            print(f"\n  Attempt {attempt}/{max_retries} failed (transient error). Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            continue
        else:
            # Non-transient error or max retries reached
            return code, stdout, stderr

    return code, stdout, stderr


def get_dockerfile_tag(dockerfile_name: str) -> str:
    """Extract tag from Dockerfile name.

    Examples:
        Dockerfile -> latest
        Dockerfile.python3.12 -> python3.12
        Dockerfile.node22 -> node22
    """
    if dockerfile_name == "Dockerfile":
        return "latest"
    # Remove "Dockerfile." prefix
    return dockerfile_name.replace("Dockerfile.", "")


def find_dockerfiles(directory: Path) -> list[tuple[Path, str]]:
    """Find all Dockerfile* files in a directory.

    Returns:
        List of (dockerfile_path, tag) tuples
    """
    dockerfiles = []
    for f in sorted(directory.iterdir()):
        if f.is_file() and f.name.startswith("Dockerfile"):
            tag = get_dockerfile_tag(f.name)
            dockerfiles.append((f, tag))
    return dockerfiles


def cmd_setup(args: argparse.Namespace) -> int:
    """Build and push sandbox images to the user's DOCR registry."""
    registry = args.registry
    build_only = args.build_only
    push_only = args.push_only

    if push_only and build_only:
        print("Error: Cannot specify both --build-only and --push-only")
        return 1

    # Handle custom Dockerfile
    if args.dockerfile:
        dockerfile_path = Path(args.dockerfile).resolve()
        if not dockerfile_path.exists():
            print(f"Error: Dockerfile not found: {dockerfile_path}")
            return 1

        if not args.name:
            print("Error: --name is required when using --dockerfile")
            return 1

        repo_name = args.name
        tag = args.tag or "latest"
        registry_url = f"registry.digitalocean.com/{registry}"
        full_tag = f"{registry_url}/{repo_name}:{tag}"

        if not push_only:
            print(f"\n{'='*60}")
            print(f"Building custom image: {repo_name}:{tag}")
            print(f"{'='*60}")
            cmd = [
                "docker", "build",
                "--platform", "linux/amd64",
                "-f", str(dockerfile_path),
                "-t", full_tag,
                str(dockerfile_path.parent)
            ]
            code, _, stderr = run_command(cmd)
            if code != 0:
                print(f"Error building image: {stderr}")
                return 1
            print(f"Successfully built: {full_tag}")

        if not build_only:
            print(f"\n{'='*60}")
            print(f"Pushing {repo_name}:{tag} to {registry}...")
            print(f"{'='*60}")
            cmd = ["docker", "push", full_tag]
            code, _, stderr = run_command_with_retry(cmd, max_retries=3, retry_delay=5)
            if code != 0:
                print(f"Error pushing image: {stderr}")
                print("\nTip: Make sure you're logged in to DOCR:")
                print(f"  doctl registry login")
                return 1
            print(f"Successfully pushed: {full_tag}")

        print(f"\n{'='*60}")
        print("Setup complete!")
        print(f"{'='*60}")
        print(f"\nYour custom image is available at: {full_tag}")
        return 0

    # Build all built-in images
    try:
        images_dir = get_images_dir()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    image_types = ["python", "node"]
    registry_url = f"registry.digitalocean.com/{registry}"
    built_images = []

    for image_type in image_types:
        image_dir = images_dir / image_type
        if not image_dir.exists():
            print(f"Warning: Image directory not found: {image_dir}")
            continue

        repo_name = IMAGE_REPOS.get(image_type, f"sandbox-{image_type}")

        # Find all Dockerfile* files
        dockerfiles = find_dockerfiles(image_dir)
        if not dockerfiles:
            print(f"Warning: No Dockerfiles found in {image_dir}")
            continue

        for dockerfile_path, tag in dockerfiles:
            full_tag = f"{registry_url}/{repo_name}:{tag}"

            if not push_only:
                # Build the image
                print(f"\n{'='*60}")
                print(f"Building {image_type}:{tag} from {dockerfile_path.name}...")
                print(f"{'='*60}")
                cmd = [
                    "docker", "build",
                    "--platform", "linux/amd64",
                    "-f", str(dockerfile_path),
                    "-t", full_tag,
                    str(image_dir)
                ]
                code, _, stderr = run_command(cmd)
                if code != 0:
                    print(f"Error building {image_type}:{tag}: {stderr}")
                    return 1
                print(f"Successfully built: {full_tag}")

            if not build_only:
                # Push the image with retry for transient network errors
                print(f"\n{'='*60}")
                print(f"Pushing {image_type}:{tag} to {registry}...")
                print(f"{'='*60}")
                cmd = ["docker", "push", full_tag]
                code, _, stderr = run_command_with_retry(cmd, max_retries=3, retry_delay=5)
                if code != 0:
                    print(f"Error pushing {image_type}:{tag}: {stderr}")
                    print("\nTip: Make sure you're logged in to DOCR:")
                    print(f"  doctl registry login")
                    return 1
                print(f"Successfully pushed: {full_tag}")

            built_images.append(full_tag)

    print(f"\n{'='*60}")
    print("Setup complete!")
    print(f"{'='*60}")
    print(f"\nBuilt {len(built_images)} images to registry: {registry}")
    for img in built_images:
        print(f"  - {img}")
    print("\nTo use the SDK, set your environment variables:")
    print(f"  export {ENV_REGISTRY}={registry}")
    print(f"  export {ENV_REGION}={args.region or DEFAULT_REGION}")
    print("\nOr pass them directly to Sandbox.create():")
    print(f'  sandbox = Sandbox.create(registry="{registry}", image="python")')

    return 0


def cmd_create(args: argparse.Namespace) -> int:
    """Create a new sandbox."""
    # Registry host is optional - defaults to GHCR public images
    registry = args.registry or os.environ.get(ENV_REGISTRY) or DEFAULT_REGISTRY_HOST
    region = (args.region or os.environ.get(ENV_REGION) or DEFAULT_REGION).lower()
    instance_size = args.instance_size or DEFAULT_INSTANCE_SIZE
    component_type = getattr(args, 'component_type', 'service') or 'service'

    registry_display = f"{registry}/{DEFAULT_IMAGE_OWNER}"

    print(f"Creating sandbox...")
    print(f"  Image: {args.image}")
    print(f"  Type: {component_type}")
    print(f"  Registry: {registry_display}")
    print(f"  Region: {region}")
    print(f"  Instance size: {instance_size}")
    if args.name:
        print(f"  Name: {args.name}")

    try:
        sandbox = Sandbox.create(
            image=args.image,
            name=args.name,
            region=region,
            instance_size=instance_size,
            component_type=component_type,
            registry=registry,
            wait_ready=not args.no_wait,
        )
        print(f"\nSandbox created successfully!")
        print(f"  ID: {sandbox.app_id}")
        url = sandbox.get_url()
        if url:
            print(f"  URL: {url}")
        else:
            print(f"  URL: (none - worker has no HTTP endpoint)")
        print(f"  Status: {sandbox.status}")

        if args.no_wait:
            print("\nNote: Sandbox may still be deploying. Use 'sandbox list' to check status.")

        return 0
    except Exception as e:
        print(f"Error creating sandbox: {e}")
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all sandboxes."""
    # Registry host is optional - defaults to GHCR host
    registry = args.registry or os.environ.get(ENV_REGISTRY) or DEFAULT_REGISTRY_HOST

    # Known sandbox repositories
    SANDBOX_REPOS = {"sandbox-python", "sandbox-node"}

    try:
        deployer = Deployer(registry=registry)

        # Get all apps using doctl
        code, stdout, stderr = deployer._run_doctl(["apps", "list"])
        if code != 0:
            print(f"Error listing apps: {stderr}")
            return 1

        apps = json.loads(stdout) if stdout.strip() else []

        # Filter by repository (sandbox-python or sandbox-node)
        # If registry is specified, also filter by registry
        sandboxes = []
        for app in apps:
            # Check services first
            services = app.get("spec", {}).get("services", [])
            # Also check workers
            workers = app.get("spec", {}).get("workers", [])
            components = services + workers

            if not components:
                continue

            image = components[0].get("image", {})
            app_registry = image.get("registry", "")
            app_repo = image.get("repository", "")
            repo_name = app_repo.split("/")[-1] if app_repo else ""

            # Match by repository name
            if repo_name not in SANDBOX_REPOS:
                continue

            # If registry host filter specified, apply it
            if registry and app_registry and app_registry != registry:
                continue

            sandboxes.append(app)

        if args.json:
            print(json.dumps(sandboxes, indent=2))
            return 0

        if not sandboxes:
            print("No sandboxes found.")
            return 0

        # Print table header
        print(f"{'NAME':<25} {'ID':<40} {'STATUS':<12} {'REGION':<8} {'URL'}")
        print("-" * 120)

        for app in sandboxes:
            name = app.get("spec", {}).get("name", "")
            app_id = app.get("id", "")
            status = app.get("active_deployment", {}).get("phase", "UNKNOWN")
            region = app.get("region", {}).get("slug", "")
            url = app.get("live_url", "")

            print(f"{name:<25} {app_id:<40} {status:<12} {region:<8} {url}")

        return 0
    except Exception as e:
        print(f"Error listing sandboxes: {e}")
        return 1


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a sandbox."""
    # Registry host is optional
    registry = args.registry or os.environ.get(ENV_REGISTRY) or DEFAULT_REGISTRY_HOST

    # Known sandbox repositories
    SANDBOX_REPOS = {"sandbox-python", "sandbox-node"}

    deployer = Deployer(registry=registry)

    if args.all:
        # Delete all sandboxes
        if not args.force:
            confirm = input("Are you sure you want to delete ALL sandboxes? [y/N]: ")
            if confirm.lower() != "y":
                print("Cancelled.")
                return 0

        code, stdout, stderr = deployer._run_doctl(["apps", "list"])
        if code != 0:
            print(f"Error listing apps: {stderr}")
            return 1

        apps = json.loads(stdout) if stdout.strip() else []
        # Filter by repository (sandbox-python or sandbox-node)
        # Include both services and workers
        sandboxes = []
        for app in apps:
            services = app.get("spec", {}).get("services", [])
            workers = app.get("spec", {}).get("workers", [])
            components = services + workers

            if not components:
                continue

            image = components[0].get("image", {})
            app_registry = image.get("registry", "")
            app_repo = image.get("repository", "")
            repo_name = app_repo.split("/")[-1] if app_repo else ""

            # Match by repository name
            if repo_name not in SANDBOX_REPOS:
                continue

            # If registry filter specified, apply it
            if registry and app_registry and app_registry != registry:
                continue

            sandboxes.append(app)

        if not sandboxes:
            print("No sandboxes to delete.")
            return 0

        deleted = 0
        for app in sandboxes:
            app_id = app.get("id", "")
            name = app.get("spec", {}).get("name", "")
            try:
                deployer.delete_app(app_id)
                print(f"Deleted: {name} ({app_id})")
                deleted += 1
            except Exception as e:
                print(f"Failed to delete {name}: {e}")

        print(f"\nDeleted {deleted} sandbox(es).")
        return 0

    # Delete specific sandbox
    target = args.name or args.id
    if not target:
        print("Error: Specify a sandbox name or --id")
        return 1

    # If it looks like an ID (UUID format), use it directly
    if args.id or (len(target) > 30 and "-" in target):
        app_id = target
    else:
        # Look up by name
        code, stdout, stderr = deployer._run_doctl(["apps", "list"])
        if code != 0:
            print(f"Error listing apps: {stderr}")
            return 1

        apps = json.loads(stdout) if stdout.strip() else []
        matching = [
            app for app in apps
            if app.get("spec", {}).get("name", "") == target
        ]

        if not matching:
            print(f"Sandbox '{target}' not found.")
            return 1

        app_id = matching[0].get("id", "")

    try:
        deployer.delete_app(app_id)
        print(f"Deleted sandbox: {target}")
        return 0
    except Exception as e:
        print(f"Error deleting sandbox: {e}")
        return 1


def cmd_exec(args: argparse.Namespace) -> int:
    """Execute a command in a sandbox."""
    # Registry is optional for exec - get_from_id doesn't need it
    registry = args.registry or os.environ.get(ENV_REGISTRY) or DEFAULT_REGISTRY_HOST

    target = args.target
    command = args.command

    # Resolve target to app ID
    if args.is_id or (len(target) > 30 and "-" in target):
        app_id = target
    else:
        # Look up by name
        deployer = Deployer(registry=registry)
        code, stdout, stderr = deployer._run_doctl(["apps", "list"])
        if code != 0:
            print(f"Error listing apps: {stderr}")
            return 1

        apps = json.loads(stdout) if stdout.strip() else []
        matching = [
            app for app in apps
            if app.get("spec", {}).get("name", "") == target
        ]

        if not matching:
            print(f"Sandbox '{target}' not found.")
            return 1

        app_id = matching[0].get("id", "")

    try:
        sandbox = Sandbox.get_from_id(app_id)
        result = sandbox.exec(command, timeout=args.timeout)

        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        return result.exit_code
    except Exception as e:
        print(f"Error executing command: {e}")
        return 1


def cmd_image_add(args: argparse.Namespace) -> int:
    """Register a new custom image for validation."""
    registry = args.registry or os.environ.get(ENV_REGISTRY)
    if not registry:
        print(f"Error: Registry is required. Set --registry or {ENV_REGISTRY} env var.")
        return 1

    # Validate Dockerfile exists
    dockerfile_path = args.dockerfile
    if not os.path.exists(dockerfile_path):
        print(f"Error: Dockerfile not found: {dockerfile_path}")
        return 1

    try:
        image_registry = ImageRegistry()
        image_info = image_registry.add_image(
            name=args.name,
            dockerfile_path=dockerfile_path,
            registry=registry,
        )

        print(f"Image '{args.name}' queued for validation.")
        print(f"  Dockerfile: {image_info.dockerfile_path}")
        print(f"  Image URL: {image_info.image_url}")
        print(f"  Log file: {image_info.validation_log}")

        # Start background validation process
        import subprocess
        validator_module = "do_app_sandbox.image_validator"
        proc = subprocess.Popen(
            [sys.executable, "-m", validator_module, args.name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Update registry with PID
        image_registry.update_status(args.name, "validating", validation_pid=proc.pid)

        print(f"\nValidation started (PID: {proc.pid})")
        print(f"Check status with: sandbox image status {args.name}")

        return 0
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error registering image: {e}")
        return 1


def cmd_image_status(args: argparse.Namespace) -> int:
    """Check validation status of a custom image."""
    try:
        image_registry = ImageRegistry()
        image = image_registry.get_image(args.name)

        if image is None:
            print(f"Image '{args.name}' not found.")
            return 1

        if image.dockerfile_path == "<built-in>":
            print(f"Image '{args.name}' is a built-in image (always ready).")
            return 0

        print(f"Image: {args.name}")
        print(f"  Status: {image.status}")
        print(f"  Dockerfile: {image.dockerfile_path}")
        print(f"  Image URL: {image.image_url}")
        print(f"  Created: {image.created_at}")

        if image.validated_at:
            print(f"  Validated: {image.validated_at}")

        if image.validation_pid:
            # Check if process is still running
            try:
                os.kill(image.validation_pid, 0)
                print(f"  Validation PID: {image.validation_pid} (running)")
            except OSError:
                print(f"  Validation PID: {image.validation_pid} (completed)")

        if image.validation_results:
            vr = image.validation_results
            print("\n  Validation Results:")
            print(f"    Dockerfile parsed: {'Yes' if vr.dockerfile_parsed else 'No'}")
            print(f"    EXPOSE 8080: {'Yes' if vr.has_expose_8080 else 'No'}")
            print(f"    ENTRYPOINT/CMD: {'Yes' if vr.has_entrypoint else 'No'}")
            print(f"    Image built: {'Yes' if vr.image_built else 'No'}")
            print(f"    Container started: {'Yes' if vr.container_started else 'No'}")
            print(f"    Health check passed: {'Yes' if vr.health_check_passed else 'No'}")
            if vr.error:
                print(f"    Error: {vr.error}")

        if image.validation_log and os.path.exists(image.validation_log):
            if args.logs:
                print(f"\n  Validation Log ({image.validation_log}):")
                print("  " + "-" * 50)
                with open(image.validation_log, "r") as f:
                    for line in f:
                        print(f"  {line}", end="")
            else:
                print(f"\n  View logs with: sandbox image status {args.name} --logs")

        return 0
    except Exception as e:
        print(f"Error getting image status: {e}")
        return 1


def cmd_image_list(args: argparse.Namespace) -> int:
    """List all registered images."""
    try:
        image_registry = ImageRegistry()
        images = image_registry.list_images()

        if args.json:
            data = []
            for img in images:
                data.append({
                    "name": img.name,
                    "status": img.status,
                    "registry": img.registry,
                    "image_url": img.image_url,
                    "created_at": img.created_at,
                    "validated_at": img.validated_at,
                })
            print(json.dumps(data, indent=2))
            return 0

        if not images:
            print("No images registered.")
            return 0

        # Print table header
        print(f"{'NAME':<15} {'STATUS':<12} {'REGISTRY':<30} {'VALIDATED_AT'}")
        print("-" * 80)

        for img in images:
            validated = img.validated_at if img.validated_at else "-"
            registry_display = img.registry if img.registry != "<built-in>" else "(built-in)"
            print(f"{img.name:<15} {img.status:<12} {registry_display:<30} {validated}")

        return 0
    except Exception as e:
        print(f"Error listing images: {e}")
        return 1


def cmd_image_remove(args: argparse.Namespace) -> int:
    """Remove a custom image from the registry."""
    try:
        image_registry = ImageRegistry()

        # Check if image exists first
        image = image_registry.get_image(args.name)
        if image is None:
            print(f"Image '{args.name}' not found.")
            return 1

        if image.dockerfile_path == "<built-in>":
            print(f"Error: Cannot remove built-in image '{args.name}'.")
            return 1

        if not args.force:
            confirm = input(f"Remove image '{args.name}'? [y/N]: ")
            if confirm.lower() != "y":
                print("Cancelled.")
                return 0

        if image_registry.remove_image(args.name):
            print(f"Image '{args.name}' removed.")
            print(f"\nNote: The Docker image {image.image_url} was NOT deleted from the registry.")
            print("You can remove it manually with: docker rmi " + image.image_url)
            return 0
        else:
            print(f"Failed to remove image '{args.name}'.")
            return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error removing image: {e}")
        return 1


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="sandbox",
        description="Manage sandbox environments on DigitalOcean App Platform",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="app-platform-sandbox 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # setup command
    setup_parser = subparsers.add_parser(
        "setup",
        help="Build and push sandbox images to your DOCR registry",
    )
    setup_parser.add_argument(
        "--registry", "-r",
        required=True,
        help="Your DOCR registry name",
    )
    setup_parser.add_argument(
        "--region",
        help=f"Default region for sandboxes (default: {DEFAULT_REGION})",
    )
    setup_parser.add_argument(
        "--build-only",
        action="store_true",
        help="Only build images, don't push",
    )
    setup_parser.add_argument(
        "--push-only",
        action="store_true",
        help="Only push images, don't build",
    )
    setup_parser.add_argument(
        "--dockerfile", "-d",
        help="Path to a custom Dockerfile (requires --name)",
    )
    setup_parser.add_argument(
        "--name", "-n",
        help="Repository name for custom Dockerfile (e.g., 'my-sandbox')",
    )
    setup_parser.add_argument(
        "--tag", "-t",
        help="Tag for custom image (default: latest)",
    )
    setup_parser.set_defaults(func=cmd_setup)

    # create command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new sandbox",
    )
    create_parser.add_argument(
        "--image", "-i",
        required=True,
        choices=["python", "node"],
        help="Sandbox image type (required)",
    )
    create_parser.add_argument(
        "--name", "-n",
        help="Name for the sandbox (auto-generated if not provided)",
    )
    create_parser.add_argument(
        "--region",
        help=f"App Platform region (or set {ENV_REGION}, default: {DEFAULT_REGION})",
    )
    create_parser.add_argument(
        "--instance-size",
        help=f"Instance size slug (default: {DEFAULT_INSTANCE_SIZE})",
    )
    create_parser.add_argument(
        "--registry", "-r",
        help=f"DOCR registry (optional - uses GHCR public images if not set)",
    )
    create_parser.add_argument(
        "--component-type", "-t",
        choices=["service", "worker"],
        default="service",
        help="Component type: 'service' for HTTP endpoint (default), 'worker' for background process",
    )
    create_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for sandbox to be ready",
    )
    create_parser.set_defaults(func=cmd_create)

    # list command
    list_parser = subparsers.add_parser(
        "list",
        help="List all sandboxes",
    )
    list_parser.add_argument(
        "--registry", "-r",
        help="Filter by DOCR registry (optional - lists all sandboxes if not set)",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    list_parser.set_defaults(func=cmd_list)

    # delete command
    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a sandbox",
    )
    delete_parser.add_argument(
        "name",
        nargs="?",
        help="Sandbox name to delete",
    )
    delete_parser.add_argument(
        "--registry", "-r",
        help="Filter by DOCR registry (optional)",
    )
    delete_parser.add_argument(
        "--id",
        help="Delete by app ID instead of name",
    )
    delete_parser.add_argument(
        "--all",
        action="store_true",
        help="Delete all sandboxes",
    )
    delete_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompts",
    )
    delete_parser.set_defaults(func=cmd_delete)

    # exec command
    exec_parser = subparsers.add_parser(
        "exec",
        help="Execute a command in a sandbox",
    )
    exec_parser.add_argument(
        "target",
        help="Sandbox name or ID",
    )
    exec_parser.add_argument(
        "command",
        help="Command to execute",
    )
    exec_parser.add_argument(
        "--registry", "-r",
        help="DOCR registry for name lookup (optional - not needed with --id)",
    )
    exec_parser.add_argument(
        "--id",
        dest="is_id",
        action="store_true",
        help="Treat target as app ID instead of name",
    )
    exec_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=120,
        help="Command timeout in seconds (default: 120)",
    )
    exec_parser.set_defaults(func=cmd_exec)

    # image command group
    image_parser = subparsers.add_parser(
        "image",
        help="Manage custom sandbox images",
    )
    image_subparsers = image_parser.add_subparsers(dest="image_command", help="Image commands")

    # image add
    image_add_parser = image_subparsers.add_parser(
        "add",
        help="Register a custom image for validation",
    )
    image_add_parser.add_argument(
        "--name", "-n",
        required=True,
        help="Unique name for the image",
    )
    image_add_parser.add_argument(
        "--dockerfile", "-d",
        required=True,
        help="Path to Dockerfile",
    )
    image_add_parser.add_argument(
        "--registry", "-r",
        help=f"DOCR registry name (or set {ENV_REGISTRY})",
    )
    image_add_parser.set_defaults(func=cmd_image_add)

    # image status
    image_status_parser = image_subparsers.add_parser(
        "status",
        help="Check validation status of a custom image",
    )
    image_status_parser.add_argument(
        "name",
        help="Image name to check",
    )
    image_status_parser.add_argument(
        "--logs",
        action="store_true",
        help="Show validation logs",
    )
    image_status_parser.set_defaults(func=cmd_image_status)

    # image list
    image_list_parser = image_subparsers.add_parser(
        "list",
        help="List all registered images",
    )
    image_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    image_list_parser.set_defaults(func=cmd_image_list)

    # image remove
    image_remove_parser = image_subparsers.add_parser(
        "remove",
        help="Remove a custom image from the registry",
    )
    image_remove_parser.add_argument(
        "name",
        help="Image name to remove",
    )
    image_remove_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    image_remove_parser.set_defaults(func=cmd_image_remove)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if not ensure_doctl_available():
        return 1

    # Handle image subcommand without action
    if args.command == "image" and not getattr(args, "image_command", None):
        image_parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
