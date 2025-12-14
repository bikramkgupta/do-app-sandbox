# Python 3.13 Sandbox Image for App Platform Sandbox SDK
# Optimized image with single Python version, no build dependencies

# Build stage for Go health server
FROM golang:1.22-alpine AS health-builder
WORKDIR /build
COPY scripts/sandbox-health-server/main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o sandbox-health-server main.go

# Main image
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install minimal base dependencies (no build-essential, no apt python)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    unzip \
    jq \
    procps \
    netcat-openbsd \
    wget \
    sudo \
    lsof \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python installer and package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH=/root/.local/bin:$PATH

# Install Python 3.13
RUN uv python install 3.13

# Create sandbox user with sudo access
RUN useradd -ms /bin/bash sandbox \
    && echo "sandbox ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create /app symlink pointing to /home/sandbox/app for convenience
# This allows users to use /app in their code (as shown in docs) while
# the actual working directory is /home/sandbox/app
RUN mkdir -p /home/sandbox/app && ln -s /home/sandbox/app /app \
    && chown -R sandbox:sandbox /home/sandbox/app

# Copy uv and Python installation to sandbox user
RUN cp -r /root/.local /home/sandbox/.local \
    && chown -R sandbox:sandbox /home/sandbox/.local

# Copy the health server binary (runs on port 9090)
COPY --from=health-builder /build/sandbox-health-server /usr/local/bin/sandbox-health-server
RUN chmod +x /usr/local/bin/sandbox-health-server

# Switch to sandbox user
USER sandbox
WORKDIR /home/sandbox

# Add local bin to PATH
ENV PATH=/home/sandbox/.local/bin:$PATH

# Create symlinks for python/python3 (must be done after copying to sandbox user)
RUN PYTHON_PATH=$(uv python find 3.13) \
    && PYTHON_BIN_DIR=$(dirname "$PYTHON_PATH") \
    && ln -sf "$PYTHON_PATH" /home/sandbox/.local/bin/python3 \
    && ln -sf "$PYTHON_PATH" /home/sandbox/.local/bin/python \
    && ln -sf "$PYTHON_BIN_DIR/pip3" /home/sandbox/.local/bin/pip3 2>/dev/null || true \
    && ln -sf "$PYTHON_BIN_DIR/pip" /home/sandbox/.local/bin/pip 2>/dev/null || true \
    && echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Set working directory (directory already created above with /app symlink)
WORKDIR /home/sandbox/app

# Copy entrypoint script
COPY --chown=sandbox:sandbox entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose ports:
# - 8080: User application (completely free for user apps)
# - 9090: Health server (internal, for App Platform health checks)
EXPOSE 8080
EXPOSE 9090

# Run entrypoint
CMD ["/entrypoint.sh"]
