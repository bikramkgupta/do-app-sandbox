# Tailscale SSH Access

SSH into your sandbox containers via Tailscale - no VPN client needed on your laptop.

## Overview

The Tailscale-enabled sandbox images allow you to SSH directly into containers using Tailscale's browser-based SSH console. This is useful for:

- Interactive debugging and development
- Running commands that need a persistent terminal
- Accessing containers without exposing SSH publicly

**Key features:**
- **No client required** - SSH via browser at login.tailscale.com
- **Userspace networking** - Works on App Platform without special privileges
- **Persistent state** - Container keeps same Tailscale IP across restarts
- **End-to-end encrypted** - WireGuard encryption between your browser and container

## Available Images

| Image | Contents | GHCR Tag |
|-------|----------|----------|
| `sandbox-tailscale-python` | Python 3.13 + uv + Tailscale | `ghcr.io/{owner}/sandbox-tailscale-python:latest` |
| `sandbox-tailscale-node` | Node.js 24 + nvm + Tailscale | `ghcr.io/{owner}/sandbox-tailscale-node:latest` |

## Setup Guide

### Step 1: Create a Tailscale Account

1. Go to [https://login.tailscale.com](https://login.tailscale.com)
2. Sign up with Google, Microsoft, GitHub, or email
3. You'll land on the admin console dashboard

### Step 2: Generate an Auth Key

Auth keys allow containers to join your Tailscale network (tailnet) automatically.

1. Go to **Settings** > **Keys** ([direct link](https://login.tailscale.com/admin/settings/keys))
2. Click **Generate auth key**
3. Configure the key:
   - **Description**: e.g., "DO App Platform sandboxes"
   - **Reusable**: Enable if deploying multiple containers
   - **Ephemeral**: Enable (recommended) - nodes auto-remove when container stops
   - **Tags**: Optional, for ACL-based access control (e.g., `tag:sandbox`)
   - **Expiry**: Set as needed (default 90 days)
4. Click **Generate key**
5. **Copy the key** - it starts with `tskey-auth-` and is only shown once

### Step 3: Configure Tailscale ACLs for SSH

By default, Tailscale blocks SSH. You need to add an SSH policy.

1. Go to **Access Controls** ([direct link](https://login.tailscale.com/admin/acls))
2. Add an SSH rule to allow access. Here's a minimal example:

```json
{
  "ssh": [
    {
      "action": "accept",
      "src": ["autogroup:admin"],
      "dst": ["*"],
      "users": ["root", "sandbox"]
    }
  ]
}
```

**ACL explanation:**
- `src: ["autogroup:admin"]` - Only admins can SSH (you, as the account owner)
- `dst: ["*"]` - Can SSH to any machine in your tailnet
- `users: ["root", "sandbox"]` - Can log in as `root` or `sandbox` user

**More restrictive example using tags:**

```json
{
  "tagOwners": {
    "tag:sandbox": ["autogroup:admin"]
  },
  "ssh": [
    {
      "action": "accept",
      "src": ["autogroup:admin"],
      "dst": ["tag:sandbox"],
      "users": ["sandbox"]
    }
  ]
}
```

3. Click **Save** to apply the ACL changes

### Step 4: Deploy the Container

#### Option A: Using App Spec YAML

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

Deploy with doctl:

```bash
doctl apps create --spec app.yaml
```

#### Option B: Using DigitalOcean Dashboard

1. Go to [DigitalOcean App Platform](https://cloud.digitalocean.com/apps)
2. Click **Create App**
3. Choose **Container Image** as source
4. Enter image details:
   - Registry: `ghcr.io`
   - Repository: `bikramkgupta/sandbox-tailscale-python`
   - Tag: `latest`
5. Add environment variables:
   - `TS_AUTHKEY` = your auth key (mark as **Encrypt**)
   - `TS_HOSTNAME` = custom name (optional)
6. Configure resources and deploy

### Step 5: SSH into the Container

Once the container is running and connected to Tailscale:

1. Go to [https://login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)
2. Find your container (e.g., `my-python-sandbox`)
3. Click the **...** menu on the right
4. Select **SSH** (or hover and click the SSH icon)
5. A browser terminal opens - you're in!

The default user is `sandbox` with full sudo access.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TS_AUTHKEY` | **Yes** | - | Tailscale auth key (`tskey-auth-...`) |
| `TS_HOSTNAME` | No | `sandbox-{python\|node}-{id}` | Custom hostname in Tailscale |
| `TS_STATE_DIR` | No | `/var/lib/tailscale` | State persistence directory |
| `TS_USERSPACE` | No | `true` | Userspace networking (don't change) |
| `TS_SSH` | No | `true` | Enable Tailscale SSH (don't change) |

## Persistent State

By default, Tailscale state is stored in `/var/lib/tailscale`. If you mount a persistent volume to this path, your container will:

- Keep the same Tailscale IP address across restarts
- Not consume a new auth key on each restart
- Maintain its identity in your tailnet

Without persistence, each container restart creates a new Tailscale node (old ephemeral nodes auto-expire).

## Troubleshooting

### Container not appearing in Tailscale admin

1. Check container logs for Tailscale errors:
   ```bash
   doctl apps logs <app-id> --type=run
   ```

2. Verify `TS_AUTHKEY` is set correctly (no extra whitespace)

3. Check if the auth key has expired or been revoked

### SSH option not available

1. Verify the SSH ACL is configured (Step 3)
2. Check that your user is in the allowed `src` group
3. Ensure the `users` field includes `sandbox` or `root`

### "Permission denied" when SSHing

1. Check ACL `users` field includes the user you're trying to log in as
2. Default users are `sandbox` (with sudo) and `root`

### Container shows "offline" in Tailscale

1. The container may have stopped - check App Platform status
2. For ephemeral nodes, offline containers auto-remove after a few minutes

## Security Considerations

1. **Auth keys are secrets** - Always mark `TS_AUTHKEY` as encrypted/secret
2. **Use ephemeral keys** - Nodes auto-remove when container stops
3. **Use tags for ACLs** - Limit SSH access to specific tagged machines
4. **Rotate keys** - Generate new auth keys periodically
5. **Review ACLs** - Audit who can SSH to what machines

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────┐
│  Your Browser   │     │  DigitalOcean App Platform           │
│                 │     │                                      │
│  Tailscale      │     │  ┌────────────────────────────────┐  │
│  Admin Console  │────▶│  │  Container                     │  │
│                 │     │  │                                │  │
│  WebAssembly    │     │  │  tailscaled (userspace mode)   │  │
│  SSH Client     │◀───▶│  │       │                        │  │
│                 │     │  │       ▼                        │  │
└─────────────────┘     │  │  Tailscale SSH ◀── sandbox     │  │
        │               │  │                    user        │  │
        │               │  │                                │  │
        │ WireGuard     │  │  Python/Node runtime           │  │
        │ (encrypted)   │  │  Health server (:9090)         │  │
        │               │  │  User app (:8080)              │  │
        │               │  └────────────────────────────────┘  │
        │               └──────────────────────────────────────┘
        │
        ▼
┌─────────────────┐
│ Tailscale       │
│ Coordination    │
│ Server          │
└─────────────────┘
```

The browser runs a full Tailscale client via WebAssembly, connecting directly to your container through Tailscale's coordination servers. The actual SSH traffic is end-to-end encrypted - Tailscale cannot read your session.

## Comparison with Standard Images

| Feature | Standard Images | Tailscale Images |
|---------|-----------------|------------------|
| HTTP access | Via App Platform URL | Via App Platform URL |
| SSH access | Not available | Via Tailscale browser console |
| VPN client needed | N/A | No |
| Special privileges | None | None (userspace mode) |
| Startup time | ~30 seconds | ~35 seconds (Tailscale connect) |
| Additional config | None | Tailscale auth key + ACLs |

## References

- [Tailscale SSH Console Docs](https://tailscale.com/kb/1216/tailscale-ssh-console)
- [Tailscale Docker Guide](https://tailscale.com/kb/1282/docker)
- [Tailscale ACLs](https://tailscale.com/kb/1018/acls)
- [Tailscale Auth Keys](https://tailscale.com/kb/1085/auth-keys)
