"""
Simulation Configuration for Manager Simulator.

Edit this file to tune simulation parameters without modifying test code.
Provides presets for different testing scenarios.

Usage:
    from .simulation_config import POOL_PRESETS, DEFAULT_TIMING, TimingConfig

    # Use a preset
    preset = POOL_PRESETS["aggressive"]
    pool_config = preset["pools"]
    max_total = preset["max_total_sandboxes"]

    # Or customize timing
    timing = TimingConfig(cold_start_time_seconds=45.0, min_hold_time_seconds=600.0)
"""

from dataclasses import dataclass
from typing import Any

# =============================================================================
# Timing Configuration
# =============================================================================


@dataclass
class TimingConfig:
    """
    Timing parameters for simulation.

    All times are in seconds unless otherwise noted.
    """

    # Sandbox creation/acquisition times
    cold_start_time_seconds: float = 30.0  # Time to create a new sandbox
    warm_start_time_seconds: float = 0.05  # Time to acquire from pool (50ms)

    # Hold time configuration (how long sandboxes are held before release)
    min_hold_time_seconds: float = 300.0  # Minimum hold time (5 minutes)
    max_hold_time_seconds: float = 3600.0  # Maximum hold time (1 hour)

    # Simulation speed
    time_acceleration: float = 1000.0  # Simulation speed multiplier

    # Metrics collection
    snapshot_interval: float = 10.0  # Seconds between metrics snapshots


# =============================================================================
# Pool Configuration
# =============================================================================


@dataclass
class PoolConfig:
    """Configuration for a single image pool."""

    target_ready: int = 5  # Target number of warm sandboxes in pool
    max_sandboxes: int = 20  # Maximum sandboxes for this pool


def pool_config_to_dict(config: PoolConfig) -> dict[str, Any]:
    """Convert PoolConfig to dict format expected by run_simulation."""
    return {
        "target_ready": config.target_ready,
        "max_sandboxes": config.max_sandboxes,
    }


# =============================================================================
# Pool Presets
# =============================================================================

# Edit these presets to tune behavior for different scenarios
POOL_PRESETS: dict[str, dict[str, Any]] = {
    # Small pool for quick tests
    "small": {
        "pools": {
            "python": pool_config_to_dict(PoolConfig(target_ready=5, max_sandboxes=10)),
        },
        "max_total_sandboxes": 10,
    },
    # Medium pool for typical workloads
    "medium": {
        "pools": {
            "python": pool_config_to_dict(PoolConfig(target_ready=10, max_sandboxes=25)),
            "node": pool_config_to_dict(PoolConfig(target_ready=8, max_sandboxes=20)),
        },
        "max_total_sandboxes": 40,
    },
    # Large pool for stress tests
    "large": {
        "pools": {
            "python": pool_config_to_dict(PoolConfig(target_ready=20, max_sandboxes=50)),
            "node": pool_config_to_dict(PoolConfig(target_ready=15, max_sandboxes=40)),
        },
        "max_total_sandboxes": 80,
    },
    # Aggressive scaling for high hit rate
    "aggressive": {
        "pools": {
            "python": pool_config_to_dict(PoolConfig(target_ready=15, max_sandboxes=20)),
        },
        "max_total_sandboxes": 20,
    },
    # Conservative for cost optimization (lower hit rate expected)
    "conservative": {
        "pools": {
            "python": pool_config_to_dict(PoolConfig(target_ready=3, max_sandboxes=10)),
        },
        "max_total_sandboxes": 10,
    },
}


# =============================================================================
# Workload Presets (App Platform Use Cases)
# =============================================================================

# These presets represent realistic App Platform sandbox workloads.
# App Platform sandboxes are designed for long-running workloads (5+ minutes),
# NOT serverless-style short calls (< 1 minute).
#
# Key formula: concurrent_load = requests_per_minute × avg_hold_minutes
# For 95% hit rate, target_ready ≈ concurrent_load × 1.1


@dataclass
class WorkloadPreset:
    """A realistic workload scenario for App Platform sandboxes."""

    name: str
    description: str
    requests_per_minute: float
    min_hold_minutes: float
    max_hold_minutes: float
    recommended_target_ready: int
    recommended_max_sandboxes: int
    expected_hit_rate: str  # e.g., "95%+"

    @property
    def avg_hold_minutes(self) -> float:
        return (self.min_hold_minutes + self.max_hold_minutes) / 2

    @property
    def concurrent_load(self) -> float:
        return self.requests_per_minute * self.avg_hold_minutes


