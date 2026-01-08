# Sandbox Node Service Image
# Service-mode sandbox with built-in FastAPI server for HTTP/SSE streaming
# Uses Bun as the default runtime (faster than Node.js)
# Node.js also available for compatibility
# API server is Python-based (FastAPI) for consistent streaming behavior

FROM oven/bun:1-slim

LABEL org.opencontainers.image.title="Sandbox Node Service"
LABEL org.opencontainers.image.description="Node/Bun sandbox for DO App Platform (service mode with HTTP API)"
LABEL org.opencontainers.image.source="https://github.com/bikramkgupta/do-app-sandbox"

# Install system dependencies, Node.js, and Python for API server
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    ca-certificates \
    openssh-client \
    gnupg \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 LTS for compatibility
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN bun --version && node --version && npm --version && python3 --version

# Install sandbox API dependencies
# Using pip since uv may not be available in all base images
RUN pip3 install --no-cache-dir --break-system-packages \
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
ENV NODE_ENV=development
ENV PYTHONPATH=/opt
ENV PYTHONUNBUFFERED=1

# Expose HTTP port for App Platform ingress
EXPOSE 8080

# Run the FastAPI server
CMD ["python3", "-m", "uvicorn", "sandbox_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
