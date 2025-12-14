# DO App Sandbox

> **Experimental**: This is an experimental project. APIs may change without notice.

A Python SDK that provides sandbox-like capabilities for DigitalOcean App Platform, similar to Cloudflare Sandbox.

## Features

- **Create sandboxes**: Deploy isolated containers to App Platform (Python/Node images)
- **Execute commands**: Run shell commands with exit code capture
- **File operations**: Read, write, upload, and download files (Spaces-backed for large files)
- **Process management**: Launch and manage background processes
- **Async support**: Both synchronous and asynchronous APIs
- **CLI tool**: Manage sandboxes from the command line
- **Hosted images**: Uses maintained Python and Node images; no custom image setup required
- **Troubleshoot existing apps**: Connect to any App Platform app for troubleshooting ([guide](docs/troubleshooting_existing_apps.md))

## Documentation
- Reference tables for SDK and CLI parameters/outputs: `docs/sandbox_reference.md`
- Troubleshooting existing App Platform apps: `docs/troubleshooting_existing_apps.md`

## Installation

### From PyPI (when published)

```bash
pip install do-app-sandbox
```

### From Source (with uv)

```bash
# Clone the repository
cd do-app-sandbox

# Development/editable install (recommended)
uv pip install -e .

# Regular install
uv pip install .

# With Spaces support for large file transfers
uv pip install -e ".[spaces]"
```

### Run Without Installing

```bash
# Run CLI directly with uv
uv sync
uv run python -m do_app_sandbox --help
uv run python -m do_app_sandbox list
```

## Quick Start

### Prerequisites

1. **doctl CLI**: Must be installed and authenticated (`doctl auth init`)
2. *(Optional)* **`DIGITALOCEAN_TOKEN`**: Only needed if not using doctl auth
3. *(Optional)* **Spaces**: For large file transfers (`SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_BUCKET`, `SPACES_REGION`)

**doctl is required** for all sandbox operations (create, exec, files, etc.). There is no API-only path; `DIGITALOCEAN_TOKEN` is only used to feed doctl auth if you prefer environment-based auth.

No image build/push step is required—the sandbox uses the maintained Python and Node images directly.
Default images live at `ghcr.io/bikramkgupta`; override with `GHCR_OWNER`/`GHCR_REGISTRY` if you host your own copies.

### Basic Usage

```python
from do_app_sandbox import Sandbox

# Create a new sandbox with the maintained Python image
sandbox = Sandbox.create(image="python", name="my-sandbox")

# Execute commands (python image ships with python3; use uv for pinned envs)
result = sandbox.exec("python3 --version")
print(result.stdout)
print(result.exit_code)  # 0

# File operations
sandbox.filesystem.write_file("/app/script.py", "print('Hello World')")
content = sandbox.filesystem.read_file("/app/script.py")

# Run the script
result = sandbox.exec("python3 /app/script.py")
print(result.stdout)  # Hello World

# Clean up
sandbox.delete()
```

### Working Directory

The sandbox working directory is `/home/sandbox/app`. For convenience, `/app` is a symlink to this location, so you can use either path:

```python
# Both paths work identically
sandbox.filesystem.write_file("/app/script.py", "print('Hello')")
sandbox.filesystem.write_file("/home/sandbox/app/script.py", "print('Hello')")

# Use cwd parameter to set working directory for commands
sandbox.exec("python script.py", cwd="/app")
```

### Context Manager

```python
from do_app_sandbox import Sandbox

with Sandbox.create(image="python") as sandbox:
    result = sandbox.exec("echo 'Hello'")
    print(result.stdout)
# Sandbox automatically deleted on exit
```

### Async API

```python
import asyncio
from do_app_sandbox import AsyncSandbox

async def main():
    sandbox = await AsyncSandbox.create(image="python")

    await sandbox.filesystem.write_file("/app/test.py", "print('async!')")
    result = await sandbox.exec("python /app/test.py")
    print(result.stdout)

    await sandbox.delete()

asyncio.run(main())
```

## CLI Reference

The `sandbox` CLI provides commands for managing sandboxes from the terminal.

### Create a Sandbox

```bash
# Create a Python sandbox (--image is required)
sandbox create --image python --name my-sandbox

# Create with custom region and instance size
sandbox create --image python --region sfo3 --instance-size apps-s-1vcpu-2gb

# Create a Node.js sandbox without waiting for ready state
sandbox create --image node --no-wait
```

### List Sandboxes

```bash
# List all sandboxes
sandbox list

# Output as JSON
sandbox list --json
```

### Execute Commands

```bash
# Execute a command in a sandbox (by name)
sandbox exec my-sandbox "python3 --version"

# Execute in sandbox by ID
sandbox exec --id abc123-def456 "ls -la"

# With custom timeout
sandbox exec my-sandbox "long-running-command" --timeout 300
```

### Delete Sandboxes

```bash
# Delete by name
sandbox delete my-sandbox

# Delete by ID
sandbox delete --id abc123-def456

# Delete all sandboxes (with confirmation)
sandbox delete --all

# Delete all without confirmation
sandbox delete --all --force
```

## API Reference

### Sandbox Class

#### Class Methods

- `Sandbox.create(*, image, name, region, instance_size, api_token, wait_ready, timeout)` - Create a new sandbox (`image` is required)
- `Sandbox.get_from_id(app_id, component, api_token)` - Connect to existing sandbox (doctl authentication required)

#### Instance Methods

