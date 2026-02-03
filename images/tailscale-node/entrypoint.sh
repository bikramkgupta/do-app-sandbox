#!/bin/bash
# Entrypoint script for Node.js + Tailscale Sandbox container
# Starts Tailscale (userspace mode), health server, and keeps container alive

set -e

echo "Tailscale Node.js Sandbox starting..."

# Verify required environment variable
if [ -z "$TS_AUTHKEY" ]; then
    echo "ERROR: TS_AUTHKEY environment variable is required"
    echo "Generate an auth key at: https://login.tailscale.com/admin/settings/keys"
    exit 1
fi

# Set default hostname if not provided
if [ -z "$TS_HOSTNAME" ]; then
    TS_HOSTNAME="sandbox-node-$(hostname | cut -c1-8)"
fi

echo "Starting Tailscale daemon (userspace mode)..."

# Start tailscaled in userspace mode (no TUN device or NET_ADMIN required)
tailscaled --state="${TS_STATE_DIR}/tailscaled.state" --socket=/var/run/tailscale/tailscaled.sock --tun=userspace-networking &
TAILSCALED_PID=$!

# Wait for tailscaled to be ready
sleep 2

# Check if tailscaled is running
if ! kill -0 $TAILSCALED_PID 2>/dev/null; then
    echo "ERROR: tailscaled failed to start"
    exit 1
fi

echo "Connecting to Tailscale network..."

# Bring up Tailscale with SSH enabled
tailscale up \
    --authkey="${TS_AUTHKEY}" \
    --hostname="${TS_HOSTNAME}" \
    --ssh \
    --accept-routes=false \
    --accept-dns=false

# Get Tailscale IP and status
TS_IP=$(tailscale ip -4 2>/dev/null || echo "pending")
TS_STATUS=$(tailscale status --json 2>/dev/null | jq -r '.Self.Online // "unknown"' || echo "unknown")

echo "Tailscale connected!"
echo "  Hostname: ${TS_HOSTNAME}"
echo "  IP: ${TS_IP}"
echo "  SSH: enabled"

# Start the health server on port 9090 (background)
/usr/local/bin/sandbox-health-server &
echo "Health server started on port 9090 (endpoint: /sandbox_health)"

# Source nvm and print Node version
export NVM_DIR="/home/sandbox/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

echo ""
echo "Node version: $(node --version 2>&1)"
echo "npm version: $(npm --version 2>&1)"

echo ""
echo "============================================"
echo "  Tailscale Node.js Sandbox Ready!"
echo "============================================"
echo "  Tailscale IP: ${TS_IP}"
echo "  Hostname: ${TS_HOSTNAME}"
echo ""
echo "  SSH Access (browser):"
echo "    1. Go to https://login.tailscale.com/admin/machines"
echo "    2. Find '${TS_HOSTNAME}' and click 'SSH'"
echo ""
echo "  Port 8080 is FREE for your application"
echo "============================================"
echo ""

# Keep container alive - user will start their app on port 8080
# Using wait to allow signal handling
tail -f /dev/null &
wait $!
