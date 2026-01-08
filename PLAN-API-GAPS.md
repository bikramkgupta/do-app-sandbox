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
| 🔴 Critical | Port Exposure / Preview URLs | Medium | FastAPI reverse proxy |
| 🔴 Critical | Auto-sleep / Hibernate | Medium | Snapshot + delete sandbox |
| 🟠 High | Process Logs API | Low | HTTP streaming endpoint |
| 🟠 High | Sessions API | Medium | Server-side session management |
| 🟠 High | `git_checkout()` | Low | Convenience wrapper |
| 🟢 New | Snapshot/Restore API | Medium | Spaces-backed tar archives |

---

## Architecture: Service Mode with HTTP API

### Container Components (Service Mode)

```
┌─────────────────────────────────────────────────────────────┐
│              Sandbox Container (Service Mode)                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Sandbox API (FastAPI + uvicorn)                        ││
│  │  Port 8080 (App Platform ingress)                       ││
│  │                                                          ││
│  │  Routes:                                                 ││
│  │  - /health          → Health check (no auth)            ││
│  │  - /api/*           → Sandbox API (auth required)       ││
│  │  - /proxy/{port}/*  → Reverse proxy to localhost:port   ││
│  └─────────────────────────────────────────────────────────┘│
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  User Processes                                         ││
│  │  - python app.py (port 3000)                            ││
│  │  - npm start (port 5000)                                ││
│  │  - etc.                                                 ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**No Caddy needed** - FastAPI handles both API and port proxying directly via `httpx`.

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

# Port Proxy (handled by FastAPI)
ANY  /proxy/{port}/{path:path}            → Proxied to localhost:{port}/{path}
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

## Container Images

### Base Image Strategy

| Image | Base | Runtime | Package Manager | Tools |
|-------|------|---------|-----------------|-------|
| `sandbox-python` | Debian slim | Python 3.12 | **uv** (default), pip | git, curl, build-essential |
| `sandbox-node` | Debian slim | **Bun** (default), Node 22 | **bun** (default), npm, yarn | git, curl |

### Why uv for Python?

- **10-100x faster** than pip for package installation
- Drop-in pip replacement: `uv pip install`
- Virtual environment management: `uv venv`
- Rust-based, single binary
- Still supports pip for compatibility

### Why Bun for Node?

- **Faster runtime** than Node.js for many workloads
- **Faster package installs** than npm/yarn
- Built-in TypeScript support
- Compatible with npm packages
- Node.js still available for compatibility

### Python Service Image

```dockerfile
# images/sandbox-python-service/Dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Install sandbox API dependencies
RUN uv pip install --system fastapi uvicorn[standard] httpx

# Copy sandbox API server
COPY sandbox_api/ /opt/sandbox_api/

# Create workspace
RUN mkdir -p /workspace
WORKDIR /workspace

ENV SANDBOX_MODE=service
ENV PATH="/root/.cargo/bin:$PATH"

EXPOSE 8080

