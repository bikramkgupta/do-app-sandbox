"""
Configuration module for SandboxManager stress tests.

Defines test configurations, pool settings, and scenario definitions.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import os


class LoadPattern(Enum):
    """Load pattern types for user simulation."""
    BURST = "burst"          # Many acquisitions quickly, then quiet
    STEADY = "steady"        # Consistent rate with small variance
    RANDOM = "random"        # Exponential distribution (Poisson-like)
    PEAK_HOURS = "peak_hours"  # Higher rate during "peak" periods


class ImageType(Enum):
    """Sandbox image types."""
    PYTHON = "python"
    NODE = "node"


@dataclass
class PoolConfig:
    """Configuration for a single sandbox pool."""
    image: ImageType
    target_ready: int = 5      # Target number of warm sandboxes
    max_sandboxes: int = 25    # Maximum sandboxes for this pool


@dataclass
class UserGroupConfig:
    """Configuration for a group of simulated users."""
    name: str
    count: int                          # Number of users in group
    image: ImageType                    # Image type to use
    pattern: LoadPattern                # Load pattern
    task_duration_range: tuple[int, int]  # Min/max task duration in seconds
    categories: list[str] = field(default_factory=lambda: ["compute", "io", "mixed"])


@dataclass
class TestConfig:
    """Main test configuration."""
    # Pool settings
    python_pool: PoolConfig = field(default_factory=lambda: PoolConfig(ImageType.PYTHON))
    node_pool: PoolConfig = field(default_factory=lambda: PoolConfig(ImageType.NODE))

    # Global limits
    max_total_sandboxes: int = 50
    max_concurrent_creates: int = 10

    # Timing settings (in seconds)
    idle_timeout: int = 120           # Time before scale-down starts
    scale_down_delay: int = 60        # Delay between destructions
    cooldown_after_acquire: int = 180 # Pause replenishment after acquire
    max_warm_age: int = 1800          # Max time a sandbox stays warm (30 min)
    health_check_interval: int = 60   # Health check frequency (0 to disable)

    # Sandbox defaults
    region: str = "syd1"
    instance_size: str = "apps-s-1vcpu-2gb"

    # Metrics collection
    metrics_interval: int = 10  # Collect metrics every N seconds

    # Paths
    programs_dir: Path = field(default_factory=lambda: Path("sandbox-execution-programs"))
    artifacts_dir: Path = field(default_factory=lambda: Path("tests/artifacts/stress"))


@dataclass
class ScenarioConfig:
    """Configuration for a complete test scenario."""
    name: str
    description: str
    duration_seconds: int
    user_groups: list[UserGroupConfig]
    test_config: TestConfig = field(default_factory=TestConfig)
    idle_periods: list[tuple[int, int]] = field(default_factory=list)  # (start_sec, duration_sec)

    @property
    def total_users(self) -> int:
        return sum(g.count for g in self.user_groups)


# Pre-defined scenarios
def get_quick_validation() -> ScenarioConfig:
    """Quick validation scenario (5-10 min)."""
    return ScenarioConfig(
        name="quick_validation",
        description="Quick validation test - 4 users, basic functionality",
        duration_seconds=600,  # 10 minutes
        user_groups=[
            UserGroupConfig(
                name="python_basic",
                count=2,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(60, 120),
                categories=["compute", "io"],
            ),
            UserGroupConfig(
                name="node_basic",
                count=2,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(60, 120),
                categories=["compute", "io"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=2, max_sandboxes=4),
            node_pool=PoolConfig(ImageType.NODE, target_ready=2, max_sandboxes=4),
            max_total_sandboxes=8,
        ),
    )


def get_burst_test() -> ScenarioConfig:
    """Burst test scenario (30 min)."""
    return ScenarioConfig(
        name="burst_test",
        description="Burst test - 20 users, tests pool exhaustion",
        duration_seconds=1800,  # 30 minutes
        user_groups=[
            UserGroupConfig(
                name="python_burst",
                count=10,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(60, 300),
                categories=["compute", "io", "mixed"],
            ),
            UserGroupConfig(
                name="node_burst",
                count=10,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(60, 300),
                categories=["compute", "io", "async"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=3, max_sandboxes=15),
            node_pool=PoolConfig(ImageType.NODE, target_ready=3, max_sandboxes=15),
            max_total_sandboxes=30,
        ),
    )


def get_steady_state() -> ScenarioConfig:
    """Steady state scenario (1 hour)."""
    return ScenarioConfig(
        name="steady_state",
        description="Steady state test - 24 users, sustained load",
        duration_seconds=3600,  # 1 hour
        user_groups=[
            UserGroupConfig(
                name="python_steady",
                count=12,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(120, 600),
                categories=["compute", "io", "mixed", "network"],
            ),
            UserGroupConfig(
                name="node_steady",
                count=12,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(120, 600),
                categories=["compute", "io", "async", "mixed"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=4, max_sandboxes=20),
            node_pool=PoolConfig(ImageType.NODE, target_ready=4, max_sandboxes=20),
            max_total_sandboxes=40,
        ),
    )


def get_scale_cycle() -> ScenarioConfig:
    """Scale cycle scenario (90 min)."""
    return ScenarioConfig(
        name="scale_cycle",
        description="Scale cycle test - 30 users, peak hours pattern with idle periods",
        duration_seconds=5400,  # 90 minutes
        user_groups=[
            UserGroupConfig(
                name="python_peak",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.PEAK_HOURS,
                task_duration_range=(180, 900),
                categories=["compute", "io", "mixed", "idle"],
            ),
            UserGroupConfig(
                name="node_peak",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.PEAK_HOURS,
                task_duration_range=(180, 900),
                categories=["compute", "io", "async", "mixed", "idle"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=5, max_sandboxes=20),
            node_pool=PoolConfig(ImageType.NODE, target_ready=5, max_sandboxes=20),
            max_total_sandboxes=40,
        ),
        idle_periods=[
            (1800, 600),   # 10 min idle at 30 min mark
            (4200, 600),   # 10 min idle at 70 min mark
        ],
    )


def get_full_stress() -> ScenarioConfig:
    """Full stress scenario (2+ hours)."""
    return ScenarioConfig(
        name="full_stress",
        description="Full stress test - 50 users, mixed patterns, 2+ hours",
        duration_seconds=7800,  # 2 hours 10 minutes
        user_groups=[
            # Heavy Python users
            UserGroupConfig(
                name="python_heavy",
                count=8,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 1800),  # 5-30 min
                categories=["compute", "mixed"],
            ),
            # Burst Python users
            UserGroupConfig(
                name="python_burst",
                count=5,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(60, 600),  # 1-10 min
                categories=["io", "network"],
            ),
            # Light Python users
            UserGroupConfig(
                name="python_light",
                count=7,
                image=ImageType.PYTHON,
                pattern=LoadPattern.RANDOM,
                task_duration_range=(60, 300),  # 1-5 min
                categories=["compute", "io", "idle"],
            ),
            # Long-running Python
            UserGroupConfig(
                name="python_long",
                count=5,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(900, 3000),  # 15-50 min
                categories=["mixed", "idle"],
            ),
            # Heavy Node users
            UserGroupConfig(
                name="node_heavy",
                count=8,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 1800),
                categories=["compute", "mixed"],
            ),
            # Burst Node users
            UserGroupConfig(
                name="node_burst",
                count=5,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(60, 600),
                categories=["async", "io"],
            ),
            # Light Node users
            UserGroupConfig(
                name="node_light",
                count=7,
                image=ImageType.NODE,
                pattern=LoadPattern.RANDOM,
                task_duration_range=(60, 300),
                categories=["compute", "io", "idle"],
            ),
            # Long-running Node
            UserGroupConfig(
                name="node_long",
                count=5,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(900, 3000),
                categories=["mixed", "idle"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=5, max_sandboxes=25),
            node_pool=PoolConfig(ImageType.NODE, target_ready=5, max_sandboxes=25),
            max_total_sandboxes=50,
            max_concurrent_creates=10,
        ),
        idle_periods=[
            (1800, 300),   # 5 min idle at 30 min
            (3600, 300),   # 5 min idle at 60 min
            (5400, 300),   # 5 min idle at 90 min
            (7200, 300),   # 5 min idle at 120 min
        ],
    )


def get_mega_stress_8hr() -> ScenarioConfig:
    """8-hour mega stress test with 500 sandboxes."""
    return ScenarioConfig(
        name="mega_stress_8hr",
        description="8-hour stress test - 200 users, 500 sandbox pool, comprehensive corner case testing",
        duration_seconds=28800,  # 8 hours
        user_groups=[
            # === SUSTAINED LOAD USERS (100 users) ===
            UserGroupConfig(
                name="python_sustained_heavy",
                count=20,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(600, 1800),  # 10-30 min
                categories=["compute", "mixed"],
            ),
            UserGroupConfig(
                name="python_sustained_medium",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 900),  # 5-15 min
                categories=["io", "network", "mixed"],
            ),
            UserGroupConfig(
                name="python_sustained_light",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.RANDOM,
                task_duration_range=(60, 300),  # 1-5 min
                categories=["compute", "io", "idle"],
            ),
            UserGroupConfig(
                name="node_sustained_heavy",
                count=20,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(600, 1800),
                categories=["compute", "mixed"],
            ),
            UserGroupConfig(
                name="node_sustained_medium",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 900),
                categories=["async", "io", "mixed"],
            ),
            UserGroupConfig(
                name="node_sustained_light",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.RANDOM,
                task_duration_range=(60, 300),
                categories=["compute", "io", "idle"],
            ),

            # === BURST USERS (60 users) ===
            UserGroupConfig(
                name="python_burst_fast",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(30, 180),  # 30s-3 min (high churn)
                categories=["compute", "io"],
            ),
            UserGroupConfig(
                name="python_burst_medium",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),  # 2-10 min
                categories=["mixed", "network"],
            ),
            UserGroupConfig(
                name="node_burst_fast",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(30, 180),
                categories=["async", "io"],
            ),
            UserGroupConfig(
                name="node_burst_medium",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),
                categories=["mixed", "compute"],
            ),

            # === PEAK HOURS USERS (40 users) ===
            UserGroupConfig(
                name="python_peak",
                count=20,
                image=ImageType.PYTHON,
                pattern=LoadPattern.PEAK_HOURS,
                task_duration_range=(180, 900),  # 3-15 min
                categories=["compute", "io", "mixed", "idle"],
            ),
            UserGroupConfig(
                name="node_peak",
                count=20,
                image=ImageType.NODE,
                pattern=LoadPattern.PEAK_HOURS,
                task_duration_range=(180, 900),
                categories=["compute", "async", "mixed", "idle"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=50, max_sandboxes=250),
            node_pool=PoolConfig(ImageType.NODE, target_ready=50, max_sandboxes=250),
            max_total_sandboxes=500,
            max_concurrent_creates=15,  # Slightly higher for scale
            idle_timeout=180,           # 3 min before scale-down (longer for stability)
            scale_down_delay=30,        # 30s between destructions
            cooldown_after_acquire=300, # 5 min cooldown
            max_warm_age=1200,          # 20 min max age (more cycling)
        ),
        idle_periods=[
            # Regular idle periods to test scale-down
            (7200, 900),    # 15 min idle at 2 hr mark
            (14400, 900),   # 15 min idle at 4 hr mark
            (21600, 900),   # 15 min idle at 6 hr mark
            (25200, 1800),  # 30 min idle at 7 hr mark (wind-down)
        ],
    )


def get_corner_case_blitz() -> ScenarioConfig:
    """Aggressive corner case testing with rapid timing."""
    return ScenarioConfig(
        name="corner_case_blitz",
        description="2-hour aggressive corner case testing with tight timing parameters",
        duration_seconds=7200,  # 2 hours
        user_groups=[
            # High-frequency short tasks (maximize pool churn)
            UserGroupConfig(
                name="python_rapid",
                count=30,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(15, 60),  # 15s-1min
                categories=["compute", "io"],
            ),
            UserGroupConfig(
                name="node_rapid",
                count=30,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(15, 60),
                categories=["async", "io"],
            ),
            # Long-running to test max_warm_age expiry
            UserGroupConfig(
                name="python_long",
                count=10,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 400),  # ~5-6 min (around max_warm_age)
                categories=["mixed", "idle"],
            ),
            UserGroupConfig(
                name="node_long",
                count=10,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 400),
                categories=["mixed", "idle"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=10, max_sandboxes=50),
            node_pool=PoolConfig(ImageType.NODE, target_ready=10, max_sandboxes=50),
            max_total_sandboxes=100,
            max_concurrent_creates=10,
            idle_timeout=30,            # 30s (aggressive)
            scale_down_delay=5,         # 5s (very aggressive)
            cooldown_after_acquire=60,  # 1 min
            max_warm_age=300,           # 5 min (trigger cycling)
            health_check_interval=10,   # 10s (very frequent - stress health checks)
        ),
        idle_periods=[
            (1800, 300),   # 5 min idle at 30 min
            (3600, 300),   # 5 min idle at 60 min
            (5400, 300),   # 5 min idle at 90 min
        ],
    )


def get_scale_boundary() -> ScenarioConfig:
    """Test scale boundaries and limits."""
    return ScenarioConfig(
        name="scale_boundary",
        description="4-hour test pushing scale boundaries - 150 users, 300 sandboxes",
        duration_seconds=14400,  # 4 hours
        user_groups=[
            # All users burst at start to test max creation
            UserGroupConfig(
                name="python_all",
                count=75,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),
                categories=["compute", "io", "mixed"],
            ),
            UserGroupConfig(
                name="node_all",
                count=75,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),
                categories=["compute", "async", "mixed"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=75, max_sandboxes=150),
            node_pool=PoolConfig(ImageType.NODE, target_ready=75, max_sandboxes=150),
            max_total_sandboxes=300,
            max_concurrent_creates=20,  # Test higher concurrency
        ),
        idle_periods=[
            (3600, 1200),   # 20 min idle at 1 hr (full scale-down test)
            (7200, 1200),   # 20 min idle at 2 hr
            (10800, 1200),  # 20 min idle at 3 hr
        ],
    )


SCENARIOS = {
    "quick_validation": get_quick_validation,
    "burst_test": get_burst_test,
    "steady_state": get_steady_state,
    "scale_cycle": get_scale_cycle,
    "full_stress": get_full_stress,
    "mega_stress_8hr": get_mega_stress_8hr,
    "corner_case_blitz": get_corner_case_blitz,
    "scale_boundary": get_scale_boundary,
}


def get_scenario(name: str) -> ScenarioConfig:
    """Get a scenario by name."""
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {name}. Available: {list(SCENARIOS.keys())}")
    return SCENARIOS[name]()


def get_programs_path() -> Path:
    """Get the path to sandbox execution programs."""
    # Try relative to project root
    candidates = [
        Path("sandbox-execution-programs"),
        Path(__file__).parent.parent.parent / "sandbox-execution-programs",
    ]

    for path in candidates:
        if path.exists():
            return path.resolve()

    raise FileNotFoundError("Could not find sandbox-execution-programs directory")


def get_artifacts_path() -> Path:
    """Get the path to test artifacts directory."""
    path = Path(__file__).parent.parent / "artifacts" / "stress"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()
