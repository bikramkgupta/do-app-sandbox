# Implementation Plan: API Gaps & Snapshot/Restore

## Overview

This plan addresses the critical and high-priority API gaps identified in the Cloudflare Sandbox SDK comparison, plus adds snapshot/restore functionality for rapid agent startup.

### Features to Implement

| Priority | Feature | Effort | Files Affected |
|----------|---------|--------|----------------|
| 🔴 Critical | `exec_stream()` - Streaming command output | Medium | executor.py, sandbox.py, async_sandbox.py, types.py |
| 🔴 Critical | `exposePort()` / Preview URLs | High | sandbox.py, deployer.py, types.py (new: port_proxy.py) |
| 🔴 Critical | Auto-sleep / Hibernate | Medium | manager.py, sandbox.py, types.py |
| 🟠 High | Process logs API | Low | process.py, sandbox.py, types.py |
| 🟠 High | Sessions API | Medium | new: session.py, sandbox.py, executor.py |
| 🟠 High | `git_checkout()` | Low | filesystem.py, sandbox.py |
| 🟢 New | Snapshot/Restore API | Medium-High | new: snapshot.py, spaces.py, sandbox.py, manager.py |

---

## 1. Streaming Command Execution (`exec_stream`)

### Goal
Enable real-time streaming of command output as it's produced, essential for long-running builds and AI agent feedback loops.

### Design

```python
# New types in types.py
@dataclass
class StreamEvent:
    """A single streaming output event."""
    type: Literal["stdout", "stderr", "exit", "error"]
    data: str
    timestamp: float

# In sandbox.py
def exec_stream(
    self,
    command: str,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    timeout: int = 120
) -> Generator[StreamEvent, None, CommandResult]:
    """Execute command with streaming output.

    Yields StreamEvent objects as output is produced.
    Returns final CommandResult when complete.

    Usage:
        stream = sandbox.exec_stream("npm run build")
        for event in stream:
            if event.type == "stdout":
                print(event.data, end="")
        result = stream.value  # Final CommandResult
    """

# Async version in async_sandbox.py
async def exec_stream(
    self,
    command: str,
    **kwargs
) -> AsyncGenerator[StreamEvent, None]:
    """Async streaming execution."""
```

### Implementation Approach

1. **Modify executor.py** to support streaming mode:
   - Use `pexpect.expect()` with small timeouts in a loop
   - Yield output chunks as they arrive via `child.before` + `child.after`
   - Parse ANSI escape sequences on-the-fly
   - Separate stdout/stderr using tee to named pipes

2. **Streaming Protocol**:
   ```bash
   # Wrap command to separate stdout/stderr
   mkfifo /tmp/stderr_$$ 2>/dev/null || true
   (command 2>/tmp/stderr_$$) &
   pid=$!
   # Read stderr in background, prefix with marker
   cat /tmp/stderr_$$ | while read line; do echo "___STDERR___:$line"; done &
   wait $pid
   echo "___EXIT___:$?"
   ```

3. **Chunk accumulation**:
   - Buffer partial lines until newline received
   - Detect `___STDERR___:` and `___EXIT___:` markers
   - Yield `StreamEvent` for each complete line

### Files to Modify

| File | Changes |
|------|---------|
| `types.py` | Add `StreamEvent` dataclass |
| `executor.py` | Add `execute_stream()` method with generator |
| `sandbox.py` | Add `exec_stream()` wrapper |
| `async_sandbox.py` | Add async `exec_stream()` using `asyncio.Queue` |
| `tests/` | Add streaming tests |

### Testing Strategy

- Unit test: Mock pexpect, verify event sequence
- Integration test: Run `for i in 1 2 3; do echo $i; sleep 1; done`, verify timing
- Stress test: Stream large output (e.g., `find /`)

---

## 2. Process Logs API

### Goal
Access stdout/stderr from background processes launched via `launch_process()`.

### Design

