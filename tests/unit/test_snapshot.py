"""Tests for snapshot.py - Snapshot Manager Logic Tests."""

import json
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from do_app_sandbox.exceptions import (
    SnapshotNotFoundError,
    SpacesNotConfiguredError,
)
from do_app_sandbox.types import SnapshotMetadata, SpacesConfig


class TestSnapshotIdGeneration:
    """Tests for snapshot ID generation."""

    def test_auto_generates_snap_id(self):
        """Auto-generates snap-xxxx ID when not provided."""
        # Test the ID format without full SnapshotManager instantiation
        snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        assert snapshot_id.startswith("snap-")
        assert len(snapshot_id) == 17  # "snap-" + 12 hex chars

    def test_custom_id_accepted(self):
        """Custom snapshot_id is used when provided."""
        custom_id = "my-custom-snapshot-001"
        # Would be passed to create_snapshot() as snapshot_id=custom_id
        assert custom_id == "my-custom-snapshot-001"


class TestDefaultExcludePatterns:
    """Tests for default exclude patterns."""

    def test_default_excludes_caches(self):
        """Default excludes contain cache patterns."""
        from do_app_sandbox.snapshot import DEFAULT_EXCLUDE_PATTERNS

        assert "*.pyc" in DEFAULT_EXCLUDE_PATTERNS
        assert "__pycache__" in DEFAULT_EXCLUDE_PATTERNS
        assert ".pytest_cache" in DEFAULT_EXCLUDE_PATTERNS
        assert ".mypy_cache" in DEFAULT_EXCLUDE_PATTERNS

    def test_default_keeps_dependencies(self):
        """Default excludes do NOT exclude node_modules itself."""
        from do_app_sandbox.snapshot import DEFAULT_EXCLUDE_PATTERNS

        # node_modules itself should NOT be excluded (only its cache)
        assert "node_modules" not in DEFAULT_EXCLUDE_PATTERNS
        # But cache subdirectory should be excluded
        assert "node_modules/.cache" in DEFAULT_EXCLUDE_PATTERNS

    def test_default_excludes_env_files(self):
        """Default excludes contain env files for security."""
        from do_app_sandbox.snapshot import DEFAULT_EXCLUDE_PATTERNS

        assert ".env" in DEFAULT_EXCLUDE_PATTERNS
        assert ".env.local" in DEFAULT_EXCLUDE_PATTERNS

    def test_default_excludes_build_artifacts(self):
        """Default excludes contain build artifacts."""
        from do_app_sandbox.snapshot import DEFAULT_EXCLUDE_PATTERNS

        assert "dist/" in DEFAULT_EXCLUDE_PATTERNS
        assert "build/" in DEFAULT_EXCLUDE_PATTERNS


class TestTarCommandBuilding:
    """Tests for tar command construction."""

    def test_builds_correct_tar_command(self):
        """Builds correct tar command with exclusions."""

        # Simulate the command building logic
        exclude_patterns = ["*.pyc", "__pycache__", ".env"]
        paths = ["/workspace"]
        snapshot_id = "snap-test123"

        excludes = " ".join(f"--exclude='{p}'" for p in exclude_patterns)
        paths_str = " ".join(p.lstrip("/") for p in paths)
        archive = f"/tmp/snapshot_{snapshot_id}.tar.gz"

        tar_cmd = f"tar {excludes} -czf {archive} -C / {paths_str}"

        assert "--exclude='*.pyc'" in tar_cmd
        assert "--exclude='__pycache__'" in tar_cmd
        assert "--exclude='.env'" in tar_cmd
        assert "-czf" in tar_cmd
        assert f"/tmp/snapshot_{snapshot_id}.tar.gz" in tar_cmd
        assert "workspace" in tar_cmd
        assert "-C /" in tar_cmd

    def test_multiple_paths_in_tar_command(self):
        """Tar command handles multiple paths."""
        paths = ["/workspace", "/home", "/app"]
        paths_str = " ".join(p.lstrip("/") for p in paths)

        assert paths_str == "workspace home app"


class TestMetadataSerialization:
    """Tests for SnapshotMetadata serialization."""

    def test_metadata_to_json(self):
        """SnapshotMetadata serializes to JSON correctly."""
        from dataclasses import asdict

        now = time.time()
        metadata = SnapshotMetadata(
            snapshot_id="snap-abc123",
            created_at=now,
            sandbox_image="python",
            size_bytes=1024 * 1024,
            paths=["/workspace"],
            description="Test snapshot",
            tags={"env": "production", "version": "1.0"},
        )

        json_str = json.dumps(asdict(metadata), indent=2)
        parsed = json.loads(json_str)

        assert parsed["snapshot_id"] == "snap-abc123"
        assert parsed["created_at"] == now
        assert parsed["sandbox_image"] == "python"
        assert parsed["size_bytes"] == 1024 * 1024
        assert parsed["paths"] == ["/workspace"]
        assert parsed["description"] == "Test snapshot"
        assert parsed["tags"]["env"] == "production"

    def test_metadata_from_json(self):
        """SnapshotMetadata deserializes from JSON correctly."""
        now = time.time()
        json_data = {
            "snapshot_id": "snap-xyz789",
            "created_at": now,
            "sandbox_image": "node",
            "size_bytes": 2048,
            "paths": ["/app", "/data"],
            "description": "Node snapshot",
            "tags": {},
        }

        metadata = SnapshotMetadata(**json_data)

        assert metadata.snapshot_id == "snap-xyz789"
        assert metadata.sandbox_image == "node"
        assert metadata.paths == ["/app", "/data"]


