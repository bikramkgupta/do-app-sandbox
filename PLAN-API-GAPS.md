# Implementation Plan: API Gaps & Snapshot/Restore

## Overview

This plan addresses the critical and high-priority API gaps identified in the Cloudflare Sandbox SDK comparison, plus adds snapshot/restore functionality for rapid agent startup.

### Architecture Decision: Service-Based Streaming

**Key Insight**: Instead of fighting pexpect limitations for streaming, leverage App Platform's native HTTP/2 ingress.

| Mode | Component Type | Use Case | Execution Method |
|------|---------------|----------|------------------|
| **Default** | Worker | Basic exec, no streaming needed | `doctl apps console` via pexpect |
| **Streaming** | Service | Real-time output, port exposure, log streaming | HTTP API with SSE |

### Features to Implement

| Priority | Feature | Effort | Approach |
|----------|---------|--------|----------|
| 🔴 Critical | `exec_stream()` | Medium | HTTP/2 + SSE via service |
| 🔴 Critical | Port Exposure / Preview URLs | Medium | Internal reverse proxy in service |
| 🔴 Critical | Auto-sleep / Hibernate | Medium | Snapshot + scale to 0 |
| 🟠 High | Process Logs API | Low | HTTP streaming endpoint |
| 🟠 High | Sessions API | Medium | Server-side session management |
| 🟠 High | `git_checkout()` | Low | Convenience wrapper |
| 🟢 New | Snapshot/Restore API | Medium | Spaces-backed tar archives |

---

## Architecture: Service Mode with HTTP API

### Container Components (Service Mode)

```
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox Container (Service)               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │  Sandbox API    │    │  User Processes                 │ │
│  │  (FastAPI)      │    │  (npm start, python app.py)     │ │
│  │  Port 8080      │    │  Ports 3000, 5000, etc.         │ │
│  └────────┬────────┘    └─────────────────────────────────┘ │
│           │                          ▲                       │
│           │    ┌─────────────────────┘                       │
│           ▼    ▼                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Reverse Proxy (Caddy)                                  │ │
│  │  - /api/* → Sandbox API (8080)                          │ │
│  │  - /proxy/{port}/* → localhost:{port}                   │ │
│  │  Port 80 (internal) → App Platform routes to 8080       │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Authentication: Dynamic Token

```python
# At sandbox creation
import secrets
sandbox_token = secrets.token_urlsafe(32)

# Passed as environment variable to container
envs:
  - key: SANDBOX_API_TOKEN
    scope: RUN_TIME
    type: SECRET
    value: ${generated_token}

# All API calls require header
Authorization: Bearer {sandbox_token}
```

### API Endpoints (Inside Container)

```
# Health (no auth)
GET  /health                              → {"status": "ok"}

# Command Execution (auth required)
POST /api/exec                            → CommandResult (JSON)
POST /api/exec/stream                     → SSE stream of output
POST /api/exec/background                 → {"pid": 12345}

# Process Management
GET  /api/processes                       → List[ProcessInfo]
GET  /api/processes/{pid}/logs            → Log content
GET  /api/processes/{pid}/logs/stream     → SSE log stream
POST /api/processes/{pid}/kill            → {"success": true}

# Sessions
POST /api/sessions                        → {"session_id": "..."}
GET  /api/sessions/{id}                   → SessionInfo
POST /api/sessions/{id}/exec              → CommandResult
POST /api/sessions/{id}/exec/stream       → SSE stream
DELETE /api/sessions/{id}                 → {"success": true}

# File Operations
GET  /api/files?path=/workspace           → FileInfo[]
GET  /api/files/content?path=/app/main.py → File content
POST /api/files/content                   → Write file
POST /api/files/upload                    → Multipart upload
GET  /api/files/download?path=...         → File download

