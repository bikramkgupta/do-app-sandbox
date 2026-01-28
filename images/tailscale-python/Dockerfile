# Python 3.13 + Tailscale Sandbox Image
# Enables SSH access via Tailscale (userspace mode, no NET_ADMIN required)

# Build stage for Go health server
FROM golang:1.22-alpine AS health-builder
WORKDIR /build
COPY scripts/sandbox-health-server/main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o sandbox-health-server main.go

# Main image
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install minimal base dependencies
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
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Tailscale from official repository
RUN curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y tailscale \
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
RUN mkdir -p /home/sandbox/app && ln -s /home/sandbox/app /app \
    && chown -R sandbox:sandbox /home/sandbox/app

# Copy uv and Python installation to sandbox user
RUN cp -r /root/.local /home/sandbox/.local \
    && chown -R sandbox:sandbox /home/sandbox/.local

# Create Tailscale state directory (for persistence)
RUN mkdir -p /var/lib/tailscale \
    && chown -R sandbox:sandbox /var/lib/tailscale

# Copy the health server binary (runs on port 9090)
COPY --from=health-builder /build/sandbox-health-server /usr/local/bin/sandbox-health-server
RUN chmod +x /usr/local/bin/sandbox-health-server

# Add local bin to PATH
ENV PATH=/home/sandbox/.local/bin:$PATH

# Create symlinks for python/python3 as root before switching user
RUN PYTHON_PATH=$(uv python find 3.13) \
    && PYTHON_BIN_DIR=$(dirname "$PYTHON_PATH") \
    && ln -sf "$PYTHON_PATH" /home/sandbox/.local/bin/python3 \
    && ln -sf "$PYTHON_PATH" /home/sandbox/.local/bin/python \
    && ln -sf "$PYTHON_BIN_DIR/pip3" /home/sandbox/.local/bin/pip3 2>/dev/null || true \
    && ln -sf "$PYTHON_BIN_DIR/pip" /home/sandbox/.local/bin/pip 2>/dev/null || true

# Setup sandbox user bashrc
RUN echo 'export PATH="$HOME/.local/bin:$PATH"' >> /home/sandbox/.bashrc

# Set working directory
WORKDIR /home/sandbox/app

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Tailscale environment variables (can be overridden at runtime)
# TS_AUTHKEY is required at runtime
ENV TS_STATE_DIR=/var/lib/tailscale
ENV TS_USERSPACE=true
ENV TS_SSH=true

# Expose ports:
# - 8080: User application
# - 9090: Health server (internal, for App Platform health checks)
EXPOSE 8080
EXPOSE 9090

# Run entrypoint as root (needed to start tailscaled, then drops to sandbox user)
CMD ["/entrypoint.sh"]
