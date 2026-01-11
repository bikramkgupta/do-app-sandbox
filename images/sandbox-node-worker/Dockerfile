# Sandbox Node Worker Image
# Base image for worker-mode sandboxes (no HTTP API)
# Uses Bun as the default runtime (faster than Node.js)
# Node.js also available for compatibility

FROM oven/bun:1-slim

LABEL org.opencontainers.image.title="Sandbox Node Worker"
LABEL org.opencontainers.image.description="Node/Bun sandbox for DO App Platform (worker mode)"
LABEL org.opencontainers.image.source="https://github.com/bikramkgupta/do-app-sandbox"

# Install system dependencies and Node.js for compatibility
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    ca-certificates \
    openssh-client \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 LTS for compatibility
# Some packages may not work with Bun yet
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN bun --version && node --version && npm --version

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Set environment
ENV SANDBOX_MODE=worker
ENV NODE_ENV=development

# Default: keep container running for doctl console access
# Workers don't expose any HTTP ports
CMD ["tail", "-f", "/dev/null"]
