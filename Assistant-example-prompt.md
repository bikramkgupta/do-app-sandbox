# Assistant Example Prompt: Deploy Multiple Vite + React Todo Apps to DigitalOcean Sandboxes

## Overview

This guide helps AI coding agents deploy multiple Node.js/React/Vite todo app variants to DigitalOcean App Platform sandboxes. Follow this guide to avoid common pitfalls and ensure successful deployments on the first attempt.

**Goal**: Deploy 3 different todo app variants, each in its own sandbox, with all apps running simultaneously.

---

## Prerequisites

1. **Install dependencies**:
   ```bash
   uv add do-app-sandbox
   # or
   pip install do-app-sandbox
   ```

2. **DigitalOcean API Token**: Set `DIGITALOCEAN_TOKEN` environment variable or authenticate with `doctl`

3. **Project structure**: Three todo app variants in separate directories:
   - `todo-app-variant-1/`
   - `todo-app-variant-2/`
   - `todo-app-variant-3/`

---

## Critical Requirements (MUST-KNOW)

### 1. Sandbox Naming Pattern

**Pattern**: `^[a-z][a-z0-9-]{0,30}[a-z0-9]$`

- ✅ **DO**: Use lowercase letters, numbers, and hyphens
- ✅ **DO**: Start with a letter, end with a letter or number
- ❌ **DON'T**: Use underscores, uppercase letters, or special characters
- ❌ **DON'T**: End with a hyphen

**Examples**:
- ✅ `sandbox-1-12345`
- ✅ `todo-app-variant-1`
- ❌ `sandbox_1_12345` (underscores not allowed)
- ❌ `Sandbox-1` (uppercase not allowed)
- ❌ `sandbox-1-` (cannot end with hyphen)

### 2. Port Configuration

**Port 9090**: Health Check (DO NOT TOUCH)
- A Go binary automatically runs here for health checks
- **NEVER** try to start a process on port 9090
- **NEVER** modify or kill processes on port 9090
- Just verify it's running: `sandbox.exec("lsof -i :9090")`

**Port 8080**: Your Vite App (MUST USE)
- Your Vite dev server **MUST** run on port 8080
- Configure in `vite.config.js` (see below)

### 3. Vite Configuration Requirements

Your `vite.config.js` **MUST** include:

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',        // Required: listen on all interfaces
    port: 8080,             // Required: use port 8080
    allowedHosts: true,      // Required: allow DigitalOcean hostnames
  },
})
```

**Why `allowedHosts: true`?**
- DigitalOcean assigns dynamic hostnames like `sandbox-1-12345-abc123.ondigitalocean.app`
- Without this, Vite will block requests with: "Blocked request. This host is not allowed"

### 4. File Upload Strategy

**DO NOT** upload `node_modules` or build artifacts:
- ❌ Including `node_modules` makes zip files huge (50-100MB+)
- ❌ Build artifacts (`dist/`, `build/`) are not needed for dev mode
- ✅ Upload only source code and config files
- ✅ Install dependencies fresh in the sandbox with `npm install`

**Exclude from zip**:
- `node_modules/`
- `dist/`, `build/`, `.next/`, `out/`
- `.git/`, `.vscode/`, `.idea/`
- `.env` (but keep `.env.example`)

---

## Deployment Workflow

### Step-by-Step Process

1. **Create sandbox** with valid name pattern
2. **Create zip archive** (exclude dependencies/build artifacts)
3. **Upload zip** to sandbox
4. **Extract files** in sandbox
5. **Install dependencies** (`npm install` in sandbox)
6. **Start dev server** using `launch_process` (NOT `nohup`)
7. **Verify process** is running
8. **Get URL** and verify accessibility

---

## Code Examples

### 1. Zip Creation with Exclusions

```python
import os
import zipfile
from pathlib import Path