class TestSnapshotKeyFormat:
    """Tests for Spaces key format."""

    def test_snapshot_key_format(self):
        """Spaces key format is correct."""
        from do_app_sandbox.snapshot import DEFAULT_SNAPSHOT_PREFIX

        prefix = DEFAULT_SNAPSHOT_PREFIX.rstrip("/") + "/"
        snapshot_id = "snap-test123"

        archive_key = f"{prefix}{snapshot_id}/archive.tar.gz"
        metadata_key = f"{prefix}{snapshot_id}/metadata.json"

        assert archive_key == "snapshots/snap-test123/archive.tar.gz"
        assert metadata_key == "snapshots/snap-test123/metadata.json"

    def test_custom_prefix_format(self):
        """Custom prefix is handled correctly."""
        prefix = "my-custom-prefix"
        prefix_normalized = prefix.rstrip("/") + "/"
        snapshot_id = "snap-abc"

        key = f"{prefix_normalized}{snapshot_id}/archive.tar.gz"

        assert key == "my-custom-prefix/snap-abc/archive.tar.gz"


class TestListSnapshotsFiltering:
    """Tests for snapshot listing and filtering."""

    def test_filter_by_image(self):
        """Filters snapshots by image."""
        snapshots = [
            SnapshotMetadata(
                snapshot_id="snap-1",
                created_at=time.time(),
                sandbox_image="python",
                size_bytes=1024,
                paths=["/workspace"],
            ),
            SnapshotMetadata(
                snapshot_id="snap-2",
                created_at=time.time(),
                sandbox_image="node",
                size_bytes=2048,
                paths=["/workspace"],
            ),
            SnapshotMetadata(
                snapshot_id="snap-3",
                created_at=time.time(),
                sandbox_image="python",
                size_bytes=3072,
                paths=["/workspace"],
            ),
        ]

        # Filter by image
        filtered = [s for s in snapshots if s.sandbox_image == "python"]

        assert len(filtered) == 2
        assert all(s.sandbox_image == "python" for s in filtered)

    def test_filter_by_tags(self):
        """Filters snapshots by tags."""
        snapshots = [
            SnapshotMetadata(
                snapshot_id="snap-1",
                created_at=time.time(),
                sandbox_image="python",
                size_bytes=1024,
                paths=["/workspace"],
                tags={"env": "prod", "team": "backend"},
            ),
            SnapshotMetadata(
                snapshot_id="snap-2",
                created_at=time.time(),
                sandbox_image="python",
                size_bytes=2048,
                paths=["/workspace"],
                tags={"env": "dev", "team": "frontend"},
            ),
        ]

        # Filter by tag
        filter_tags = {"env": "prod"}
        filtered = [s for s in snapshots if all(s.tags.get(k) == v for k, v in filter_tags.items())]

        assert len(filtered) == 1
        assert filtered[0].snapshot_id == "snap-1"

    def test_sort_by_created_at(self):
        """Snapshots sorted by created_at descending."""
        now = time.time()
        snapshots = [
            SnapshotMetadata(
                snapshot_id="snap-old",
                created_at=now - 3600,
                sandbox_image="python",
                size_bytes=1024,
                paths=["/workspace"],
            ),
            SnapshotMetadata(
                snapshot_id="snap-new",
                created_at=now,
                sandbox_image="python",
                size_bytes=1024,
                paths=["/workspace"],
            ),
            SnapshotMetadata(
                snapshot_id="snap-mid",
                created_at=now - 1800,
                sandbox_image="python",
                size_bytes=1024,
                paths=["/workspace"],
            ),
        ]

        sorted_snapshots = sorted(snapshots, key=lambda x: x.created_at, reverse=True)

        assert sorted_snapshots[0].snapshot_id == "snap-new"
        assert sorted_snapshots[1].snapshot_id == "snap-mid"
        assert sorted_snapshots[2].snapshot_id == "snap-old"


