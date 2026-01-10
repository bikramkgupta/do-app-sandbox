#!/usr/bin/env python3
"""
Rigorous Pool Test - Main Entry Point

A comprehensive stress test for the do-app-sandbox SDK that validates:
- Command correctness (0 failure tolerance)
- Pool effectiveness (pool hits vs cold starts)
- Capacity enforcement (never exceed 25 sandboxes)
- Lifecycle robustness

Usage:
    # Smoke test (10 minutes)
    uv run python -m tests.stress.pool_capacity.run_25cap_4hr --smoke

    # Main 4-hour run
    uv run python -m tests.stress.pool_capacity.run_25cap_4hr

    # Custom configuration
    uv run python -m tests.stress.pool_capacity.run_25cap_4hr \
        --duration-seconds 3600 \
        --max-total 15 \
        --concurrency 8
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for SDK imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from do_app_sandbox import PoolConfig, SandboxManager

from .config import (
    SMOKE_CONFIG,
    RetryConfig,
    TestConfig,
    WatchdogConfig,
)
from .metrics import MetricsCollector
from .reporter import Reporter
from .session import session_worker
from .utils import format_duration, setup_logging
from .watchdog import DisabledWatchdog, SandboxWatchdog

logger = logging.getLogger("rigorous_pool_test")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Rigorous Pool Test for do-app-sandbox SDK",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Preset modes
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run smoke test (10 minutes, 5 sandboxes, 4 workers)",
    )

    # Duration
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=14400,
        help="Test duration in seconds",
    )

    # Sandbox limits
    parser.add_argument(
        "--max-total",
        type=int,
        default=25,
        help="Maximum total sandboxes (HARD LIMIT)",
    )

    # Region and sizing
    parser.add_argument(
        "--region",
        type=str,
        default="syd1",
        help="Sandbox region",
    )
    parser.add_argument(
        "--instance-size",
        type=str,
        default="basic-xxs",
        help="Sandbox instance size",
    )

    # Concurrency
    parser.add_argument(
        "--concurrency",
        type=int,
        default=12,
        help="Number of virtual users (workers)",
    )

    # Pool configuration
    parser.add_argument(
        "--python-target-ready",
        type=int,
        default=12,
        help="Python pool target ready count",
    )
    parser.add_argument(
        "--python-max-ready",
        type=int,
        default=15,
        help="Python pool max ready count",
    )
    parser.add_argument(
        "--node-target-ready",
        type=int,
        default=0,
        help="Node pool target ready count (0 to disable)",
    )

    # Commands
    parser.add_argument(
        "--disable-network-commands",
        action="store_true",
        help="Disable network-dependent commands",
    )

    # Reporting
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Report output directory (auto-generated if not specified)",
    )

    # Watchdog
    parser.add_argument(
        "--watchdog-interval",
        type=float,
        default=10.0,
        help="Watchdog polling interval in seconds",
    )
    parser.add_argument(
        "--watchdog-grace",
        type=int,
        default=2,
        help="Watchdog grace period (allow brief overage)",
    )
    parser.add_argument(
        "--disable-watchdog",
        action="store_true",
        help="Disable external watchdog monitoring",
    )
    parser.add_argument(
        "--enable-emergency-cleanup",
        action="store_true",
        help="Enable watchdog emergency cleanup of excess sandboxes",
    )

    # Logging
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def build_config(args: argparse.Namespace) -> TestConfig:
    """Build TestConfig from command line arguments."""
    if args.smoke:
        config = SMOKE_CONFIG
        # Override report_dir to include timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        config.report_dir = f"tests/artifacts/rigorous_pool_test/smoke_{timestamp}"
        return config

    return TestConfig(
        duration_seconds=args.duration_seconds,
        max_total_sandboxes=args.max_total,
        region=args.region,
        instance_size=args.instance_size,
        concurrency=args.concurrency,
        python_target_ready=args.python_target_ready,
        python_max_ready=args.python_max_ready,
        node_target_ready=args.node_target_ready,
        enable_network_commands=not args.disable_network_commands,
        report_dir=args.report_dir,
        watchdog_enabled=not args.disable_watchdog,
        watchdog_interval=args.watchdog_interval,
        watchdog_grace_period=args.watchdog_grace,
    )


async def main():
    """Main entry point."""
    args = parse_args()
    config = build_config(args)
    retry_config = RetryConfig()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(config.report_dir, level=log_level)

    logger.info("=" * 60)
    logger.info("RIGOROUS POOL TEST")
    logger.info("=" * 60)
    logger.info(f"Duration: {format_duration(config.duration_seconds)}")
    logger.info(f"Max sandboxes: {config.max_total_sandboxes}")
    logger.info(f"Concurrency: {config.concurrency}")
    logger.info(f"Region: {config.region}")
    logger.info(f"Report dir: {config.report_dir}")
    logger.info(f"Watchdog: {'enabled' if config.watchdog_enabled else 'disabled'}")
    logger.info("=" * 60)

    # Pre-flight check: count existing sandbox apps
    try:
        import json
        import subprocess

        result = subprocess.run(
            ["doctl", "apps", "list", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            apps = json.loads(result.stdout)
            existing_sandboxes = [a for a in apps if "sandbox" in a.get("spec", {}).get("name", "").lower()]
            if existing_sandboxes:
                logger.warning(f"PRE-FLIGHT: Found {len(existing_sandboxes)} existing sandbox apps!")
                for app in existing_sandboxes[:5]:
                    name = app.get("spec", {}).get("name", "unknown")
                    created = app.get("created_at", "unknown")
                    logger.warning(f"  - {name} (created: {created})")
                if len(existing_sandboxes) > 5:
                    logger.warning(f"  ... and {len(existing_sandboxes) - 5} more")
                logger.warning("These will be counted by watchdog but NOT by internal metrics!")
                logger.warning(
                    "Consider cleaning up with: doctl apps list | grep sandbox | awk '{print $1}' | xargs -I{} doctl apps delete {} --force"
                )
            else:
                logger.info("PRE-FLIGHT: No existing sandbox apps found - clean environment")
    except Exception as e:
        logger.warning(f"PRE-FLIGHT check failed: {e}")

    # Initialize components
    stop_event = asyncio.Event()
    metrics_collector = MetricsCollector(max_total=config.max_total_sandboxes)
    reporter = Reporter(config.report_dir)

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.warning(f"Received signal {sig} - initiating shutdown")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Setup watchdog
    watchdog = None
    if config.watchdog_enabled:
        watchdog_config = WatchdogConfig(
            max_sandboxes=config.max_total_sandboxes,
            poll_interval=config.watchdog_interval,
            grace_period=config.watchdog_grace_period,
        )

        def on_violation():
            logger.critical("WATCHDOG TRIGGERED - stopping all workers")
            stop_event.set()

        emergency_cleanup = None
        if args.enable_emergency_cleanup:

            async def emergency_cleanup(apps):
                await watchdog.emergency_delete(apps, config.max_total_sandboxes)

        watchdog = SandboxWatchdog(
            config=watchdog_config,
            on_violation=on_violation,
            on_emergency_cleanup=emergency_cleanup,
        )
    else:
        watchdog = DisabledWatchdog()

    # Build pool configuration
    pools = {}
    if config.python_target_ready > 0:
        pools["python"] = PoolConfig(
            target_ready=config.python_target_ready,
            max_ready=config.python_max_ready,
            idle_timeout=120,
            health_check_interval=60,
            on_empty="create",
            create_retries=3,
            create_retry_delay=5,
        )

    if config.node_target_ready > 0:
        pools["node"] = PoolConfig(
            target_ready=config.node_target_ready,
            max_ready=config.node_target_ready + 3,
            idle_timeout=120,
            health_check_interval=60,
            on_empty="create",
            create_retries=3,
            create_retry_delay=5,
        )

    # Initialize manager
    manager = SandboxManager(
        max_total_sandboxes=config.max_total_sandboxes,
        max_concurrent_creates=10,
        sandbox_defaults={
            "region": config.region,
            "instance_size": config.instance_size,
        },
        pools=pools,
    )

    try:
        # Start manager
        logger.info("Starting SandboxManager...")
        await manager.start()
        logger.info("SandboxManager started")

        # Start metrics collection
        metrics_collector.start()

        # Start watchdog
        watchdog_task = asyncio.create_task(watchdog.run(stop_event))

        # Start pool metrics sampling
        sampling_task = asyncio.create_task(
            metrics_collector.sample_pool_metrics(
                manager,
                interval=5.0,
                stop_event=stop_event,
            )
        )

        # Determine which image to use (default to python)
        image = "python" if "python" in pools else list(pools.keys())[0]

        # Launch worker tasks
        logger.info(f"Launching {config.concurrency} workers...")
        worker_tasks = []
        for i in range(config.concurrency):
            task = asyncio.create_task(
                session_worker(
                    worker_id=i,
                    manager=manager,
                    image=image,
                    config=config,
                    retry_config=retry_config,
                    stop_event=stop_event,
                    results_callback=metrics_collector.add_session,
                )
            )
            worker_tasks.append(task)

        # Set up duration timer
        async def duration_timer():
            try:
                await asyncio.sleep(config.duration_seconds)
                logger.info("Test duration elapsed - stopping workers")
                stop_event.set()
            except asyncio.CancelledError:
                pass

        timer_task = asyncio.create_task(duration_timer())

        # Wait for workers to complete
        logger.info(f"Test running for {format_duration(config.duration_seconds)}...")
        await asyncio.gather(*worker_tasks, return_exceptions=True)

        # Cancel timer if still running
        timer_task.cancel()
        try:
            await timer_task
        except asyncio.CancelledError:
            pass

        # Stop metrics sampling
        stop_event.set()
        await sampling_task

        # Stop watchdog
        watchdog.stop()
        await watchdog_task

        logger.info("All workers completed")

    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        stop_event.set()
        raise

    finally:
        # Shutdown manager
        logger.info("Shutting down SandboxManager...")
        try:
            await manager.shutdown(timeout=60.0, wait_for_active=True)
            logger.info("SandboxManager shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        # Final Cleanup Sweep
        logger.info("Performing final cleanup sweep...")
        try:
            # Re-use watchdog or create temporary one to clean up
            if watchdog:
                count, apps = await watchdog.get_sandbox_count()
                if count > 0:
                    logger.warning(f"Final Sweep: Found {count} remaining sandboxes. Deleting...")
                    await watchdog.emergency_delete(apps, keep_count=0)
                else:
                    logger.info("Final Sweep: No leftover sandboxes found.")
        except Exception as e:
            logger.error(f"Final cleanup failed: {e}")

        # Mark test end
        metrics_collector.stop()

        # Get final metrics from manager
        try:
            raw_pool_metrics = manager.metrics()
        except Exception:
            raw_pool_metrics = {}

        # Get watchdog metrics
        watchdog_metrics = watchdog.get_metrics()

        # Generate summary
        summary = metrics_collector.get_summary(watchdog_metrics)

        # Write reports
        reporter.write_all(
            summary=summary,
            sessions=metrics_collector.sessions,
            raw_pool_metrics=raw_pool_metrics,
            max_observed=metrics_collector.max_observed_total,
        )

        # Exit with appropriate code
        if summary.passed:
            logger.info("TEST PASSED")
            sys.exit(0)
        else:
            logger.error("TEST FAILED")
            if summary.total_command_failures > 0:
                logger.error(f"  - {summary.total_command_failures} command failures")
            if summary.capacity_violations > 0:
                logger.error(f"  - {summary.capacity_violations} capacity violations")
            if watchdog_metrics.violation_detected:
                logger.error("  - Watchdog violation detected")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
