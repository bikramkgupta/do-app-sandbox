"""Pytest configuration and fixtures for unit tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def mock_spaces_config():
    """Create a mock SpacesConfig."""
    from do_app_sandbox.types import SpacesConfig
    return SpacesConfig(
        bucket="test-bucket",
        region="nyc3",
        access_key="test-key",
        secret_key="test-secret"
    )


@pytest.fixture
def mock_sandbox():
    """Create a mock Sandbox object."""
    mock = MagicMock()
    mock._app_id = "test-app-123"
    mock._image = "python"
    mock.exec.return_value = MagicMock(success=True, stdout="", stderr="", exit_code=0)
    return mock


@pytest.fixture
def mock_doctl():
    """Mock doctl subprocess calls."""
    with pytest.MonkeyPatch().context() as mp:
        mock_run = MagicMock()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="{}",
            stderr=""
        )
        mp.setattr("subprocess.run", mock_run)
        yield mock_run


@pytest.fixture
def sample_snapshot_metadata():
    """Create sample SnapshotMetadata."""
    import time
    from do_app_sandbox.types import SnapshotMetadata
    return SnapshotMetadata(
        snapshot_id="snap-test123",
        created_at=time.time(),
        sandbox_image="python",
        size_bytes=1024 * 1024,
        paths=["/workspace"],
        description="Test snapshot",
        tags={"env": "test"}
    )


@pytest.fixture
def sample_hibernated_sandbox():
    """Create sample HibernatedSandbox."""
    import time
    from do_app_sandbox.types import HibernatedSandbox, SandboxMode
    return HibernatedSandbox(
        snapshot_id="hibernate-test",
        image="python",
        mode=SandboxMode.WORKER,
        service_config=None,
        hibernated_at=time.time(),
        metadata={"app_id": "old-app-123"}
    )