```python
# In process.py / sandbox.py
def get_process_logs(
    self,
    pid: int,
    tail: Optional[int] = None,
    since: Optional[float] = None
) -> str:
    """Get logs from a background process.

    Args:
        pid: Process ID from launch_process()
        tail: Only return last N lines
        since: Only return logs after this timestamp
    """

def stream_process_logs(
    self,
    pid: int,
    follow: bool = True
) -> Generator[str, None, None]:
    """Stream logs from a background process.

    Args:
        pid: Process ID
        follow: If True, continue streaming new output (like tail -f)
    """
```

### Implementation Approach

1. **Leverage existing log files**: `launch_process()` already redirects to `/tmp/sandbox_proc_{uuid}.log`

2. **Track log file mapping**:
   ```python
   # In ProcessManager
   _pid_to_logfile: Dict[int, str] = {}

   def launch(self, command, ...):
       log_file = f"/tmp/sandbox_proc_{uuid.uuid4().hex[:8]}.log"
       # ... launch with redirect to log_file ...
       self._pid_to_logfile[pid] = log_file
   ```

3. **Log retrieval**:
   ```python
   def get_process_logs(self, pid: int, tail: Optional[int] = None) -> str:
       log_file = self._pid_to_logfile.get(pid)
       if not log_file:
           raise ValueError(f"No log file tracked for PID {pid}")

       if tail:
           result = self._executor.execute(f"tail -n {tail} {log_file}")
       else:
           result = self._executor.execute(f"cat {log_file}")
       return result.stdout
   ```

4. **Streaming logs** (uses `exec_stream`):
   ```python
   def stream_process_logs(self, pid: int, follow: bool = True) -> Generator[str, None, None]:
       log_file = self._pid_to_logfile.get(pid)
       cmd = f"tail -f {log_file}" if follow else f"cat {log_file}"

       for event in self._executor.execute_stream(cmd):
           if event.type == "stdout":
               yield event.data
   ```

### Files to Modify

| File | Changes |
|------|---------|
| `process.py` | Add log file tracking, `get_process_logs()`, `stream_process_logs()` |
| `sandbox.py` | Expose methods on Sandbox class |
| `async_sandbox.py` | Add async versions |
| `types.py` | No changes needed |

---

## 3. Git Checkout Convenience Method

### Goal
Provide native git repository checkout without requiring manual `exec()` calls.

### Design

```python
# In filesystem.py / sandbox.py
def git_checkout(
    self,
    url: str,
    path: str = "/workspace",
    branch: Optional[str] = None,
    depth: Optional[int] = 1,
    credentials: Optional[GitCredentials] = None
) -> CommandResult:
    """Clone a git repository into the sandbox.

    Args:
        url: Repository URL (https or ssh)
        path: Destination path (default: /workspace)
        branch: Specific branch to checkout
        depth: Clone depth (default: 1 for shallow clone)
        credentials: Optional auth for private repos

    Returns:
        CommandResult from git clone operation
    """

@dataclass
class GitCredentials:
    """Credentials for private repository access."""
    username: Optional[str] = None
    password: Optional[str] = None  # or personal access token
    ssh_key: Optional[str] = None   # Private key content
```

### Implementation

```python
def git_checkout(self, url: str, path: str = "/workspace",
                 branch: Optional[str] = None, depth: Optional[int] = 1,
                 credentials: Optional[GitCredentials] = None) -> CommandResult:

    # Build git clone command
    cmd_parts = ["git", "clone"]

    if depth:
        cmd_parts.extend(["--depth", str(depth)])

    if branch:
        cmd_parts.extend(["--branch", branch])

    # Handle credentials
    if credentials:
        if credentials.ssh_key:
            # Write SSH key and configure git
            self.filesystem.write_file("/tmp/git_key", credentials.ssh_key)
            self.exec("chmod 600 /tmp/git_key")
            cmd_parts.insert(0, "GIT_SSH_COMMAND='ssh -i /tmp/git_key -o StrictHostKeyChecking=no'")
        elif credentials.username and credentials.password:
            # Embed credentials in URL (for HTTPS)
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            url = urlunparse(parsed._replace(
                netloc=f"{credentials.username}:{credentials.password}@{parsed.netloc}"
            ))

    cmd_parts.extend([url, path])

    result = self.exec(" ".join(cmd_parts))

    # Cleanup credentials
    if credentials and credentials.ssh_key:
        self.exec("rm -f /tmp/git_key")

    return result
```

