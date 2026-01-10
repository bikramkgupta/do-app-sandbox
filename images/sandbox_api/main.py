"""Sandbox API Server - FastAPI server for service-mode containers.

Provides HTTP/SSE endpoints for:
- Command execution (sync and streaming)
- Background process management
- Port proxying (reverse proxy to internal ports)
- Persistent sessions
- File operations
"""

import asyncio
import json
import os
import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    import httpx
except ImportError:
    httpx = None

from .sessions import sessions

app = FastAPI(title="Sandbox API", description="HTTP API for sandbox command execution and management", version="0.1.0")

# Configuration from environment
SANDBOX_TOKEN = os.environ.get("SANDBOX_API_TOKEN", "")
SANDBOX_MODE = os.environ.get("SANDBOX_MODE", "service")

# Process tracking for background commands
_processes: dict[int, dict] = {}


# =============================================================================
# Authentication
# =============================================================================


async def verify_token(authorization: str = Header(None)):
    """Verify bearer token for protected endpoints."""
    if not SANDBOX_TOKEN:
        return  # No token configured = allow all (development mode)

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")

    token = authorization[7:]
    if token != SANDBOX_TOKEN:
        raise HTTPException(403, "Invalid token")


# =============================================================================
# Health Check (no auth required)
# =============================================================================


@app.get("/health")
async def health():
    """Health check endpoint for App Platform."""
    return {"status": "healthy", "mode": SANDBOX_MODE, "timestamp": time.time()}


# =============================================================================
# Command Execution
# =============================================================================


class ExecRequest(BaseModel):
    """Request body for command execution."""

    command: str
    env: dict[str, str] | None = None
    cwd: str = "/workspace"
    timeout: int = 120


class ExecResult(BaseModel):
    """Response for command execution."""

    stdout: str
    stderr: str
    exit_code: int


