"""Tests for types.py - Type and Dataclass Tests."""

import time
import pytest

from do_app_sandbox.types import (
    SandboxMode,
    SandboxState,
    ServiceConfig,
    HibernationConfig,
    StreamEvent,
    SnapshotMetadata,
    HibernatedSandbox,
    GitCredentials,
    ExposedPort,
    CommandResult,
    ProcessInfo,
    FileInfo,
)


class TestSandboxModeEnum:
    """Tests for SandboxMode enum."""

    def test_sandbox_mode_worker_value(self):
        """Verify SandboxMode.WORKER has correct value."""
        assert SandboxMode.WORKER.value == "worker"

    def test_sandbox_mode_service_value(self):
        """Verify SandboxMode.SERVICE has correct value."""
        assert SandboxMode.SERVICE.value == "service"

    def test_sandbox_mode_all_values(self):
        """Verify all SandboxMode enum members."""
        modes = list(SandboxMode)
        assert len(modes) == 2
        assert SandboxMode.WORKER in modes
        assert SandboxMode.SERVICE in modes


class TestSandboxStateEnum:
    """Tests for SandboxState enum."""

    def test_sandbox_state_creating(self):
        """Verify SandboxState.CREATING value."""
        assert SandboxState.CREATING.value == "creating"

    def test_sandbox_state_active(self):
        """Verify SandboxState.ACTIVE value."""
        assert SandboxState.ACTIVE.value == "active"

    def test_sandbox_state_hibernated(self):
        """Verify SandboxState.HIBERNATED value."""
        assert SandboxState.HIBERNATED.value == "hibernated"

    def test_sandbox_state_deleted(self):
        """Verify SandboxState.DELETED value."""
        assert SandboxState.DELETED.value == "deleted"

    def test_sandbox_state_all_values(self):
        """Verify all SandboxState enum members."""
        states = list(SandboxState)
        assert len(states) == 4


class TestServiceConfig:
    """Tests for ServiceConfig dataclass."""

    def test_service_config_defaults(self):
        """ServiceConfig has correct defaults."""
        config = ServiceConfig()
        assert config.api_port == 8080
        assert config.proxy_ports == [3000, 5000, 8000]
        assert config.enable_file_api is True
        assert config.enable_sessions is True
        assert config.token is None

    def test_service_config_custom_values(self):
        """ServiceConfig accepts custom values."""
        config = ServiceConfig(
            api_port=9000,
            proxy_ports=[4000],
            enable_file_api=False,
            enable_sessions=False,
            token="my-token"
        )
        assert config.api_port == 9000
        assert config.proxy_ports == [4000]
        assert config.enable_file_api is False
        assert config.enable_sessions is False
        assert config.token == "my-token"

    def test_service_config_repr(self):
        """ServiceConfig repr is informative."""
        config = ServiceConfig()
        repr_str = repr(config)
        assert "ServiceConfig" in repr_str
        assert "8080" in repr_str


class TestHibernationConfig:
    """Tests for HibernationConfig dataclass."""

    def test_hibernation_config_defaults(self):
        """HibernationConfig has correct defaults (enabled=True, sleep_after=600)."""
        config = HibernationConfig()
        assert config.enabled is True
        assert config.sleep_after == 600  # 10 minutes

    def test_hibernation_config_custom_values(self):
        """HibernationConfig accepts custom values."""
        config = HibernationConfig(enabled=False, sleep_after=300)
        assert config.enabled is False
        assert config.sleep_after == 300

    def test_hibernation_config_repr(self):
        """HibernationConfig repr shows enabled and sleep_after."""
        config = HibernationConfig(enabled=True, sleep_after=600)
        repr_str = repr(config)
        assert "HibernationConfig" in repr_str
        assert "600" in repr_str