### Files to Modify

| File | Changes |
|------|---------|
| `types.py` | Add `GitCredentials` dataclass |
| `filesystem.py` | Add `git_checkout()` method |
| `sandbox.py` | Expose on Sandbox class |
| `async_sandbox.py` | Add async version |

---

## 4. Sessions API (Isolated Execution Contexts)

### Goal
Enable multiple isolated execution contexts within a single sandbox, each with its own shell state, environment variables, and working directory.

### Design

```python
# New file: session.py
@dataclass
class SessionConfig:
    """Configuration for a session."""
    env: Dict[str, str] = field(default_factory=dict)
    cwd: str = "/workspace"
    shell: str = "/bin/bash"

class Session:
    """An isolated execution context within a sandbox."""

    def __init__(self, session_id: str, sandbox: 'Sandbox', config: SessionConfig):
        self.id = session_id
        self._sandbox = sandbox
        self._config = config
        self._executor = None  # Dedicated pexpect session
        self._env = dict(config.env)
        self._cwd = config.cwd

    def exec(self, command: str, timeout: int = 120) -> CommandResult:
        """Execute command in this session's context."""

    def exec_stream(self, command: str, timeout: int = 120) -> Generator[StreamEvent, None, CommandResult]:
        """Stream command output in this session."""

    def set_env(self, key: str, value: str) -> None:
        """Set an environment variable for this session."""

    def get_env(self) -> Dict[str, str]:
        """Get all environment variables for this session."""

    def set_cwd(self, path: str) -> None:
        """Change the working directory for this session."""

    def get_cwd(self) -> str:
        """Get the current working directory."""

    def close(self) -> None:
        """Close this session and release resources."""

# In sandbox.py
class Sandbox:
    def create_session(
        self,
        session_id: str,
        env: Optional[Dict[str, str]] = None,
        cwd: str = "/workspace"
    ) -> Session:
        """Create an isolated execution session.

        Args:
            session_id: Unique identifier for this session
            env: Initial environment variables
            cwd: Initial working directory

        Returns:
            Session object for isolated execution
        """

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get an existing session by ID."""

    def list_sessions(self) -> List[str]:
        """List all active session IDs."""

    def close_session(self, session_id: str) -> bool:
        """Close and cleanup a session."""
```

### Implementation Approach

1. **Persistent Shell Sessions**:
   - Each Session maintains its own `pexpect.spawn` connection
   - Shell variables and state persist across commands
   - Connection kept alive with periodic null commands

2. **Session State Management**:
   ```python
   class Session:
       def __init__(self, ...):
           self._executor = SessionExecutor(sandbox.app_id, sandbox.component)
           self._executor.connect()

           # Initialize environment
           for key, value in self._env.items():
               self._executor.execute_raw(f"export {key}={shlex.quote(value)}")

           # Set working directory
           self._executor.execute_raw(f"cd {self._cwd}")

       def exec(self, command: str, timeout: int = 120) -> CommandResult:
           # Execute in persistent shell context
           return self._executor.execute(command, timeout=timeout)

       def set_env(self, key: str, value: str):
           self._env[key] = value
           self._executor.execute_raw(f"export {key}={shlex.quote(value)}")
   ```

3. **Session Registry in Sandbox**:
   ```python
   class Sandbox:
       def __init__(self, ...):
           self._sessions: Dict[str, Session] = {}

       def create_session(self, session_id: str, ...) -> Session:
           if session_id in self._sessions:
               raise ValueError(f"Session {session_id} already exists")

           session = Session(session_id, self, SessionConfig(env=env or {}, cwd=cwd))
           self._sessions[session_id] = session
           return session
   ```

