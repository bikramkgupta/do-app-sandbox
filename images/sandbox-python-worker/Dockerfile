# Sandbox Python Worker Image
# Base image for worker-mode sandboxes (no HTTP API)
# Uses uv for fast Python package management

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Sandbox Python Worker"
LABEL org.opencontainers.image.description="Python sandbox for DO App Platform (worker mode)"
LABEL org.opencontainers.image.source="https://github.com/bikramkgupta/do-app-sandbox"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    build-essential \
    ca-certificates \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager - 10-100x faster than pip)
# https://github.com/astral-sh/uv
ENV UV_INSTALL_DIR="/usr/local/bin"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.local/bin:/usr/local/bin:$PATH"

# Verify uv installation
RUN uv --version

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Set environment
ENV SANDBOX_MODE=worker
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default: keep container running for doctl console access
# Workers don't expose any HTTP ports
CMD ["tail", "-f", "/dev/null"]