WORKLOAD_PRESETS: dict[str, WorkloadPreset] = {
    # Light batch processing - typical for small data jobs
    "light_batch": WorkloadPreset(
        name="light_batch",
        description="Light batch processing (4 jobs/min, 10-min avg)",
        requests_per_minute=4.0,
        min_hold_minutes=5.0,
        max_hold_minutes=15.0,
        recommended_target_ready=50,
        recommended_max_sandboxes=75,
        expected_hit_rate="95%+",
    ),
    # Heavy batch processing - typical for ETL, data pipelines
    "heavy_batch": WorkloadPreset(
        name="heavy_batch",
        description="Heavy batch processing (10 jobs/min, 30-min avg)",
        requests_per_minute=10.0,
        min_hold_minutes=15.0,
        max_hold_minutes=60.0,
        recommended_target_ready=400,
        recommended_max_sandboxes=600,
        expected_hit_rate="95%+",
    ),
    # AI/ML inference - typical for model serving with longer inference times
    "ai_inference": WorkloadPreset(
        name="ai_inference",
        description="AI inference jobs (2 jobs/min, 5-min avg)",
        requests_per_minute=2.0,
        min_hold_minutes=3.0,
        max_hold_minutes=10.0,
        recommended_target_ready=15,
        recommended_max_sandboxes=25,
        expected_hit_rate="95%+",
    ),
    # Code execution - typical for interactive coding environments
    "code_execution": WorkloadPreset(
        name="code_execution",
        description="Code execution sessions (6 jobs/min, 15-min avg)",
        requests_per_minute=6.0,
        min_hold_minutes=5.0,
        max_hold_minutes=30.0,
        recommended_target_ready=120,
        recommended_max_sandboxes=180,
        expected_hit_rate="95%+",
    ),
    # Long-running jobs - builds, deployments, CI/CD
    "long_running": WorkloadPreset(
        name="long_running",
        description="Long-running jobs (1 job/min, 45-min avg)",
        requests_per_minute=1.0,
        min_hold_minutes=30.0,
        max_hold_minutes=60.0,
        recommended_target_ready=50,
        recommended_max_sandboxes=75,
        expected_hit_rate="95%+",
    ),
}


def get_workload_preset(name: str) -> WorkloadPreset:
    """Get a workload preset by name."""
    if name not in WORKLOAD_PRESETS:
        available = ", ".join(WORKLOAD_PRESETS.keys())
        raise KeyError(f"Unknown workload preset '{name}'. Available: {available}")
    return WORKLOAD_PRESETS[name]


def list_workload_presets() -> None:
    """Print all available workload presets with their parameters."""
    print("\nAvailable Workload Presets:")
    print("=" * 70)
    for name, preset in WORKLOAD_PRESETS.items():
        print(f"\n{name}:")
        print(f"  {preset.description}")
        print(f"  Concurrent load: {preset.concurrent_load:.0f} sandboxes")
        print(f"  Recommended: target_ready={preset.recommended_target_ready}")
        print(f"  Expected hit rate: {preset.expected_hit_rate}")
    print()


# =============================================================================
# Demand Curve Presets
# =============================================================================

# These are parameter dictionaries that can be passed to curve generators
CURVE_PRESETS: dict[str, dict[str, Any]] = {
    # 1-hour wave pattern (simulates daily traffic cycles)
    "wave_1h": {
        "type": "wave_pattern",
        "min_rps": 2,
        "max_rps": 10,
        "period_seconds": 1800,  # 30-minute wave cycle
        "duration_seconds": 3600,  # 1 hour total
    },
    # Spike test - sudden burst of traffic
    "spike_test": {
        "type": "sudden_spike",
        "baseline": 3,
        "spike": 15,
        "spike_at": 300,  # Spike at 5 minutes
        "spike_duration": 120,  # 2 minutes of spike
        "total_duration": 900,  # 15 minutes total
    },
    # Steady load for baseline testing
    "steady_load": {
        "type": "steady_load",
        "requests_per_10s": 5,
        "duration_seconds": 1800,  # 30 minutes
    },
    # Gradual ramp up
    "ramp_up": {
        "type": "gradual_ramp",
        "start_rps": 1,
        "end_rps": 15,
        "duration_seconds": 1800,  # 30-minute ramp
    },
    # Bursty pattern (CI/CD style)
    "bursty": {
        "type": "bursty",
        "burst_size": 10,
        "burst_interval_seconds": 60,
        "quiet_duration_seconds": 30,
        "total_duration_seconds": 900,  # 15 minutes
    },
}


# =============================================================================
# Default Configuration
# =============================================================================

DEFAULT_TIMING = TimingConfig()
DEFAULT_POOL_PRESET = "medium"
DEFAULT_CURVE_PRESET = "wave_1h"


# =============================================================================
# Helper Functions
# =============================================================================


def get_pool_config(preset_name: str) -> dict[str, dict[str, Any]]:
    """
    Get pool configuration dict from a preset name.

    Args:
        preset_name: Name of the preset (small, medium, large, aggressive, conservative)

    Returns:
        Dict with 'pools' and 'max_total_sandboxes' keys

    Raises:
        KeyError: If preset_name is not found
    """
    if preset_name not in POOL_PRESETS:
        available = ", ".join(POOL_PRESETS.keys())
        raise KeyError(f"Unknown preset '{preset_name}'. Available: {available}")
    return POOL_PRESETS[preset_name]


def create_custom_timing(
    cold_start: float = 30.0,
    warm_start: float = 0.05,
    min_hold: float = 300.0,
    max_hold: float = 3600.0,
    acceleration: float = 1000.0,
) -> TimingConfig:
    """
    Create a custom TimingConfig with specified values.

    Args:
        cold_start: Time to create new sandbox (seconds)
        warm_start: Time to acquire from pool (seconds)
        min_hold: Minimum hold time before release (seconds)
        max_hold: Maximum hold time before release (seconds)
        acceleration: Simulation speed multiplier

    Returns:
        Configured TimingConfig instance
    """
    return TimingConfig(
        cold_start_time_seconds=cold_start,
        warm_start_time_seconds=warm_start,
        min_hold_time_seconds=min_hold,
        max_hold_time_seconds=max_hold,
        time_acceleration=acceleration,
    )