### Files to Create/Modify

| File | Changes |
|------|---------|
| `session.py` | **NEW**: Session class, SessionExecutor |
| `types.py` | Add `SessionConfig` dataclass |
| `sandbox.py` | Add session management methods |
| `async_sandbox.py` | Add async Session wrapper |
| `executor.py` | Refactor to support persistent connections |

---

## 5. Snapshot/Restore API

### Goal
Enable fast sandbox initialization by saving and restoring filesystem state (code + dependencies) to/from DO Spaces.

### Design

```python
# New file: snapshot.py
@dataclass
class SnapshotMetadata:
    """Metadata about a saved snapshot."""
    snapshot_id: str
    created_at: float
    sandbox_image: str  # python, node, etc.
    size_bytes: int
    paths: List[str]  # Paths included in snapshot
    description: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class SnapshotConfig:
    """Configuration for snapshot operations."""
    include_paths: List[str] = field(default_factory=lambda: ["/workspace"])
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "*.pyc", "__pycache__", ".git", "node_modules/.cache",
        "*.log", ".env", "*.tmp"
    ])
    compress: bool = True
    compression_level: int = 6  # 1-9, higher = smaller but slower

class SnapshotManager:
    """Manages sandbox snapshots in DO Spaces."""

    def __init__(self, spaces_config: SpacesConfig):
        self._spaces = SpacesClient(spaces_config)
        self._prefix = "snapshots/"

    def create_snapshot(
        self,
        sandbox: Sandbox,
        snapshot_id: Optional[str] = None,
        paths: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> SnapshotMetadata:
        """Create a snapshot of sandbox filesystem state.

        Args:
            sandbox: Source sandbox to snapshot
            snapshot_id: Custom ID (auto-generated if not provided)
            paths: Paths to include (default: ["/workspace"])
            exclude_patterns: Glob patterns to exclude
            description: Human-readable description
            tags: Key-value tags for organization
            progress_callback: Called with (bytes_uploaded, total_bytes)

        Returns:
            SnapshotMetadata with snapshot details
        """

    def restore_snapshot(
        self,
        sandbox: Sandbox,
        snapshot_id: str,
        target_path: str = "/",
        overwrite: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """Restore a snapshot to a sandbox.

        Args:
            sandbox: Target sandbox
            snapshot_id: ID of snapshot to restore
            target_path: Base path for restoration
            overwrite: Whether to overwrite existing files
            progress_callback: Called with (bytes_downloaded, total_bytes)

        Returns:
            True if successful
        """

    def list_snapshots(
        self,
        prefix: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        limit: int = 100
    ) -> List[SnapshotMetadata]:
        """List available snapshots."""

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """Get metadata for a specific snapshot."""

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot from storage."""

# Integration with Sandbox class
class Sandbox:
    def create_snapshot(
        self,
        snapshot_id: Optional[str] = None,
        paths: Optional[List[str]] = None,
        **kwargs
    ) -> SnapshotMetadata:
        """Create a snapshot of this sandbox's state."""

    def restore_snapshot(
        self,
        snapshot_id: str,
        target_path: str = "/",
        **kwargs
    ) -> bool:
        """Restore a snapshot to this sandbox."""

# Integration with SandboxManager for warm pools
class SandboxManager:
    async def acquire_with_snapshot(
        self,
        image: str,
        snapshot_id: str,
        timeout: float = 300
    ) -> Sandbox:
        """Acquire a sandbox and restore a snapshot.

        This enables rapid startup:
        1. Get pre-warmed sandbox from pool
        2. Restore snapshot with code + dependencies
        3. Ready for execution in seconds
        """
```

### Implementation Approach