CMD ["uvicorn", "sandbox_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Node Service Image

```dockerfile
# images/sandbox-node-service/Dockerfile
FROM oven/bun:1-slim

# Install Node.js for compatibility
RUN apt-get update && apt-get install -y \
    git curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Install sandbox API (Python-based, or could be Bun-based)
# Option A: Python API server
RUN apt-get update && apt-get install -y python3 python3-pip \
    && pip3 install fastapi uvicorn httpx \
    && rm -rf /var/lib/apt/lists/*

COPY sandbox_api/ /opt/sandbox_api/

# Create workspace
RUN mkdir -p /workspace
WORKDIR /workspace

ENV SANDBOX_MODE=service

EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "sandbox_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Worker Images (No API Server)

```dockerfile
# images/sandbox-python-worker/Dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

RUN mkdir -p /workspace
WORKDIR /workspace

# Keep container running for doctl console access
CMD ["tail", "-f", "/dev/null"]
```

```dockerfile
# images/sandbox-node-worker/Dockerfile
FROM oven/bun:1-slim

RUN apt-get update && apt-get install -y \
    git curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /workspace
WORKDIR /workspace

CMD ["tail", "-f", "/dev/null"]
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
    token = config.token or secrets.token_urlsafe(32)

    return {
        "name": name,
        "region": self._region,
        "services": [{
            "name": "sandbox",
            "image": {
                "registry_type": "GHCR",
                "registry": self._registry,
                "repository": f"sandbox-{image}-service",
                "tag": "latest"
            },
            "instance_size_slug": self._instance_size,
            "instance_count": 1,
            "http_port": config.api_port,
            "protocol": "HTTP2",  # For SSE streaming
            "envs": [
                {
                    "key": "SANDBOX_API_TOKEN",
                    "scope": "RUN_TIME",
                    "type": "SECRET",
                    "value": token
                },
                {
                    "key": "SANDBOX_MODE",
                    "scope": "RUN_TIME",
                    "value": "service"
                }
            ],
            "health_check": {
                "http_path": "/health",
                "initial_delay_seconds": 5,
                "period_seconds": 10
            }
        }]
    }, token  # Return token for SDK to store
```

### SDK Client for Service Mode

```python
# New file: service_client.py
import httpx
import json
from typing import AsyncGenerator, Generator

class SandboxServiceClient:
    """HTTP client for service-mode sandboxes."""

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip('/')
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}

    def exec(self, command: str, env: dict = None,
             cwd: str = None, timeout: int = 120) -> CommandResult:
        """Execute command and return result."""
        with httpx.Client(timeout=timeout + 10) as client:
            response = client.post(
                f"{self._base_url}/api/exec",
                json={"command": command, "env": env, "cwd": cwd, "timeout": timeout},
                headers=self._headers
            )
            response.raise_for_status()
            data = response.json()
            return CommandResult(
                stdout=data["stdout"],
                stderr=data["stderr"],
                exit_code=data["exit_code"]
            )

    def exec_stream(self, command: str, **kwargs) -> Generator[StreamEvent, None, None]:
        """Execute command with streaming output via SSE."""
        with httpx.Client(timeout=None) as client:
            with client.stream(
                "POST",
                f"{self._base_url}/api/exec/stream",
                json={"command": command, **kwargs},
                headers=self._headers
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        yield StreamEvent(
                            type=event_type,
                            data=data.get("line", ""),
                            timestamp=data.get("timestamp", 0)
                        )

class AsyncSandboxServiceClient:
    """Async HTTP client for service-mode sandboxes."""

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip('/')
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}

    async def exec_stream(self, command: str, **kwargs) -> AsyncGenerator[StreamEvent, None]:
        """Async streaming execution."""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/exec/stream",
                json={"command": command, **kwargs},
                headers=self._headers
            ) as response:
                event_type = "stdout"
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        yield StreamEvent(
                            type=event_type,
                            data=data.get("line", ""),
                            timestamp=data.get("timestamp", 0)
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

## 2. Sandbox API Server (Container)

### Goal
FastAPI server running inside service containers, handling all API requests including port proxying.

### Implementation

```python
# sandbox_api/main.py
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import subprocess
import asyncio
import httpx
import os
import json
import time

app = FastAPI(title="Sandbox API")

SANDBOX_TOKEN = os.environ.get("SANDBOX_API_TOKEN", "")

# =============================================================================
# Authentication
# =============================================================================

async def verify_token(authorization: str = Header(None)):
    """Verify bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")
    token = authorization[7:]
    if token != SANDBOX_TOKEN:
        raise HTTPException(403, "Invalid token")

# =============================================================================
# Health Check (no auth)
# =============================================================================

@app.get("/health")
async def health():
    return {"status": "ok", "mode": "service"}

# =============================================================================
# Command Execution
# =============================================================================

class ExecRequest(BaseModel):
    command: str
    env: dict = None
    cwd: str = "/workspace"
    timeout: int = 120

class ExecResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int

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
            stdout=stdout.decode(errors='replace'),
            stderr=stderr.decode(errors='replace'),
            exit_code=proc.returncode or 0
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(408, "Command timed out")

@app.post("/api/exec/stream")
async def exec_stream(req: ExecRequest, _=Depends(verify_token)):
    """Execute command with SSE streaming output."""

    async def generate():
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
            """Read lines from stream and yield SSE events."""
            while True:
                line = await stream.readline()
                if not line:
                    break
                yield f"event: {stream_type}\ndata: {json.dumps({'line': line.decode(errors='replace'), 'timestamp': time.time()})}\n\n"

        # Read both streams concurrently
        stdout_gen = read_stream(proc.stdout, "stdout")
        stderr_gen = read_stream(proc.stderr, "stderr")

        async def merged_streams():
            """Merge stdout and stderr streams."""
            tasks = {
                asyncio.create_task(stdout_gen.__anext__()): "stdout",
                asyncio.create_task(stderr_gen.__anext__()): "stderr"
            }

            while tasks:
                done, _ = await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED)

                for task in done:
                    stream_name = tasks.pop(task)
                    try:
                        result = task.result()
                        yield result
                        # Schedule next read from same stream
                        gen = stdout_gen if stream_name == "stdout" else stderr_gen
                        new_task = asyncio.create_task(gen.__anext__())
                        tasks[new_task] = stream_name
                    except StopAsyncIteration:
                        pass  # Stream finished

        async for event in merged_streams():
            yield event

        await proc.wait()
        yield f"event: exit\ndata: {json.dumps({'code': proc.returncode, 'timestamp': time.time()})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# =============================================================================
# Port Proxy (replaces Caddy)
# =============================================================================

@app.api_route("/proxy/{port}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_port(port: int, path: str, request: Request, _=Depends(verify_token)):
    """Proxy requests to internal port."""
    target_url = f"http://localhost:{port}/{path}"

    # Forward query string
    if request.url.query:
        target_url += f"?{request.url.query}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Forward the request
            response = await client.request(
                method=request.method,
                url=target_url,
                headers={k: v for k, v in request.headers.items()
                        if k.lower() not in ('host', 'authorization')},
                content=await request.body()
            )

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except httpx.ConnectError:
            raise HTTPException(502, f"Cannot connect to port {port}")
        except httpx.TimeoutException:
            raise HTTPException(504, f"Timeout connecting to port {port}")

# =============================================================================
# Process Management
# =============================================================================

# Process tracking
_processes: dict = {}  # pid -> {"command": str, "log_file": str}

class BackgroundExecRequest(BaseModel):
    command: str
    cwd: str = "/workspace"
    env: dict = None

@app.post("/api/exec/background")
async def exec_background(req: BackgroundExecRequest, _=Depends(verify_token)):
    """Start a background process."""
    import uuid
    log_file = f"/tmp/proc_{uuid.uuid4().hex[:8]}.log"

    env = os.environ.copy()
    if req.env:
        env.update(req.env)

    # Start process with nohup, redirect output to log file
    full_cmd = f"nohup {req.command} > {log_file} 2>&1 & echo $!"

    proc = await asyncio.create_subprocess_shell(
        full_cmd,
        stdout=asyncio.subprocess.PIPE,
        cwd=req.cwd,
        env=env
    )
    stdout, _ = await proc.communicate()
    pid = int(stdout.decode().strip())

    _processes[pid] = {"command": req.command, "log_file": log_file}

    return {"pid": pid, "log_file": log_file}

@app.get("/api/processes")
async def list_processes(_=Depends(verify_token)):
    """List tracked background processes."""
    result = []
    for pid, info in list(_processes.items()):
        # Check if still running
        try:
            os.kill(pid, 0)
            status = "running"
        except OSError:
            status = "stopped"

        result.append({
            "pid": pid,
            "command": info["command"],
            "status": status,
            "log_file": info["log_file"]
        })
    return result

@app.get("/api/processes/{pid}/logs")
async def get_process_logs(pid: int, tail: int = None, _=Depends(verify_token)):
    """Get logs from a background process."""
    if pid not in _processes:
        raise HTTPException(404, f"Process {pid} not tracked")

    log_file = _processes[pid]["log_file"]

    if tail:
        proc = await asyncio.create_subprocess_shell(
            f"tail -n {tail} {log_file}",
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return {"logs": stdout.decode(errors='replace')}
    else:
        try:
            with open(log_file, 'r') as f:
                return {"logs": f.read()}
        except FileNotFoundError:
            return {"logs": ""}

@app.get("/api/processes/{pid}/logs/stream")
async def stream_process_logs(pid: int, _=Depends(verify_token)):
    """Stream logs from a background process (tail -f)."""
    if pid not in _processes:
        raise HTTPException(404, f"Process {pid} not tracked")

    log_file = _processes[pid]["log_file"]

    async def generate():
        proc = await asyncio.create_subprocess_shell(
            f"tail -f {log_file}",
            stdout=asyncio.subprocess.PIPE
        )

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield f"data: {json.dumps({'line': line.decode(errors='replace'), 'timestamp': time.time()})}\n\n"
        finally:
            proc.kill()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@app.post("/api/processes/{pid}/kill")
async def kill_process(pid: int, signal: int = 15, _=Depends(verify_token)):
    """Kill a background process."""
    try:
        os.kill(pid, signal)
        return {"success": True}
    except OSError as e:
        raise HTTPException(400, f"Failed to kill process: {e}")
```

---

## 3. Hibernate: Snapshot + Delete (Cloudflare-aligned)

### Goal
Cost-effective hibernation by snapshotting state and deleting the sandbox entirely.

### Hibernate Conditions (Activity Tracking)

**Activity = any of these keeps sandbox AWAKE:**

| Activity Type | Resets Idle Timer |
|--------------|-------------------|
| `exec()` / `exec_stream()` | Yes |
| Active SSE connections (log streaming) | Yes (keeps awake while open) |
| HTTP requests to `/proxy/*` | Yes |
| File operations | Yes |
| Session operations | Yes |

**Sandbox sleeps when:**
1. No activity for `sleep_after` seconds (default: 600 = 10 min)
2. No active SSE streams open
3. User explicitly calls `sandbox.hibernate()`

### Design

```python
# In types.py
@dataclass
class HibernationConfig:
    """Configuration for sandbox hibernation (Cloudflare-aligned)."""
    enabled: bool = True
    sleep_after: int = 600  # Seconds of inactivity before hibernate
    # Like Cloudflare's sleepAfter: "10m"

class SandboxState(Enum):
    """Sandbox lifecycle states."""
    CREATING = "creating"
    ACTIVE = "active"
    HIBERNATED = "hibernated"  # Snapshot exists, sandbox deleted
    DELETED = "deleted"

@dataclass
class HibernatedSandbox:
    """Reference to a hibernated sandbox."""
    snapshot_id: str
    image: str
    mode: SandboxMode
    service_config: Optional[ServiceConfig]
    hibernated_at: float
    metadata: Dict[str, Any]  # User-defined metadata

# In sandbox.py
class Sandbox:
    _last_activity: float
    _active_streams: int = 0
    _hibernation_config: HibernationConfig
    _state: SandboxState

    def _record_activity(self):
        """Record activity to reset idle timer."""
        self._last_activity = time.time()

    def _is_idle(self) -> bool:
        """Check if sandbox is idle (ready to hibernate)."""
        if self._active_streams > 0:
            return False  # Active streams = not idle
        idle_time = time.time() - self._last_activity
        return idle_time > self._hibernation_config.sleep_after

    def exec(self, command: str, ...) -> CommandResult:
        """Execute command."""
        self._ensure_awake()
        self._record_activity()
        # ... execute ...

    def exec_stream(self, command: str, ...) -> Generator[StreamEvent, None, None]:
        """Stream command execution."""
        self._ensure_awake()
        self._active_streams += 1
        try:
            self._record_activity()
            # ... stream ...
        finally:
            self._active_streams -= 1
            self._record_activity()

    def hibernate(self) -> HibernatedSandbox:
        """Hibernate sandbox: snapshot state and DELETE sandbox.

        Unlike scale-to-0, this completely removes the sandbox to save costs.
        Wake by acquiring new sandbox from pool + restore snapshot.

        Returns:
            HibernatedSandbox reference for later wake()
        """
        if self._state != SandboxState.ACTIVE:
            raise SandboxError(f"Cannot hibernate sandbox in state {self._state}")

        # Create snapshot
        snapshot_id = f"hibernate-{self.app_id}-{int(time.time())}"
        self.create_snapshot(
            snapshot_id=snapshot_id,
            paths=["/workspace", "/home", "/tmp"],
            description=f"Hibernation snapshot for {self.app_id}"
        )

        # Store metadata for restoration
        hibernated = HibernatedSandbox(
            snapshot_id=snapshot_id,
            image=self._image,
            mode=self._mode,
            service_config=self._service_config,
            hibernated_at=time.time(),
            metadata={"app_id": self.app_id}
        )

        # DELETE the sandbox (not just scale to 0)
        self.delete()

        self._state = SandboxState.HIBERNATED
        return hibernated

    @classmethod
    def wake(cls, hibernated: HibernatedSandbox,
             pool: Optional['SandboxManager'] = None) -> 'Sandbox':
        """Wake a hibernated sandbox.

        Args:
            hibernated: Reference from hibernate()
            pool: Optional pool for fast acquisition

        Returns:
            New Sandbox with restored state
        """
        # Acquire new sandbox (from pool if available, else create)
        if pool:
            sandbox = pool.acquire_sync(hibernated.image)
        else:
            sandbox = cls.create(
                image=hibernated.image,
                mode=hibernated.mode,
                service_config=hibernated.service_config
            )

        # Restore snapshot
        sandbox.restore_snapshot(hibernated.snapshot_id)

        return sandbox

    def _ensure_awake(self):
        """Called before operations - wake if hibernated."""
        if self._state == SandboxState.HIBERNATED:
            raise SandboxError("Sandbox is hibernated. Call Sandbox.wake() first.")
```

### Pool Integration for Fast Wake

```python
# In manager.py
class SandboxManager:
    async def acquire_with_snapshot(
        self,
        image: str,
        snapshot_id: str,
        timeout: float = 300
    ) -> Sandbox:
        """Acquire sandbox and restore snapshot for rapid startup.

        Combines:
        1. Pool acquisition (instant if warm sandbox available)
        2. Snapshot restoration (few seconds for typical projects)

        Total wake time: ~5-15 seconds vs ~60-90s cold start
        """
        sandbox = await self.acquire(image, timeout=timeout)

        snapshot_mgr = SnapshotManager(self._spaces_config)
        snapshot_mgr.restore_snapshot(sandbox, snapshot_id)

        return sandbox

    async def wake_hibernated(
        self,
        hibernated: HibernatedSandbox,
        timeout: float = 300
    ) -> Sandbox:
        """Wake a hibernated sandbox using pool."""
        return await self.acquire_with_snapshot(
            hibernated.image,
            hibernated.snapshot_id,
            timeout
        )
```

### Cost Comparison

| Approach | Idle Cost | Wake Time |
|----------|-----------|-----------|
| Keep running | ~$5/mo per sandbox | Instant |
| Scale to 0 | ~$1/mo (app exists) | 30-60s |
| **Hibernate (snapshot + delete)** | ~$0.02/mo (Spaces only) | 5-15s (with pool) |

---

## 4. Snapshot/Restore API

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
        """Create a snapshot of sandbox filesystem.

        NOTE: Snapshots include dependencies (node_modules, .venv) by default
        for rapid startup. Only caches and temp files are excluded.
        """
        snapshot_id = snapshot_id or f"snap-{uuid.uuid4().hex[:12]}"
        paths = paths or ["/workspace"]
        # Include dependencies (node_modules, .venv) - only exclude caches
        exclude_patterns = exclude_patterns or [
            "*.pyc", "__pycache__",          # Python bytecode
            ".git/objects", ".git/lfs",       # Git internals (keep .git for branch info)
            "node_modules/.cache",            # npm/yarn cache (keep node_modules itself)
            ".venv/lib/*/site-packages/*.dist-info",  # Keep packages, skip metadata
            "*.log", "*.tmp", ".env",         # Logs, temp files, secrets
            ".pytest_cache", ".mypy_cache",   # Tool caches
            "coverage/", ".coverage",         # Coverage data
        ]

        # Build tar command with exclusions
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

        # Upload via presigned URL (sandbox uploads directly to Spaces)
        spaces_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
        upload_url = self._spaces.generate_presigned_upload_url(spaces_key, expires_in=3600)

        upload_result = sandbox.exec(
            f"curl -X PUT -T {archive} '{upload_url}'",
            timeout=600
        )
        if not upload_result.success:
            raise SnapshotError(f"Failed to upload snapshot: {upload_result.stderr}")

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

        # Cleanup archive in sandbox
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
        download_url = self._spaces.generate_presigned_download_url(spaces_key, expires_in=3600)
        archive = f"/tmp/restore_{snapshot_id}.tar.gz"

        download_result = sandbox.exec(
            f"curl -sSfL -o {archive} '{download_url}'",
            timeout=600
        )
        if not download_result.success:
            raise SnapshotError(f"Failed to download snapshot: {download_result.stderr}")

        # Extract
        result = sandbox.exec(f"tar -xzf {archive} -C {target_path}", timeout=600)

        # Cleanup
        sandbox.exec(f"rm -f {archive}")

        return result.success

    def _save_metadata(self, metadata: SnapshotMetadata):
        """Save metadata to Spaces."""
        key = f"{self._prefix}{metadata.snapshot_id}/metadata.json"
        content = json.dumps(asdict(metadata)).encode()
        self._spaces.put_object(key, content, content_type="application/json")

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """Get snapshot metadata."""
        key = f"{self._prefix}{snapshot_id}/metadata.json"
        try:
            content = self._spaces.get_object(key)
            return SnapshotMetadata(**json.loads(content))
        except:
            return None

    def list_snapshots(self, prefix: str = None) -> List[SnapshotMetadata]:
        """List all snapshots."""
        search_prefix = f"{self._prefix}{prefix}" if prefix else self._prefix
        keys = self._spaces.list_objects(search_prefix)

        snapshots = []
        for key in keys:
            if key.endswith("/metadata.json"):
                snapshot_id = key.split("/")[-2]
                meta = self.get_snapshot(snapshot_id)
                if meta:
                    snapshots.append(meta)

        return sorted(snapshots, key=lambda x: x.created_at, reverse=True)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        self._spaces.delete_object(f"{self._prefix}{snapshot_id}/archive.tar.gz")
        self._spaces.delete_object(f"{self._prefix}{snapshot_id}/metadata.json")
        return True
```

### Storage Layout

```
spaces-bucket/
├── snapshots/
│   ├── snap-abc123def456/
│   │   ├── metadata.json      # SnapshotMetadata as JSON
│   │   └── archive.tar.gz     # Compressed filesystem (includes deps)
│   ├── hibernate-app123-1704672000/
│   │   ├── metadata.json
│   │   └── archive.tar.gz
│   └── ...
```

### Typical Snapshot Sizes (with dependencies)

| Project Type | Uncompressed | Compressed (.tar.gz) | Restore Time |
|--------------|--------------|----------------------|--------------|
| Python (FastAPI + deps) | ~150MB | ~40MB | ~3-5s |
| Python (ML/pandas/numpy) | ~800MB | ~200MB | ~10-15s |
| Node (Express + deps) | ~100MB | ~25MB | ~2-4s |
| Node (Next.js + deps) | ~400MB | ~100MB | ~8-12s |

**Spaces storage cost**: ~$0.02/GB/month → typical snapshot costs < $0.01/month

---

## 5. Sessions API

### Goal
Isolated execution contexts with persistent shell state.

### Container-Side Implementation

```python
# sandbox_api/sessions.py
import os
import pty
import select
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class Session:
    id: str
    pid: int
    master_fd: int
    env: Dict[str, str]
    cwd: str

class SessionManager:
    """Manages persistent shell sessions."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, session_id: str, env: dict = None, cwd: str = "/workspace") -> Session:
        """Create a new session with persistent bash shell."""
        if session_id in self._sessions:
            raise ValueError(f"Session {session_id} already exists")

        master, slave = pty.openpty()

        session_env = os.environ.copy()
        if env:
            session_env.update(env)

        proc = subprocess.Popen(
            ["/bin/bash", "--norc", "--noprofile", "-i"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=session_env,
            preexec_fn=os.setsid
        )

        os.close(slave)

        session = Session(
            id=session_id,
            pid=proc.pid,
            master_fd=master,
            env=env or {},
            cwd=cwd
        )
        self._sessions[session_id] = session

        # Wait for shell prompt
        self._read_until_prompt(master)

        return session

    def exec_in_session(self, session_id: str, command: str, timeout: int = 120) -> str:
        """Execute command in session's persistent shell."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Send command
        os.write(session.master_fd, f"{command}\n".encode())

        # Read output until next prompt
        output = self._read_until_prompt(session.master_fd, timeout)

        # Remove command echo and prompt from output
        lines = output.split('\n')
        if lines and command in lines[0]:
            lines = lines[1:]

        return '\n'.join(lines).strip()

    def _read_until_prompt(self, fd: int, timeout: int = 30) -> str:
        """Read from PTY until shell prompt appears."""
        output = []
        while True:
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                break

            try:
                data = os.read(fd, 4096)
                if not data:
                    break
                output.append(data.decode(errors='replace'))

                # Check for prompt ($ or #)
                if output[-1].rstrip().endswith(('$ ', '# ')):
                    break
            except OSError:
                break

        return ''.join(output)

    def close(self, session_id: str):
        """Close a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            os.close(session.master_fd)
            try:
                os.kill(session.pid, 9)
            except OSError:
                pass

# Global session manager
sessions = SessionManager()
```

### API Endpoints

```python
# In sandbox_api/main.py

from .sessions import sessions, SessionManager

class CreateSessionRequest(BaseModel):
    session_id: str
    env: dict = None
    cwd: str = "/workspace"

@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest, _=Depends(verify_token)):
    """Create a new persistent session."""
    try:
        session = sessions.create(req.session_id, req.env, req.cwd)
        return {"session_id": session.id, "pid": session.pid}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, _=Depends(verify_token)):
    """Get session info."""
    if session_id not in sessions._sessions:
        raise HTTPException(404, f"Session {session_id} not found")

    session = sessions._sessions[session_id]
    return {
        "session_id": session.id,
        "pid": session.pid,
        "cwd": session.cwd,
        "env": session.env
    }

class SessionExecRequest(BaseModel):
    command: str
    timeout: int = 120

@app.post("/api/sessions/{session_id}/exec")
async def session_exec(session_id: str, req: SessionExecRequest, _=Depends(verify_token)):
    """Execute command in session."""
    try:
        output = await asyncio.to_thread(
            sessions.exec_in_session,
            session_id, req.command, req.timeout
        )
        return {"output": output}
    except ValueError as e:
        raise HTTPException(404, str(e))

@app.delete("/api/sessions/{session_id}")
async def close_session(session_id: str, _=Depends(verify_token)):
    """Close a session."""
    sessions.close(session_id)
    return {"success": True}
```

---

## 6. Other Features

### git_checkout() Convenience Method

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
        """Clone a git repository.

        Args:
            url: Repository URL (HTTPS or SSH)
            path: Destination path
            branch: Branch to checkout
            depth: Clone depth (1 for shallow)
            credentials: Auth for private repos
        """
        cmd = ["git", "clone"]

        if depth:
            cmd.extend(["--depth", str(depth)])
        if branch:
            cmd.extend(["--branch", branch])

        clone_url = url
        env = None

        if credentials:
            if credentials.ssh_key:
                # Write SSH key temporarily
                self.filesystem.write_file("/tmp/git_key", credentials.ssh_key)
                self.exec("chmod 600 /tmp/git_key")
                env = {"GIT_SSH_COMMAND": "ssh -i /tmp/git_key -o StrictHostKeyChecking=no"}
            elif credentials.token:
                # Embed token in HTTPS URL
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(url)
                auth = f"{credentials.username or 'git'}:{credentials.token}"
                clone_url = urlunparse(parsed._replace(netloc=f"{auth}@{parsed.netloc}"))

        cmd.extend([clone_url, path])
        result = self.exec(" ".join(cmd), env=env)

        # Cleanup SSH key
        if credentials and credentials.ssh_key:
            self.exec("rm -f /tmp/git_key")

        return result
```

### Port Exposure

```python
# In sandbox.py
@dataclass
class ExposedPort:
    port: int
    url: str
    protocol: str  # "https" or "wss"

class Sandbox:
    def expose_port(self, port: int) -> ExposedPort:
        """Get public URL for an internal port.

        Requires service mode. Uses FastAPI reverse proxy.
        """
        if self._mode != SandboxMode.SERVICE:
            raise NotImplementedError("Port exposure requires service mode")

        base_url = self.get_url()
        proxy_url = f"{base_url}/proxy/{port}"

        return ExposedPort(
            port=port,
            url=proxy_url,
            protocol="https"
        )
```

---

## Implementation Order

### Phase 1: Foundation
1. **Types** - Add `SandboxMode`, `ServiceConfig`, `StreamEvent`, `HibernationConfig`
2. **Deployer** - Service spec generation with token
3. **Service Client** - HTTP/SSE client for service mode

### Phase 2: Container Images
4. **Python worker image** - With uv
5. **Node worker image** - With bun
6. **Python service image** - FastAPI + uvicorn + uv
7. **Node service image** - FastAPI + bun/node

### Phase 3: Sandbox API Server
8. **Core API** - exec, exec/stream, health
9. **Process API** - background exec, logs, kill
10. **Port Proxy** - /proxy/{port} routing
11. **Sessions API** - Persistent shell sessions

### Phase 4: Snapshot & Hibernate
12. **SnapshotManager** - Create/restore/list/delete
13. **Hibernate** - Snapshot + delete flow
14. **Wake** - Pool acquire + restore flow

### Phase 5: Integration & Polish
15. **Pool integration** - `acquire_with_snapshot()`, `wake_hibernated()`
16. **git_checkout()** - Convenience method
17. **Documentation & Tests**

---

## Files Summary

| File | Status | Description |
|------|--------|-------------|
| `types.py` | Modify | Add SandboxMode, ServiceConfig, StreamEvent, HibernationConfig |
| `deployer.py` | Modify | Add service spec builder, return token |
| `service_client.py` | **NEW** | HTTP/SSE client for service mode |
| `snapshot.py` | **NEW** | SnapshotManager |
| `sandbox.py` | Modify | Service mode, hibernate/wake, activity tracking |
| `async_sandbox.py` | Modify | Async service client |
| `manager.py` | Modify | acquire_with_snapshot(), wake_hibernated() |
| `exceptions.py` | Modify | Add SnapshotError, SnapshotNotFoundError |
| `images/` | **NEW** | Container images directory |
| `images/sandbox-python-worker/` | **NEW** | Python worker Dockerfile |
| `images/sandbox-python-service/` | **NEW** | Python service Dockerfile + API |
| `images/sandbox-node-worker/` | **NEW** | Node/Bun worker Dockerfile |
| `images/sandbox-node-service/` | **NEW** | Node/Bun service Dockerfile + API |
| `images/sandbox_api/` | **NEW** | FastAPI server code for containers |

---

## Usage Examples

```python
# =============================================================================
# Basic worker mode (default, unchanged)
# =============================================================================
sandbox = Sandbox.create(image="python")
result = sandbox.exec("uv pip install requests && python script.py")
sandbox.delete()

# =============================================================================
# Service mode with streaming
# =============================================================================
sandbox = Sandbox.create(
    image="python",
    mode=SandboxMode.SERVICE
)

# Stream command output in real-time
for event in sandbox.exec_stream("uv pip install -r requirements.txt"):
    if event.type == "stdout":
        print(event.data, end="", flush=True)

# Start server and get preview URL
sandbox.exec("python -m http.server 3000 &")
port_info = sandbox.expose_port(3000)
print(f"Preview: {port_info.url}")  # https://app-xxx.ondigitalocean.app/proxy/3000

# =============================================================================
# Sessions for isolated contexts
# =============================================================================
dev_session = sandbox.create_session("dev", env={"DEBUG": "1"})
dev_session.exec("cd /workspace && source .venv/bin/activate")
dev_session.exec("python manage.py runserver &")

test_session = sandbox.create_session("test", env={"NODE_ENV": "test"})
test_session.exec("bun test")

# =============================================================================
# Snapshot for rapid startup
# =============================================================================
# After installing dependencies...
meta = sandbox.create_snapshot(
    description="Python app with deps",
    paths=["/workspace"]
)
print(f"Snapshot: {meta.snapshot_id}, Size: {meta.size_bytes} bytes")

# Later: instant startup with pre-warmed pool + snapshot
manager = SandboxManager(...)
sandbox = await manager.acquire_with_snapshot("python", meta.snapshot_id)
# Ready in ~5-10 seconds with all dependencies!

# =============================================================================
# Hibernate idle sandbox (Cloudflare-style)
# =============================================================================
# Sandbox auto-hibernates after 10 min idle, or manually:
hibernated = sandbox.hibernate()  # Snapshots state, DELETES sandbox
print(f"Hibernated. Snapshot: {hibernated.snapshot_id}")

# Cost while hibernated: ~$0.02/mo (Spaces storage only)

# Wake later:
sandbox = Sandbox.wake(hibernated, pool=manager)  # Pool acquire + restore
# Back online in seconds!

# =============================================================================
# Node with Bun
# =============================================================================
sandbox = Sandbox.create(image="node", mode=SandboxMode.SERVICE)

# Bun is the default runtime
sandbox.exec("bun install")  # Fast!
sandbox.exec("bun run build")

# Node.js still available
sandbox.exec("node --version")
sandbox.exec("npm install legacy-package")
```

This architecture provides Cloudflare-like functionality while leveraging DO App Platform's native capabilities and maintaining cost efficiency through hibernate (snapshot + delete).
