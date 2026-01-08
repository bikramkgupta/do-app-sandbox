"""Snapshot management for sandbox state persistence.

This module provides functionality to create, restore, list, and delete
snapshots of sandbox filesystem state. Snapshots are stored in DO Spaces
and include dependencies (node_modules, .venv) for rapid restoration.

Typical use cases:
- Hibernate idle sandboxes (snapshot + delete for cost savings)
- Pre-warm sandboxes with common dependencies
- Create checkpoints during long-running agent tasks
"""

import json
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .exceptions import (
    SnapshotError,
    SnapshotNotFoundError,
    SnapshotUploadError,
    SnapshotRestoreError,
    SpacesNotConfiguredError,
)
from .spaces import SpacesClient
from .types import SnapshotMetadata, SpacesConfig

if TYPE_CHECKING:
    from .sandbox import Sandbox

# Default snapshot prefix in Spaces
DEFAULT_SNAPSHOT_PREFIX = "snapshots/"

# Default paths to snapshot
DEFAULT_SNAPSHOT_PATHS = ["/workspace"]

# Default exclude patterns - keep dependencies, exclude caches
DEFAULT_EXCLUDE_PATTERNS = [
    # Python bytecode and caches
    "*.pyc",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    # Git internals (keep .git for branch info)
    ".git/objects",
    ".git/lfs",
    # Node.js caches (keep node_modules itself)
    "node_modules/.cache",
    ".npm",
    ".yarn/cache",
    # Temp files and logs
    "*.log",
    "*.tmp",
    ".env",
    ".env.local",
    # Coverage and test artifacts
    "coverage/",
    ".coverage",
    "htmlcov/",
    # Build artifacts that can be regenerated
    "dist/",
    "build/",
    "*.egg-info/",
]