1. **Snapshot Creation**:
   ```python
   def create_snapshot(self, sandbox: Sandbox, ...) -> SnapshotMetadata:
       snapshot_id = snapshot_id or f"snap-{uuid.uuid4().hex[:12]}"

       # Build tar command with exclusions
       exclude_args = " ".join(f"--exclude='{p}'" for p in exclude_patterns)
       paths_arg = " ".join(paths)

       # Create compressed archive in sandbox
       archive_path = f"/tmp/snapshot_{snapshot_id}.tar.gz"
       result = sandbox.exec(
           f"tar {exclude_args} -czf {archive_path} {paths_arg}",
           timeout=600
       )

       if not result.success:
           raise SnapshotError(f"Failed to create archive: {result.stderr}")

       # Get archive size
       size_result = sandbox.exec(f"stat -c %s {archive_path}")
       size_bytes = int(size_result.stdout.strip())

       # Upload to Spaces
       spaces_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
       sandbox.filesystem.download_large(
           archive_path,
           local_temp_path,
           progress_callback=progress_callback
       )
       self._spaces.upload_file(local_temp_path, spaces_key)

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
       sandbox.exec(f"rm -f {archive_path}")

       return metadata
   ```

2. **Snapshot Restoration**:
   ```python
   def restore_snapshot(self, sandbox: Sandbox, snapshot_id: str, ...) -> bool:
       metadata = self.get_snapshot(snapshot_id)
       if not metadata:
           raise SnapshotNotFoundError(snapshot_id)

       # Download from Spaces to sandbox
       spaces_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
       archive_path = f"/tmp/restore_{snapshot_id}.tar.gz"

       # Generate presigned URL and download in sandbox
       url = self._spaces.generate_presigned_download_url(spaces_key)
       sandbox.exec(f"curl -sSfL -o {archive_path} '{url}'")

       # Extract to target path
       if overwrite:
           result = sandbox.exec(
               f"tar -xzf {archive_path} -C {target_path}",
               timeout=600
           )
       else:
           result = sandbox.exec(
               f"tar -xzf {archive_path} -C {target_path} --skip-old-files",
               timeout=600
           )

       # Cleanup
       sandbox.exec(f"rm -f {archive_path}")

       return result.success
   ```

3. **Metadata Storage in Spaces**:
   ```python
   def _save_metadata(self, metadata: SnapshotMetadata):
       key = f"{self._prefix}{metadata.snapshot_id}/metadata.json"
       content = json.dumps(asdict(metadata))
       self._spaces.upload_bytes(key, content.encode())

   def _load_metadata(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
       key = f"{self._prefix}{snapshot_id}/metadata.json"
       try:
           content = self._spaces.download_bytes(key)
           return SnapshotMetadata(**json.loads(content))
       except:
           return None
   ```

4. **Pool Integration for Rapid Startup**:
   ```python
   class SandboxManager:
       async def acquire_with_snapshot(
           self,
           image: str,
           snapshot_id: str,
           timeout: float = 300
       ) -> Sandbox:
           # Get warm sandbox from pool
           sandbox = await self.acquire(image, timeout=timeout)

           # Restore snapshot
           snapshot_mgr = SnapshotManager(self._spaces_config)
           snapshot_mgr.restore_snapshot(sandbox, snapshot_id)

           return sandbox
   ```

### Storage Layout in Spaces

```
bucket/
├── snapshots/
│   ├── snap-abc123def456/
│   │   ├── metadata.json
│   │   └── archive.tar.gz
│   ├── snap-xyz789ghi012/
│   │   ├── metadata.json
│   │   └── archive.tar.gz
│   └── ...
```

### Files to Create/Modify

| File | Changes |
|------|---------|
| `snapshot.py` | **NEW**: SnapshotManager, SnapshotMetadata, SnapshotConfig |
| `types.py` | Add snapshot-related dataclasses |
| `sandbox.py` | Add `create_snapshot()`, `restore_snapshot()` methods |
| `async_sandbox.py` | Add async snapshot methods |
| `manager.py` | Add `acquire_with_snapshot()` method |
| `spaces.py` | Add `upload_bytes()`, `download_bytes()` for metadata |
| `exceptions.py` | Add `SnapshotError`, `SnapshotNotFoundError` |

