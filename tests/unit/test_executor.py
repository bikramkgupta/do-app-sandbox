"""Unit tests for executor.py."""

import pytest

from do_app_sandbox.executor import Executor


def test_executor_rejects_invalid_app_id():
    """Executor rejects unsafe app IDs."""
    with pytest.raises(ValueError, match="app_id"):
        Executor(app_id="bad id")


def test_executor_rejects_invalid_component():
    """Executor rejects unsafe component names."""
    with pytest.raises(ValueError, match="component"):
        Executor(app_id="app-123", component="bad/component")


def test_get_doctl_args_returns_arg_vector():
    """doctl command is represented as argv parts (not shell string)."""
    executor = Executor(app_id="app-123", component="sandbox")
    assert executor._get_doctl_args() == ["apps", "console", "app-123", "sandbox"]


def test_build_command_rejects_invalid_env_key():
    """Invalid env var names are rejected to prevent command injection."""
    executor = Executor(app_id="app-123", component="sandbox")
    with pytest.raises(ValueError, match="Invalid environment variable"):
        executor._build_command("echo ok", env={"BAD-KEY!": "value"})


def test_build_command_quotes_env_value():
    """Environment values are shell-quoted safely."""
    executor = Executor(app_id="app-123", component="sandbox")
    cmd = executor._build_command("echo ok", env={"TOKEN": "a b;c"}, cwd="/app")

    assert "cd /app" in cmd
    assert "export TOKEN='a b;c'" in cmd
    assert cmd.endswith("echo ok")