def should_include_file(file_path, base_dir):
    """Determine if a file should be included in the zip archive."""
    rel_path = Path(file_path).relative_to(base_dir)
    parts = rel_path.parts
    
    # Exclude dependency directories
    if 'node_modules' in parts or '__pycache__' in parts:
        return False
    if any(part in ['.venv', 'venv', 'env'] for part in parts):
        return False
    
    # Exclude build artifacts
    if any(part in ['dist', 'build', '.next', 'out', 'coverage'] for part in parts):
        return False
    
    # Exclude version control
    if any(part in ['.git', '.svn', '.hg'] for part in parts):
        return False
    
    # Exclude IDE and OS files
    if any(part in ['.vscode', '.idea', '.DS_Store', 'Thumbs.db'] for part in parts):
        return False
    
    # Keep important config files
    keep_patterns = {'.env.example', '.gitignore', '.npmignore', '.eslintrc', '.eslintrc.js'}
    if rel_path.name in keep_patterns:
        return True
    
    # Exclude .env files (but keep .env.example)
    if rel_path.name == '.env':
        return False
    
    # Exclude other hidden files/directories
    if any(part.startswith('.') for part in parts):
        return False
    
    return True

def create_zip_archive(source_dir, output_path):
    """Create a zip archive excluding dependencies and build artifacts."""
    # Delete old zip if exists
    if Path(output_path).exists():
        Path(output_path).unlink()
    
    source_path = Path(source_dir)
    files_included = 0
    files_excluded = 0
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_path):
            # Modify dirs in-place to skip excluded directories
            dirs[:] = [d for d in dirs if should_include_file(Path(root) / d, source_path)]
            
            for file in files:
                file_path = Path(root) / file
                if should_include_file(file_path, source_path):
                    arcname = file_path.relative_to(source_path)
                    zipf.write(file_path, arcname)
                    files_included += 1
                else:
                    files_excluded += 1
    
    zip_size = Path(output_path).stat().st_size / 1024  # KB
    print(f"✓ Zip created: {output_path} ({zip_size:.1f} KB)")
    print(f"  Files included: {files_included}, excluded: {files_excluded}")
    return output_path
```

### 2. Sandbox Creation

```python
from do_app_sandbox import Sandbox
import random

# Generate valid sandbox name
random_suffix = random.randint(10000, 99999)
sandbox_name = f"sandbox-1-{random_suffix}"  # ✅ Valid pattern

# Create sandbox
sandbox = Sandbox.create(
    image="node",
    name=sandbox_name,
    wait_ready=True,
    timeout=600
)

print(f"Sandbox created: {sandbox.app_id}")
```

### 3. File Upload and Extraction

```python
# Create zip
zip_path = create_zip_archive("todo-app-variant-1", "temp.zip")

# Upload zip
remote_zip_path = "/home/sandbox/todo-app.zip"
sandbox.filesystem.upload_file(str(zip_path), remote_zip_path)

# Extract (zip contains todo-app-variant-1 folder)
extract_result = sandbox.exec(
    f"cd /home/sandbox && mkdir -p app && "
    f"unzip -o {remote_zip_path} && "
    f"mv todo-app-variant-1/* app/ 2>/dev/null && "
    f"mv todo-app-variant-1/.* app/ 2>/dev/null || true && "
    f"rmdir todo-app-variant-1 2>/dev/null || true && "
    f"rm {remote_zip_path}",
    timeout=60
)

# Clean up local zip
Path(zip_path).unlink()
```

### 4. Install Dependencies

```python
# Install dependencies in sandbox (NOT uploaded)
install_result = sandbox.exec(
    "cd /home/sandbox/app && npm install",
    timeout=300
)

if not install_result.success:
    print(f"npm install failed: {install_result.stderr}")
    return None
```

### 5. Start Dev Server (CORRECT WAY)

```python
# ✅ CORRECT: Use launch_process directly
pid = sandbox.launch_process(
    "npm run dev",
    cwd="/home/sandbox/app"
)