---

## 6. Auto-Sleep / Hibernate

### Goal
Automatically pause idle sandboxes to reduce costs, with automatic wake-on-access.

### Design

```python
# In types.py
@dataclass
class HibernationConfig:
    """Configuration for sandbox hibernation."""
    enabled: bool = True
    idle_timeout: int = 600  # Seconds before hibernation (default: 10 min)
    hibernate_after_commands: int = 0  # Hibernate after N commands (0 = disabled)
    wake_on_access: bool = True  # Auto-wake when accessed

class SandboxState(Enum):
    """Sandbox lifecycle states."""
    CREATING = "creating"
    ACTIVE = "active"
    HIBERNATING = "hibernating"  # In process of hibernating
    HIBERNATED = "hibernated"    # Fully hibernated
    WAKING = "waking"            # In process of waking
    DELETED = "deleted"

# In sandbox.py
class Sandbox:
    def hibernate(self) -> bool:
        """Manually hibernate the sandbox.

        Saves current state and pauses the container.
        """

    def wake(self, timeout: int = 60) -> bool:
        """Wake a hibernated sandbox.

        Restores state and resumes the container.
        """

    @property
    def state(self) -> SandboxState:
        """Current sandbox state."""

    def configure_hibernation(self, config: HibernationConfig) -> None:
        """Configure auto-hibernation settings."""
```

### Implementation Approach

Since App Platform doesn't natively support hibernation, we implement it via:

1. **Idle Detection in SDK**:
   ```python
   class Sandbox:
       def __init__(self, ...):
           self._last_activity = time.time()
           self._hibernation_config = HibernationConfig()
           self._state = SandboxState.ACTIVE

       def exec(self, command, ...):
           self._wake_if_hibernated()
           self._last_activity = time.time()
           return self._executor.execute(command, ...)

       def _wake_if_hibernated(self):
           if self._state == SandboxState.HIBERNATED:
               self.wake()
   ```

2. **Hibernation via Snapshot**:
   ```python
   def hibernate(self) -> bool:
       """Hibernate by saving state to Spaces and stopping container."""
       if self._state != SandboxState.ACTIVE:
           return False

       self._state = SandboxState.HIBERNATING

       # Create hibernation snapshot
       snapshot_id = f"hibernate-{self.app_id}"
       self.create_snapshot(
           snapshot_id=snapshot_id,
           paths=["/workspace", "/home"],
           tags={"type": "hibernation", "app_id": self.app_id}
       )

       # Scale down to 0 instances (stop container)
       self._deployer.scale_down(self.app_id)

       self._state = SandboxState.HIBERNATED
       return True

   def wake(self, timeout: int = 60) -> bool:
       """Wake by scaling up and restoring snapshot."""
       if self._state != SandboxState.HIBERNATED:
           return self._state == SandboxState.ACTIVE

       self._state = SandboxState.WAKING

       # Scale up to 1 instance
       self._deployer.scale_up(self.app_id)
       self.wait_ready(timeout=timeout)

       # Restore hibernation snapshot
       snapshot_id = f"hibernate-{self.app_id}"
       self.restore_snapshot(snapshot_id)

       self._state = SandboxState.ACTIVE
       self._last_activity = time.time()
       return True
   ```

3. **Pool Manager Integration**:
   ```python
   class SandboxPool:
       async def _idle_hibernation_loop(self):
           """Background task to hibernate idle sandboxes."""
           while self._running:
               await asyncio.sleep(60)  # Check every minute

               for sandbox in list(self._ready_sandboxes):
                   if sandbox._hibernation_config.enabled:
                       idle_time = time.time() - sandbox._last_activity
                       if idle_time > sandbox._hibernation_config.idle_timeout:
                           await asyncio.to_thread(sandbox.hibernate)
                           self._hibernated_sandboxes.add(sandbox)
                           self._ready_sandboxes.remove(sandbox)
   ```

