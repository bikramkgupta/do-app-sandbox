# Service Mode Guide

Service mode sandboxes provide an HTTP API with streaming support, port exposure, and persistent sessions. This is the recommended mode for interactive use cases.

## Worker vs Service Mode

| Feature | Worker Mode | Service Mode |
|---------|-------------|--------------|
| Command execution | Via doctl console | Via HTTP API |
| Streaming output | No | Yes (SSE) |
| Port exposure | No | Yes (proxy) |
| Persistent sessions | No | Yes |
| Public URL | No | Yes |
| Use case | Background tasks, batch jobs | Interactive apps, web services |

## Creating a Service Mode Sandbox

```python
from do_app_sandbox import Sandbox, SandboxMode

# Service mode (default for most use cases)
sandbox = Sandbox.create(image="python", mode=SandboxMode.SERVICE)

# Worker mode (no HTTP endpoint)
worker = Sandbox.create(image="python", mode=SandboxMode.WORKER)
```

## Streaming Command Execution

Stream command output in real-time via Server-Sent Events (SSE):

```python
from do_app_sandbox import Sandbox, SandboxMode

sandbox = Sandbox.create(image="python", mode=SandboxMode.SERVICE)

# Stream output as it happens
for event in sandbox.exec_stream("pip install requests numpy pandas"):
    if event.type == "stdout":
        print(event.data, end="", flush=True)
    elif event.type == "stderr":
        print(f"[stderr] {event.data}", end="", flush=True)
    elif event.type == "exit":
        print(f"\nCommand exited with code: {event.data}")
```

### StreamEvent Types

| Type | Description | Data |
|------|-------------|------|
| `stdout` | Standard output line | Line content |
| `stderr` | Standard error line | Line content |
| `exit` | Command completed | Exit code |
| `error` | Execution error | Error message |

### Async Streaming

```python
from do_app_sandbox import AsyncSandbox, SandboxMode

sandbox = await AsyncSandbox.create(image="python", mode=SandboxMode.SERVICE)

async for event in sandbox.exec_stream("python train.py"):
    if event.type == "stdout":
        print(event.data)
```

## Port Exposure

Expose internal ports through the sandbox's public URL:

```python
sandbox = Sandbox.create(image="python", mode=SandboxMode.SERVICE)

# Start a web server inside the sandbox
sandbox.exec("cd /workspace && python -m http.server 3000 &")

# Get public URL for the internal port
port_info = sandbox.expose_port(3000)
print(f"Access your app at: {port_info.url}")
# Output: https://sandbox-xxx.ondigitalocean.app/proxy/3000
```

### ExposedPort Properties

```python
port_info = sandbox.expose_port(8000)

print(port_info.port)       # 8000
print(port_info.url)        # https://sandbox-xxx.ondigitalocean.app/proxy/8000
print(port_info.protocol)   # https
```

### Example: Running a Flask App

```python
# Upload Flask app
sandbox.filesystem.write_file("/workspace/app.py", """
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello from sandbox!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
""")

# Install dependencies and run
sandbox.exec("pip install flask")
pid = sandbox.launch_process("python /workspace/app.py")

# Get public URL
port_info = sandbox.expose_port(5000)
print(f"Flask app running at: {port_info.url}")
```

## Background Process Logs

Stream logs from background processes in real-time:

```python
# Start a long-running process
pid = sandbox.launch_process("python train_model.py")

# Stream logs as they're written
client = sandbox._get_service_client()
for line in client.stream_process_logs(pid):
    print(line)
```

### Getting Process Logs (Non-Streaming)

```python
# Get all logs
logs = client.get_process_logs(pid)
print(logs)

# Get last 100 lines
logs = client.get_process_logs(pid, tail=100)
```

## Persistent Sessions

Sessions maintain shell state (environment variables, working directory) across commands:

```python
client = sandbox._get_service_client()

# Create a session
client.create_session("my-session", env={"DEBUG": "1"}, cwd="/workspace")

# Execute commands in the session (state persists)
result = client.session_exec("my-session", "export MY_VAR=hello")
result = client.session_exec("my-session", "echo $MY_VAR")  # Outputs: hello
result = client.session_exec("my-session", "cd /tmp")
result = client.session_exec("my-session", "pwd")  # Outputs: /tmp

# Close when done
client.close_session("my-session")
```

### Session Use Cases

- **Interactive debugging**: Maintain state while exploring
- **Multi-step builds**: cd into directories, set environment
- **REPL-like experience**: Variables persist between commands

## HTTP API Reference

Service mode exposes these endpoints (automatically used by the SDK):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth) |
| `/api/exec` | POST | Execute command |
| `/api/exec/stream` | POST | Execute with SSE streaming |
| `/api/exec/background` | POST | Start background process |
| `/api/processes` | GET | List background processes |
| `/api/processes/{pid}/logs` | GET | Get process logs |
| `/api/processes/{pid}/logs/stream` | GET | Stream process logs |
| `/api/processes/{pid}/kill` | POST | Kill process |
| `/api/sessions` | POST | Create session |
| `/api/sessions/{id}` | GET | Get session info |
| `/api/sessions/{id}/exec` | POST | Execute in session |
| `/api/sessions/{id}` | DELETE | Close session |
| `/api/files` | GET | List directory |
| `/api/files/content` | GET | Read file |
| `/api/files/content` | POST | Write file |
| `/api/files/download` | GET | Download file |
| `/proxy/{port}/{path}` | * | Proxy to internal port |

### Authentication

All endpoints except `/health` require a bearer token:

```bash
curl -H "Authorization: Bearer $SANDBOX_API_TOKEN" \
     https://sandbox-xxx.ondigitalocean.app/api/exec \
     -d '{"command": "echo hello"}'
```

The SDK handles authentication automatically.

## Working Directory

- **Service mode**: Default working directory is `/workspace`
- **Worker mode**: Default working directory is `/home/sandbox/app`

```python
# Service mode uses /workspace
sandbox = Sandbox.create(image="python", mode=SandboxMode.SERVICE)
sandbox.exec("pwd")  # /workspace

# Worker mode uses /home/sandbox/app
worker = Sandbox.create(image="python", mode=SandboxMode.WORKER)
worker.exec("pwd")  # /home/sandbox/app
```

## Limitations

1. **Text output only**: Streaming output (`exec_stream`) is designed for text. Binary data is decoded with `errors='replace'`, which may corrupt binary content. Use file operations for binary transfers.

2. **Port 8080 reserved**: The sandbox API runs on port 8080. Your apps should use other ports (e.g., 3000, 5000) and access them via `expose_port()`.

3. **Session cleanup**: Sessions are cleaned up when the sandbox restarts. For long-running state, use files or snapshots.