# ❌ WRONG: Don't use nohup, &, or output redirection
# pid = sandbox.launch_process("nohup npm run dev > log 2>&1 &", ...)  # DON'T DO THIS
# pid = sandbox.launch_process("cd /home/sandbox/app && npm run dev", ...)  # DON'T DO THIS
```

**Why?**
- `launch_process` handles backgrounding automatically
- Using `nohup` or `&` creates extra bash processes
- Using `cd` in command is redundant when `cwd` parameter exists
- Output redirection is handled by the SDK

### 6. Verify Process is Running

```python
import time

# Wait for server to start
time.sleep(8)

# Verify using list_processes (NOT ps aux | grep)
all_procs = sandbox.list_processes()

# Look for relevant processes
relevant_procs = []
for proc in all_procs:
    cmd_lower = proc.command.lower()
    if any(term in cmd_lower for term in ["vite", "npm", "dev"]) and "grep" not in cmd_lower:
        relevant_procs.append(proc)

if relevant_procs:
    print(f"✓ Found {len(relevant_procs)} process(es):")
    for proc in relevant_procs:
        print(f"  PID {proc.pid}: {proc.command} (Status: {proc.status})")
else:
    print("⚠ Warning: Could not find Vite process")

# Verify port 8080 is listening
port_check = sandbox.exec("lsof -i :8080 || netstat -tuln | grep 8080 || ss -tuln | grep 8080")
if port_check.success:
    print("✓ Vite is listening on port 8080")
```

### 7. Verify Health Check (Don't Modify)

```python
# Verify health check on port 9090 (should already be running)
health_check = sandbox.exec("lsof -i :9090 || netstat -tuln | grep 9090 || ss -tuln | grep 9090")
if health_check.success:
    print("✓ Health check running on port 9090")
else:
    print("⚠ Warning: Could not verify health check (may be normal)")
```

### 8. Get URL

```python
url = sandbox.get_url()
print(f"App URL: {url}")
```

---

## Common Pitfalls & Solutions

### ❌ Pitfall 1: Using `nohup` or `&` with `launch_process`

**Wrong**:
```python
pid = sandbox.launch_process("nohup npm run dev > /tmp/log 2>&1 &", cwd="/home/sandbox/app")
```

**Right**:
```python
pid = sandbox.launch_process("npm run dev", cwd="/home/sandbox/app")
```

**Why**: `launch_process` handles backgrounding automatically. Adding `nohup` or `&` creates extra bash processes and can cause the process to not start correctly.

### ❌ Pitfall 2: Including `node_modules` in Zip

**Wrong**: Uploading everything including `node_modules` (50-100MB+ zip files)

**Right**: Exclude `node_modules`, upload only source code, install dependencies in sandbox

**Impact**: Huge zip files take forever to upload and waste bandwidth.

### ❌ Pitfall 3: Using Underscores in Sandbox Name

**Wrong**:
```python
sandbox_name = f"sandbox_1_{random_suffix}"  # ❌ Underscores not allowed
```

**Right**:
```python
sandbox_name = f"sandbox-1-{random_suffix}"  # ✅ Hyphens only
```

**Error**: `name in body should match '^[a-z][a-z0-9-]{0,30}[a-z0-9]$'`

### ❌ Pitfall 4: Missing `allowedHosts: true` in Vite Config

**Wrong**:
```javascript
server: {
  host: '0.0.0.0',
  port: 8080,
  // Missing allowedHosts
}
```

**Right**:
```javascript
server: {
  host: '0.0.0.0',
  port: 8080,
  allowedHosts: true,  // Required for DO hostnames
}
```

**Error**: "Blocked request. This host is not allowed"

### ❌ Pitfall 5: Using `cd` in Command When `cwd` Exists

**Wrong**:
```python
sandbox.launch_process("cd /home/sandbox/app && npm run dev")
```

**Right**:
```python
sandbox.launch_process("npm run dev", cwd="/home/sandbox/app")
```

**Why**: Redundant and can cause issues. Use the `cwd` parameter.

### ❌ Pitfall 6: Trying to Modify Port 9090

**Wrong**: Starting processes on port 9090 or killing the health check process

**Right**: Leave port 9090 alone. It's managed by DigitalOcean for health checks.

---

## Complete Example: Deploy 3 Todo App Variants

```python
#!/usr/bin/env python3
"""
Deploy 3 Vite + React todo app variants to separate sandboxes.
"""

