"""Type definitions for the App Platform Sandbox SDK."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


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