@app.post("/api/exec", response_model=ExecResult)
async def exec_command(req: ExecRequest, _=Depends(verify_token)):
    """Execute a command and return the result."""
    env = os.environ.copy()
    if req.env:
        env.update(req.env)

    proc = await asyncio.create_subprocess_shell(
        req.command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=req.cwd, env=env
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=req.timeout)
        return ExecResult(
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            exit_code=proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(408, "Command timed out")


@app.post("/api/exec/stream")
async def exec_stream(req: ExecRequest, _=Depends(verify_token)):
    """Execute a command with SSE streaming output."""

    async def generate():
        env = os.environ.copy()
        if req.env:
            env.update(req.env)

        proc = await asyncio.create_subprocess_shell(
            req.command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=req.cwd, env=env
        )

        start_time = time.time()

        async def read_stream(stream, stream_type):
            """Read lines from stream and yield SSE events."""
            while True:
                line = await stream.readline()
                if not line:
                    break
                yield stream_type, line.decode(errors="replace")

        # Create tasks for both streams
        stdout_task = asyncio.create_task(read_stream(proc.stdout, "stdout").__anext__())
        stderr_task = asyncio.create_task(read_stream(proc.stderr, "stderr").__anext__())

        pending = {stdout_task: "stdout", stderr_task: "stderr"}
        readers = {"stdout": read_stream(proc.stdout, "stdout"), "stderr": read_stream(proc.stderr, "stderr")}

        while pending:
            done, _ = await asyncio.wait(pending.keys(), return_when=asyncio.FIRST_COMPLETED, timeout=req.timeout)

            if not done:
                # Timeout
                proc.kill()
                yield f"event: error\ndata: {json.dumps({'message': 'Command timed out', 'code': 'TIMEOUT'})}\n\n"
                return

            for task in done:
                stream_type = pending.pop(task)
                try:
                    _, line = task.result()
                    event_data = {"line": line.rstrip("\n"), "timestamp": time.time()}
                    yield f"event: {stream_type}\ndata: {json.dumps(event_data)}\n\n"

                    # Schedule next read from same stream
                    new_task = asyncio.create_task(readers[stream_type].__anext__())
                    pending[new_task] = stream_type
                except StopAsyncIteration:
                    pass  # Stream finished

        await proc.wait()
        duration_ms = int((time.time() - start_time) * 1000)
        yield f"event: exit\ndata: {json.dumps({'code': proc.returncode, 'duration_ms': duration_ms, 'timestamp': time.time()})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# =============================================================================
# Background Process Management
# =============================================================================


class BackgroundExecRequest(BaseModel):
    """Request body for background execution."""

    command: str
    cwd: str = "/workspace"
    env: dict[str, str] | None = None


@app.post("/api/exec/background")
async def exec_background(req: BackgroundExecRequest, _=Depends(verify_token)):
    """Start a background process."""
    log_file = f"/tmp/proc_{uuid.uuid4().hex[:8]}.log"

    env = os.environ.copy()
    if req.env:
        env.update(req.env)

    # Start process with nohup, redirect output to log file
    # Use subprocess.run for this quick operation to avoid async complexity
    import subprocess
    import shlex

    # Properly escape the command for shell execution
    escaped_cmd = shlex.quote(req.command)
    full_cmd = f'nohup /bin/bash -c {escaped_cmd} > {log_file} 2>&1 & echo $!'

    result = await asyncio.to_thread(
        subprocess.run,
        ["/bin/bash", "-c", full_cmd],
        capture_output=True,
        text=True,
        cwd=req.cwd,
        env=env,
        timeout=10,
    )
    pid = int(result.stdout.strip())

    _processes[pid] = {"command": req.command, "log_file": log_file, "cwd": req.cwd, "started_at": time.time()}

    return {"pid": pid, "log_file": log_file}


def _check_process_status(pid: int) -> str:
    """Check if a process is still running, handling zombies properly."""
    try:
        # Try to reap zombie processes
        waited_pid, status_code = os.waitpid(pid, os.WNOHANG)
        if waited_pid == pid:
            # Process has exited
            return "stopped"
        # Process still running (waitpid returned 0)
        return "running"
    except ChildProcessError:
        # Not a child of this process, use kill to check
        try:
            os.kill(pid, 0)
            return "running"
        except OSError:
            return "stopped"
    except OSError:
        return "stopped"


@app.get("/api/processes")
async def list_processes(_=Depends(verify_token)):
    """List tracked background processes."""
    result = []
    for pid, info in list(_processes.items()):
        status = _check_process_status(pid)
        result.append(
            {
                "pid": pid,
                "command": info["command"],
                "status": status,
                "log_file": info["log_file"],
                "started_at": info.get("started_at"),
            }
        )
    return result


@app.get("/api/processes/{pid}")
async def get_process(pid: int, _=Depends(verify_token)):
    """Get status of a specific background process."""
    if pid not in _processes:
        raise HTTPException(404, f"Process {pid} not tracked")

    info = _processes[pid]
    status = _check_process_status(pid)

    return {
        "pid": pid,
        "command": info["command"],
        "status": status,
        "log_file": info["log_file"],
        "started_at": info.get("started_at"),
    }


@app.get("/api/processes/{pid}/logs")
async def get_process_logs(pid: int, tail: int | None = None, _=Depends(verify_token)):
    """Get logs from a background process."""
    if pid not in _processes:
        raise HTTPException(404, f"Process {pid} not tracked")

    log_file = _processes[pid]["log_file"]

    if tail:
        proc = await asyncio.create_subprocess_shell(
            f"tail -n {tail} {log_file}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return {"logs": stdout.decode(errors="replace")}
    else:
        try:
            with open(log_file) as f:
                return {"logs": f.read()}
        except FileNotFoundError:
            return {"logs": ""}


@app.get("/api/processes/{pid}/logs/stream")
async def stream_process_logs(pid: int, _=Depends(verify_token)):
    """Stream logs from a background process (tail -f style)."""
    if pid not in _processes:
        raise HTTPException(404, f"Process {pid} not tracked")

    log_file = _processes[pid]["log_file"]

    async def generate():
        proc = await asyncio.create_subprocess_shell(f"tail -f {log_file}", stdout=asyncio.subprocess.PIPE)

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                event_data = {"line": line.decode(errors="replace").rstrip("\n"), "timestamp": time.time()}
                yield f"data: {json.dumps(event_data)}\n\n"
        finally:
            proc.kill()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "X-Accel-Buffering": "no"},
    )


class KillRequest(BaseModel):
    """Request body for killing a process."""

    signal: int = 15  # SIGTERM


@app.post("/api/processes/{pid}/kill")
async def kill_process(pid: int, req: KillRequest = None, _=Depends(verify_token)):
    """Kill a background process."""
    signal = req.signal if req else 15
    try:
        os.kill(pid, signal)
        return {"success": True}
    except OSError as e:
        raise HTTPException(400, f"Failed to kill process: {e}")


# =============================================================================
# Port Proxy (Reverse Proxy to Internal Ports)
# =============================================================================