import os
import time
import random
import zipfile
from pathlib import Path
from do_app_sandbox import Sandbox

def should_include_file(file_path, base_dir):
    """Exclude dependencies and build artifacts."""
    rel_path = Path(file_path).relative_to(base_dir)
    parts = rel_path.parts
    
    if 'node_modules' in parts or any(part in ['dist', 'build', '.git', '.vscode'] for part in parts):
        return False
    
    keep_patterns = {'.env.example', '.gitignore', '.npmignore', '.eslintrc', '.eslintrc.js'}
    if rel_path.name in keep_patterns:
        return True
    
    if rel_path.name == '.env' or any(part.startswith('.') for part in parts):
        return False
    
    return True

def create_zip_archive(source_dir, output_path):
    """Create zip excluding node_modules and build artifacts."""
    if Path(output_path).exists():
        Path(output_path).unlink()
    
    source_path = Path(source_dir)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_path):
            dirs[:] = [d for d in dirs if should_include_file(Path(root) / d, source_path)]
            for file in files:
                file_path = Path(root) / file
                if should_include_file(file_path, source_path):
                    zipf.write(file_path, file_path.relative_to(source_path))
    
    zip_size = Path(output_path).stat().st_size / 1024
    print(f"✓ Zip created: {zip_size:.1f} KB")
    return output_path

def deploy_variant(variant_name, variant_dir):
    """Deploy a single todo app variant to a sandbox."""
    print(f"\n{'='*60}")
    print(f"Deploying {variant_name}")
    print(f"{'='*60}\n")
    
    # Create sandbox with valid name
    random_suffix = random.randint(10000, 99999)
    sandbox_name = f"sandbox-{variant_name.split('-')[-1]}-{random_suffix}"
    
    print(f"Creating sandbox: {sandbox_name}")
    sandbox = Sandbox.create(
        image="node",
        name=sandbox_name,
        wait_ready=True,
        timeout=600
    )
    
    print(f"✓ Sandbox ready: {sandbox.app_id}")
    
    # Create and upload zip
    temp_zip = Path(f"{variant_name}-temp.zip")
    try:
        zip_path = create_zip_archive(variant_dir, temp_zip)
        
        remote_zip_path = "/home/sandbox/todo-app.zip"
        sandbox.filesystem.upload_file(str(zip_path), remote_zip_path)
        print("✓ Zip uploaded")
        
        # Extract
        extract_result = sandbox.exec(
            f"cd /home/sandbox && mkdir -p app && "
            f"unzip -o {remote_zip_path} && "
            f"mv {variant_name}/* app/ 2>/dev/null && "
            f"mv {variant_name}/.* app/ 2>/dev/null || true && "
            f"rmdir {variant_name} 2>/dev/null || true && "
            f"rm {remote_zip_path}",
            timeout=60
        )
        print("✓ Files extracted")
    finally:
        if temp_zip.exists():
            temp_zip.unlink()
    
    # Install dependencies
    print("Installing dependencies...")
    install_result = sandbox.exec(
        "cd /home/sandbox/app && npm install",
        timeout=300
    )
    if not install_result.success:
        print(f"❌ npm install failed: {install_result.stderr}")
        return None
    print("✓ Dependencies installed")
    
    # Start Vite dev server
    print("Starting Vite dev server...")
    pid = sandbox.launch_process(
        "npm run dev",
        cwd="/home/sandbox/app"
    )
    print(f"✓ Vite launched with PID: {pid}")
    
    # Wait and verify
    time.sleep(8)
    processes = sandbox.list_processes()
    vite_procs = [p for p in processes if "vite" in p.command.lower() or "npm" in p.command.lower()]
    if vite_procs:
        print(f"✓ Process verified: {vite_procs[0].command}")
    
    # Get URL
    url = sandbox.get_url()
    print(f"✓ URL: {url}")
    
    return {
        'name': variant_name,
        'sandbox_name': sandbox_name,
        'url': url,
        'app_id': sandbox.app_id,
        'sandbox': sandbox
    }