4. **App Platform Scale Control**:
   ```python
   # In deployer.py
   def scale_down(self, app_id: str) -> bool:
       """Scale app to 0 instances."""
       # Use doctl or API to update instance count
       spec = self._get_app_spec(app_id)
       spec['services'][0]['instance_count'] = 0
       return self._update_app(app_id, spec)

   def scale_up(self, app_id: str, count: int = 1) -> bool:
       """Scale app to specified instance count."""
       spec = self._get_app_spec(app_id)
       spec['services'][0]['instance_count'] = count
       return self._update_app(app_id, spec)
   ```

### Files to Modify

| File | Changes |
|------|---------|
| `types.py` | Add `HibernationConfig`, `SandboxState` |
| `sandbox.py` | Add `hibernate()`, `wake()`, state tracking, idle detection |
| `deployer.py` | Add `scale_down()`, `scale_up()` methods |
| `manager.py` | Add hibernation loop to pool management |
| `async_sandbox.py` | Add async hibernate/wake methods |

---

## 7. Dynamic Port Exposure (Preview URLs)

### Goal
Enable dynamic port exposure with public preview URLs, allowing users to start a web server and share it immediately.

### Design

```python
# In types.py
@dataclass
class ExposedPort:
    """Information about an exposed port."""
    port: int
    url: str
    protocol: Literal["http", "https", "ws", "wss"]
    created_at: float
    expires_at: Optional[float] = None

# In sandbox.py
class Sandbox:
    def expose_port(
        self,
        port: int,
        protocol: Literal["http", "https"] = "https",
        hostname: Optional[str] = None,
        auth: Optional[PortAuth] = None
    ) -> ExposedPort:
        """Expose an internal port with a public URL.

        Args:
            port: Internal port to expose
            protocol: URL protocol (default: https)
            hostname: Custom hostname (optional)
            auth: Authentication config (optional)

        Returns:
            ExposedPort with public URL
        """

    def unexpose_port(self, port: int) -> bool:
        """Stop exposing a port."""

    def get_exposed_ports(self) -> List[ExposedPort]:
        """List all exposed ports."""

    def ws_connect(
        self,
        request: Any,  # WebSocket upgrade request
        port: int
    ) -> Any:
        """Proxy WebSocket connection to internal port."""
```

### Implementation Approaches

**Option A: App Platform Route Configuration (Recommended)**

App Platform supports adding routes dynamically. We can configure multiple internal ports at creation time and expose them via subdomains.

```python
# In deployer.py - Modified app spec
def _build_service_spec(self, name: str, image: str, ports: List[int] = None):
    """Build service spec with multiple port support."""
    ports = ports or [8080]

    return {
        "name": name,
        "image": {"registry_type": self._registry_type, "registry": self._registry},
        "instance_size_slug": self._instance_size,
        "http_port": ports[0],  # Primary port
        "internal_ports": ports[1:] if len(ports) > 1 else [],
        "routes": [
            {"path": "/", "preserve_path_prefix": True}
        ] + [
            {"path": f"/port/{p}", "preserve_path_prefix": True}
            for p in ports[1:]
        ]
    }

# In sandbox.py
def expose_port(self, port: int, ...) -> ExposedPort:
    # Check if port is already configured
    if port in self._configured_ports:
        url = f"{self.get_url()}/port/{port}"
        return ExposedPort(port=port, url=url, protocol="https", created_at=time.time())

    # Add port to app configuration
    self._deployer.add_internal_port(self.app_id, port)
    self.wait_ready(timeout=60)  # Wait for redeployment

    url = f"{self.get_url()}/port/{port}"
    self._exposed_ports[port] = ExposedPort(
        port=port, url=url, protocol="https", created_at=time.time()
    )
    return self._exposed_ports[port]
```

