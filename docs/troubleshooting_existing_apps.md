# Troubleshooting Existing App Platform Apps

The DO App Sandbox SDK can connect to **any** running App Platform app—not just sandboxes you create with `Sandbox.create()`. This makes it a powerful tool for troubleshooting, running diagnostics, and managing files on your existing deployments.

## Prerequisites

- **doctl** installed and authenticated (`doctl auth init`)
- An existing App Platform app that is running

## Step 1: Find the Component Name

Every App Platform app has one or more components (services, workers, or jobs). You need to know the component name to connect.

```bash
# Get the component name(s) from your app
doctl apps get <APP_ID> --output json | jq '.spec.services[].name'

# Or for workers
doctl apps get <APP_ID> --output json | jq '.spec.workers[].name'
```

Example output: `"web"` or `"api"` or `"dev-workspace"`

## Step 2: Connect with the SDK

```python
from do_app_sandbox import Sandbox

# Connect to your existing app
app = Sandbox.get_from_id(
    app_id="ea1525eb-7e39-4fc5-91d4-5c8dc187581f",
    component="dev-workspace"  # Your actual component name
)

# Run commands
result = app.exec("whoami")
print(f"User: {result.stdout.strip()}")  # e.g., "devcontainer"

result = app.exec("pwd")
print(f"Working dir: {result.stdout.strip()}")

result = app.exec("uname -a")
print(f"System: {result.stdout.strip()}")
```

## Step 3: File Operations

The SDK's file operations also work on existing apps:

```python
# List directory contents
files = app.filesystem.list_dir("/app")
for f in files:
    print(f"  {f.name} ({f.type})")

# Read a file
content = app.filesystem.read_file("/app/config.py")
print(content)

# Write a file (e.g., for debugging)
app.filesystem.write_file("/tmp/debug.txt", "debug info here")

# Clean up
app.filesystem.rm("/tmp/debug.txt")
```

## CLI Usage

You can also use the CLI to run commands on existing apps:

```bash
# Execute a command by app ID
sandbox exec --id ea1525eb-7e39-4fc5-91d4-5c8dc187581f "ls -la"

# Note: CLI defaults to component "sandbox". For other components,
# use the SDK or doctl directly:
doctl apps console ea1525eb-7e39-4fc5-91d4-5c8dc187581f dev-workspace
```

## Common Use Cases

| Use Case | Example |
|----------|---------|
| Check running processes | `app.exec("ps aux")` |
| View logs | `app.exec("tail -100 /var/log/app.log")` |
| Check disk usage | `app.exec("df -h")` |
| Inspect environment | `app.exec("env")` |
| Debug networking | `app.exec("netstat -tlnp")` |
| Read config files | `app.filesystem.read_file("/app/.env")` |
| Download logs | `app.filesystem.download_file("/var/log/app.log", "./app.log")` |

## Important Notes

1. **Component name is required** - For sandbox-created apps, the component is always `"sandbox"`. For other apps, you must specify the actual component name.

2. **Read-only recommended** - While you can write files, be careful not to disrupt running applications.

3. **No credentials stored** - The SDK uses your existing doctl authentication.
