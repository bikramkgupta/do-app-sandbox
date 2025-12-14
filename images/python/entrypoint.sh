#!/bin/bash
# Entrypoint script for Python Sandbox container
# Starts health server on port 9090 and leaves port 8080 free for user apps

# Note: Python is managed by uv

echo "Sandbox container starting..."
echo "Python version: $(uv run python --version 2>&1)"
echo "uv version: $(uv --version)"

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
