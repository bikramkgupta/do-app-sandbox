# DO App Sandbox

> **Experimental**: This is an experimental project and not an official DigitalOcean product.

## Overview
Python SDK providing sandbox capabilities for DigitalOcean App Platform.

## Architecture
```
Sandbox/AsyncSandbox (API) → Executor (pexpect) → doctl apps console → Container
SandboxManager (Pool) → AsyncSandbox → Executor → Container
```

## Key Files
- `src/do_app_sandbox/sandbox.py` - Main Sandbox class (sync API)
- `src/do_app_sandbox/async_sandbox.py` - AsyncSandbox class (async API)
- `src/do_app_sandbox/manager.py` - SandboxManager for pool management
- `src/do_app_sandbox/adaptive_pool.py` - Scaling algorithms (EMA, PID, Predictive)
- `src/do_app_sandbox/executor.py` - Command execution via pexpect
- `src/do_app_sandbox/filesystem.py` - File operations (base64)
- `src/do_app_sandbox/process.py` - Process management
- `src/do_app_sandbox/deployer.py` - App Platform deployment
- `src/do_app_sandbox/cli.py` - CLI commands
- `src/do_app_sandbox/image_registry.py` - Custom image management
- `src/do_app_sandbox/image_validator.py` - Image validation
- `src/do_app_sandbox/spaces.py` - DO Spaces integration for large files
- `src/do_app_sandbox/types.py` - Type definitions
- `src/do_app_sandbox/exceptions.py` - Custom exceptions

## CLI Commands
```bash
sandbox create --image python|node       # Create sandbox (uses GHCR public images by default)
sandbox exec SANDBOX "command"           # Execute command
sandbox list / sandbox delete            # Manage sandboxes
```

## Environment Variables
```
DIGITALOCEAN_TOKEN    # Used for doctl auth (optional if already authenticated)
GHCR_OWNER            # GHCR namespace/owner (default: bikramkgupta)
GHCR_REGISTRY         # GHCR host (default: ghcr.io)
APP_SANDBOX_REGION    # Default region (atl1)

# For large file transfers via Spaces
SPACES_ACCESS_KEY     # DO Spaces access key
SPACES_SECRET_KEY     # DO Spaces secret key
SPACES_BUCKET         # Default bucket name
SPACES_REGION         # Default region (e.g., nyc3)
SPACES_ENDPOINT       # Optional custom endpoint (will be normalized if bucket-prefixed)
```

## Streaming Logs (No SDK needed)
Use doctl directly:
```bash
doctl apps logs -f APP_ID COMPONENT --type run    # Follow runtime logs
doctl apps logs -f APP_ID COMPONENT --type build  # Follow build logs
doctl apps logs -f APP_ID COMPONENT --type deploy # Follow deploy logs
```

## Docker Images
- `images/python/` - Ubuntu 24.04 + Python 3.13 + uv
- `images/node/` - Ubuntu 24.04 + Node.js 24 + nvm
- Both images include: curl, git, lsof, jq, procps
- Working directory: `/home/sandbox/app` (with `/app` as symlink)

## Ports
- **Port 8080**: Completely free for user applications
- **Port 9090**: Internal health server (handled by sandbox, not user)

## SDK Usage

### Sync API (Sandbox)
```python
from do_app_sandbox import Sandbox

sandbox = Sandbox.create(image="python")
result = sandbox.exec("python --version")
print(result.stdout)
sandbox.delete()

# Context manager
with Sandbox.create(image="python") as sandbox:
    result = sandbox.exec("echo 'Hello'")
```

### Async API (AsyncSandbox)
```python
from do_app_sandbox import AsyncSandbox

sandbox = await AsyncSandbox.create(image="python")
result = await sandbox.exec("python --version")
await sandbox.delete()
```

### Pool Management (SandboxManager)
Eliminates cold-start latency by maintaining pre-warmed sandboxes:
```python
from do_app_sandbox import SandboxManager, PoolConfig

manager = SandboxManager(
    pools={"python": PoolConfig(target_ready=3, max_ready=10)},
)
await manager.start()

# Instant acquisition from pool
sandbox = await manager.acquire(image="python")
result = sandbox.exec("python --version")
sandbox.delete()

await manager.shutdown()
```

**PoolConfig options:**
- `target_ready` - Target number of ready sandboxes (default: 0)
- `max_ready` - Maximum sandboxes in pool (default: 10)
- `idle_timeout` - Seconds before scaling down (default: 60)
- `max_warm_age` - Max seconds a sandbox can warm (default: 1800)

