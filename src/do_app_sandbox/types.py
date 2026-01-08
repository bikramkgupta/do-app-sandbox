"""Type definitions for the App Platform Sandbox SDK."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Literal


# =============================================================================
# Enums
# =============================================================================


class SandboxMode(Enum):
    """Sandbox deployment mode."""

    WORKER = "worker"  # Default: doctl console execution
    SERVICE = "service"  # HTTP API with streaming support


class SandboxState(Enum):
    """Sandbox lifecycle states."""

    CREATING = "creating"
    ACTIVE = "active"
    HIBERNATED = "hibernated"  # Snapshot exists, sandbox deleted
    DELETED = "deleted"


# =============================================================================
# Configuration Types
# =============================================================================


@dataclass
class ServiceConfig:
    """Configuration for service mode sandboxes."""

    api_port: int = 8080
    proxy_ports: List[int] = field(default_factory=lambda: [3000, 5000, 8000])
    enable_file_api: bool = True
    enable_sessions: bool = True
    token: Optional[str] = None  # Auto-generated if not provided

    def __repr__(self) -> str:
        return f"ServiceConfig(api_port={self.api_port}, proxy_ports={self.proxy_ports})"


@dataclass
class HibernationConfig:
    """Configuration for sandbox hibernation (Cloudflare-aligned)."""

    enabled: bool = True
    sleep_after: int = 600  # Seconds of inactivity before hibernate (default: 10 min)

    def __repr__(self) -> str:
        return f"HibernationConfig(enabled={self.enabled}, sleep_after={self.sleep_after}s)"


# =============================================================================
# Streaming Types
# =============================================================================


@dataclass
class StreamEvent:
    """A single streaming output event from exec_stream()."""

    type: str  # "stdout", "stderr", "exit", "error"
    data: str
    timestamp: float

    @property
    def is_output(self) -> bool:
        """Returns True if this is stdout or stderr output."""
        return self.type in ("stdout", "stderr")

    @property
    def is_complete(self) -> bool:
        """Returns True if this is a terminal event (exit or error)."""
        return self.type in ("exit", "error")

    def __repr__(self) -> str:
        preview = self.data[:50] if len(self.data) > 50 else self.data
        return f"StreamEvent(type={self.type!r}, data={preview!r})"


# =============================================================================
# Snapshot Types
# =============================================================================


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

    def __repr__(self) -> str:
        size_mb = self.size_bytes / (1024 * 1024)
        return f"SnapshotMetadata(id={self.snapshot_id!r}, size={size_mb:.1f}MB)"


@dataclass
class HibernatedSandbox:
    """Reference to a hibernated sandbox for later wake()."""

    snapshot_id: str
    image: str
    mode: SandboxMode
    service_config: Optional[ServiceConfig]
    hibernated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"HibernatedSandbox(snapshot={self.snapshot_id!r}, image={self.image!r})"


# =============================================================================
# Git Types
# =============================================================================


@dataclass
class GitCredentials:
    """Credentials for private repository access."""

    username: Optional[str] = None
    token: Optional[str] = None  # Personal Access Token for HTTPS
    ssh_key: Optional[str] = None  # Private key content for SSH

    def __repr__(self) -> str:
        auth_type = "ssh" if self.ssh_key else "token" if self.token else "none"
        return f"GitCredentials(type={auth_type})"


# =============================================================================
# Port Exposure Types
# =============================================================================


@dataclass
class ExposedPort:
    """Information about an exposed port with public URL."""

    port: int
    url: str
    protocol: str = "https"  # "https" or "wss"
    created_at: float = 0

    def __repr__(self) -> str:
        return f"ExposedPort(port={self.port}, url={self.url!r})"


# =============================================================================
# Existing Types (unchanged)
# =============================================================================


@dataclass
class CommandResult:
    """Result of a command execution."""

    stdout: str
    stderr: str
    exit_code: int

    @property
    def success(self) -> bool:
        """Returns True if the command exited with code 0."""
        return self.exit_code == 0

    def __repr__(self) -> str:
        return f"CommandResult(exit_code={self.exit_code}, stdout={self.stdout[:50]!r}{'...' if len(self.stdout) > 50 else ''}, stderr={self.stderr[:50]!r}{'...' if len(self.stderr) > 50 else ''})"


@dataclass
class ProcessInfo:
    """Information about a running process."""

    pid: int
    command: str
    status: str
    cpu: Optional[str] = None
    memory: Optional[str] = None

    def __repr__(self) -> str:
        return f"ProcessInfo(pid={self.pid}, command={self.command!r}, status={self.status!r})"


@dataclass
class FileInfo:
    """Information about a file or directory."""

    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    permissions: Optional[str] = None

    def __repr__(self) -> str:
        type_str = "dir" if self.is_dir else "file"
        return f"FileInfo({type_str}: {self.path})"


@dataclass
class AppInfo:
    """Information about a deployed App Platform application."""

    app_id: str
    name: str
    status: str
    url: Optional[str] = None
    region: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __repr__(self) -> str:
        return f"AppInfo(id={self.app_id}, name={self.name!r}, status={self.status!r})"


@dataclass
class ValidationResult:
    """Result of custom image validation."""

    dockerfile_parsed: bool = False
    has_expose_8080: bool = False
    has_entrypoint: bool = False
    image_built: bool = False
    container_started: bool = False
    health_check_passed: bool = False
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Returns True if all validation checks passed."""
        return (
            self.dockerfile_parsed
            and self.has_expose_8080
            and self.has_entrypoint
            and self.image_built
            and self.container_started
            and self.health_check_passed
            and self.error is None
        )

    def __repr__(self) -> str:
        if self.is_valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, error={self.error!r})"


@dataclass
class ImageInfo:
    """Information about a registered custom image."""

    name: str
    dockerfile_path: str
    registry: str
    image_url: str
    status: str  # "validating" | "validated" | "failed"
    created_at: str
    validated_at: Optional[str] = None
    validation_pid: Optional[int] = None
    validation_log: Optional[str] = None
    validation_results: Optional[ValidationResult] = None

    @property
    def is_ready(self) -> bool:
        """Returns True if image is validated and ready for use."""
        return self.status == "validated"

    def __repr__(self) -> str:
        return f"ImageInfo(name={self.name!r}, status={self.status!r})"


@dataclass
class SpacesConfig:
    """Configuration for DO Spaces file transfers."""

    bucket: str
    region: str
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    endpoint: Optional[str] = None

    def __repr__(self) -> str:
        return f"SpacesConfig(bucket={self.bucket!r}, region={self.region!r}, endpoint={self.endpoint!r})"
