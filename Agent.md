# DO App Sandbox

> **Experimental**: This is an experimental project and not an official DigitalOcean product.

## Overview
Python SDK providing sandbox capabilities for DigitalOcean App Platform.

## Architecture
```
Sandbox/AsyncSandbox (API) → Executor (pexpect) → doctl apps console → Container
```

## Key Files
- `src/do_app_sandbox/sandbox.py` - Main Sandbox class
- `src/do_app_sandbox/executor.py` - Command execution via pexpect
- `src/do_app_sandbox/filesystem.py` - File operations (base64)
- `src/do_app_sandbox/deployer.py` - App Platform deployment
- `src/do_app_sandbox/cli.py` - CLI commands
- `src/do_app_sandbox/image_registry.py` - Custom image management
- `src/do_app_sandbox/spaces.py` - DO Spaces integration for large files

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

## Large File Transfers
Files >= 5MB use DO Spaces as intermediary with time-limited presigned URLs:
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

**How it works**:
- Upload: SDK uploads to Spaces via boto3, generates presigned URL (15 min), sandbox downloads via curl
- Download: SDK generates presigned URL (15 min), sandbox uploads via curl, SDK downloads via boto3
- No credentials in container - presigned URLs are time-limited and single-use
- Spaces objects are deleted after transfer by default

## SDK Usage Notes
- `Sandbox.create(image="python")` - uses GHCR public images by default (no registry setup needed)
- `Sandbox.create(image="python", component_type="worker")` - create a worker (no HTTP endpoint)
- `Sandbox.create(image="python", registry="custom-registry-host")` - override registry host if needed
- `Sandbox.get_from_id()` - connect to existing sandbox by app_id
- Both `/app` and `/home/sandbox/app` work (symlinked)

### Troubleshooting Existing Apps
The SDK works with **any** App Platform app, not just sandboxes. Use `Sandbox.get_from_id(app_id, component="your-component")` to connect. See `docs/troubleshooting_existing_apps.md` for details.

### Service vs Worker
- **Service** (default): Has public HTTP endpoint on port 8080, ideal for web apps
- **Worker**: No HTTP endpoint, ideal for background tasks, batch processing, or CLI tools

## Deploying Your Own App

### No Health Endpoint Required
The sandbox automatically handles App Platform health checks on port 9090. Your app can run on port 8080 without implementing any health endpoint.

### Simple Deployment
```python
# Upload your app
sandbox.filesystem.upload_file("app.py", "/home/sandbox/app/app.py")
sandbox.filesystem.upload_file("requirements.txt", "/home/sandbox/app/requirements.txt")

# Install dependencies (Python requires venv)
sandbox.exec("cd /home/sandbox/app && uv venv .venv")
sandbox.exec("cd /home/sandbox/app && source .venv/bin/activate && uv pip install -r requirements.txt")

# Start your app - just run it, no health endpoint needed!
pid = sandbox.launch_process(
    "cd /home/sandbox/app && source .venv/bin/activate && python app.py",
    cwd="/home/sandbox/app"
)
```

### Requirements
1. **Your app MUST listen on port 8080** - This is the only requirement
2. **Python apps require a virtual environment** (uv-managed Python):
   ```python
   sandbox.exec("cd /home/sandbox/app && uv venv .venv")
   sandbox.exec("cd /home/sandbox/app && source .venv/bin/activate && uv pip install -r requirements.txt")
   ```

### Efficient File Transfers
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
- **Zip upload**: Initial deployment, 10+ files, faster and more reliable
- **Single file upload**: Quick edits, config changes, hot-reloading single files

### Example Flask App (No Health Endpoint Needed)
```python
# app.py - Just a normal Flask app
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello World!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### Example Express App (No Health Endpoint Needed)
```javascript
// app.js - Just a normal Express app
const express = require('express');
const app = express();

app.get('/', (req, res) => res.send('Hello World!'));

app.listen(8080, () => console.log('Server running on port 8080'));
```

## Custom Image Requirements
Custom Dockerfiles must:
1. `EXPOSE 8080` - For user application
2. Have ENTRYPOINT or CMD
3. Optionally: Include the sandbox health server on port 9090 (or implement your own)

## Testing
```bash
pytest tests/  # Requires DIGITALOCEAN_TOKEN
```