class TestStreamEvent:
    """Tests for StreamEvent dataclass."""

    def test_stream_event_creation(self):
        """StreamEvent dataclass creation."""
        now = time.time()
        event = StreamEvent(type="stdout", data="hello world", timestamp=now)
        assert event.type == "stdout"
        assert event.data == "hello world"
        assert event.timestamp == now

    def test_stream_event_is_output_stdout(self):
        """is_output returns True for stdout."""
        event = StreamEvent(type="stdout", data="test", timestamp=time.time())
        assert event.is_output is True

    def test_stream_event_is_output_stderr(self):
        """is_output returns True for stderr."""
        event = StreamEvent(type="stderr", data="error", timestamp=time.time())
        assert event.is_output is True

    def test_stream_event_is_output_exit(self):
        """is_output returns False for exit."""
        event = StreamEvent(type="exit", data="0", timestamp=time.time())
        assert event.is_output is False

    def test_stream_event_is_complete_exit(self):
        """is_complete returns True for exit."""
        event = StreamEvent(type="exit", data="0", timestamp=time.time())
        assert event.is_complete is True

    def test_stream_event_is_complete_error(self):
        """is_complete returns True for error."""
        event = StreamEvent(type="error", data="failed", timestamp=time.time())
        assert event.is_complete is True

    def test_stream_event_is_complete_stdout(self):
        """is_complete returns False for stdout."""
        event = StreamEvent(type="stdout", data="hello", timestamp=time.time())
        assert event.is_complete is False

    def test_stream_event_repr_truncates_long_data(self):
        """StreamEvent repr truncates long data."""
        long_data = "x" * 100
        event = StreamEvent(type="stdout", data=long_data, timestamp=time.time())
        repr_str = repr(event)
        assert len(repr_str) < 150


class TestSnapshotMetadata:
    """Tests for SnapshotMetadata dataclass."""

    def test_snapshot_metadata_creation(self):
        """SnapshotMetadata with all fields."""
        now = time.time()
        meta = SnapshotMetadata(
            snapshot_id="snap-abc123",
            created_at=now,
            sandbox_image="python",
            size_bytes=1024 * 1024,  # 1 MB
            paths=["/workspace"],
            description="Test snapshot",
            tags={"env": "test"}
        )
        assert meta.snapshot_id == "snap-abc123"
        assert meta.created_at == now
        assert meta.sandbox_image == "python"
        assert meta.size_bytes == 1024 * 1024
        assert meta.paths == ["/workspace"]
        assert meta.description == "Test snapshot"
        assert meta.tags == {"env": "test"}

    def test_snapshot_metadata_defaults(self):
        """SnapshotMetadata has sensible defaults."""
        meta = SnapshotMetadata(
            snapshot_id="snap-xyz",
            created_at=time.time(),
            sandbox_image="node",
            size_bytes=2048,
            paths=["/app"]
        )
        assert meta.description is None
        assert meta.tags == {}

    def test_snapshot_metadata_repr_shows_size(self):
        """SnapshotMetadata repr shows size in MB."""
        meta = SnapshotMetadata(
            snapshot_id="snap-test",
            created_at=time.time(),
            sandbox_image="python",
            size_bytes=5 * 1024 * 1024,  # 5 MB
            paths=["/workspace"]
        )
        repr_str = repr(meta)
        assert "5.0MB" in repr_str or "5MB" in repr_str


class TestHibernatedSandbox:
    """Tests for HibernatedSandbox dataclass."""

    def test_hibernated_sandbox_creation(self):
        """HibernatedSandbox stores mode, config, metadata."""
        now = time.time()
        config = ServiceConfig(api_port=8080)
        hibernated = HibernatedSandbox(
            snapshot_id="hibernate-abc123",
            image="python",
            mode=SandboxMode.SERVICE,
            service_config=config,
            hibernated_at=now,
            metadata={"app_id": "test-app"}
        )
        assert hibernated.snapshot_id == "hibernate-abc123"
        assert hibernated.image == "python"
        assert hibernated.mode == SandboxMode.SERVICE
        assert hibernated.service_config == config
        assert hibernated.hibernated_at == now
        assert hibernated.metadata == {"app_id": "test-app"}

    def test_hibernated_sandbox_worker_mode(self):
        """HibernatedSandbox works with worker mode."""
        hibernated = HibernatedSandbox(
            snapshot_id="hibernate-worker",
            image="node",
            mode=SandboxMode.WORKER,
            service_config=None,
            hibernated_at=time.time()
        )
        assert hibernated.mode == SandboxMode.WORKER
        assert hibernated.service_config is None

    def test_hibernated_sandbox_repr(self):
        """HibernatedSandbox repr is informative."""
        hibernated = HibernatedSandbox(
            snapshot_id="hibernate-test",
            image="python",
            mode=SandboxMode.SERVICE,
            service_config=None,
            hibernated_at=time.time()
        )
        repr_str = repr(hibernated)
        assert "hibernate-test" in repr_str
        assert "python" in repr_str


