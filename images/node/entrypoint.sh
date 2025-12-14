#!/bin/bash
# Entrypoint script for Node.js Sandbox container
# Starts health server on port 9090 and leaves port 8080 free for user apps

set -e

# Source nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

echo "Sandbox container starting..."
echo "Node version: $(node --version)"
echo "npm version: $(npm --version)"

# Start the health server on port 9090 (background)
# This handles App Platform health checks so user apps don't need to
/usr/local/bin/sandbox-health-server &
echo "Health server started on port 9090 (endpoint: /sandbox_health)"

echo ""
echo "============================================"
echo "  Sandbox Ready!"
echo "  Port 8080 is FREE for your application"
echo "  No health endpoint required from your app"
echo "============================================"
echo ""

# Keep container alive - user will start their app on port 8080
tail -f /dev/null
