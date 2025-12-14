# Node.js 24 Sandbox Image for App Platform Sandbox SDK
# Optimized image with single Node version, no build dependencies

# Build stage for Go health server
FROM golang:1.22-alpine AS health-builder
WORKDIR /build
COPY scripts/sandbox-health-server/main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o sandbox-health-server main.go

# Main image
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install minimal base dependencies (no build-essential)
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

# Install Node.js 24 via nvm
ENV NVM_DIR=/root/.nvm
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash \
    && . "$NVM_DIR/nvm.sh" \
    && nvm install 24 \
    && nvm alias default 24

# Create sandbox user with sudo access
RUN useradd -ms /bin/bash sandbox \
    && echo "sandbox ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create /app symlink pointing to /home/sandbox/app for convenience
# This allows users to use /app in their code (as shown in docs) while
# the actual working directory is /home/sandbox/app
RUN mkdir -p /home/sandbox/app && ln -s /home/sandbox/app /app \
    && chown -R sandbox:sandbox /home/sandbox/app

# Copy nvm to sandbox user
RUN cp -r /root/.nvm /home/sandbox/.nvm \
    && mkdir -p /home/sandbox/.local/bin \
    && chown -R sandbox:sandbox /home/sandbox/.nvm /home/sandbox/.local

# Copy the health server binary (runs on port 9090)
COPY --from=health-builder /build/sandbox-health-server /usr/local/bin/sandbox-health-server
RUN chmod +x /usr/local/bin/sandbox-health-server

# Switch to sandbox user
USER sandbox
WORKDIR /home/sandbox

# Add local bin to PATH and setup nvm
ENV PATH=/home/sandbox/.local/bin:$PATH
ENV NVM_DIR=/home/sandbox/.nvm

# Create symlinks for node/npm/npx (must be done after copying to sandbox user)
RUN . "$NVM_DIR/nvm.sh" \
    && NODE_BIN_DIR="$NVM_DIR/versions/node/$(node --version)/bin" \
    && ln -sf "$NODE_BIN_DIR/node" /home/sandbox/.local/bin/node \
    && ln -sf "$NODE_BIN_DIR/npm" /home/sandbox/.local/bin/npm \
    && ln -sf "$NODE_BIN_DIR/npx" /home/sandbox/.local/bin/npx \
    && echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc \
    && echo 'export NVM_DIR="$HOME/.nvm"' >> ~/.bashrc \
    && echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> ~/.bashrc

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
