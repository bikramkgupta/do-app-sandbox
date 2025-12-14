# Sandbox Lifecycle

Learn how to create, discover, connect to, and manage sandboxes throughout their lifecycle.

## Creating Sandboxes

### Basic Creation

Create a new sandbox with default settings (uses GHCR public images):

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.create(image="python")
print(f"Created: {sandbox.app_id}")
```

**Async:**

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def main():
    sandbox = await AsyncSandbox.create(image="python")
    print(f"Created: {sandbox.app_id}")

asyncio.run(main())
```

**CLI:**

```bash
sandbox create --image python
```

### Creation Options

Customize your sandbox with these parameters:

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.create(
    image="python",                     # Required: "python" or "node"
    component_type="service",           # "service" (HTTP) or "worker" (no HTTP)
    name="my-custom-sandbox",           # Custom name (auto-generated if omitted)
    region="sfo",                       # Region: atl1, nyc, sfo, ams, sgp, lon, fra, tor, blr, syd
    instance_size="apps-s-1vcpu-2gb",   # Instance size (see below)
    registry="my-docr",                 # Optional: DOCR registry (uses GHCR if omitted)
    wait_ready=True,                    # Wait for deployment (default: True)
    timeout=600                         # Max wait time in seconds (default: 600)
)
```

**CLI:**

```bash
# Service with HTTP endpoint (default)
sandbox create --image python --name my-custom-sandbox --region sfo

# Worker without HTTP endpoint
sandbox create --image python --type worker --name my-worker
```

### Available Instance Sizes

See [App Platform Pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/) for the full list of available instance sizes.

### Available Regions

See [App Platform Availability](https://docs.digitalocean.com/products/app-platform/details/availability/) for the full list of supported regions.

## Discovering Existing Sandboxes

List all your sandboxes to find their App IDs:

### CLI

```bash
sandbox list
```

**Output:**

```
NAME                  APP_ID                                 STATUS    URL
data-processor        a1b2c3d4-e5f6-7890-abcd-ef1234567890   ACTIVE    https://data-processor-xxxxx.ondigitalocean.app
ml-inference          b2c3d4e5-f6a7-8901-bcde-f23456789012   ACTIVE    https://ml-inference-yyyyy.ondigitalocean.app
test-sandbox          c3d4e5f6-a7b8-9012-cdef-345678901234   DEPLOYING https://test-sandbox-zzzzz.ondigitalocean.app
```

### SDK

You can also use doctl directly to list apps:

```python
import subprocess
import json

result = subprocess.run(
    ["doctl", "apps", "list", "--output", "json"],
    capture_output=True,
    text=True
)
apps = json.loads(result.stdout)
for app in apps:
    print(f"{app['spec']['name']}: {app['id']}")
```

## Connecting to Existing Sandboxes

Connect to a sandbox that's already running. This is the recommended workflow for repeated interactions:

### SDK

**Sync:**

```python
from app_platform_sandbox import Sandbox

# Connect by App ID
sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Verify connection
result = sandbox.exec("echo 'Connected!'")
print(result.stdout)  # Output: Connected!

# Access sandbox properties
print(f"App ID: {sandbox.app_id}")
print(f"URL: {sandbox.get_url()}")
```

**Async:**

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def main():
    sandbox = await AsyncSandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    result = await sandbox.exec("hostname")
    print(result.stdout)

asyncio.run(main())
```

### CLI

```bash
# Run commands on existing sandbox by ID
sandbox exec --id a1b2c3d4-e5f6-7890-abcd-ef1234567890 "echo 'Hello'"

# Or by name (if unique)
sandbox exec data-processor "python --version"
```

### Example: Reusing a Sandbox Across Sessions

Save the App ID after creation and reuse it later:

**Session 1 - Create and save ID:**

```python
from app_platform_sandbox import Sandbox

# Create sandbox
sandbox = Sandbox.create(image="python", name="persistent-worker")

# Save the App ID for later
app_id = sandbox.app_id
print(f"Save this ID: {app_id}")

# Do some work
sandbox.exec("pip install pandas numpy")
```

**Session 2 - Reconnect and continue:**

```python
from app_platform_sandbox import Sandbox

# Connect to the same sandbox
sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Packages are still installed!
result = sandbox.exec("python -c 'import pandas; print(pandas.__version__)'")
print(result.stdout)  # Output: 2.0.0
```

## Checking Sandbox Status

### Is Ready Check

Check if a sandbox is ready to accept commands:

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

if sandbox.is_ready():
    print("Sandbox is ready!")
    result = sandbox.exec("echo 'Hello'")