### Connecting to Existing Apps
```python
# Works with any App Platform app
sandbox = Sandbox.get_from_id(app_id, component="your-component")
```

### Service vs Worker
- **Service** (default): Has public HTTP endpoint on port 8080
- **Worker**: No HTTP endpoint, for background tasks
```python
sandbox = Sandbox.create(image="python", component_type="worker")
```

## Large File Transfers
Files >= 5MB use DO Spaces as intermediary:
```python
sandbox = Sandbox.create(
    image="python",
    spaces_config={
        "bucket": "my-bucket",
        "region": "nyc3",
        "access_key": "...",
        "secret_key": "...",
    }
)
sandbox.filesystem.upload_large("/local/big.zip", "/app/big.zip")
sandbox.filesystem.download_large("/app/output.tar.gz", "/local/output.tar.gz")
```

## Deploying Your Own App

### No Health Endpoint Required
The sandbox automatically handles App Platform health checks on port 9090. Your app runs on port 8080 without implementing any health endpoint.

### Simple Deployment
```python
sandbox.filesystem.upload_file("app.py", "/home/sandbox/app/app.py")

# Python requires venv
sandbox.exec("cd /home/sandbox/app && uv venv .venv")
sandbox.exec("cd /home/sandbox/app && source .venv/bin/activate && uv pip install -r requirements.txt")

# Start app
pid = sandbox.launch_process(
    "cd /home/sandbox/app && source .venv/bin/activate && python app.py",
    cwd="/home/sandbox/app"
)
```

### Efficient File Transfers
For many files, use zip:
```python
import shutil
shutil.make_archive("/tmp/app", "zip", "/path/to/project")
sandbox.filesystem.upload_file("/tmp/app.zip", "/home/sandbox/app.zip")
sandbox.exec("cd /home/sandbox && unzip -o app.zip -d app && rm app.zip")
```

## Types
Key types exported from `do_app_sandbox`:
- `CommandResult` - Result of exec() with stdout, stderr, exit_code
- `ProcessInfo` - Process information (pid, command, status)
- `FileInfo` - File metadata
- `AppInfo` - App Platform app information
- `SpacesConfig` - Spaces configuration dict
- `PoolConfig` - Pool configuration for SandboxManager
- `PoolMetrics` - Pool metrics (ready, in_use, etc.)

## Exceptions
```python
from do_app_sandbox import (
    SandboxError,           # Base exception
    SandboxCreationError,   # Failed to create sandbox
    SandboxNotFoundError,   # Sandbox not found
    SandboxNotReadyError,   # Sandbox not ready
    CommandExecutionError,  # Command failed
    CommandTimeoutError,    # Command timed out
    FileOperationError,     # File operation failed
    ConnectionError,        # Connection failed
    SpacesNotConfiguredError,
    ImageNotValidatedError,
    ImageValidationError,
    PoolError,              # Base pool exception
    PoolExhaustedError,     # No sandboxes available
    PoolShutdownError,      # Pool is shutting down
    WarmUpTimeoutError,     # Warm-up timed out
)
```

## Custom Image Requirements
Custom Dockerfiles must:
1. `EXPOSE 8080` - For user application
2. Have ENTRYPOINT or CMD
3. Optionally: Include the sandbox health server on port 9090

**Service Mode Note:** If using `SandboxMode.SERVICE` (HTTP API mode) with a custom image, your Dockerfile must include the `sandbox_api` FastAPI server. The easiest approach is to base your image on one of the provided service images:
```dockerfile
FROM ghcr.io/bikramkgupta/sandbox-python-service:latest
# Add your customizations here
```

## Limitations & Constraints

### Streaming Output (exec_stream)
The `exec_stream` API endpoint returns output as JSON over Server-Sent Events (SSE). It is designed for **text output only**. Binary data (non-UTF8) will be decoded with `errors='replace'`, which may corrupt binary content. For binary file transfers, use the Filesystem API (`upload_file`/`download_file`) or Spaces for large files.

### Snapshot Restore Paths
When using `acquire_with_snapshot` to restore sandbox state, the snapshot extracts to `/workspace` by default. The `sandbox_api` server lives in `/opt/sandbox_api`. **Do not include `/opt/sandbox_api` in snapshots** as overwriting it could destabilize the sandbox. Keep application code and data in `/workspace` or `/home/sandbox/app`.

## Testing
```bash
pytest tests/  # Requires DIGITALOCEAN_TOKEN
```

## AI Assistant Guidance
For comprehensive App Platform skills (troubleshooting, deployment, postgres, networking, etc.), see:
https://github.com/bikramkgupta/do-app-platform-skills