# Port Proxy (handled by Caddy)
ANY  /proxy/{port}/*                      → Proxied to localhost:{port}
```

### SSE Streaming Format

```typescript
// Event types
event: stdout
data: {"line": "Building project...", "timestamp": 1704672000.123}

event: stderr
data: {"line": "Warning: deprecated API", "timestamp": 1704672000.456}

event: exit
data: {"code": 0, "duration_ms": 5234}

event: error
data: {"message": "Command timed out", "code": "TIMEOUT"}
```

---

## 1. Service Mode Implementation

### Goal
Add ability to deploy sandbox as a Service with HTTP API for streaming capabilities.

### Design

```python
# In types.py
class SandboxMode(Enum):
    """Sandbox deployment mode."""
    WORKER = "worker"      # Default: doctl console execution
    SERVICE = "service"    # HTTP API with streaming support

@dataclass
class ServiceConfig:
    """Configuration for service mode."""
    api_port: int = 8080
    proxy_ports: List[int] = field(default_factory=lambda: [3000, 5000, 8000])
    enable_file_api: bool = True
    enable_sessions: bool = True
    token: Optional[str] = None  # Auto-generated if not provided

# In sandbox.py
class Sandbox:
    @classmethod
    def create(
        cls,
        image: str = "python",
        mode: SandboxMode = SandboxMode.WORKER,  # NEW
        service_config: Optional[ServiceConfig] = None,  # NEW
        region: str = "nyc",
        ...
    ) -> "Sandbox":
        """Create a new sandbox.

        Args:
            image: Base image (python, node)
            mode: WORKER (default) or SERVICE (for streaming)
            service_config: Configuration for service mode
            ...
        """
```

### Implementation

```python
# In deployer.py
def _build_app_spec(self, name: str, image: str, mode: SandboxMode,
                    service_config: Optional[ServiceConfig] = None) -> dict:
    """Build App Platform spec based on mode."""

    if mode == SandboxMode.WORKER:
        return self._build_worker_spec(name, image)
    else:
        return self._build_service_spec(name, image, service_config)

def _build_service_spec(self, name: str, image: str,
                        config: ServiceConfig) -> dict:
    """Build service spec with HTTP API."""
    return {
        "name": name,
        "region": self._region,
        "services": [{
            "name": "sandbox",
            "image": {
                "registry_type": "GHCR",
                "registry": self._registry,
                "repository": f"sandbox-{image}-service",  # Service variant
                "tag": "latest"
            },
            "instance_size_slug": self._instance_size,
            "instance_count": 1,
            "http_port": config.api_port,
            "envs": [
                {
                    "key": "SANDBOX_API_TOKEN",
                    "scope": "RUN_TIME",
                    "type": "SECRET",
                    "value": config.token or secrets.token_urlsafe(32)
                },
                {
                    "key": "SANDBOX_MODE",
                    "scope": "RUN_TIME",
                    "value": "service"
                },
                {
                    "key": "PROXY_PORTS",
                    "scope": "RUN_TIME",
                    "value": ",".join(str(p) for p in config.proxy_ports)
                }
            ],
            "health_check": {
                "http_path": "/health",
                "initial_delay_seconds": 10,
                "period_seconds": 10
            }
        }]
    }
```

### SDK Client for Service Mode

```python
# New file: service_client.py
import httpx
from typing import AsyncGenerator, Generator

class SandboxServiceClient:
    """HTTP client for service-mode sandboxes."""

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip('/')
        self._token = token
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0
        )

    def exec(self, command: str, env: dict = None,
             cwd: str = None, timeout: int = 120) -> CommandResult:
        """Execute command and return result."""
        response = self._client.post("/api/exec", json={
            "command": command,
            "env": env,
            "cwd": cwd,
            "timeout": timeout
        })
        response.raise_for_status()
        data = response.json()
        return CommandResult(
            stdout=data["stdout"],
            stderr=data["stderr"],
            exit_code=data["exit_code"]
        )

    def exec_stream(self, command: str, **kwargs) -> Generator[StreamEvent, None, None]:
        """Execute command with streaming output via SSE."""
        with self._client.stream("POST", "/api/exec/stream", json={
            "command": command, **kwargs
        }) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    yield StreamEvent(
                        type=data["type"],
                        data=data.get("line", ""),
                        timestamp=data["timestamp"]
                    )

class AsyncSandboxServiceClient:
    """Async HTTP client for service-mode sandboxes."""

    async def exec_stream(self, command: str, **kwargs) -> AsyncGenerator[StreamEvent, None]:
        """Async streaming execution."""
        async with self._client.stream("POST", "/api/exec/stream", json={
            "command": command, **kwargs
        }) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    yield StreamEvent(
                        type=data["type"],
                        data=data.get("line", ""),
                        timestamp=data["timestamp"]
                    )
```

### Files to Create/Modify

| File | Changes |
|------|---------|
| `types.py` | Add `SandboxMode`, `ServiceConfig`, `StreamEvent` |
| `deployer.py` | Add service spec builder |
| `service_client.py` | **NEW**: HTTP client for service mode |
| `sandbox.py` | Add mode selection, integrate service client |
| `async_sandbox.py` | Add async service client integration |

---

## 2. Container Image: Service Variant

### Goal
Create sandbox container images with built-in HTTP API and reverse proxy.

### Dockerfile Structure

```dockerfile
# sandbox-python-service/Dockerfile
FROM ghcr.io/bikramkgupta/sandbox-python:latest

# Install API server dependencies
RUN pip install fastapi uvicorn[standard] httpx

# Install Caddy for reverse proxy
RUN apt-get update && apt-get install -y caddy && rm -rf /var/lib/apt/lists/*

# Copy API server
COPY sandbox_api/ /opt/sandbox_api/
COPY Caddyfile /etc/caddy/Caddyfile
COPY entrypoint.sh /entrypoint.sh

ENV SANDBOX_MODE=service
ENV SANDBOX_API_PORT=8080

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
```

### API Server Implementation

```python
# sandbox_api/main.py
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import subprocess
import asyncio
import os
import pty
import select

app = FastAPI()

SANDBOX_TOKEN = os.environ.get("SANDBOX_API_TOKEN", "")

async def verify_token(authorization: str = Header(...)):
    """Verify bearer token."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")
    token = authorization[7:]
    if token != SANDBOX_TOKEN:
        raise HTTPException(403, "Invalid token")

class ExecRequest(BaseModel):
    command: str
    env: dict = None
    cwd: str = "/workspace"
    timeout: int = 120

class ExecResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/exec", response_model=ExecResult)
async def exec_command(req: ExecRequest, _=Depends(verify_token)):
    """Execute command and return result."""
    env = os.environ.copy()
    if req.env:
        env.update(req.env)

    proc = await asyncio.create_subprocess_shell(
        req.command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=req.cwd,
        env=env
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=req.timeout
        )
        return ExecResult(
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            exit_code=proc.returncode
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(408, "Command timed out")

@app.post("/api/exec/stream")
async def exec_stream(req: ExecRequest, _=Depends(verify_token)):
    """Execute command with SSE streaming output."""

    async def generate():
        import time
        env = os.environ.copy()
        if req.env:
            env.update(req.env)

        proc = await asyncio.create_subprocess_shell(
            req.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=req.cwd,
            env=env
        )

        async def read_stream(stream, stream_type):
            while True:
                line = await stream.readline()
                if not line:
                    break
                yield f"event: {stream_type}\ndata: {json.dumps({'line': line.decode(), 'timestamp': time.time()})}\n\n"

        # Merge stdout and stderr streams
        import json

        stdout_task = asyncio.create_task(read_stream(proc.stdout, "stdout").__anext__())
        stderr_task = asyncio.create_task(read_stream(proc.stderr, "stderr").__anext__())

        pending = {stdout_task, stderr_task}

        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    result = task.result()
                    yield result
                    # Restart the task
                    if task == stdout_task and proc.stdout:
                        stdout_task = asyncio.create_task(read_stream(proc.stdout, "stdout").__anext__())
                        pending.add(stdout_task)
                    elif task == stderr_task and proc.stderr:
                        stderr_task = asyncio.create_task(read_stream(proc.stderr, "stderr").__anext__())
                        pending.add(stderr_task)
                except StopAsyncIteration:
                    pass

        await proc.wait()
        yield f"event: exit\ndata: {json.dumps({'code': proc.returncode, 'timestamp': time.time()})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

### Caddyfile for Reverse Proxy

```caddyfile
# /etc/caddy/Caddyfile
{
    auto_https off
}

:8080 {
    # Health check (no auth)
    handle /health {
        reverse_proxy localhost:8000
    }

    # API endpoints
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Dynamic port proxy: /proxy/3000/* → localhost:3000/*
    handle /proxy/* {
        uri strip_prefix /proxy
        # Extract port from path and proxy
        reverse_proxy {
            to localhost:{http.request.uri.path.0}
            header_up Host {http.reverse_proxy.upstream.hostport}
        }
    }

    # Default: proxy to primary user port
    handle {
        reverse_proxy localhost:3000
    }
}
```

### Entrypoint Script

```bash
#!/bin/bash
# /entrypoint.sh

# Start the sandbox API server
cd /opt/sandbox_api
uvicorn main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

# Start Caddy reverse proxy
caddy run --config /etc/caddy/Caddyfile &
CADDY_PID=$!

# Wait for both to be ready
sleep 2

# Keep container running
wait $API_PID $CADDY_PID
```

---

## 3. Streaming Command Execution (`exec_stream`)

### Goal
Enable real-time streaming of command output via HTTP/2 SSE.

### Design (Updated for Service Mode)

```python
# In sandbox.py
class Sandbox:
    def exec_stream(
        self,
        command: str,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: int = 120
    ) -> Generator[StreamEvent, None, CommandResult]:
        """Execute command with streaming output.

        Note: Requires service mode. Falls back to buffered exec in worker mode.

        Usage:
            for event in sandbox.exec_stream("npm run build"):
                if event.type == "stdout":
                    print(event.data, end="")
        """
        if self._mode == SandboxMode.SERVICE:
            return self._service_client.exec_stream(command, env=env, cwd=cwd, timeout=timeout)
        else:
            # Worker mode fallback: execute and yield single event
            result = self.exec(command, env=env, cwd=cwd, timeout=timeout)
            yield StreamEvent(type="stdout", data=result.stdout, timestamp=time.time())
            if result.stderr:
                yield StreamEvent(type="stderr", data=result.stderr, timestamp=time.time())
            yield StreamEvent(type="exit", data=str(result.exit_code), timestamp=time.time())
```

### Types

```python
# In types.py
@dataclass
class StreamEvent:
    """A single streaming output event."""
    type: Literal["stdout", "stderr", "exit", "error"]
    data: str
    timestamp: float

    @property
    def is_output(self) -> bool:
        return self.type in ("stdout", "stderr")

    @property
    def is_complete(self) -> bool:
        return self.type in ("exit", "error")
```

---

## 4. Process Logs API

### Goal
Access stdout/stderr from background processes.

### Design

```python
# API endpoints in container
GET /api/processes/{pid}/logs?tail=100      → Last 100 lines
GET /api/processes/{pid}/logs/stream        → SSE stream (tail -f)

# SDK methods
class Sandbox:
    def get_process_logs(
        self,
        pid: int,
        tail: Optional[int] = None
    ) -> str:
        """Get logs from a background process."""
        if self._mode == SandboxMode.SERVICE:
            params = {"tail": tail} if tail else {}
            response = self._service_client.get(f"/api/processes/{pid}/logs", params=params)
            return response.text
        else:
            # Worker mode: read from tracked log file
            log_file = self._process_manager._pid_to_logfile.get(pid)
            if not log_file:
                raise ValueError(f"No log file tracked for PID {pid}")
            cmd = f"tail -n {tail} {log_file}" if tail else f"cat {log_file}"
            return self.exec(cmd).stdout

    def stream_process_logs(
        self,
        pid: int
    ) -> Generator[str, None, None]:
        """Stream logs from a background process."""
        if self._mode == SandboxMode.SERVICE:
            for event in self._service_client.stream_get(f"/api/processes/{pid}/logs/stream"):
                yield event.data
        else:
            raise NotImplementedError("Log streaming requires service mode")
```

---

## 5. Sessions API

### Goal
Isolated execution contexts with persistent shell state.

### Design

```python
# API endpoints in container
POST   /api/sessions                → Create session
GET    /api/sessions/{id}           → Get session info
POST   /api/sessions/{id}/exec      → Execute in session
POST   /api/sessions/{id}/exec/stream → Stream execute in session
POST   /api/sessions/{id}/env       → Set environment variable
DELETE /api/sessions/{id}           → Close session

# Container-side session management
class SessionManager:
    """Manages shell sessions inside the container."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, session_id: str, env: dict = None, cwd: str = "/workspace") -> Session:
        """Create a new session with persistent shell."""
        import pty
        master, slave = pty.openpty()

        proc = subprocess.Popen(
            ["/bin/bash", "-i"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env={**os.environ, **(env or {})}
        )

        session = Session(
            id=session_id,
            pid=proc.pid,
            master_fd=master,
            env=env or {},
            cwd=cwd
        )
        self._sessions[session_id] = session
        return session

    def exec_in_session(self, session_id: str, command: str) -> str:
        """Execute command in session's shell."""
        session = self._sessions[session_id]
        # Write command to PTY master
        os.write(session.master_fd, f"{command}\n".encode())
        # Read output...

# SDK methods
class Sandbox:
    def create_session(
        self,
        session_id: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace"
    ) -> "Session":
        """Create an isolated execution session."""
        if self._mode == SandboxMode.SERVICE:
            response = self._service_client.post("/api/sessions", json={
                "session_id": session_id,
                "env": env,
                "cwd": cwd
            })
            return Session(self, session_id)
        else:
            raise NotImplementedError("Sessions require service mode")

class Session:
    """An isolated execution context within a sandbox."""

    def __init__(self, sandbox: Sandbox, session_id: str):
        self._sandbox = sandbox
        self.id = session_id

    def exec(self, command: str, timeout: int = 120) -> CommandResult:
        """Execute command in this session."""
        return self._sandbox._service_client.post(
            f"/api/sessions/{self.id}/exec",
            json={"command": command, "timeout": timeout}
        )

    def exec_stream(self, command: str) -> Generator[StreamEvent, None, None]:
        """Stream command output in this session."""
        return self._sandbox._service_client.stream_post(
            f"/api/sessions/{self.id}/exec/stream",
            json={"command": command}
        )

    def set_env(self, key: str, value: str) -> None:
        """Set environment variable for this session."""
        self._sandbox._service_client.post(
            f"/api/sessions/{self.id}/env",
            json={"key": key, "value": value}
        )

    def close(self) -> None:
        """Close this session."""
        self._sandbox._service_client.delete(f"/api/sessions/{self.id}")
```

---

## 6. Port Exposure / Preview URLs

### Goal
Dynamic port exposure with public URLs via internal reverse proxy.

### Design

```python
# Caddy handles routing: /proxy/{port}/* → localhost:{port}

# SDK methods
class Sandbox:
    def expose_port(self, port: int) -> ExposedPort:
        """Get public URL for an internal port.

        The port must be running a server inside the sandbox.
        Uses internal Caddy proxy for routing.
        """
        if self._mode != SandboxMode.SERVICE:
            raise NotImplementedError("Port exposure requires service mode")

        base_url = self.get_url()  # https://app-xxx.ondigitalocean.app
        proxy_url = f"{base_url}/proxy/{port}"

        return ExposedPort(
            port=port,
            url=proxy_url,
            protocol="https",
            created_at=time.time()
        )

    def get_exposed_ports(self) -> List[ExposedPort]:
        """List configured proxy ports."""
        return [
            ExposedPort(port=p, url=f"{self.get_url()}/proxy/{p}",
                       protocol="https", created_at=0)
            for p in self._service_config.proxy_ports
        ]

# Types
@dataclass
class ExposedPort:
    port: int
    url: str
    protocol: Literal["http", "https"]
    created_at: float
```

### Usage

```python
# Start a server in the sandbox
sandbox.exec("cd /workspace && npm start &")  # Starts on port 3000

# Get preview URL
port_info = sandbox.expose_port(3000)
print(f"Preview: {port_info.url}")  # https://app-xxx.ondigitalocean.app/proxy/3000

# WebSocket also works through the proxy
ws_url = port_info.url.replace("https://", "wss://")
```

---

## 7. Snapshot/Restore API

### Goal
Save and restore sandbox filesystem state to DO Spaces for rapid startup.

### Design

```python
# In snapshot.py
@dataclass
class SnapshotMetadata:
    """Metadata about a saved snapshot."""
    snapshot_id: str
    created_at: float
    sandbox_image: str
    size_bytes: int
    paths: List[str]
    description: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

class SnapshotManager:
    """Manages sandbox snapshots in DO Spaces."""

    def __init__(self, spaces_config: SpacesConfig):
        self._spaces = SpacesClient(spaces_config)
        self._prefix = "snapshots/"

    def create_snapshot(
        self,
        sandbox: Sandbox,
        snapshot_id: Optional[str] = None,
        paths: List[str] = None,
        exclude_patterns: List[str] = None,
        description: str = None,
        tags: Dict[str, str] = None
    ) -> SnapshotMetadata:
        """Create a snapshot of sandbox filesystem."""
        snapshot_id = snapshot_id or f"snap-{uuid.uuid4().hex[:12]}"
        paths = paths or ["/workspace"]
        exclude_patterns = exclude_patterns or [
            "*.pyc", "__pycache__", ".git/objects",
            "node_modules/.cache", "*.log", ".env"
        ]

        # Build tar command
        excludes = " ".join(f"--exclude='{p}'" for p in exclude_patterns)
        paths_str = " ".join(paths)
        archive = f"/tmp/snapshot_{snapshot_id}.tar.gz"

        result = sandbox.exec(
            f"tar {excludes} -czf {archive} -C / {paths_str}",
            timeout=600
        )
        if not result.success:
            raise SnapshotError(f"Failed to create archive: {result.stderr}")

        # Get size
        size_result = sandbox.exec(f"stat -c %s {archive}")
        size_bytes = int(size_result.stdout.strip())

        # Upload via presigned URL
        spaces_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
        upload_url = self._spaces.generate_presigned_upload_url(spaces_key)
        sandbox.exec(f"curl -X PUT -T {archive} '{upload_url}'", timeout=600)

        # Save metadata
        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            created_at=time.time(),
            sandbox_image=sandbox._image,
            size_bytes=size_bytes,
            paths=paths,
            description=description,
            tags=tags or {}
        )
        self._save_metadata(metadata)

        # Cleanup
        sandbox.exec(f"rm -f {archive}")

        return metadata

    def restore_snapshot(
        self,
        sandbox: Sandbox,
        snapshot_id: str,
        target_path: str = "/"
    ) -> bool:
        """Restore a snapshot to sandbox."""
        metadata = self.get_snapshot(snapshot_id)
        if not metadata:
            raise SnapshotNotFoundError(snapshot_id)

        # Download via presigned URL
        spaces_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
        download_url = self._spaces.generate_presigned_download_url(spaces_key)
        archive = f"/tmp/restore_{snapshot_id}.tar.gz"

        sandbox.exec(f"curl -sSfL -o {archive} '{download_url}'", timeout=600)

        # Extract
        result = sandbox.exec(f"tar -xzf {archive} -C {target_path}", timeout=600)

        # Cleanup
        sandbox.exec(f"rm -f {archive}")

        return result.success
```

### Pool Integration

```python
# In manager.py
class SandboxManager:
    async def acquire_with_snapshot(
        self,
        image: str,
        snapshot_id: str,
        timeout: float = 300
    ) -> Sandbox:
        """Acquire sandbox and restore snapshot for rapid startup."""
        # Get pre-warmed sandbox from pool
        sandbox = await self.acquire(image, timeout=timeout)

        # Restore snapshot
        snapshot_mgr = SnapshotManager(self._spaces_config)
        snapshot_mgr.restore_snapshot(sandbox, snapshot_id)

        return sandbox
```

### Storage Layout

```
spaces-bucket/
├── snapshots/
│   ├── snap-abc123/
│   │   ├── metadata.json
│   │   └── archive.tar.gz
│   └── snap-xyz789/
│       ├── metadata.json
│       └── archive.tar.gz
```

---

## 8. Auto-Sleep / Hibernate

### Goal
Reduce costs by hibernating idle sandboxes, with automatic wake on access.

### Design

```python
# In types.py
@dataclass
class HibernationConfig:
    enabled: bool = True
    idle_timeout: int = 600  # 10 minutes
    wake_on_access: bool = True

class SandboxState(Enum):
    CREATING = "creating"
    ACTIVE = "active"
    HIBERNATED = "hibernated"
    DELETED = "deleted"

# In sandbox.py
class Sandbox:
    def hibernate(self) -> bool:
        """Hibernate sandbox: snapshot state and scale to 0."""
        if self._state != SandboxState.ACTIVE:
            return False

        # Create hibernation snapshot
        snapshot_id = f"hibernate-{self.app_id}"
        self.create_snapshot(
            snapshot_id=snapshot_id,
            paths=["/workspace", "/home", "/tmp"],
            tags={"type": "hibernation"}
        )

        # Scale to 0 instances
        self._deployer.scale(self.app_id, instances=0)

        self._state = SandboxState.HIBERNATED
        return True

    def wake(self, timeout: int = 120) -> bool:
        """Wake hibernated sandbox: scale up and restore state."""
        if self._state != SandboxState.HIBERNATED:
            return self._state == SandboxState.ACTIVE

        # Scale up
        self._deployer.scale(self.app_id, instances=1)
        self.wait_ready(timeout=timeout)

        # Restore state
        snapshot_id = f"hibernate-{self.app_id}"
        self.restore_snapshot(snapshot_id)

        self._state = SandboxState.ACTIVE
        return True

    def _ensure_awake(self):
        """Auto-wake if hibernated (called before operations)."""
        if self._state == SandboxState.HIBERNATED and self._hibernation_config.wake_on_access:
            self.wake()

# In deployer.py
def scale(self, app_id: str, instances: int) -> bool:
    """Scale app to specified instance count."""
    # Get current spec
    result = subprocess.run(
        ["doctl", "apps", "get", app_id, "--output", "json"],
        capture_output=True, text=True
    )
    spec = json.loads(result.stdout)["spec"]

    # Update instance count
    if "services" in spec:
        spec["services"][0]["instance_count"] = instances
    elif "workers" in spec:
        spec["workers"][0]["instance_count"] = instances

    # Update app
    # ... doctl apps update ...
```

---

## 9. Git Checkout Convenience Method

### Goal
Simple git clone without manual exec calls.

### Implementation

```python
# In sandbox.py
@dataclass
class GitCredentials:
    username: Optional[str] = None
    token: Optional[str] = None      # PAT for HTTPS
    ssh_key: Optional[str] = None    # Private key content

class Sandbox:
    def git_checkout(
        self,
        url: str,
        path: str = "/workspace",
        branch: Optional[str] = None,
        depth: int = 1,
        credentials: Optional[GitCredentials] = None
    ) -> CommandResult:
        """Clone a git repository."""
        cmd = ["git", "clone"]

        if depth:
            cmd.extend(["--depth", str(depth)])
        if branch:
            cmd.extend(["--branch", branch])

        # Handle authentication
        clone_url = url
        if credentials:
            if credentials.ssh_key:
                # Write key and use SSH
                self.filesystem.write_file("/tmp/git_key", credentials.ssh_key, mode="600")
                env = {"GIT_SSH_COMMAND": "ssh -i /tmp/git_key -o StrictHostKeyChecking=no"}
            elif credentials.token:
                # Embed token in HTTPS URL
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(url)
                auth = f"{credentials.username or 'git'}:{credentials.token}"
                clone_url = urlunparse(parsed._replace(netloc=f"{auth}@{parsed.netloc}"))
                env = None
        else:
            env = None

        cmd.extend([clone_url, path])

        result = self.exec(" ".join(cmd), env=env)

        # Cleanup
        if credentials and credentials.ssh_key:
            self.exec("rm -f /tmp/git_key")

        return result
```

---

## Implementation Order

### Phase 1: Foundation
1. **Types & Service Mode** - Add `SandboxMode`, `ServiceConfig`, `StreamEvent`
2. **Deployer Updates** - Service spec generation with token
3. **Service Client** - HTTP/SSE client for service mode
4. **Container Image** - FastAPI + Caddy service variant

### Phase 2: Core Features
5. **exec_stream()** - Streaming execution via SSE
6. **Process Logs API** - Log retrieval and streaming
7. **Port Exposure** - Caddy proxy integration

### Phase 3: Advanced
8. **Sessions API** - Isolated execution contexts
9. **Snapshot/Restore** - Spaces-backed state persistence
10. **Hibernate/Wake** - Cost optimization

### Phase 4: Polish
11. **git_checkout()** - Convenience method
12. **Pool Integration** - `acquire_with_snapshot()`
13. **Documentation & Tests**

---

## Files Summary

| File | Status | Description |
|------|--------|-------------|
| `types.py` | Modify | Add SandboxMode, ServiceConfig, StreamEvent, etc. |
| `deployer.py` | Modify | Add service spec, scale() method |
| `service_client.py` | **NEW** | HTTP/SSE client for service mode |
| `snapshot.py` | **NEW** | Snapshot manager |
| `sandbox.py` | Modify | Integrate service mode, add new methods |
| `async_sandbox.py` | Modify | Async service client |
| `manager.py` | Modify | Add acquire_with_snapshot() |
| `exceptions.py` | Modify | Add SnapshotError |
| `container/` | **NEW** | Service container image (Dockerfile, API, Caddy) |

---

## Usage Examples

```python
# Basic worker mode (default, unchanged)
sandbox = Sandbox.create(image="python")
result = sandbox.exec("python script.py")

# Service mode with streaming
sandbox = Sandbox.create(
    image="python",
    mode=SandboxMode.SERVICE,
    service_config=ServiceConfig(proxy_ports=[3000, 8000])
)

# Stream command output
for event in sandbox.exec_stream("pip install -r requirements.txt"):
    print(event.data, end="", flush=True)

# Start server and get preview URL
sandbox.exec("python -m http.server 3000 &")
port_info = sandbox.expose_port(3000)
print(f"Preview: {port_info.url}")

# Sessions for isolated contexts
dev_session = sandbox.create_session("dev", env={"DEBUG": "1"})
dev_session.exec("npm run dev")

test_session = sandbox.create_session("test", env={"NODE_ENV": "test"})
test_session.exec("npm test")

# Snapshot and restore for rapid startup
meta = sandbox.create_snapshot(description="deps installed")

# Later: rapid startup with pre-warmed pool + snapshot
manager = SandboxManager(...)
sandbox = await manager.acquire_with_snapshot("python", meta.snapshot_id)
# Ready in seconds with all dependencies!

# Hibernate idle sandbox
sandbox.hibernate()  # Saves state, scales to 0
# ... later ...
sandbox.wake()  # Scales up, restores state
```

This architecture leverages App Platform's native HTTP/2 capabilities for streaming while maintaining backward compatibility with worker mode for simple use cases.
