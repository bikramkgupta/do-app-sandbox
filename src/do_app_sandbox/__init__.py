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
from .sandbox import Sandbox
from .async_sandbox import AsyncSandbox

# Environment variable constants
from .sandbox import ENV_REGISTRY, ENV_REGION
from .deployer import DEFAULT_REGION, DEFAULT_INSTANCE_SIZE

# Types
from .types import (
    CommandResult,
    ProcessInfo,
    FileInfo,
    AppInfo,
    SpacesConfig,
    ImageInfo,
    ValidationResult,
)

# Exceptions
from .exceptions import (
    SandboxError,
    SandboxCreationError,
    SandboxNotFoundError,
    SandboxNotReadyError,
    CommandExecutionError,
    CommandTimeoutError,
    FileOperationError,
    ConnectionError,
    SpacesNotConfiguredError,
    ImageNotValidatedError,
    ImageValidationError,
)

# Image registry
from .image_registry import ImageRegistry

__all__ = [
    # Main classes
    "Sandbox",
    "AsyncSandbox",
    # Image management
    "ImageRegistry",
    # Configuration constants
    "ENV_REGISTRY",
    "ENV_REGION",
    "DEFAULT_REGION",
    "DEFAULT_INSTANCE_SIZE",
    # Types
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
]