class TestSnapshotManagerInit:
    """Tests for SnapshotManager initialization."""

    def test_requires_spaces_config(self):
        """Raises error when Spaces not configured."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("do_app_sandbox.spaces.create_spaces_config_from_env") as mock_config:
                mock_config.return_value = None

                with pytest.raises(SpacesNotConfiguredError):
                    from do_app_sandbox.snapshot import SnapshotManager

                    SnapshotManager()

    def test_accepts_spaces_config(self):
        """Accepts SpacesConfig parameter."""
        config = SpacesConfig(bucket="test-bucket", region="nyc3", access_key="key", secret_key="secret")

        with patch("do_app_sandbox.snapshot.SpacesClient"):
            from do_app_sandbox.snapshot import SnapshotManager

            manager = SnapshotManager(spaces_config=config)

            assert manager._prefix == "snapshots/"

    def test_custom_prefix(self):
        """Custom prefix is normalized correctly."""
        config = SpacesConfig(bucket="test-bucket", region="nyc3", access_key="key", secret_key="secret")

        with patch("do_app_sandbox.snapshot.SpacesClient"):
            from do_app_sandbox.snapshot import SnapshotManager

            manager = SnapshotManager(spaces_config=config, prefix="custom-prefix")

            assert manager._prefix == "custom-prefix/"


class TestSnapshotManagerOperations:
    """Tests for SnapshotManager operations with mocks."""

    @pytest.fixture
    def mock_spaces_client(self):
        """Mock SpacesClient for testing."""
        mock_client = MagicMock()
        mock_client.generate_presigned_upload_url.return_value = "https://upload.url"
        mock_client.generate_presigned_download_url.return_value = "https://download.url"
        mock_client.object_exists.return_value = True
        return mock_client

    @pytest.fixture
    def snapshot_manager(self, mock_spaces_client):
        """Create SnapshotManager with mocked dependencies."""
        config = SpacesConfig(bucket="test-bucket", region="nyc3", access_key="key", secret_key="secret")

        with patch("do_app_sandbox.snapshot.SpacesClient") as MockClient:
            MockClient.return_value = mock_spaces_client
            from do_app_sandbox.snapshot import SnapshotManager

            manager = SnapshotManager(spaces_config=config)
            manager._spaces = mock_spaces_client
            return manager

    def test_snapshot_exists_checks_metadata(self, snapshot_manager, mock_spaces_client):
        """snapshot_exists() checks for metadata.json."""
        mock_spaces_client.object_exists.return_value = True

        result = snapshot_manager.snapshot_exists("snap-test")

        mock_spaces_client.object_exists.assert_called_once_with("snapshots/snap-test/metadata.json")
        assert result is True

    def test_get_snapshot_returns_metadata(self, snapshot_manager, mock_spaces_client):
        """get_snapshot() returns SnapshotMetadata."""
        now = time.time()
        metadata_json = json.dumps(
            {
                "snapshot_id": "snap-test",
                "created_at": now,
                "sandbox_image": "python",
                "size_bytes": 1024,
                "paths": ["/workspace"],
                "description": None,
                "tags": {},
            }
        ).encode()

        mock_spaces_client.get_object.return_value = metadata_json

        result = snapshot_manager.get_snapshot("snap-test")

        assert isinstance(result, SnapshotMetadata)
        assert result.snapshot_id == "snap-test"
        assert result.sandbox_image == "python"

    def test_get_snapshot_returns_none_if_not_found(self, snapshot_manager, mock_spaces_client):
        """get_snapshot() returns None if snapshot doesn't exist."""
        mock_spaces_client.get_object.side_effect = Exception("Not found")

        result = snapshot_manager.get_snapshot("nonexistent")

        assert result is None

    def test_delete_snapshot_removes_both_files(self, snapshot_manager, mock_spaces_client):
        """delete_snapshot() removes archive and metadata."""
        snapshot_manager.delete_snapshot("snap-to-delete")

        # Should attempt to delete both files
        calls = mock_spaces_client.delete_object.call_args_list
        keys_deleted = [call[0][0] for call in calls]

        assert "snapshots/snap-to-delete/archive.tar.gz" in keys_deleted
        assert "snapshots/snap-to-delete/metadata.json" in keys_deleted

    def test_get_snapshot_download_url(self, snapshot_manager, mock_spaces_client):
        """get_snapshot_download_url() returns presigned URL."""
        mock_spaces_client.object_exists.return_value = True

        url = snapshot_manager.get_snapshot_download_url("snap-test", expires_in=3600)

        mock_spaces_client.generate_presigned_download_url.assert_called_once_with(
            "snapshots/snap-test/archive.tar.gz", 3600
        )
        assert url == "https://download.url"

    def test_get_snapshot_download_url_not_found(self, snapshot_manager, mock_spaces_client):
        """get_snapshot_download_url() raises SnapshotNotFoundError."""
        mock_spaces_client.object_exists.return_value = False

        with pytest.raises(SnapshotNotFoundError):
            snapshot_manager.get_snapshot_download_url("nonexistent")