class TestGitCredentials:
    """Tests for GitCredentials dataclass."""

    def test_git_credentials_https_with_token(self):
        """GitCredentials with token for HTTPS."""
        creds = GitCredentials(username="user", token="ghp_xxx")
        assert creds.username == "user"
        assert creds.token == "ghp_xxx"
        assert creds.ssh_key is None

    def test_git_credentials_ssh_with_key(self):
        """GitCredentials with ssh_key."""
        ssh_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
        creds = GitCredentials(ssh_key=ssh_key)
        assert creds.ssh_key == ssh_key
        assert creds.token is None

    def test_git_credentials_repr_shows_type(self):
        """GitCredentials repr shows auth type."""
        token_creds = GitCredentials(token="xxx")
        assert "token" in repr(token_creds)

        ssh_creds = GitCredentials(ssh_key="xxx")
        assert "ssh" in repr(ssh_creds)

        no_creds = GitCredentials()
        assert "none" in repr(no_creds)


class TestExposedPort:
    """Tests for ExposedPort dataclass."""

    def test_exposed_port_creation(self):
        """ExposedPort with url and protocol."""
        port = ExposedPort(
            port=3000,
            url="https://sandbox-xxx.ondigitalocean.app/proxy/3000",
            protocol="https",
            created_at=time.time()
        )
        assert port.port == 3000
        assert port.url == "https://sandbox-xxx.ondigitalocean.app/proxy/3000"
        assert port.protocol == "https"

    def test_exposed_port_defaults(self):
        """ExposedPort has sensible defaults."""
        port = ExposedPort(port=8000, url="https://example.com")
        assert port.protocol == "https"
        assert port.created_at == 0

    def test_exposed_port_repr(self):
        """ExposedPort repr shows port and url."""
        port = ExposedPort(port=5000, url="https://test.app/proxy/5000")
        repr_str = repr(port)
        assert "5000" in repr_str


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_command_result_success(self):
        """CommandResult.success returns True for exit_code 0."""
        result = CommandResult(stdout="hello", stderr="", exit_code=0)
        assert result.success is True

    def test_command_result_failure(self):
        """CommandResult.success returns False for non-zero exit_code."""
        result = CommandResult(stdout="", stderr="error", exit_code=1)
        assert result.success is False

    def test_command_result_repr_truncates(self):
        """CommandResult repr truncates long output."""
        long_output = "x" * 100
        result = CommandResult(stdout=long_output, stderr="", exit_code=0)
        repr_str = repr(result)
        assert "..." in repr_str


class TestProcessInfo:
    """Tests for ProcessInfo dataclass."""

    def test_process_info_creation(self):
        """ProcessInfo stores all fields."""
        info = ProcessInfo(
            pid=12345,
            command="python server.py",
            status="running",
            cpu="5%",
            memory="50MB"
        )
        assert info.pid == 12345
        assert info.command == "python server.py"
        assert info.status == "running"
        assert info.cpu == "5%"
        assert info.memory == "50MB"


class TestFileInfo:
    """Tests for FileInfo dataclass."""

    def test_file_info_file(self):
        """FileInfo for a file."""
        info = FileInfo(
            name="test.py",
            path="/workspace/test.py",
            is_dir=False,
            size=1024,
            permissions="rw-r--r--"
        )
        assert info.name == "test.py"
        assert info.is_dir is False

    def test_file_info_directory(self):
        """FileInfo for a directory."""
        info = FileInfo(
            name="src",
            path="/workspace/src",
            is_dir=True
        )
        assert info.is_dir is True
