"""
Orchestrator module for SandboxManager stress tests.

Coordinates the entire stress test execution including:
- Manager initialization
- User group management
- Metrics collection
- Idle period handling
- Report generation
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .algorithmic_simulator import create_algorithmic_mock
from .config import (
    ScenarioConfig,
    get_artifacts_path,
    get_programs_path,
    get_scenario,
)
from .metrics_collector import MetricsCollector
from .reporter import generate_report
from .user_simulator import UserSimulator
from .workload_generator import WorkloadGenerator

logger = logging.getLogger(__name__)


class StressTestOrchestrator:
    """
    Orchestrates the complete stress test execution.

    Responsibilities:
    - Initialize SandboxManager with scenario config
    - Start user simulators for each group
    - Collect metrics at regular intervals
    - Handle idle periods
    - Generate reports on completion
    """

    def __init__(
        self,
        scenario: ScenarioConfig,
        manager: Any | None = None,
        output_dir: Path | None = None,
        dry_run: bool = False,
    ):
        self.scenario = scenario
        self.dry_run = dry_run
        self.output_dir = output_dir or get_artifacts_path()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.workload_gen = WorkloadGenerator(get_programs_path())
        self.metrics = MetricsCollector(scenario.name, self.output_dir)

        # Manager - use provided or create mock
        if manager is not None:
            self.manager = manager
        elif dry_run:
            # Use algorithmic mock that faithfully implements limit tracking
            self.manager = create_algorithmic_mock(scenario)
            logger.info("Using AlgorithmicMockManager for dry-run (enforces real limits)")
        else:
            self.manager = self._create_manager()

        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._users: list[UserSimulator] = []
        self._metrics_task: asyncio.Task | None = None

    def _create_manager(self) -> Any:
        """Create a SandboxManager with scenario configuration."""
        try:
            from do_app_sandbox.manager import PoolConfig, SandboxManager

            config = self.scenario.test_config

            # Create per-image pool configurations
            python_config = PoolConfig(
                max_ready=config.python_pool.max_sandboxes,
                target_ready=config.python_pool.target_ready,
                idle_timeout=config.idle_timeout,
                scale_down_delay=config.scale_down_delay,
                cooldown_after_acquire=config.cooldown_after_acquire,
                max_warm_age=config.max_warm_age,
            )

            node_config = PoolConfig(
                max_ready=config.node_pool.max_sandboxes,
                target_ready=config.node_pool.target_ready,
                idle_timeout=config.idle_timeout,
                scale_down_delay=config.scale_down_delay,
                cooldown_after_acquire=config.cooldown_after_acquire,
                max_warm_age=config.max_warm_age,
            )

            return SandboxManager(
                pools={
                    "python": python_config,
                    "node": node_config,
                },
                max_total_sandboxes=config.max_total_sandboxes,
                max_concurrent_creates=config.max_concurrent_creates,
                sandbox_defaults={
                    "region": config.region,
                    "instance_size": config.instance_size,
                },
            )
        except ImportError as e:
            logger.warning(f"Could not import SandboxManager: {e}")
            logger.warning("Using mock manager for testing")
            return MockSandboxManager()

    async def run(self) -> dict:
        """
        Run the complete stress test.

        Returns dict with:
        - success: bool
        - summary: TestSummary
        - files: dict of output file paths
        """
        logger.info(f"Starting stress test: {self.scenario.name}")
        logger.info(f"Duration: {self.scenario.duration_seconds}s ({self.scenario.duration_seconds / 60:.1f} min)")
        logger.info(f"Total users: {self.scenario.total_users}")
        logger.info(f"Output directory: {self.output_dir}")

        self._running = True
        start_time = time.time()
        end_time = start_time + self.scenario.duration_seconds

        # Set up signal handlers
        self._setup_signal_handlers()

        try:
            # Start metrics collection
            self._metrics_task = asyncio.create_task(self._collect_metrics_loop(end_time))

            # Start manager if it has a start method
            if hasattr(self.manager, "start"):
                await self.manager.start()

            # Run user groups
            await self._run_test(end_time)

        except asyncio.CancelledError:
            logger.info("Test cancelled")
        except Exception as e:
            logger.error(f"Test error: {e}")
            raise
        finally:
            self._running = False

            # Cancel metrics collection
            if self._metrics_task:
                self._metrics_task.cancel()
                try:
                    await self._metrics_task
                except asyncio.CancelledError:
                    pass

            # Stop manager
            if hasattr(self.manager, "shutdown"):
                logger.info("Shutting down manager...")
                await self.manager.shutdown()

        # Report violations from algorithmic mock
        violations = []
        max_observed = 0
        if hasattr(self.manager, "get_violations"):
            violations = self.manager.get_violations()
            max_observed = self.manager.get_max_observed()
            if violations:
                logger.error(f"DETECTED {len(violations)} LIMIT VIOLATIONS!")
                for v in violations:
                    logger.error(f"  {v.violation_type}: {v.actual_value} > {v.limit_value}")
                    logger.error(f"    at {v.timestamp}: {v.details}")
            else:
                logger.info(
                    f"No limit violations detected (max observed: {max_observed}/{self.scenario.test_config.max_total_sandboxes})"
                )

        # Generate reports
        logger.info("Generating reports...")
        files = self.metrics.save_all()
        report_path = generate_report(
            self.metrics,
            self.output_dir / f"report_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.html",
        )
        files["report_html"] = report_path

        summary = self.metrics.generate_summary()

        logger.info("=" * 60)
        logger.info("STRESS TEST COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Duration: {summary.duration_seconds:.1f}s")
        logger.info(f"Total tasks: {summary.total_tasks}")
        logger.info(f"Success rate: {summary.success_rate:.1f}%")
        logger.info(f"Pool hit rate: {summary.pool_hit_rate:.1f}%")
        logger.info(f"Avg acquire latency: {summary.avg_acquire_latency_ms:.0f}ms")
        logger.info(f"Max concurrent: {summary.max_concurrent_sandboxes}")
        if max_observed > 0:
            logger.info(f"Max observed total: {max_observed}/{self.scenario.test_config.max_total_sandboxes}")
        if violations:
            logger.error(f"LIMIT VIOLATIONS: {len(violations)}")
        logger.info("=" * 60)
        logger.info(f"Report: {report_path}")

        # Test passes if: success rate >= 95% AND no limit violations
        test_passed = summary.success_rate >= 95.0 and len(violations) == 0

        return {
            "success": test_passed,
            "summary": summary,
            "files": files,
            "violations": violations,
            "max_observed": max_observed,
        }

    async def _run_test(self, end_time: float):
        """Run all user groups with idle period handling."""
        # Sort idle periods by start time
        idle_periods = sorted(self.scenario.idle_periods, key=lambda x: x[0])
        idle_idx = 0

        # Create all user tasks
        user_tasks = []
        for group in self.scenario.user_groups:
            for i in range(group.count):
                user_id = f"{group.name}_{i + 1}"
                user = UserSimulator(
                    user_id=user_id,
                    group=group,
                    workload_gen=self.workload_gen,
                    metrics=self.metrics,
                    manager=self.manager,
                    test_duration=self.scenario.duration_seconds,
                )
                self._users.append(user)
                user_tasks.append(asyncio.create_task(user.run(end_time)))

        # Monitor and handle idle periods
        while time.time() < end_time and not self._shutdown_event.is_set():
            elapsed = time.time() - (end_time - self.scenario.duration_seconds)

            # Check for idle periods
            if idle_idx < len(idle_periods):
                idle_start, idle_duration = idle_periods[idle_idx]
                if elapsed >= idle_start and elapsed < idle_start + idle_duration:
                    logger.info(f"Entering idle period ({idle_duration}s)...")
                    # During idle, users continue but may not acquire new sandboxes
                    await asyncio.sleep(min(idle_duration, end_time - time.time()))
                    idle_idx += 1
                    logger.info("Idle period ended")

            await asyncio.sleep(1)

        # Wait for all users to complete
        if user_tasks:
            await asyncio.gather(*user_tasks, return_exceptions=True)

    async def _collect_metrics_loop(self, end_time: float):
        """Collect metrics at regular intervals."""
        interval = self.scenario.test_config.metrics_interval

        while time.time() < end_time and not self._shutdown_event.is_set():
            try:
                snapshot = self.metrics.take_snapshot(self.manager)
                logger.debug(
                    f"Metrics: total={snapshot.total_sandboxes} "
                    f"ready={snapshot.total_ready} "
                    f"in_use={snapshot.total_in_use} "
                    f"hit_rate={snapshot.pool_hit_rate:.1f}%"
                )
            except Exception as e:
                logger.error(f"Metrics collection error: {e}")

            await asyncio.sleep(interval)

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._shutdown_event.set()
            for user in self._users:
                user.stop()

        if sys.platform != "win32":
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

    def stop(self):
        """Request graceful shutdown."""
        self._shutdown_event.set()
        for user in self._users:
            user.stop()


class MockSandboxManager:
    """Mock manager for dry-run testing."""

    def __init__(self):
        self._sandboxes = {}
        self._acquire_count = 0
        self._pool_hits = 0

    async def start(self):
        logger.info("Mock manager started")

    async def shutdown(self):
        logger.info("Mock manager shutdown")

    async def acquire(self, image: str):
        self._acquire_count += 1
        from_pool = random.random() > 0.3
        if from_pool:
            self._pool_hits += 1

        # Simulate acquire time
        if from_pool:
            await asyncio.sleep(random.uniform(0.1, 0.5))
        else:
            await asyncio.sleep(random.uniform(1.0, 5.0))

        sandbox = MockSandbox(image, from_pool)
        self._sandboxes[id(sandbox)] = sandbox
        return sandbox

    async def release(self, sandbox):
        self._sandboxes.pop(id(sandbox), None)

    def get_stats(self) -> dict:
        return {
            "python_ready": random.randint(0, 5),
            "python_creating": random.randint(0, 2),
            "python_in_use": random.randint(0, 10),
            "node_ready": random.randint(0, 5),
            "node_creating": random.randint(0, 2),
            "node_in_use": random.randint(0, 10),
            "total_sandboxes": len(self._sandboxes) + random.randint(0, 10),
        }


class MockSandbox:
    """Mock sandbox for testing."""

    def __init__(self, image: str, from_pool: bool):
        self.image = image
        self._from_pool = from_pool
        self.filesystem = MockFilesystem()

    def exec(self, command: str, timeout: int = 60) -> str:
        # Simulate execution
        time.sleep(min(0.5, timeout / 100))
        return "RESULT: mock=true duration=0.5s iterations=100"

    async def close(self):
        pass


class MockFilesystem:
    """Mock filesystem for testing."""

    def write_file(self, path: str, content: str):
        pass

    def read_file(self, path: str) -> str:
        return ""


# Need to import random for MockSandboxManager
import random


async def run_stress_test(
    scenario_name: str,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Convenience function to run a stress test.

    Args:
        scenario_name: Name of predefined scenario or path to YAML
        output_dir: Output directory for reports
        dry_run: If True, use mock manager

    Returns:
        dict with test results
    """
    scenario = get_scenario(scenario_name)
    orchestrator = StressTestOrchestrator(
        scenario=scenario,
        output_dir=output_dir,
        dry_run=dry_run,
    )
    return await orchestrator.run()
