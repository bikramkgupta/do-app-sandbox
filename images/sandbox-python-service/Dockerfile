# Sandbox Python Service Image
# Service-mode sandbox with built-in FastAPI server for HTTP/SSE streaming
# Uses uv for fast Python package management

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Sandbox Python Service"
LABEL org.opencontainers.image.description="Python sandbox for DO App Platform (service mode with HTTP API)"
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
ENV UV_INSTALL_DIR="/usr/local/bin"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.local/bin:/usr/local/bin:$PATH"

# Verify uv installation
RUN uv --version

# Install sandbox API dependencies using uv
# Using --system to install globally (not in a venv)
RUN uv pip install --system \
    fastapi==0.109.2 \
    uvicorn[standard]==0.27.1 \
    httpx==0.26.0 \
    pydantic==2.6.1

# Copy sandbox API server
COPY sandbox_api/ /opt/sandbox_api/

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Set environment
ENV SANDBOX_MODE=service
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/opt

# Expose HTTP port for App Platform ingress
EXPOSE 8080

# Run the FastAPI server
CMD ["uvicorn", "sandbox_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
