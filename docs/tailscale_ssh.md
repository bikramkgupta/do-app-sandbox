# Tailscale SSH Access

SSH into your sandbox containers from your terminal using Tailscale's private network.

## Overview

The Tailscale-enabled sandbox images allow you to SSH directly into containers using standard terminal SSH. This enables:

- **Direct terminal SSH** - `ssh sandbox@100.x.x.x` from your terminal
- **SSH tunneling** - Forward ports to access container services locally
- **VS Code Remote** - Full IDE experience over SSH
- **scp/rsync** - File transfers
- **Any SSH-based tooling** - tmux, mosh, etc.

**Key features:**
- **Private network** - Containers are not exposed to the public internet
- **No SSH keys to manage** - Tailscale authenticates via your identity
- **End-to-end encrypted** - WireGuard encryption
- **Works anywhere** - Access containers from any network

## Requirements

- **Tailscale client on your laptop** - One-time install (~30MB)
- **Tailscale account** - Free tier works fine

## Available Images

| Image | Contents | GHCR Tag |
|-------|----------|----------|
| `sandbox-tailscale-python` | Python 3.13 + uv + Tailscale | `ghcr.io/{owner}/sandbox-tailscale-python:latest` |
| `sandbox-tailscale-node` | Node.js 24 + nvm + Tailscale | `ghcr.io/{owner}/sandbox-tailscale-node:latest` |

## Setup Guide

### Step 1: Install Tailscale on Your Laptop

**macOS:**
```bash
brew install tailscale
# Or download from https://tailscale.com/download/mac
```

**Linux:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

**Windows:**
Download from https://tailscale.com/download/windows

Then authenticate:
```bash
tailscale up
# Opens browser to authenticate with your Tailscale account
```

### Step 2: Create a Tailscale Account (if needed)