class SnapshotManager:
    """Manages sandbox snapshots in DO Spaces.

    Snapshots are tar.gz archives of sandbox filesystem paths stored in
    DO Spaces. Metadata is stored alongside each archive as JSON.

    Storage layout:
        snapshots/
        ├── snap-abc123def456/
        │   ├── metadata.json
        │   └── archive.tar.gz
        ├── hibernate-app123-1704672000/
        │   ├── metadata.json
        │   └── archive.tar.gz
        └── ...
    """

    def __init__(
        self,
        spaces_config: Optional[SpacesConfig] = None,
        prefix: str = DEFAULT_SNAPSHOT_PREFIX
    ):
        """Initialize the snapshot manager.

        Args:
            spaces_config: Configuration for DO Spaces. If not provided,
                          will attempt to create from environment variables.
            prefix: Prefix for snapshot objects in Spaces bucket.

        Raises:
            SpacesNotConfiguredError: If Spaces is not configured
        """
        if spaces_config is None:
            from .spaces import create_spaces_config_from_env
            spaces_config = create_spaces_config_from_env()
            if spaces_config is None:
                raise SpacesNotConfiguredError(
                    "Spaces configuration required for snapshots. "
                    "Set SPACES_BUCKET, SPACES_REGION, SPACES_ACCESS_KEY, "
                    "and SPACES_SECRET_KEY environment variables."
                )

        self._spaces = SpacesClient(spaces_config)
        self._prefix = prefix.rstrip("/") + "/"

    def create_snapshot(
        self,
        sandbox: "Sandbox",
        snapshot_id: Optional[str] = None,
        paths: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        timeout: int = 600
    ) -> SnapshotMetadata:
        """Create a snapshot of sandbox filesystem.

        Snapshots include dependencies (node_modules, .venv) by default
        for rapid startup. Only caches and temp files are excluded.

        Args:
            sandbox: Sandbox to snapshot
            snapshot_id: Optional unique ID (auto-generated if not provided)
            paths: Paths to include (default: ["/workspace"])
            exclude_patterns: Patterns to exclude (default: caches only)
            description: Optional human-readable description
            tags: Optional key-value tags for organization
            timeout: Timeout for tar/upload operations in seconds

        Returns:
            SnapshotMetadata with snapshot details

        Raises:
            SnapshotError: If snapshot creation fails
            SnapshotUploadError: If upload to Spaces fails
        """
        # Generate snapshot ID if not provided
        snapshot_id = snapshot_id or f"snap-{uuid.uuid4().hex[:12]}"
        paths = paths or DEFAULT_SNAPSHOT_PATHS
        exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS

        # Build tar command with exclusions
        excludes = " ".join(f"--exclude='{p}'" for p in exclude_patterns)
        # Convert absolute paths to relative for tar
        paths_str = " ".join(p.lstrip("/") for p in paths)
        archive = f"/tmp/snapshot_{snapshot_id}.tar.gz"

        # Create the archive
        tar_cmd = f"tar {excludes} -czf {archive} -C / {paths_str}"
        result = sandbox.exec(tar_cmd, timeout=timeout)

        if not result.success:
            raise SnapshotError(f"Failed to create archive: {result.stderr}")

        # Get archive size
        size_result = sandbox.exec(f"stat -c %s {archive}")
        if not size_result.success:
            raise SnapshotError(f"Failed to get archive size: {size_result.stderr}")
        size_bytes = int(size_result.stdout.strip())

        # Upload to Spaces using presigned URL
        spaces_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
        upload_url = self._spaces.generate_presigned_upload_url(
            spaces_key,
            expires_in=3600
        )

        # Use curl to upload from sandbox (sandbox uploads directly to Spaces)
        upload_cmd = f"curl -sSf -X PUT -T {archive} '{upload_url}'"
        upload_result = sandbox.exec(upload_cmd, timeout=timeout)

        if not upload_result.success:
            raise SnapshotUploadError(
                f"Failed to upload snapshot: {upload_result.stderr}"
            )

        # Create and save metadata
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

        # Cleanup archive in sandbox
        sandbox.exec(f"rm -f {archive}")

        return metadata

    def restore_snapshot(
        self,
        sandbox: "Sandbox",
        snapshot_id: str,
        target_path: str = "/",
        timeout: int = 600
    ) -> bool:
        """Restore a snapshot to sandbox.

        Args:
            sandbox: Sandbox to restore to
            snapshot_id: ID of snapshot to restore
            target_path: Base path for extraction (default: /)
            timeout: Timeout for download/extract operations

        Returns:
            True if restoration succeeded

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
            SnapshotRestoreError: If restoration fails
        """
        # Verify snapshot exists
        metadata = self.get_snapshot(snapshot_id)
        if metadata is None:
            raise SnapshotNotFoundError(f"Snapshot not found: {snapshot_id}")

        # Download via presigned URL
        spaces_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
        download_url = self._spaces.generate_presigned_download_url(
            spaces_key,
            expires_in=3600
        )
        archive = f"/tmp/restore_{snapshot_id}.tar.gz"

        # Download in sandbox
        download_cmd = f"curl -sSfL -o {archive} '{download_url}'"
        download_result = sandbox.exec(download_cmd, timeout=timeout)

        if not download_result.success:
            raise SnapshotRestoreError(
                f"Failed to download snapshot: {download_result.stderr}"
            )

        # Extract archive
        extract_cmd = f"tar -xzf {archive} -C {target_path}"
        extract_result = sandbox.exec(extract_cmd, timeout=timeout)

        if not extract_result.success:
            raise SnapshotRestoreError(
                f"Failed to extract snapshot: {extract_result.stderr}"
            )

        # Cleanup archive
        sandbox.exec(f"rm -f {archive}")

        return True

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """Get snapshot metadata.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            SnapshotMetadata or None if not found
        """
        key = f"{self._prefix}{snapshot_id}/metadata.json"
        try:
            content = self._spaces.get_object(key)
            data = json.loads(content.decode())
            return SnapshotMetadata(**data)
        except Exception:
            return None

    def list_snapshots(
        self,
        prefix: Optional[str] = None,
        image: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> List[SnapshotMetadata]:
        """List all snapshots.

        Args:
            prefix: Optional prefix filter for snapshot IDs
            image: Optional filter by sandbox image
            tags: Optional filter by tags (all must match)

        Returns:
            List of SnapshotMetadata, sorted by created_at descending
        """
        search_prefix = f"{self._prefix}{prefix}" if prefix else self._prefix
        keys = self._spaces.list_objects(search_prefix)

        snapshots = []
        for key in keys:
            if key.endswith("/metadata.json"):
                # Extract snapshot_id from key
                # snapshots/snap-xxx/metadata.json -> snap-xxx
                parts = key.replace(self._prefix, "").split("/")
                if len(parts) >= 2:
                    snapshot_id = parts[0]
                    meta = self.get_snapshot(snapshot_id)
                    if meta:
                        # Apply filters
                        if image and meta.sandbox_image != image:
                            continue
                        if tags:
                            if not all(
                                meta.tags.get(k) == v
                                for k, v in tags.items()
                            ):
                                continue
                        snapshots.append(meta)

        # Sort by created_at descending (newest first)
        return sorted(snapshots, key=lambda x: x.created_at, reverse=True)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            True if deletion succeeded
        """
        # Delete archive
        archive_key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
        try:
            self._spaces.delete_object(archive_key)
        except Exception:
            pass  # Archive may not exist

        # Delete metadata
        metadata_key = f"{self._prefix}{snapshot_id}/metadata.json"
        try:
            self._spaces.delete_object(metadata_key)
        except Exception:
            pass  # Metadata may not exist

        return True

    def snapshot_exists(self, snapshot_id: str) -> bool:
        """Check if a snapshot exists.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            True if snapshot exists
        """
        key = f"{self._prefix}{snapshot_id}/metadata.json"
        return self._spaces.object_exists(key)

    def get_snapshot_download_url(
        self,
        snapshot_id: str,
        expires_in: int = 3600
    ) -> str:
        """Get a presigned URL to download a snapshot archive.

        Args:
            snapshot_id: Snapshot identifier
            expires_in: URL expiration in seconds

        Returns:
            Presigned download URL

        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
        """
        if not self.snapshot_exists(snapshot_id):
            raise SnapshotNotFoundError(f"Snapshot not found: {snapshot_id}")

        key = f"{self._prefix}{snapshot_id}/archive.tar.gz"
        return self._spaces.generate_presigned_download_url(key, expires_in)

    def _save_metadata(self, metadata: SnapshotMetadata) -> None:
        """Save metadata to Spaces.

        Args:
            metadata: SnapshotMetadata to save
        """
        key = f"{self._prefix}{metadata.snapshot_id}/metadata.json"
        content = json.dumps(asdict(metadata), indent=2).encode()
        self._spaces.put_object(key, content, content_type="application/json")

    def copy_snapshot(
        self,
        source_id: str,
        target_id: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> SnapshotMetadata:
        """Create a copy of an existing snapshot.

        Args:
            source_id: Source snapshot ID
            target_id: Target snapshot ID (auto-generated if not provided)
            description: Optional new description
            tags: Optional new tags (merged with source tags)

        Returns:
            New SnapshotMetadata

        Raises:
            SnapshotNotFoundError: If source snapshot doesn't exist
        """
        source = self.get_snapshot(source_id)
        if source is None:
            raise SnapshotNotFoundError(f"Snapshot not found: {source_id}")

        target_id = target_id or f"snap-{uuid.uuid4().hex[:12]}"

        # Copy archive
        source_key = f"{self._prefix}{source_id}/archive.tar.gz"
        target_key = f"{self._prefix}{target_id}/archive.tar.gz"

        self._spaces.client.copy_object(
            Bucket=self._spaces.bucket,
            CopySource={"Bucket": self._spaces.bucket, "Key": source_key},
            Key=target_key
        )

        # Create new metadata
        merged_tags = {**source.tags, **(tags or {})}
        metadata = SnapshotMetadata(
            snapshot_id=target_id,
            created_at=time.time(),
            sandbox_image=source.sandbox_image,
            size_bytes=source.size_bytes,
            paths=source.paths,
            description=description or f"Copy of {source_id}",
            tags=merged_tags
        )
        self._save_metadata(metadata)

        return metadata
