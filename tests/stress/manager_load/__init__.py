"""SandboxManager stress test suite.

This module provides comprehensive stress testing for SandboxManager
with support for 50 concurrent sandboxes (25 Python + 25 Node),
various load patterns, and detailed metrics collection.

Usage:
    # Run from command line
    uv run python -m tests.stress.manager_load --scenario quick_validation
    uv run python -m tests.stress.manager_load --scenario full_stress --dry-run
    uv run python -m tests.stress.manager_load --list-scenarios

    # Programmatic usage
    from tests.stress.manager_load import run_stress_test
    result = await run_stress_test("quick_validation", dry_run=True)

See PLAN.md for the full implementation plan and progress tracking.
"""

from .config import (
    SCENARIOS,
    ImageType,
    LoadPattern,
    PoolConfig,
    ScenarioConfig,
    TestConfig,
    UserGroupConfig,
    get_scenario,
)
from .metrics_collector import (
    MetricsCollector,
    PoolSnapshot,
    TaskResult,
    TestSummary,
)
from .orchestrator import (
    StressTestOrchestrator,
    run_stress_test,
)
from .reporter import (
    HTMLReporter,
    generate_report,
)
from .user_simulator import (
    LoadPatternGenerator,
    UserSimulator,
    UserState,
)
from .workload_generator import (
    ProgramSpec,
    WorkloadGenerator,
    create_workload_generator,
)

__all__ = [
    # Config
    "LoadPattern",
    "ImageType",
    "PoolConfig",
    "UserGroupConfig",
    "TestConfig",
    "ScenarioConfig",
    "get_scenario",
    "SCENARIOS",
    # Metrics
    "MetricsCollector",
    "PoolSnapshot",
    "TaskResult",
    "TestSummary",
    # Workload
    "WorkloadGenerator",
    "ProgramSpec",
    "create_workload_generator",
    # User simulation
    "UserSimulator",
    "UserState",
    "LoadPatternGenerator",
    # Orchestration
    "StressTestOrchestrator",
    "run_stress_test",
    # Reporting
    "HTMLReporter",
    "generate_report",
]