def main():
    """Deploy all 3 variants."""
    variants = [
        ('variant-1', 'todo-app-variant-1'),
        ('variant-2', 'todo-app-variant-2'),
        ('variant-3', 'todo-app-variant-3'),
    ]
    
    results = []
    for variant_name, variant_dir in variants:
        variant_path = Path(variant_dir)
        if not variant_path.exists():
            print(f"⚠ Skipping {variant_dir} (not found)")
            continue
        
        result = deploy_variant(variant_name, str(variant_path))
        if result:
            results.append(result)
        
        # Small delay between deployments
        if variant_name != variants[-1][0]:
            print("\nWaiting 10 seconds before next deployment...")
            time.sleep(10)
    
    # Summary
    print(f"\n{'='*60}")
    print("DEPLOYMENT SUMMARY")
    print(f"{'='*60}\n")
    
    for result in results:
        print(f"{result['name'].upper()}:")
        print(f"  Sandbox: {result['sandbox_name']}")
        print(f"  URL: {result['url']}")
        print(f"  App ID: {result['app_id']}")
        print()
    
    return results

if __name__ == "__main__":
    main()
```

---

## Verification Checklist

Before considering deployment successful, verify:

- [ ] Health check on port 9090 is running (verify, don't modify)
- [ ] Vite process is running (use `sandbox.list_processes()`)
- [ ] Port 8080 is listening (check with `lsof -i :8080`)
- [ ] URL is accessible (visit in browser)
- [ ] No errors in process output
- [ ] Zip file size is reasonable (< 1MB, not 50MB+)

---

## Troubleshooting

### Process Not Running

**Symptoms**: `list_processes()` shows no Vite process

**Solutions**:
1. Check if process exited: `sandbox.process_manager.get_output(pid)`
2. Verify `npm install` succeeded
3. Check Vite config has correct port and `allowedHosts: true`
4. Ensure you're using `launch_process` directly (not with `nohup`)

### Port 8080 Not Listening

**Symptoms**: `lsof -i :8080` returns nothing

**Solutions**:
1. Wait longer (Vite may need 10-15 seconds to start)
2. Check process output for errors
3. Verify Vite config has `port: 8080` and `host: '0.0.0.0'`

### "Blocked request" Error

**Symptoms**: Browser shows "Blocked request. This host is not allowed"

**Solution**: Add `allowedHosts: true` to `vite.config.js` server config

### Sandbox Creation Fails

**Symptoms**: Error about name pattern validation

**Solution**: Ensure sandbox name matches `^[a-z][a-z0-9-]{0,30}[a-z0-9]$` (lowercase, hyphens only, no underscores)

### Zip File Too Large

**Symptoms**: Zip file is 50MB+ instead of < 1MB

**Solution**: Ensure `node_modules` and `dist/` are excluded from zip

---

## Best Practices Summary

1. ✅ **Always exclude `node_modules`** from zip files
2. ✅ **Use `launch_process` directly** (no `nohup`, no `&`)
3. ✅ **Use `cwd` parameter** instead of `cd` in commands
4. ✅ **Set `allowedHosts: true`** in Vite config
5. ✅ **Verify health check** on 9090 (don't modify it)
6. ✅ **Use `list_processes()`** for verification (not `ps aux | grep`)
7. ✅ **Follow naming pattern** strictly (lowercase, hyphens only)
8. ✅ **Wait 8-10 seconds** after launching process before verification

---

## Next Steps

After successful deployment:
- Monitor processes: `sandbox.list_processes()`
- View logs: Use `doctl apps logs` if needed
- Clean up: `sandbox.delete()` when done
- Scale: Deploy more variants using the same pattern

---

**Remember**: The key to success is following the exact patterns above. Don't try to "improve" them with shell redirection, `nohup`, or other workarounds - the SDK handles everything correctly when used as shown.

