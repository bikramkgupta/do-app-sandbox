"""Custom exceptions for the App Platform Sandbox SDK."""


class SandboxError(Exception):
    """Base exception for all sandbox-related errors."""

    pass


class SandboxCreationError(SandboxError):
    """Raised when sandbox creation fails."""

    pass


class SandboxNotReadyError(SandboxError):
    """Raised when sandbox is not yet ready for operations."""

    pass


class SandboxNotFoundError(SandboxError):
    """Raised when a sandbox with the given ID cannot be found."""

    pass


class CommandExecutionError(SandboxError):
    """Raised when command execution fails."""

    pass


class CommandTimeoutError(SandboxError):
    """Raised when a command times out."""

    pass


class FileOperationError(SandboxError):
    """Raised when a file operation fails."""

    pass


class ConnectionError(SandboxError):
    """Raised when connection to the sandbox fails."""

    pass


class SpacesNotConfiguredError(SandboxError):
    """Raised when large file operation attempted without Spaces configuration."""

    pass


class ImageNotValidatedError(SandboxError):
    """Raised when trying to create sandbox with an unvalidated custom image."""

    pass


class ImageValidationError(SandboxError):
    """Raised when custom image validation fails."""

    pass


# Pool/Manager exceptions


class PoolError(SandboxError):
    """Base exception for pool-related errors."""

    pass


class PoolExhaustedError(PoolError):
    """Raised when pool is empty and on_empty='fail'."""

    pass


class PoolShutdownError(PoolError):
    """Raised when acquire() called after shutdown initiated."""

    pass


class WarmUpTimeoutError(PoolError):
    """Raised when warm_up() times out before pools reach target."""

    pass


# Snapshot exceptions


class SnapshotError(SandboxError):
    """Base exception for snapshot-related errors."""

    pass


class SnapshotNotFoundError(SnapshotError):
    """Raised when a snapshot with the given ID cannot be found."""

    pass


class SnapshotUploadError(SnapshotError):
    """Raised when snapshot upload to Spaces fails."""

    pass


class SnapshotRestoreError(SnapshotError):
    """Raised when snapshot restoration fails."""

    pass


# Service mode exceptions


class ServiceModeError(SandboxError):
    """Base exception for service mode errors."""

    pass


class ServiceNotAvailableError(ServiceModeError):
    """Raised when service mode operation attempted on worker sandbox."""

    pass


class ServiceConnectionError(ServiceModeError):
    """Raised when connection to sandbox service API fails."""

    pass


# Hibernation exceptions


class HibernationError(SandboxError):
    """Base exception for hibernation errors."""

    pass


class SandboxHibernatedError(HibernationError):
    """Raised when operation attempted on hibernated sandbox."""

    pass