1. Go to [https://login.tailscale.com](https://login.tailscale.com)
2. Sign up with Google, Microsoft, GitHub, or email
3. Your laptop is now part of your "tailnet" (private network)

### Step 3: Generate an Auth Key for Containers

Auth keys allow containers to join your tailnet automatically.

1. Go to **Settings** > **Keys** ([direct link](https://login.tailscale.com/admin/settings/keys))
2. Click **Generate auth key**
3. Configure the key:
   - **Description**: e.g., "DO App Platform sandboxes"
   - **Reusable**: Enable if deploying multiple containers
   - **Ephemeral**: Enable (recommended) - nodes auto-remove when container stops
   - **Expiry**: Set as needed (default 90 days)
4. Click **Generate key**
5. **Copy the key** - it starts with `tskey-auth-` and is only shown once

### Step 4: Configure Tailscale ACLs for SSH

By default, Tailscale blocks SSH. Add an SSH policy:

1. Go to **Access Controls** ([direct link](https://login.tailscale.com/admin/acls/file))
2. Add an SSH rule:

```json
{
  "ssh": [
    {
      "action": "accept",
      "src": ["autogroup:member"],
      "dst": ["*"],
      "users": ["root", "sandbox"]
    }
  ]
}
```

3. Click **Save**

**ACL explanation:**
- `src: ["autogroup:member"]` - Any member of your tailnet (you) can SSH
- `dst: ["*"]` - Can SSH to any machine in your tailnet
- `users: ["root", "sandbox"]` - Can log in as `root` or `sandbox` user

### Step 5: Deploy the Container

Create an `app.yaml` file:

```yaml
name: my-tailscale-sandbox
region: nyc1
services:
  - name: sandbox
    image:
      registry_type: GHCR
      registry: bikramkgupta
      repository: sandbox-tailscale-python
      tag: latest
    instance_count: 1
    instance_size_slug: apps-s-1vcpu-1gb
    http_port: 8080
    internal_ports:
      - 9090
    health_check:
      http_path: /sandbox_health
      port: 9090
      initial_delay_seconds: 30
      period_seconds: 10
    envs:
      - key: TS_AUTHKEY
        value: "tskey-auth-xxxxx-xxxxxxxxx"
        type: SECRET
      - key: TS_HOSTNAME
        value: "my-python-sandbox"
```

Deploy:
```bash
doctl apps create --spec app.yaml
```

### Step 6: SSH into the Container

Once deployed, find the container's Tailscale IP:

```bash
# List all machines in your tailnet
tailscale status

# You'll see something like:
# 100.64.1.2    my-python-sandbox    linux   -
# 100.64.1.1    your-laptop          macOS   -
```

SSH in:
```bash
ssh sandbox@100.64.1.2
```

That's it! You're in with a full terminal session.

## Usage Examples

### Basic SSH

```bash
# SSH as sandbox user (has sudo)
ssh sandbox@100.64.1.2

# SSH as root
ssh root@100.64.1.2

# Run a single command
ssh sandbox@100.64.1.2 "python3 --version"
```

### Port Forwarding (SSH Tunnels)

Forward a port from the container to your laptop:

```bash
# Forward container's port 3000 to localhost:3000
ssh -L 3000:localhost:3000 sandbox@100.64.1.2

# Now open http://localhost:3000 in your browser
```

Example workflow - run a web app in the container:
```bash
# Terminal 1: SSH with port forward
ssh -L 8000:localhost:8000 sandbox@100.64.1.2

# In the SSH session, start a web server
cd /app
python -m http.server 8000

# On your laptop, open http://localhost:8000
```

### VS Code Remote SSH

1. Install the "Remote - SSH" extension in VS Code
2. Open Command Palette (Cmd+Shift+P) → "Remote-SSH: Connect to Host"
3. Enter: `sandbox@100.64.1.2`
4. VS Code opens with full access to the container filesystem

**Tip:** Add to `~/.ssh/config` for easier access:
```
Host sandbox
    HostName 100.64.1.2
    User sandbox
```

Then just: "Remote-SSH: Connect to Host" → "sandbox"

### File Transfers

```bash
# Copy file to container
scp ./myfile.py sandbox@100.64.1.2:/app/

# Copy file from container
scp sandbox@100.64.1.2:/app/output.txt ./

# Sync directory
rsync -avz ./myproject/ sandbox@100.64.1.2:/app/
```

### Multiple Containers

Deploy multiple containers with different hostnames:

```yaml
envs:
  - key: TS_HOSTNAME
    value: "sandbox-dev"    # or "sandbox-staging", etc.
```

Then:
```bash
tailscale status
# 100.64.1.2    sandbox-dev        linux   -
# 100.64.1.3    sandbox-staging    linux   -

ssh sandbox@100.64.1.2  # dev
ssh sandbox@100.64.1.3  # staging
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TS_AUTHKEY` | **Yes** | - | Tailscale auth key (`tskey-auth-...`) |
| `TS_HOSTNAME` | No | `sandbox-{python\|node}-{id}` | Custom hostname in Tailscale |
| `TS_STATE_DIR` | No | `/var/lib/tailscale` | State persistence directory |

## Finding Your Container's IP

**Option 1: Tailscale CLI**
```bash
tailscale status
```

**Option 2: Tailscale Admin Console**
Go to [https://login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)

**Option 3: From container logs**
```bash
doctl apps logs <app-id> --type=run | grep "Tailscale IP"
```

## Browser-Based SSH (Fallback)

If you can't install Tailscale on a particular machine, you can still SSH via browser:

1. Go to [https://login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)
2. Find your container
3. Click **...** → **SSH**

This runs an SSH client in your browser via WebAssembly.

## Troubleshooting

### Container not appearing in `tailscale status`

1. Check container logs:
   ```bash
   doctl apps logs <app-id> --type=run
   ```

2. Verify `TS_AUTHKEY` is set correctly (no extra whitespace)

3. Check if the auth key has expired or been revoked

### "Permission denied" when SSHing

1. Check ACL `users` field includes `sandbox` or `root`
2. Verify your laptop is authenticated: `tailscale status`
3. Try with verbose output: `ssh -v sandbox@100.64.1.2`

### Can't connect to container IP

1. Verify both machines are online: `tailscale status`
2. Check your laptop's Tailscale is running: `tailscale status`
3. Try pinging: `tailscale ping 100.64.1.2`

### SSH works but port forwarding doesn't

1. Verify the service is running in the container on that port
2. Check the service is bound to `0.0.0.0` or `localhost`, not just `127.0.0.1`

## Security Considerations

1. **Auth keys are secrets** - Always mark `TS_AUTHKEY` as encrypted/secret
2. **Use ephemeral keys** - Nodes auto-remove when container stops
3. **Rotate keys** - Generate new auth keys periodically
4. **Review ACLs** - Audit who can SSH to what machines
5. **MFA** - Enable MFA on your Tailscale account

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Your Laptop                                                     │
│                                                                 │
│  Terminal ──► Tailscale Client ──► WireGuard Tunnel            │
│      │              │                    │                      │
│   ssh sandbox@   100.64.1.1          encrypted                 │
│   100.64.1.2                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ (internet, encrypted)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ DigitalOcean App Platform                                       │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Container                                   100.64.1.2    │  │
│  │                                                           │  │
│  │   tailscaled (userspace) ◄── WireGuard Tunnel            │  │
│  │        │                                                  │  │
│  │        ▼                                                  │  │
│  │   Tailscale SSH ◄── sandbox user (sudo)                  │  │
│  │                                                           │  │
│  │   Python/Node runtime                                     │  │
│  │   Health server (:9090)                                   │  │
│  │   Your app (:8080)                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

All traffic between your laptop and container is end-to-end encrypted via WireGuard. The container is not exposed to the public internet - only members of your tailnet can reach it.

## References

- [Tailscale Downloads](https://tailscale.com/download)
- [Tailscale SSH Docs](https://tailscale.com/kb/1193/tailscale-ssh)
- [Tailscale ACLs](https://tailscale.com/kb/1018/acls)
- [Tailscale Auth Keys](https://tailscale.com/kb/1085/auth-keys)
