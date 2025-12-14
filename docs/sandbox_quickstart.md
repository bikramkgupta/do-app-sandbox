# Quickstart

Get up and running with App Platform Sandbox in minutes. This guide covers installation, creating your first sandbox, and executing commands.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.10+** installed
- **doctl** (DigitalOcean CLI) installed and authenticated (`doctl auth init`)

That's it! No registry setup required - the SDK uses public GHCR images by default.

## Installation

Install the App Platform Sandbox SDK using pip:

```bash
pip install app-platform-sandbox
```

Or with uv:

```bash
uv add app-platform-sandbox
```

## Create Your First Sandbox

### SDK

**Sync:**

```python
from app_platform_sandbox import Sandbox

# Create a new Python sandbox (uses GHCR public images)
sandbox = Sandbox.create(
    image="python",          # or "node"
    name="my-first-sandbox"  # optional, auto-generated if omitted
)

print(f"Sandbox ready at: {sandbox.get_url()}")
print(f"App ID: {sandbox.app_id}")
```

**Async:**

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def main():
    # Create a new Python sandbox
    sandbox = await AsyncSandbox.create(image="python")

    print(f"Sandbox ready at: {await sandbox.get_url()}")
    print(f"App ID: {sandbox.app_id}")

asyncio.run(main())
```

### CLI

```bash
# Create a Python sandbox
sandbox create --image python --name my-first-sandbox

# Create a Node.js sandbox
sandbox create --image node --name my-node-sandbox

# Create a worker (no HTTP endpoint)
sandbox create --image python --type worker
```

**Output:**

```
Creating sandbox...
  Image: python
  Type: service
  Registry: GHCR: bikramkgupta (public)
  Region: atl1
  Instance size: apps-s-1vcpu-1gb
  Name: my-first-sandbox

Sandbox created successfully!
  ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
  URL: https://my-first-sandbox-xxxxx.ondigitalocean.app
  Status: ACTIVE
```

## Run a Command

### SDK

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.create(image="python")

# Execute a command
result = sandbox.exec("echo 'Hello from the sandbox!'")
print(result.stdout)  # Output: Hello from the sandbox!
print(result.exit_code)  # Output: 0

# Run Python code
result = sandbox.exec("python -c \"print(2 + 2)\"")
print(result.stdout)  # Output: 4
```

**Async:**

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def main():
    sandbox = await AsyncSandbox.create(image="python")

    result = await sandbox.exec("echo 'Hello from the sandbox!'")
    print(result.stdout)

    # Run Python code
    result = await sandbox.exec("python -c \"print(2 + 2)\"")
    print(result.stdout)

asyncio.run(main())
```

### CLI

```bash
# Execute a command in a sandbox by name
sandbox exec my-first-sandbox "echo 'Hello from the sandbox!'"

# Execute by App ID
sandbox exec --id a1b2c3d4-e5f6-7890-abcd-ef1234567890 "python -c 'print(2 + 2)'"
```

**Output:**

```
Hello from the sandbox!
```

## Connect to an Existing Sandbox

You don't need to create a new sandbox every time. Connect to an existing one using its App ID:

### SDK

**Sync:**

```python
from app_platform_sandbox import Sandbox

# Connect to an existing sandbox by App ID
sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Now use it like normal
result = sandbox.exec("whoami")
print(result.stdout)
```

**Async:**

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def main():
    # Connect to an existing sandbox
    sandbox = await AsyncSandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    result = await sandbox.exec("pwd")
    print(result.stdout)

asyncio.run(main())
```

### CLI

```bash
# List all sandboxes to find App IDs
sandbox list

# Execute command on existing sandbox
sandbox exec --id a1b2c3d4-e5f6-7890-abcd-ef1234567890 "ls -la"
```

**Output from `sandbox list`:**

```
NAME                  APP_ID                                 STATUS    URL
my-first-sandbox      a1b2c3d4-e5f6-7890-abcd-ef1234567890   ACTIVE    https://my-first-sandbox-xxxxx.ondigitalocean.app
my-node-sandbox       b2c3d4e5-f6a7-8901-bcde-f23456789012   ACTIVE    https://my-node-sandbox-yyyyy.ondigitalocean.app
```

## Cleanup Options

### Delete the Sandbox

When you're done, delete the sandbox to stop billing:

**SDK:**

```python
sandbox.delete()
print("Sandbox deleted")
```

**CLI:**

```bash
# Delete by name
sandbox delete my-first-sandbox

# Delete by App ID
sandbox delete --id a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Delete all sandboxes (use with caution!)
sandbox delete --all
```

### Keep the Sandbox Running

Sandboxes persist until explicitly deleted. To reuse a sandbox later:

1. Note the App ID after creation
2. Connect using `Sandbox.get_from_id()` in future sessions
3. Delete only when you no longer need it

This approach saves the 2-5 minute creation time for subsequent uses.

### Use Context Managers (Auto-Cleanup)

For temporary sandboxes that should be cleaned up automatically:

**Sync:**

```python
from app_platform_sandbox import Sandbox

with Sandbox.create(image="python") as sandbox:
    result = sandbox.exec("python -c 'print(42)'")
    print(result.stdout)
# Sandbox automatically deleted when exiting the block
```

**Async:**

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def main():
    async with await AsyncSandbox.create(image="python") as sandbox:
        result = await sandbox.exec("echo 'temporary sandbox'")
        print(result.stdout)
    # Sandbox automatically deleted

asyncio.run(main())
```

## Using a Custom Registry (Optional)

If you prefer to use your own DigitalOcean Container Registry (DOCR):

```python
# Use custom DOCR registry
sandbox = Sandbox.create(image="python", registry="my-registry")
```

Or set the environment variable:

```bash
export APP_SANDBOX_REGISTRY="my-registry"
```

## Next Steps

- [Sandbox Lifecycle](sandbox_lifecycle.md) - Learn about creating, discovering, and managing sandboxes
- [Run Commands](sandbox_runcommands.md) - Advanced command execution with environment variables and timeouts
- [File Operations](sandbox_fileops.md) - Upload, download, and manage files in your sandbox
- [Large File Transfers](sandbox_large_files.md) - Handle files larger than ~250KB using Spaces