- `exec(command, env, cwd, timeout)` - Execute a command
- `launch_process(command, cwd, env)` - Start a background process
- `list_processes(pattern)` - List running processes
- `kill_process(pid)` - Kill a process
- `kill_all_processes()` - Kill all launched processes
- `get_url()` - Get the public URL
- `delete()` - Delete the sandbox

#### Properties

- `app_id` - The App Platform application ID
- `component` - The component name
- `status` - Current deployment status
- `filesystem` - FileSystem instance for file operations

### FileSystem Class

- `read_file(path, binary)` - Read a file
- `write_file(path, content, binary)` - Write a file
- `upload_file(local_path, remote_path)` - Upload local file
- `download_file(remote_path, local_path)` - Download file
- `list_dir(path)` - List directory contents
- `mkdir(path, recursive)` - Create directory
- `rm(path, recursive, force)` - Remove file/directory
- `exists(path)` - Check if path exists
- `is_file(path)` - Check if path is a file
- `is_dir(path)` - Check if path is a directory

### CommandResult

```python
@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int

    @property
    def success(self) -> bool:
        return self.exit_code == 0
```

## Large Files (Spaces)

Set `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_BUCKET`, and `SPACES_REGION` to enable Spaces-backed transfers. The SDK will automatically use Spaces for files larger than ~250KB (configurable via `SANDBOX_LARGE_FILE_THRESHOLD`) via `filesystem.upload_large` / `download_large`.

```python
sandbox = Sandbox.create(image="python", spaces_config={"bucket": "my-bucket", "region": "nyc3"})
sandbox.filesystem.upload_large("./big.zip", "/tmp/big.zip")
sandbox.filesystem.download_large("/tmp/output.zip", "./output.zip")
```

**How it works**: Uses time-limited presigned URLs (15 min expiry by default) so no credentials are needed in the container. Files are transferred via curl and Spaces objects are deleted after transfer by default.

## Efficient File Transfers

For initial deployment with many files (10+), use zip to transfer in bulk rather than file-by-file:

```python
# LOCAL: Create zip of your project (excluding node_modules, .git, etc.)
import shutil
shutil.make_archive("/tmp/app", "zip", "/path/to/your/project")

# Upload single zip file
sandbox.filesystem.upload_file("/tmp/app.zip", "/home/sandbox/app.zip")

# REMOTE: Unzip in sandbox
sandbox.exec("cd /home/sandbox && unzip -o app.zip -d app && rm app.zip")
```

**When to use each approach:**
| Scenario | Recommended Method |
|----------|-------------------|
| Initial deployment (10+ files) | Zip and upload once |
| Quick config change | Single file upload |
| Hot-reload during development | Single file upload |
| Replacing entire codebase | Zip and upload once |

## Log Streaming

Use `doctl` directly for build/run logs:

```bash
doctl apps logs -f <APP_ID> sandbox --type run
doctl apps logs -f <APP_ID> sandbox --type build
```

## Smoke & Perf Harness

- Smoke: `uv run python -m tests.smoke.main --spaces` (writes JSON to `tests/artifacts/`)
- Perf (light by default): `uv run python -m tests.perf.main --spaces --run-large-file` (100MB Spaces transfer)

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DIGITALOCEAN_TOKEN` | No | DigitalOcean API token for doctl auth (optional if doctl is already authenticated) |
| `GHCR_OWNER` | No | GHCR image owner/namespace (default: `bikramkgupta`) |
| `GHCR_REGISTRY` | No | GHCR registry host (default: `ghcr.io`) |
| `APP_SANDBOX_REGION` | No | Default region (defaults to `atl1`) |

### Sandbox.create() Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `image` | **Required** | Sandbox image (`"python"` or `"node"`) |
| `name` | Auto-generated | Sandbox name |
| `region` | From env or `"atl1"` | App Platform region |
| `instance_size` | `"apps-s-1vcpu-1gb"` | Instance size slug |
| `component_type` | `"service"` | `"service"` for HTTP endpoint, `"worker"` for background process |
| `wait_ready` | `True` | Wait for sandbox to be ready |
| `timeout` | `600` | Max wait time in seconds |
| `api_token` | From env | DigitalOcean API token for doctl auth (optional if doctl is already authenticated) |

### Creating a Worker (No HTTP Endpoint)

Workers are useful for long-running background tasks that don't need a public URL:

```python
# Create a worker sandbox
worker = Sandbox.create(image="python", component_type="worker")

# Execute commands just like a service
result = worker.exec("python3 --version")
print(result.stdout)

# Workers have no URL (get_url() returns None)
```

### Sandbox.get_from_id() Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `app_id` | **Required** | The App Platform application ID |
| `component` | `"sandbox"` | The component/service name |
| `api_token` | From env | DigitalOcean API token |
| `spaces_config` | None | SpacesConfig for large file transfers |

**Note**: Registry is NOT required for `get_from_id()`. All operations work with just the app_id and doctl authentication.

### Available Regions

See [App Platform Availability](https://docs.digitalocean.com/products/app-platform/details/availability/) for the full list of supported regions.

### Available Instance Sizes

See [App Platform Pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/) for the full list of available instance sizes.

## Known Limitations

1. **Deployment Time**: Creating a sandbox takes approximately 30-45 seconds
2. **Static Port**: User applications must listen on port 8080 (health checks are on port 9090)
3. **Per-Command Console**: Each command opens a new console session
4. **No Persistent Storage**: Data is lost when sandbox is deleted

## Development

```bash
# Clone the repository
cd app-platform-sandbox

# Install dependencies
uv sync

# Run the CLI directly
python -m app_platform_sandbox --help

# Run tests
uv run pytest tests/ -v
```

## License

MIT
