"""Tests for sandbox.py - Sandbox State Machine Tests."""

import time
from unittest.mock import MagicMock, patch

import pytest

from do_app_sandbox.types import (
    SandboxMode,
    SandboxState,
    HibernationConfig,
    ServiceConfig,
)
from do_app_sandbox.exceptions import SandboxHibernatedError


class TestInitialState:
    """Tests for initial sandbox state."""

    def test_initial_state_active(self):
        """New sandbox starts in ACTIVE state."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    component="sandbox"
                )

                assert sandbox._state == SandboxState.ACTIVE

    def test_initial_mode_worker(self):
        """Default mode is WORKER."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")

                assert sandbox._mode == SandboxMode.WORKER

    def test_service_mode_set(self):
        """Service mode can be set."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _mode=SandboxMode.SERVICE,
                    _service_token="test-token"
                )

                assert sandbox._mode == SandboxMode.SERVICE


class TestActivityTracking:
    """Tests for activity tracking."""

    def test_record_activity_updates_timestamp(self):
        """_record_activity() updates timestamp."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")
                old_time = sandbox._last_activity

                time.sleep(0.01)  # Small delay
                sandbox._record_activity()

                assert sandbox._last_activity > old_time

    def test_last_activity_initialized(self):
        """_last_activity is initialized to current time."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                before = time.time()
                sandbox = Sandbox(app_id="test-app-123")
                after = time.time()

                assert before <= sandbox._last_activity <= after


class TestIdleDetection:
    """Tests for idle detection."""

    def test_is_idle_returns_true_after_sleep_after(self):
        """_is_idle() returns True after sleep_after seconds."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                config = HibernationConfig(sleep_after=1)  # 1 second
                sandbox = Sandbox(
                    app_id="test-app-123",
                    _hibernation_config=config
                )

                # Initially not idle
                assert sandbox._is_idle() is False

                # Simulate time passing
                sandbox._last_activity = time.time() - 2  # 2 seconds ago

                assert sandbox._is_idle() is True

    def test_is_idle_returns_false_with_active_streams(self):
        """_is_idle() returns False with active streams."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                config = HibernationConfig(sleep_after=1)
                sandbox = Sandbox(
                    app_id="test-app-123",
                    _hibernation_config=config
                )

                # Simulate old last_activity but active stream
                sandbox._last_activity = time.time() - 10
                sandbox._active_streams = 1

                assert sandbox._is_idle() is False

    def test_is_idle_returns_false_when_recently_active(self):
        """_is_idle() returns False when recently active."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                config = HibernationConfig(sleep_after=600)  # 10 minutes
                sandbox = Sandbox(
                    app_id="test-app-123",
                    _hibernation_config=config
                )

                sandbox._record_activity()

                assert sandbox._is_idle() is False


class TestEnsureAwake:
    """Tests for _ensure_awake() method."""

    def test_ensure_awake_passes_for_active(self):
        """_ensure_awake() passes for ACTIVE state."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")
                sandbox._state = SandboxState.ACTIVE

                # Should not raise
                sandbox._ensure_awake()

    def test_ensure_awake_raises_for_hibernated(self):
        """_ensure_awake() raises for HIBERNATED state."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")
                sandbox._state = SandboxState.HIBERNATED

                with pytest.raises(SandboxHibernatedError):
                    sandbox._ensure_awake()


class TestModeProperty:
    """Tests for mode property."""

    def test_mode_property_returns_worker(self):
        """mode property returns WORKER when set."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _mode=SandboxMode.WORKER
                )

                assert sandbox.mode == SandboxMode.WORKER

    def test_mode_property_returns_service(self):
        """mode property returns SERVICE when set."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _mode=SandboxMode.SERVICE,
                    _service_token="token"
                )

                assert sandbox.mode == SandboxMode.SERVICE


class TestStateProperty:
    """Tests for state property."""

    def test_state_property_returns_active(self):
        """state property returns ACTIVE initially."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")

                assert sandbox.state == SandboxState.ACTIVE

    def test_state_property_returns_hibernated(self):
        """state property returns HIBERNATED when set."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")
                sandbox._state = SandboxState.HIBERNATED

                assert sandbox.state == SandboxState.HIBERNATED


class TestImageProperty:
    """Tests for image property."""

    def test_image_property_returns_python(self):
        """image property returns correct image type."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _image="python"
                )

                assert sandbox.image == "python"

    def test_image_property_returns_node(self):
        """image property returns node when set."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _image="node"
                )

                assert sandbox.image == "node"


class TestHibernationConfigDefault:
    """Tests for default hibernation config."""

    def test_default_hibernation_config(self):
        """Default HibernationConfig is applied."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")

                assert sandbox._hibernation_config.enabled is True
                assert sandbox._hibernation_config.sleep_after == 600

    def test_custom_hibernation_config(self):
        """Custom HibernationConfig is used when provided."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                config = HibernationConfig(enabled=False, sleep_after=300)
                sandbox = Sandbox(
                    app_id="test-app-123",
                    _hibernation_config=config
                )

                assert sandbox._hibernation_config.enabled is False
                assert sandbox._hibernation_config.sleep_after == 300


class TestServiceClient:
    """Tests for service client management."""

    def test_service_client_not_created_for_worker(self):
        """Service client is None for worker mode."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _mode=SandboxMode.WORKER
                )

                assert sandbox._service_client is None

    def test_executor_not_created_for_service(self):
        """Executor is None for service mode."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _mode=SandboxMode.SERVICE,
                    _service_token="token"
                )

                assert sandbox._executor is None


class TestSandboxRepr:
    """Tests for sandbox string representation."""

    def test_repr_includes_app_id(self):
        """repr includes app_id."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(app_id="test-app-123")
                repr_str = repr(sandbox)

                assert "test-app-123" in repr_str

    def test_repr_includes_mode(self):
        """repr includes mode."""
        with patch("do_app_sandbox.sandbox._ensure_doctl_available"):
            with patch("do_app_sandbox.sandbox.Executor"):
                from do_app_sandbox.sandbox import Sandbox

                sandbox = Sandbox(
                    app_id="test-app-123",
                    _mode=SandboxMode.SERVICE,
                    _service_token="token"
                )
                repr_str = repr(sandbox)

                assert "service" in repr_str
