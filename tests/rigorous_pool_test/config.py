"""
Configuration dataclasses for the rigorous pool test.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class TestConfig:
    """Main test configuration."""

    # Duration
    duration_seconds: int = 14400  # 4 hours

    # Sandbox limits
    max_total_sandboxes: int = 25  # Hard cap - NEVER exceed
    max_concurrent_creates: int = 10

    # Region and sizing
    region: str = "syd1"
    instance_size: str = "basic-xxs"

    # Concurrency
    concurrency: int = 12  # Number of virtual users

    # Pool configuration
    python_target_ready: int = 12
    python_max_ready: int = 15
    node_target_ready: int = 0
    node_max_ready: int = 0

    # Command execution
    enable_network_commands: bool = True

    # Hold time configuration (seconds)
    # For smoke tests, use shorter hold times (60-180s)
    # For main tests, use longer hold times (300-3600s)
    hold_time_min: int = 300  # 5 minutes default
    hold_time_max: int = 600  # 10 minutes default

    # Reporting
    report_dir: Optional[str] = None

    # Watchdog configuration
    watchdog_enabled: bool = True
    watchdog_interval: float = 10.0  # seconds
    watchdog_grace_period: int = 15  # Allow surge for terminating apps (Concurrency 12 + buffer)
    watchdog_sandbox_pattern: str = "sandbox"

    def __post_init__(self):
        """Generate report directory if not specified."""
        if self.report_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.report_dir = f"tests/artifacts/rigorous_pool_test/{timestamp}"


@dataclass
class WatchdogConfig:
    """Configuration for the external sandbox watchdog."""

    max_sandboxes: int = 25
    poll_interval: float = 10.0  # seconds
    sandbox_name_pattern: str = "sandbox"
    grace_period: int = 2  # Allow brief overage for in-flight creates


@dataclass
class HoldTimeConfig:
    """Configuration for hold time distribution."""

    # Distribution: 40% short, 40% medium, 20% long
    short_min: int = 300  # 5 minutes
    short_max: int = 600  # 10 minutes
    short_weight: float = 0.4

    medium_min: int = 600  # 10 minutes
    medium_max: int = 1200  # 20 minutes
    medium_weight: float = 0.4

    long_min: int = 1200  # 20 minutes
    long_max: int = 3600  # 60 minutes
    long_weight: float = 0.2


@dataclass
class RetryConfig:
    """Configuration for retry policies."""

    # Command execution retries
    exec_retries: int = 2
    exec_retry_delay: float = 1.5  # seconds

    # Delete retries
    delete_retries: int = 3
    delete_retry_delay: float = 2.0  # seconds


# Preset configurations
SMOKE_CONFIG = TestConfig(
    duration_seconds=600,  # 10 minutes
    max_total_sandboxes=5,
    concurrency=2,  # Reduced to 2 so (2 workers + 3 pool) <= 5 max
    python_target_ready=3,
    python_max_ready=5,
    hold_time_min=60,   # 1 minute - SHORT for smoke test
    hold_time_max=120,  # 2 minutes - SHORT for smoke test
)

MAIN_4HR_CONFIG = TestConfig(
    duration_seconds=14400,  # 4 hours
    max_total_sandboxes=25,
    concurrency=12,
    python_target_ready=12,
    python_max_ready=15,
    region="syd1",
)

STARVATION_CONFIG = TestConfig(
    duration_seconds=1800,  # 30 minutes
    max_total_sandboxes=25,
    concurrency=16,  # More demand than pool can handle
    python_target_ready=2,  # Force cold starts
    python_max_ready=5,
)
