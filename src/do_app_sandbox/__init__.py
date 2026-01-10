"""App Platform Sandbox SDK - Sandbox-like capabilities for DigitalOcean App Platform.

This SDK provides a Vercel Sandbox / Koyeb Sandbox-like interface for running
code in isolated containers on DigitalOcean App Platform.

Setup:
    First, build and push sandbox images to your DOCR registry:

    $ sandbox setup --registry YOUR_REGISTRY

    Or set environment variables:

    $ export APP_SANDBOX_REGISTRY=your-registry
    $ export APP_SANDBOX_REGION=nyc  # optional, defaults to nyc

Example usage:

    Synchronous API:
    >>> from do_app_sandbox import Sandbox
    >>> sandbox = Sandbox.create(registry="my-registry", image="python")
    >>> result = sandbox.exec("python --version")
    >>> print(result.stdout)
    >>> sandbox.delete()

    Asynchronous API:
    >>> from do_app_sandbox import AsyncSandbox
    >>> sandbox = await AsyncSandbox.create(registry="my-registry", image="python")
    >>> result = await sandbox.exec("python --version")
    >>> await sandbox.delete()

    With environment variables (APP_SANDBOX_REGISTRY set):
    >>> sandbox = Sandbox.create(image="python")

    Context manager:
    >>> with Sandbox.create(registry="my-registry", image="python") as sandbox:
    ...     result = sandbox.exec("echo 'Hello World'")
    ...     print(result.stdout)
"""

__version__ = "0.1.0"

# Main classes
from .async_sandbox import AsyncSandbox
from .deployer import DEFAULT_INSTANCE_SIZE, DEFAULT_REGION

# Exceptions
from .exceptions import (
    CommandExecutionError,
    CommandTimeoutError,
    ConnectionError,
    FileOperationError,
    # Hibernation exceptions
    HibernationError,
    ImageNotValidatedError,
    ImageValidationError,
    PoolError,
    PoolExhaustedError,
    PoolShutdownError,
    SandboxCreationError,
    SandboxError,
    SandboxHibernatedError,
    SandboxNotFoundError,
    SandboxNotReadyError,
    ServiceConnectionError,
    # Service mode exceptions
    ServiceModeError,
    ServiceNotAvailableError,
    # Snapshot exceptions
    SnapshotError,
    SnapshotNotFoundError,
    SnapshotRestoreError,
    SnapshotUploadError,
    SpacesNotConfiguredError,
    WarmUpTimeoutError,
)

# Image registry
from .image_registry import ImageRegistry
from .manager import PoolConfig, PoolMetrics, SandboxManager

# Environment variable constants
from .sandbox import ENV_REGION, ENV_REGISTRY, Sandbox

# Service mode HTTP clients
from .service_client import AsyncSandboxServiceClient, SandboxServiceClient

# Snapshot management
from .snapshot import SnapshotManager

# Types
from .types import (
    AppInfo,
    # Existing types
    CommandResult,
    # Port exposure
    ExposedPort,
    FileInfo,
    # Git
    GitCredentials,
    HibernatedSandbox,
    HibernationConfig,
    ImageInfo,
    ProcessInfo,
    # Enums
    SandboxMode,
    SandboxState,
    # Configuration
    ServiceConfig,
    # Snapshots
    SnapshotMetadata,
    SpacesConfig,
    # Streaming
    StreamEvent,
    ValidationResult,
)

__all__ = [
    # Main classes
    "Sandbox",
    "AsyncSandbox",
    # Pool management
    "SandboxManager",
    "PoolConfig",
    "PoolMetrics",
    # Image management
    "ImageRegistry",
    # Snapshot management
    "SnapshotManager",
    # Service mode HTTP clients
    "SandboxServiceClient",
    "AsyncSandboxServiceClient",
    # Configuration constants
    "ENV_REGISTRY",
    "ENV_REGION",
    "DEFAULT_REGION",
    "DEFAULT_INSTANCE_SIZE",
    # Types - Enums
    "SandboxMode",
    "SandboxState",
    # Types - Configuration
    "ServiceConfig",
    "HibernationConfig",
    # Types - Streaming
    "StreamEvent",
    # Types - Snapshots
    "SnapshotMetadata",
    "HibernatedSandbox",
    # Types - Git
    "GitCredentials",
    # Types - Port exposure
    "ExposedPort",
    # Types - Existing
    "CommandResult",
    "ProcessInfo",
    "FileInfo",
    "AppInfo",
    "SpacesConfig",
    "ImageInfo",
    "ValidationResult",
    # Exceptions
    "SandboxError",
    "SandboxCreationError",
    "SandboxNotFoundError",
    "SandboxNotReadyError",
    "CommandExecutionError",
    "CommandTimeoutError",
    "FileOperationError",
    "ConnectionError",
    "SpacesNotConfiguredError",
    "ImageNotValidatedError",
    "ImageValidationError",
    "PoolError",
    "PoolExhaustedError",
    "PoolShutdownError",
    "WarmUpTimeoutError",
    # Snapshot exceptions
    "SnapshotError",
    "SnapshotNotFoundError",
    "SnapshotUploadError",
    "SnapshotRestoreError",
    # Service mode exceptions
    "ServiceModeError",
    "ServiceNotAvailableError",
    "ServiceConnectionError",
    # Hibernation exceptions
    "HibernationError",
    "SandboxHibernatedError",
]