**Option B: Reverse Proxy in Container**

Include a reverse proxy (like Caddy or nginx) in the sandbox image that can dynamically route to internal ports.

```python
# Start internal proxy to expose port
def expose_port(self, port: int, ...) -> ExposedPort:
    # Configure internal proxy to forward /exposed/{port} → localhost:{port}
    self.exec(f"sandbox-proxy add {port}")

    url = f"{self.get_url()}/exposed/{port}"
    return ExposedPort(port=port, url=url, protocol="https", created_at=time.time())
```

**Option C: External Tunnel Service**

Use a tunneling approach (similar to ngrok) for dynamic port exposure.

```python
def expose_port(self, port: int, ...) -> ExposedPort:
    # Start tunnel client in sandbox
    result = self.exec(f"sandbox-tunnel expose {port}")
    url = result.stdout.strip()  # Parse tunnel URL

    return ExposedPort(port=port, url=url, protocol="https", created_at=time.time())
```

### Recommended Approach

Start with **Option A** (App Platform routes) for simplicity:
1. Configure common ports (3000, 5000, 8000, 8080) at creation time
2. Use path-based routing: `https://app-url.com/port/3000/`
3. Internal reverse proxy handles routing

For advanced use cases, add **Option B** with container-based proxy.

### Files to Modify

| File | Changes |
|------|---------|
| `types.py` | Add `ExposedPort`, `PortAuth` dataclasses |
| `deployer.py` | Add multi-port configuration, `add_internal_port()` |
| `sandbox.py` | Add `expose_port()`, `unexpose_port()`, `get_exposed_ports()` |
| `async_sandbox.py` | Add async port exposure methods |
| Container image | Add internal reverse proxy (Caddy/nginx) |

---

## Implementation Order

Based on dependencies and impact:

### Phase 1: Foundation (Week 1-2)
1. **Process Logs API** - Low effort, enables streaming work
2. **`git_checkout()`** - Low effort, quick win
3. **Snapshot/Restore API** - Core infrastructure for hibernation

### Phase 2: Streaming (Week 2-3)
4. **`exec_stream()`** - Build on executor, needed for log streaming

### Phase 3: Advanced Features (Week 3-4)
5. **Auto-Sleep / Hibernate** - Depends on snapshot API
6. **Sessions API** - Requires executor refactoring

### Phase 4: Port Exposure (Week 4-5)
7. **Dynamic Port Exposure** - Requires container image changes and App Platform configuration

---

## Testing Strategy

### Unit Tests
- Mock pexpect for executor tests
- Mock Spaces client for snapshot tests
- Test event parsing for streaming

### Integration Tests
- Real sandbox creation/deletion
- File transfer with actual Spaces
- Snapshot create/restore round-trip

### Functional Tests
- Long-running command streaming
- Multi-session isolation
- Hibernation/wake cycle
- Port exposure with HTTP requests

---

## API Summary

After implementation, the SDK will support:

```python
# Streaming execution
stream = sandbox.exec_stream("npm run build")
for event in stream:
    print(event.data)

# Process logs
sandbox.launch_process("npm start")
logs = sandbox.get_process_logs(pid)
for line in sandbox.stream_process_logs(pid):
    print(line)

# Git checkout
sandbox.git_checkout("https://github.com/user/repo.git", "/workspace")

# Sessions
session = sandbox.create_session("dev", env={"NODE_ENV": "development"})
session.exec("npm start")

# Snapshots
meta = sandbox.create_snapshot(paths=["/workspace"])
sandbox.restore_snapshot(meta.snapshot_id)

# Hibernation
sandbox.hibernate()
sandbox.wake()

# Port exposure
port_info = sandbox.expose_port(3000)
print(f"Preview at: {port_info.url}")
```

This brings the SDK to feature parity with Cloudflare Sandbox SDK while maintaining the unique advantages of pre-warmed pools and troubleshooting capabilities.