else:
    print("Sandbox is not ready yet")
```

**Async:**

```python
if await sandbox.is_ready():
    print("Sandbox is ready!")
```

### Wait for Ready

Wait for a sandbox to become ready with a timeout:

**Sync:**

```python
from app_platform_sandbox import Sandbox

# Create without waiting
sandbox = Sandbox.create(
    image="python",
    wait_ready=False  # Don't wait during creation
)

print("Sandbox created, waiting for it to be ready...")

# Wait separately with custom timeout
sandbox.wait_ready(timeout=300)  # 5 minutes

print("Sandbox is now ready!")
```

**Async:**

```python
sandbox = await AsyncSandbox.create(
    image="python",
    wait_ready=False
)

await sandbox.wait_ready(timeout=300)
```

### Get Deployment Status

**Sync:**

```python
status = sandbox.status
print(f"Status: {status}")  # e.g., "ACTIVE", "DEPLOYING", "ERROR"
```

**Async:**

```python
status = await sandbox.get_status()
print(f"Status: {status}")  # e.g., "ACTIVE", "DEPLOYING", "ERROR"
```

## Deleting Sandboxes

### Delete a Single Sandbox

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")
sandbox.delete()
print("Sandbox deleted")
```

**Async:**

```python
await sandbox.delete()
```

**CLI:**

```bash
# Delete by name
sandbox delete my-sandbox

# Delete by App ID
sandbox delete --id a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### Delete All Sandboxes

**CLI:**

```bash
# Delete all sandboxes (prompts for confirmation)
sandbox delete --all
```

### When to Delete vs Keep

**Keep the sandbox running when:**
- You'll use it again within hours/days
- You've installed packages or dependencies
- You have data or state you want to preserve
- Creation time (2-5 min) is a concern

**Delete the sandbox when:**
- The task is complete
- You won't need it for a while
- You want to stop billing
- You're using context managers for auto-cleanup

## Context Managers (Auto-Cleanup)

Use context managers for sandboxes that should be deleted automatically:

### Sync Context Manager

```python
from app_platform_sandbox import Sandbox

with Sandbox.create(image="python") as sandbox:
    # Upload data
    sandbox.filesystem.write_file("/tmp/data.csv", "col1,col2\n1,2\n3,4")

    # Process data
    result = sandbox.exec("python -c \"import csv; print('Processed')\"")
    print(result.stdout)

# Sandbox is automatically deleted when exiting the 'with' block
print("Sandbox cleaned up automatically")
```

### Async Context Manager

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def process_data():
    async with await AsyncSandbox.create(image="python") as sandbox:
        await sandbox.filesystem.write_file("/tmp/input.txt", "Hello World")
        result = await sandbox.exec("cat /tmp/input.txt | wc -c")
        print(f"Character count: {result.stdout}")

    # Sandbox deleted automatically
    print("Done and cleaned up")

asyncio.run(process_data())
```

### Context Manager with Existing Sandbox

Note: Context managers with `get_from_id()` will also delete the sandbox on exit:

```python
# Be careful! This will delete the existing sandbox
with Sandbox.get_from_id(app_id="...") as sandbox:
    result = sandbox.exec("echo 'This sandbox will be deleted!'")
```

If you don't want auto-deletion, don't use context managers:

```python
# This sandbox persists after the script ends
sandbox = Sandbox.get_from_id(app_id="...")
result = sandbox.exec("echo 'This sandbox will persist'")
# No delete() called, sandbox keeps running
```

## Error Handling

### Common Exceptions

```python
from app_platform_sandbox import Sandbox
from app_platform_sandbox.exceptions import (
    SandboxCreationError,
    SandboxNotFoundError,
    SandboxNotReadyError,
    ConnectionError
)

try:
    sandbox = Sandbox.get_from_id(app_id="invalid-app-id")
except SandboxNotFoundError:
    print("Sandbox not found - check the App ID")

try:
    sandbox = Sandbox.create(
        image="python",
        timeout=60  # Short timeout
    )
except SandboxCreationError as e:
    print(f"Failed to create sandbox: {e}")

try:
    sandbox = Sandbox.create(
        image="python",
        wait_ready=False
    )
    # Try to use before ready
    result = sandbox.exec("echo 'hello'")
except SandboxNotReadyError:
    print("Sandbox not ready yet - wait or call wait_ready()")
```

## Next Steps

- [Run Commands](sandbox_runcommands.md) - Execute commands with environment variables and timeouts
- [File Operations](sandbox_fileops.md) - Upload, download, and manage files
- [Large File Transfers](sandbox_large_files.md) - Handle files larger than 5MB using Spaces
