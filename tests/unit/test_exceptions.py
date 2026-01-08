"""Tests for exceptions.py - Exception hierarchy tests."""

import pytest

from do_app_sandbox.exceptions import (
    # Base
    SandboxError,
    # Sandbox lifecycle
    SandboxCreationError,
    SandboxNotReadyError,
    SandboxNotFoundError,
    # Command execution
    CommandExecutionError,
    CommandTimeoutError,
    # File operations
    FileOperationError,
    ConnectionError,
    # Spaces
    SpacesNotConfiguredError,
    # Image validation
    ImageNotValidatedError,
    ImageValidationError,
    # Pool/Manager
    PoolError,
    PoolExhaustedError,
    PoolShutdownError,
    WarmUpTimeoutError,
    # Snapshot
    SnapshotError,
    SnapshotNotFoundError,
    SnapshotUploadError,
    SnapshotRestoreError,
    # Service mode
    ServiceModeError,
    ServiceNotAvailableError,
    ServiceConnectionError,
    # Hibernation
    HibernationError,
    SandboxHibernatedError,
)


class TestExceptionHierarchy:
    """Test that exception hierarchy is correct."""

    def test_sandbox_error_is_base(self):
        """SandboxError is the base for all exceptions."""
        assert issubclass(SandboxCreationError, SandboxError)
        assert issubclass(SandboxNotReadyError, SandboxError)
        assert issubclass(SandboxNotFoundError, SandboxError)
        assert issubclass(CommandExecutionError, SandboxError)
        assert issubclass(CommandTimeoutError, SandboxError)
        assert issubclass(FileOperationError, SandboxError)
        assert issubclass(ConnectionError, SandboxError)
        assert issubclass(SpacesNotConfiguredError, SandboxError)
        assert issubclass(ImageNotValidatedError, SandboxError)
        assert issubclass(ImageValidationError, SandboxError)

    def test_pool_error_hierarchy(self):
        """Pool errors inherit from PoolError -> SandboxError."""
        assert issubclass(PoolError, SandboxError)
        assert issubclass(PoolExhaustedError, PoolError)
        assert issubclass(PoolShutdownError, PoolError)
        assert issubclass(WarmUpTimeoutError, PoolError)

    def test_snapshot_error_hierarchy(self):
        """SnapshotError subclasses inherit correctly."""
        assert issubclass(SnapshotError, SandboxError)
        assert issubclass(SnapshotNotFoundError, SnapshotError)
        assert issubclass(SnapshotUploadError, SnapshotError)
        assert issubclass(SnapshotRestoreError, SnapshotError)

    def test_service_mode_error_hierarchy(self):
        """ServiceModeError subclasses inherit correctly."""
        assert issubclass(ServiceModeError, SandboxError)
        assert issubclass(ServiceNotAvailableError, ServiceModeError)
        assert issubclass(ServiceConnectionError, ServiceModeError)

    def test_hibernation_error_hierarchy(self):
        """HibernationError subclasses inherit correctly."""
        assert issubclass(HibernationError, SandboxError)
        assert issubclass(SandboxHibernatedError, HibernationError)


class TestExceptionMessages:
    """Test that exceptions have descriptive messages."""

    def test_sandbox_creation_error_message(self):
        """SandboxCreationError stores message."""
        err = SandboxCreationError("Failed to create sandbox: quota exceeded")
        assert "quota exceeded" in str(err)

    def test_sandbox_not_found_error_message(self):
        """SandboxNotFoundError stores message."""
        err = SandboxNotFoundError("App abc123 not found")
        assert "abc123" in str(err)

    def test_command_timeout_error_message(self):
        """CommandTimeoutError stores message."""
        err = CommandTimeoutError("Command timed out after 120s")
        assert "120s" in str(err)

    def test_snapshot_not_found_error_message(self):
        """SnapshotNotFoundError stores message."""
        err = SnapshotNotFoundError("Snapshot snap-xyz not found")
        assert "snap-xyz" in str(err)

    def test_snapshot_upload_error_message(self):
        """SnapshotUploadError stores message."""
        err = SnapshotUploadError("Failed to upload to Spaces")
        assert "Spaces" in str(err)

    def test_snapshot_restore_error_message(self):
        """SnapshotRestoreError stores message."""
        err = SnapshotRestoreError("Failed to extract archive")
        assert "extract" in str(err)

    def test_service_not_available_error_message(self):
        """ServiceNotAvailableError stores message."""
        err = ServiceNotAvailableError("Service mode required for streaming")
        assert "streaming" in str(err)

    def test_service_connection_error_message(self):
        """ServiceConnectionError stores message."""
        err = ServiceConnectionError("Connection refused to sandbox API")
        assert "Connection" in str(err)

    def test_sandbox_hibernated_error_message(self):
        """SandboxHibernatedError stores message."""
        err = SandboxHibernatedError("Sandbox is hibernated, call wake() first")
        assert "hibernated" in str(err)

    def test_spaces_not_configured_error_message(self):
        """SpacesNotConfiguredError stores message."""
        err = SpacesNotConfiguredError("Set SPACES_BUCKET environment variable")
        assert "SPACES_BUCKET" in str(err)

    def test_pool_exhausted_error_message(self):
        """PoolExhaustedError stores message."""
        err = PoolExhaustedError("Pool empty and on_empty='fail'")
        assert "Pool empty" in str(err)


class TestExceptionRaising:
    """Test that exceptions can be raised and caught."""

    def test_raise_sandbox_error(self):
        """Can raise and catch SandboxError."""
        with pytest.raises(SandboxError):
            raise SandboxError("Test error")

    def test_catch_specific_exception(self):
        """Specific exceptions can be caught."""
        with pytest.raises(SnapshotNotFoundError):
            raise SnapshotNotFoundError("Snapshot not found")

    def test_catch_parent_exception(self):
        """Child exceptions can be caught by parent type."""
        with pytest.raises(SnapshotError):
            raise SnapshotNotFoundError("Snapshot not found")

        with pytest.raises(SandboxError):
            raise SnapshotNotFoundError("Snapshot not found")

    def test_catch_service_errors_as_sandbox_error(self):
        """Service mode errors can be caught as SandboxError."""
        with pytest.raises(SandboxError):
            raise ServiceConnectionError("Connection failed")

    def test_catch_hibernation_errors_as_sandbox_error(self):
        """Hibernation errors can be caught as SandboxError."""
        with pytest.raises(SandboxError):
            raise SandboxHibernatedError("Already hibernated")
