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
from typing import Dict, Any


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


def pool_config_to_dict(config: PoolConfig) -> Dict[str, Any]:
    """Convert PoolConfig to dict format expected by run_simulation."""
    return {
        "target_ready": config.target_ready,
        "max_sandboxes": config.max_sandboxes,
    }


# =============================================================================
# Pool Presets
# =============================================================================

# Edit these presets to tune behavior for different scenarios
POOL_PRESETS: Dict[str, Dict[str, Any]] = {
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
# Demand Curve Presets
# =============================================================================

# These are parameter dictionaries that can be passed to curve generators
CURVE_PRESETS: Dict[str, Dict[str, Any]] = {
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


def get_pool_config(preset_name: str) -> Dict[str, Dict[str, Any]]:
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
