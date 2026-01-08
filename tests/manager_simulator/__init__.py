"""Manager Stress Algorithmic Simulator.

This module provides deterministic demand curve testing for the SandboxManager
pool algorithm. Run simulations in seconds without real sandboxes.

Usage:
    # Run algorithm tests
    uv run --extra dev pytest tests/manager_simulator/test_demand_curves.py -v

    # Run demo with chart generation
    uv run python -m tests.manager_simulator.demand_curves
"""

from .algorithmic_simulator import AlgorithmicMockManager, SimulatedSandbox
from .demand_curves import (
    DemandPoint,
    DemandCurve,
    SimulationResult,
    steady_load,
    sudden_spike,
    wave_pattern,
    bursty,
    run_simulation,
    generate_chart_html,
)

__all__ = [
    # Mock manager
    "AlgorithmicMockManager",
    "SimulatedSandbox",
    # Demand curves
    "DemandPoint",
    "DemandCurve",
    "SimulationResult",
    "steady_load",
    "sudden_spike",
    "wave_pattern",
    "bursty",
    "run_simulation",
    "generate_chart_html",
]
