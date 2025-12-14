"""File system operations for sandbox containers.

This module provides methods for reading, writing, and managing files
on the remote sandbox container.
"""

import base64
import os
import shlex
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from .exceptions import FileOperationError, SpacesNotConfiguredError
from .executor import Executor
from .types import FileInfo

if TYPE_CHECKING:
    from .spaces import SpacesClient


class FileSystem:
    """File system operations for a sandbox container."""

    # Default large file threshold (5 MB)
    DEFAULT_LARGE_FILE_THRESHOLD = 5 * 1024 * 1024

    @staticmethod
    def _error_detail(result) -> str:
        """Build error detail from command result, handling empty stderr."""
        detail = result.stderr.strip() if result.stderr else ""
        if not detail and result.stdout:
            detail = result.stdout.strip()
        if not detail:
            detail = f"exit code {result.exit_code}"
        return detail

    def __init__(
        self,
        executor: Executor,
        spaces_client: Optional["SpacesClient"] = None,
        sandbox_id: Optional[str] = None,
    ):
        """Initialize the file system handler.

        Args:
            executor: The executor instance for running commands
            spaces_client: Optional SpacesClient for large file transfers
            sandbox_id: Sandbox ID (required for Spaces operations)
        """
        self._executor = executor
        self._spaces_client = spaces_client
        self._sandbox_id = sandbox_id

    def read_file(self, path: str, binary: bool = False) -> str | bytes:
        """Read a file from the sandbox.

        Args:
            path: The path to the file
            binary: If True, return bytes (uses base64 encoding internally)

        Returns:
            The file content as string or bytes

        Raises:
            FileOperationError: If the file cannot be read
        """
        if binary:
            # Use base64 for binary files
            result = self._executor.execute(f"base64 {shlex.quote(path)}")
            if not result.success:
                raise FileOperationError(
                    f"Failed to read file {path}: {self._error_detail(result)}"
                )
            try:
                return base64.b64decode(result.stdout.replace("\n", ""))
            except Exception as e:
                raise FileOperationError(f"Failed to decode file content: {e}")
        else:
            result = self._executor.execute(f"cat {shlex.quote(path)}")
            if not result.success:
                raise FileOperationError(
                    f"Failed to read file {path}: {self._error_detail(result)}"
                )
            return result.stdout

    def write_file(
        self, path: str, content: str | bytes, binary: bool = False
    ) -> None:
        """Write content to a file on the sandbox.

        Args:
            path: The path to the file
            content: The content to write
            binary: If True, content is bytes (kept for API compatibility)

        Raises:
            FileOperationError: If the file cannot be written
        """
        # Always use base64 encoding to avoid shell escaping issues
        # (special chars like $, `, !, %, newlines, etc.)
        if isinstance(content, str):
            content = content.encode("utf-8")
        b64_content = base64.b64encode(content).decode("ascii")
        result = self._executor.execute(
            f"echo {shlex.quote(b64_content)} | base64 -d > {shlex.quote(path)}"
        )

        if not result.success:
            raise FileOperationError(f"Failed to write file {path}: {self._error_detail(result)}")

    def append_file(self, path: str, content: str | bytes) -> None:
        """Append content to a file on the sandbox.

        Args:
            path: The path to the file
            content: The content to append

        Raises:
            FileOperationError: If the file cannot be written
        """
        # Always use base64 encoding to avoid shell escaping issues
        if isinstance(content, str):
            content = content.encode("utf-8")
        b64_content = base64.b64encode(content).decode("ascii")
        result = self._executor.execute(
            f"echo {shlex.quote(b64_content)} | base64 -d >> {shlex.quote(path)}"
        )
        if not result.success:
            raise FileOperationError(f"Failed to append to file {path}: {self._error_detail(result)}")

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a local file to the sandbox.

        Args:
            local_path: Path to the local file
            remote_path: Destination path on the sandbox

        Raises:
            FileOperationError: If the upload fails
        """
        local = Path(local_path)
        if not local.exists():
            raise FileOperationError(f"Local file not found: {local_path}")

        content = local.read_bytes()
        self.write_file(remote_path, content, binary=True)

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the sandbox to local filesystem.

        Args:
            remote_path: Path to the file on the sandbox
            local_path: Destination path locally

        Raises:
            FileOperationError: If the download fails
        """
        content = self.read_file(remote_path, binary=True)
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(content)

    def list_dir(self, path: str = ".") -> list[FileInfo]:
        """List directory contents.

        Args:
            path: The directory path to list

        Returns:
            List of FileInfo objects

        Raises:
            FileOperationError: If the directory cannot be listed
        """
        result = self._executor.execute(f"ls -la {shlex.quote(path)}")
        if not result.success:
            raise FileOperationError(
                f"Failed to list directory {path}: {self._error_detail(result)}"
            )

        files = []
        lines = result.stdout.strip().split("\n")

        for line in lines:
            # Skip header line and empty lines
            if not line or line.startswith("total "):
                continue

            parts = line.split()
            if len(parts) < 9:
                continue

            permissions = parts[0]
            size = int(parts[4]) if parts[4].isdigit() else None
            name = " ".join(parts[8:])  # Handle filenames with spaces

            # Skip . and ..
            if name in (".", ".."):
                continue

            is_dir = permissions.startswith("d")
            full_path = f"{path.rstrip('/')}/{name}" if path != "." else name

            files.append(
                FileInfo(
                    name=name,
                    path=full_path,
                    is_dir=is_dir,
                    size=size,
                    permissions=permissions,
                )
            )

        return files

    def mkdir(self, path: str, recursive: bool = True) -> None:
        """Create a directory.

        Args:
            path: The directory path to create
            recursive: If True, create parent directories as needed

        Raises:
            FileOperationError: If the directory cannot be created
        """
        flag = "-p" if recursive else ""
        result = self._executor.execute(f"mkdir {flag} {shlex.quote(path)}")
        if not result.success:
            raise FileOperationError(
                f"Failed to create directory {path}: {self._error_detail(result)}"
            )

    def rm(self, path: str, recursive: bool = False, force: bool = True) -> None:
        """Remove a file or directory.

        Args:
            path: The path to remove
            recursive: If True, remove directories recursively
            force: If True, ignore nonexistent files

        Raises:
            FileOperationError: If the removal fails
        """
        flags = []
        if recursive:
            flags.append("-r")
        if force:
            flags.append("-f")

        flag_str = " ".join(flags)
        result = self._executor.execute(f"rm {flag_str} {shlex.quote(path)}")
        if not result.success:
            raise FileOperationError(f"Failed to remove {path}: {self._error_detail(result)}")

    def exists(self, path: str) -> bool:
        """Check if a path exists.

        Args:
            path: The path to check

        Returns:
            True if the path exists
        """
        result = self._executor.execute(
            f'test -e {shlex.quote(path)} && echo "EXISTS" || echo "MISSING"'
        )
        return "EXISTS" in result.stdout

    def is_file(self, path: str) -> bool:
        """Check if a path is a regular file.

        Args:
            path: The path to check

        Returns:
            True if the path is a regular file
        """
        result = self._executor.execute(
            f'test -f {shlex.quote(path)} && echo "FILE" || echo "NOT_FILE"'
        )
        return "FILE" in result.stdout and "NOT_FILE" not in result.stdout

    def is_dir(self, path: str) -> bool:
        """Check if a path is a directory.

        Args:
            path: The path to check

        Returns:
            True if the path is a directory
        """
        result = self._executor.execute(
            f'test -d {shlex.quote(path)} && echo "DIR" || echo "NOT_DIR"'
        )
        return "DIR" in result.stdout and "NOT_DIR" not in result.stdout

    def copy(self, src: str, dst: str, recursive: bool = False) -> None:
        """Copy a file or directory.

        Args:
            src: Source path
            dst: Destination path
            recursive: If True, copy directories recursively

        Raises:
            FileOperationError: If the copy fails
        """
        flag = "-r" if recursive else ""
        result = self._executor.execute(
            f"cp {flag} {shlex.quote(src)} {shlex.quote(dst)}"
        )
        if not result.success:
            raise FileOperationError(f"Failed to copy {src} to {dst}: {self._error_detail(result)}")

    def move(self, src: str, dst: str) -> None:
        """Move a file or directory.

        Args:
            src: Source path
            dst: Destination path

        Raises:
            FileOperationError: If the move fails
        """
        result = self._executor.execute(f"mv {shlex.quote(src)} {shlex.quote(dst)}")
        if not result.success:
            raise FileOperationError(f"Failed to move {src} to {dst}: {self._error_detail(result)}")

    def chmod(self, path: str, mode: str) -> None:
        """Change file permissions.

        Args:
            path: The file path
            mode: The permission mode (e.g., "755", "u+x")

        Raises:
            FileOperationError: If the operation fails
        """
        result = self._executor.execute(f"chmod {mode} {shlex.quote(path)}")
        if not result.success:
            raise FileOperationError(
                f"Failed to change permissions on {path}: {self._error_detail(result)}"
            )

    def get_size(self, path: str) -> int:
        """Get the size of a file in bytes.

        Args:
            path: The file path

        Returns:
            File size in bytes

        Raises:
            FileOperationError: If the operation fails
        """
        result = self._executor.execute(f"stat -c%s {shlex.quote(path)} 2>/dev/null || stat -f%z {shlex.quote(path)}")
        if not result.success:
            raise FileOperationError(f"Failed to get size of {path}: {self._error_detail(result)}")
        try:
            return int(result.stdout.strip())
        except ValueError:
            raise FileOperationError(f"Invalid size returned for {path}")

    def _get_large_file_threshold(self) -> int:
        """Get the configured large file threshold.

        Returns:
            Threshold in bytes
        """
        threshold_str = os.environ.get("SANDBOX_LARGE_FILE_THRESHOLD")
        if threshold_str:
            try:
                return int(threshold_str)
            except ValueError:
                pass
        return self.DEFAULT_LARGE_FILE_THRESHOLD

    def _require_spaces(self) -> None:
        """Verify Spaces is configured.

        Raises:
            SpacesNotConfiguredError: If Spaces is not configured
        """
        if self._spaces_client is None:
            raise SpacesNotConfiguredError(
                "Spaces not configured. Pass spaces_config to Sandbox.create() for large file transfers."
            )
        if self._sandbox_id is None:
            raise SpacesNotConfiguredError("Sandbox ID not available for Spaces operations.")

    def upload_large(
        self,
        local_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        cleanup: bool = True,
    ) -> None:
        """Upload a large file to the sandbox via DO Spaces.

        For files >= 5MB, this uses Spaces as an intermediary:
        1. Uploads file from client to Spaces (authenticated via boto3)
        2. Generates a time-limited presigned URL (15 min default)
        3. Sandbox downloads using curl with the presigned URL
        4. Deletes Spaces object after transfer (default: True)

        Args:
            local_path: Path to local file
            remote_path: Destination path on sandbox
            progress_callback: Optional callback(bytes_transferred) for progress
            cleanup: If True, delete Spaces object after transfer (default: True)

        Raises:
            SpacesNotConfiguredError: If Spaces is not configured
            FileOperationError: If the transfer fails
        """
        local = Path(local_path)
        if not local.exists():
            raise FileOperationError(f"Local file not found: {local_path}")

        file_size = local.stat().st_size
        threshold = self._get_large_file_threshold()

        # For small files, use regular upload
        if file_size < threshold:
            self.upload_file(local_path, remote_path)
            return

        # Large file - require Spaces
        self._require_spaces()

        filename = local.name
        key = self._spaces_client.generate_key(self._sandbox_id, filename, "upload")

        try:
            # Step 1: Upload to Spaces (authenticated via boto3)
            self._spaces_client.upload_file(local_path, key, progress_callback)

            # Step 2: Generate presigned download URL (15 min expiry)
            presigned_url = self._spaces_client.generate_presigned_download_url(key)

            # Step 3: Download to sandbox using curl with presigned URL
            parent_dir = os.path.dirname(remote_path)
            if parent_dir:
                self._executor.execute(f"mkdir -p {shlex.quote(parent_dir)}")

            # Use curl to download - presigned URL contains auth in query params
            # Combine curl + stat in same command to avoid race condition between
            # separate executor connections (file may not be visible in new connection
            # immediately after download completes)
            result = self._executor.execute(
                f"curl -sSfL -o {shlex.quote(remote_path)} {shlex.quote(presigned_url)} && "
                f"stat {shlex.quote(remote_path)} >/dev/null 2>&1",
                timeout=600,  # 10 minute timeout for large downloads
            )

            if not result.success:
                raise FileOperationError(
                    f"Failed to download file to sandbox: {self._error_detail(result)}"
                )

        finally:
            # Step 4: Cleanup (default: True for presigned URL approach)
            if cleanup:
                try:
                    self._spaces_client.delete_object(key)
                except Exception:
                    pass  # Best effort cleanup

    def download_large(
        self,
        remote_path: str,
        local_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        cleanup: bool = True,
    ) -> None:
        """Download a large file from the sandbox via DO Spaces.

        For files >= 5MB, this uses Spaces as an intermediary:
        1. Generates a time-limited presigned upload URL (15 min default)
        2. Sandbox uploads using curl with the presigned URL
        3. Client downloads from Spaces (authenticated via boto3)
        4. Deletes Spaces object after transfer (default: True)

        Args:
            remote_path: Path to file on sandbox
            local_path: Destination path locally
            progress_callback: Optional callback(bytes_transferred) for progress
            cleanup: If True, delete Spaces object after transfer (default: True)

        Raises:
            SpacesNotConfiguredError: If Spaces is not configured
            FileOperationError: If the transfer fails
        """
        # Check file size
        file_size = self.get_size(remote_path)
        threshold = self._get_large_file_threshold()

        # For small files, use regular download
        if file_size < threshold:
            self.download_file(remote_path, local_path)
            return

        # Large file - require Spaces
        self._require_spaces()

        filename = os.path.basename(remote_path)
        key = self._spaces_client.generate_key(self._sandbox_id, filename, "download")

        try:
            # Step 1: Generate presigned upload URL (15 min expiry)
            presigned_url = self._spaces_client.generate_presigned_upload_url(key)

            # Step 2: Upload from sandbox to Spaces using curl with presigned URL
            result = self._executor.execute(
                f"curl -sSfL -X PUT -T {shlex.quote(remote_path)} {shlex.quote(presigned_url)}",
                timeout=600,  # 10 minute timeout for large uploads
            )

            if not result.success:
                raise FileOperationError(
                    f"Failed to upload file from sandbox: {self._error_detail(result)}"
                )

            # Verify upload succeeded
            if not self._spaces_client.object_exists(key):
                raise FileOperationError(
                    f"File upload appeared to succeed but object not found in Spaces"
                )

            # Step 3: Download from Spaces to local (authenticated via boto3)
            local = Path(local_path)
            local.parent.mkdir(parents=True, exist_ok=True)
            self._spaces_client.download_file(key, local_path, progress_callback)

        finally:
            # Step 4: Cleanup (default: True for presigned URL approach)
            if cleanup:
                try:
                    self._spaces_client.delete_object(key)
                except Exception:
                    pass  # Best effort cleanup

    @property
    def has_spaces(self) -> bool:
        """Check if Spaces is configured for large file transfers.

        Returns:
            True if Spaces client is available
        """
        return self._spaces_client is not None
