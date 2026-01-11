#!/usr/bin/env python3
"""Create snapshots for benchmark testing.

This script creates service-mode sandboxes, installs real applications
with dependencies, verifies they work, then creates snapshots.

Usage:
    cd tests/benchmarks && python scripts/create_snapshots.py

Output:
    Creates snapshots in DO Spaces and writes config to results/snapshot_config.json
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from do_app_sandbox import Sandbox
from do_app_sandbox.spaces import create_spaces_config_from_env
from do_app_sandbox.types import SandboxMode


def write_file_via_api(sandbox: Sandbox, path: str, content: str, retries: int = 3):
    """Write a file using the sandbox HTTP API with retries."""
    url = f"{sandbox.get_url()}/api/files/content"
    headers = {"Authorization": f"Bearer {sandbox._service_token}"}

    last_error = None
    for attempt in range(retries):
        try:
            response = httpx.post(
                url,
                json={"path": path, "content": content},
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries} for {path}: {e}")
                time.sleep(5)  # Wait before retry

    raise last_error


# Configuration
BENCHMARK_DIR = Path(__file__).parent.parent
FIXTURES_DIR = BENCHMARK_DIR / "fixtures"
RESULTS_DIR = BENCHMARK_DIR / "results"
CONFIG_FILE = RESULTS_DIR / "snapshot_config.json"


def print_step(step: int, total: int, message: str):
    """Print a formatted step message."""
    print(f"\n[{step}/{total}] {message}")
    print("-" * 60)


def create_python_snapshot(do_token: str, spaces_config) -> dict:
    """Create a snapshot of the Python Flask app."""
    print("\n" + "=" * 60)
    print("  Creating Python Flask App Snapshot")
    print("=" * 60)

    sandbox = None
    snapshot_id = f"bench-python-flask-{int(time.time())}"

    try:
        # Step 1: Create sandbox
        print_step(1, 6, "Creating service-mode sandbox...")
        start = time.time()
        sandbox = Sandbox.create(
            image="python",
            mode=SandboxMode.SERVICE,
            wait_ready=True,
            timeout=300,
            spaces_config=spaces_config,
        )
        create_time = time.time() - start
        print(f"  Created {sandbox.app_id} in {create_time:.1f}s")
        print(f"  URL: {sandbox.get_url()}")

        # Wait a bit for DNS propagation
        print("  Waiting for DNS propagation...")
        time.sleep(10)

        # Step 2: Upload app files
        print_step(2, 6, "Uploading Python app files...")
        app_dir = FIXTURES_DIR / "python_app"

        # Read and upload files
        with open(app_dir / "requirements.txt") as f:
            requirements = f.read()
        with open(app_dir / "app.py") as f:
            app_code = f.read()

        write_file_via_api(sandbox, "/workspace/requirements.txt", requirements)
        write_file_via_api(sandbox, "/workspace/app.py", app_code)
        print("  Uploaded requirements.txt and app.py")

        # Step 3: Install dependencies
        print_step(3, 6, "Installing Python dependencies (this takes a while)...")
        start = time.time()

        # Create venv and install
        result = sandbox.exec("cd /workspace && python -m venv .venv", timeout=60)
        if result.exit_code != 0:
            raise RuntimeError(f"venv creation failed: {result.stderr}")

        result = sandbox.exec(
            "cd /workspace && . .venv/bin/activate && pip install -r requirements.txt",
            timeout=600,
        )
        if result.exit_code != 0:
            raise RuntimeError(f"pip install failed: {result.stderr}")

        install_time = time.time() - start
        print(f"  Dependencies installed in {install_time:.1f}s")

        # Check venv size
        result = sandbox.exec("du -sh /workspace/.venv")
        print(f"  .venv size: {result.stdout.strip()}")

        # Step 4: Initialize DB and verify app starts
        print_step(4, 6, "Starting app and verifying...")

        # Get service client for background execution
        client = sandbox._get_service_client()

        # Start the app in background using the proper background API
        pid = client.exec_background(
            command=". .venv/bin/activate && python app.py",
            cwd="/workspace",
        )
        print(f"  Started Flask app with PID {pid}")

        # Wait for app to start
        time.sleep(5)

        # Check health endpoint
        for attempt in range(10):
            try:
                health_result = client.exec("curl -s http://localhost:5000/health", timeout=10)
                if "healthy" in health_result.stdout:
                    print(f"  Health check passed: {health_result.stdout.strip()}")
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("App health check failed after 10 attempts")

        # Check verify endpoint
        verify_result = client.exec("curl -s http://localhost:5000/verify", timeout=10)
        print(f"  Verify check: {verify_result.stdout.strip()[:100]}...")

        if "verified" not in verify_result.stdout:
            raise RuntimeError(f"App verification failed: {verify_result.stdout}")

        # Stop the app
        client.kill_process(pid)

        # Step 5: Create snapshot
        print_step(5, 6, "Creating snapshot...")
        start = time.time()

        metadata = sandbox.create_snapshot(
            snapshot_id=snapshot_id,
            paths=["/workspace"],
            description="Python Flask benchmark app with SQLAlchemy, Pydantic, numpy",
        )

        snapshot_time = time.time() - start
        print(f"  Snapshot created in {snapshot_time:.1f}s")
        print(f"  Snapshot ID: {metadata.snapshot_id}")
        print(f"  Size: {metadata.size_bytes / 1024 / 1024:.1f} MB")

        # Step 6: Cleanup
        print_step(6, 6, "Deleting sandbox...")
        sandbox.delete()
        print("  Sandbox deleted")

        return {
            "snapshot_id": metadata.snapshot_id,
            "size_bytes": metadata.size_bytes,
            "size_mb": round(metadata.size_bytes / 1024 / 1024, 1),
            "created_at": metadata.created_at,
            "image": "python",
            "app_type": "flask",
        }

    except Exception as e:
        print(f"\nERROR: {e}")
        if sandbox:
            try:
                sandbox.delete()
            except Exception:
                pass
        raise


def create_node_snapshot(do_token: str, spaces_config) -> dict:
    """Create a snapshot of the Node Express app."""
    print("\n" + "=" * 60)
    print("  Creating Node Express App Snapshot")
    print("=" * 60)

    sandbox = None
    snapshot_id = f"bench-node-express-{int(time.time())}"

    try:
        # Step 1: Create sandbox
        print_step(1, 6, "Creating service-mode sandbox...")
        start = time.time()
        sandbox = Sandbox.create(
            image="node",
            mode=SandboxMode.SERVICE,
            wait_ready=True,
            timeout=300,
            spaces_config=spaces_config,
        )
        create_time = time.time() - start
        print(f"  Created {sandbox.app_id} in {create_time:.1f}s")
        print(f"  URL: {sandbox.get_url()}")

        # Wait a bit for DNS propagation
        print("  Waiting for DNS propagation...")
        time.sleep(10)

        # Step 2: Upload app files
        print_step(2, 6, "Uploading Node app files...")
        app_dir = FIXTURES_DIR / "node_app"

        with open(app_dir / "package.json") as f:
            package_json = f.read()
        with open(app_dir / "app.js") as f:
            app_code = f.read()

        write_file_via_api(sandbox, "/workspace/package.json", package_json)
        write_file_via_api(sandbox, "/workspace/app.js", app_code)
        print("  Uploaded package.json and app.js")

        # Step 3: Install dependencies
        print_step(3, 6, "Installing Node dependencies (this takes a while)...")
        start = time.time()

        result = sandbox.exec("cd /workspace && npm install", timeout=600)
        if result.exit_code != 0:
            raise RuntimeError(f"npm install failed: {result.stderr}")

        install_time = time.time() - start
        print(f"  Dependencies installed in {install_time:.1f}s")

        # Check node_modules size
        result = sandbox.exec("du -sh /workspace/node_modules")
        print(f"  node_modules size: {result.stdout.strip()}")

        # Step 4: Verify app starts
        print_step(4, 6, "Starting app and verifying...")

        # Get service client for background execution
        client = sandbox._get_service_client()

        # Start the app in background using the proper background API
        pid = client.exec_background(
            command="node app.js",
            cwd="/workspace",
        )
        print(f"  Started Express app with PID {pid}")

        # Wait for app to start
        time.sleep(5)

        # Check health endpoint
        for attempt in range(10):
            try:
                health_result = client.exec("curl -s http://localhost:5000/health", timeout=10)
                if "healthy" in health_result.stdout:
                    print(f"  Health check passed: {health_result.stdout.strip()}")
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("App health check failed after 10 attempts")

        # Check verify endpoint
        verify_result = client.exec("curl -s http://localhost:5000/verify", timeout=10)
        print(f"  Verify check: {verify_result.stdout.strip()[:100]}...")

        if "verified" not in verify_result.stdout:
            raise RuntimeError(f"App verification failed: {verify_result.stdout}")

        # Stop the app
        client.kill_process(pid)

        # Step 5: Create snapshot
        print_step(5, 6, "Creating snapshot...")
        start = time.time()

        metadata = sandbox.create_snapshot(
            snapshot_id=snapshot_id,
            paths=["/workspace"],
            description="Node Express benchmark app with Sequelize, Joi, bcryptjs",
        )

        snapshot_time = time.time() - start
        print(f"  Snapshot created in {snapshot_time:.1f}s")
        print(f"  Snapshot ID: {metadata.snapshot_id}")
        print(f"  Size: {metadata.size_bytes / 1024 / 1024:.1f} MB")

        # Step 6: Cleanup
        print_step(6, 6, "Deleting sandbox...")
        sandbox.delete()
        print("  Sandbox deleted")

        return {
            "snapshot_id": metadata.snapshot_id,
            "size_bytes": metadata.size_bytes,
            "size_mb": round(metadata.size_bytes / 1024 / 1024, 1),
            "created_at": metadata.created_at,
            "image": "node",
            "app_type": "express",
        }

    except Exception as e:
        print(f"\nERROR: {e}")
        if sandbox:
            try:
                sandbox.delete()
            except Exception:
                pass
        raise


def main():
    """Create snapshots for benchmark testing."""
    print("=" * 60)
    print("  SNAPSHOT CREATION FOR BENCHMARKS")
    print("=" * 60)

    # Check credentials
    do_token = os.environ.get("DIGITALOCEAN_TOKEN")
    if not do_token:
        print("ERROR: DIGITALOCEAN_TOKEN not set")
        sys.exit(1)

    spaces_config = create_spaces_config_from_env()
    if not spaces_config:
        print("ERROR: Spaces credentials not configured")
        print("Set: SPACES_BUCKET, SPACES_REGION, SPACES_ACCESS_KEY, SPACES_SECRET_KEY")
        sys.exit(1)

    print(f"\nSpaces bucket: {spaces_config.bucket}")
    print(f"Spaces region: {spaces_config.region}")

    # Ensure results directory exists
    RESULTS_DIR.mkdir(exist_ok=True)

    # Create snapshots
    config = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshots": {},
    }

    # Python snapshot
    try:
        python_info = create_python_snapshot(do_token, spaces_config)
        config["snapshots"]["python"] = python_info
        # Save progress after each successful snapshot
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\n  Saved Python snapshot config to {CONFIG_FILE}")
    except Exception as e:
        print(f"\nERROR creating Python snapshot: {e}")

    # Node snapshot
    try:
        node_info = create_node_snapshot(do_token, spaces_config)
        config["snapshots"]["node"] = node_info
        # Save progress after each successful snapshot
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\n  Saved Node snapshot config to {CONFIG_FILE}")
    except Exception as e:
        print(f"\nWARNING: Node snapshot failed: {e}")
        print("  Continuing with Python snapshot only...")

    # Final check
    if not config["snapshots"]:
        print("\nFATAL ERROR: No snapshots created")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  SNAPSHOT CREATION COMPLETE")
    print("=" * 60)
    print(f"\nConfig saved to: {CONFIG_FILE}")
    print("\nSnapshots created:")
    for image, info in config["snapshots"].items():
        print(f"  {image}: {info['snapshot_id']} ({info['size_mb']} MB)")

    print("\nRun the benchmark with:")
    print("  python snapshot_restore_benchmark.py")


if __name__ == "__main__":
    main()