@app.api_route("/proxy/{port}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_port(port: int, path: str, request: Request, _=Depends(verify_token)):
    """Proxy requests to internal port.

    This allows exposing services running on internal ports
    through the sandbox's public URL.
    """
    if httpx is None:
        raise HTTPException(500, "httpx not installed for proxy support")

    target_url = f"http://localhost:{port}/{path}"

    # Forward query string
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Filter headers (don't forward host or auth)
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in ("host", "authorization", "content-length")
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            body = await request.body()
            response = await client.request(
                method=request.method, url=target_url, headers=forward_headers, content=body if body else None
            )

            # Filter response headers
            response_headers = dict(response.headers)
            response_headers.pop("transfer-encoding", None)
            response_headers.pop("content-encoding", None)

            return Response(content=response.content, status_code=response.status_code, headers=response_headers)
        except httpx.ConnectError:
            raise HTTPException(502, f"Cannot connect to port {port}")
        except httpx.TimeoutException:
            raise HTTPException(504, f"Timeout connecting to port {port}")


# =============================================================================
# Sessions API
# =============================================================================


class CreateSessionRequest(BaseModel):
    """Request body for creating a session."""

    session_id: str
    env: dict[str, str] | None = None
    cwd: str = "/workspace"


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest, _=Depends(verify_token)):
    """Create a new persistent shell session."""
    try:
        session = await asyncio.to_thread(sessions.create, req.session_id, req.env, req.cwd)
        return {"session_id": session.id, "pid": session.pid}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/sessions")
async def list_sessions(_=Depends(verify_token)):
    """List all active sessions."""
    return sessions.list_sessions()


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, _=Depends(verify_token)):
    """Get session info."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    # Check if still running
    try:
        os.kill(session.pid, 0)
        status = "running"
    except OSError:
        status = "stopped"

    return {
        "session_id": session.id,
        "pid": session.pid,
        "cwd": session.cwd,
        "env": session.env,
        "status": status,
        "created_at": session.created_at,
    }


class SessionExecRequest(BaseModel):
    """Request body for session execution."""

    command: str
    timeout: int = 120


@app.post("/api/sessions/{session_id}/exec")
async def session_exec(session_id: str, req: SessionExecRequest, _=Depends(verify_token)):
    """Execute command in session's persistent shell."""
    try:
        output = await asyncio.to_thread(sessions.exec_in_session, session_id, req.command, req.timeout)
        return {"output": output}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/sessions/{session_id}")
async def close_session(session_id: str, _=Depends(verify_token)):
    """Close a session."""
    success = sessions.close(session_id)
    if not success:
        raise HTTPException(404, f"Session {session_id} not found")
    return {"success": True}


# =============================================================================
# File Operations
# =============================================================================


class FileListResponse(BaseModel):
    """Response for file listing."""

    files: list[dict]


@app.get("/api/files")
async def list_files(path: str = "/workspace", _=Depends(verify_token)):
    """List files in a directory."""
    if not os.path.exists(path):
        raise HTTPException(404, f"Path not found: {path}")

    if not os.path.isdir(path):
        raise HTTPException(400, f"Not a directory: {path}")

    files = []
    for name in os.listdir(path):
        full_path = os.path.join(path, name)
        stat = os.stat(full_path)
        files.append(
            {
                "name": name,
                "path": full_path,
                "is_dir": os.path.isdir(full_path),
                "size": stat.st_size if not os.path.isdir(full_path) else None,
                "permissions": oct(stat.st_mode)[-3:],
            }
        )

    return {"files": files}


@app.get("/api/files/content")
async def read_file(path: str, _=Depends(verify_token)):
    """Read file content."""
    if not os.path.exists(path):
        raise HTTPException(404, f"File not found: {path}")

    if os.path.isdir(path):
        raise HTTPException(400, f"Path is a directory: {path}")

    try:
        with open(path) as f:
            return {"content": f.read(), "path": path}
    except UnicodeDecodeError:
        # Binary file - return base64
        import base64

        with open(path, "rb") as f:
            return {"content": base64.b64encode(f.read()).decode(), "path": path, "encoding": "base64"}


class WriteFileRequest(BaseModel):
    """Request body for writing a file."""

    path: str
    content: str
    encoding: str | None = None  # "base64" for binary


@app.post("/api/files/content")
async def write_file(req: WriteFileRequest, _=Depends(verify_token)):
    """Write content to a file."""
    # Ensure parent directory exists
    parent = os.path.dirname(req.path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    if req.encoding == "base64":
        import base64

        content = base64.b64decode(req.content)
        with open(req.path, "wb") as f:
            f.write(content)
    else:
        with open(req.path, "w") as f:
            f.write(req.content)

    return {"success": True, "path": req.path}


@app.get("/api/files/download")
async def download_file(path: str, _=Depends(verify_token)):
    """Download a file."""
    if not os.path.exists(path):
        raise HTTPException(404, f"File not found: {path}")

    if os.path.isdir(path):
        raise HTTPException(400, f"Path is a directory: {path}")

    with open(path, "rb") as f:
        content = f.read()

    filename = os.path.basename(path)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================================
# Startup/Shutdown
# =============================================================================


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    sessions.close_all()

    # Kill tracked background processes
    for pid in list(_processes.keys()):
        try:
            os.kill(pid, 9)
        except OSError:
            pass
