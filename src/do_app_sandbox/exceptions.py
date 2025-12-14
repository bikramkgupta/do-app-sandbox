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
