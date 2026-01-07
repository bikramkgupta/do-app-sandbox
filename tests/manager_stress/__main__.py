#!/usr/bin/env python3
"""
CLI entry point for SandboxManager stress tests.

Usage:
    # Run quick validation (5-10 min)
    uv run python -m tests.manager_stress --scenario quick_validation

    # Run full stress test (2+ hours)
    uv run python -m tests.manager_stress --scenario full_stress

    # Dry run (mock manager, no real sandboxes)
    uv run python -m tests.manager_stress --scenario quick_validation --dry-run

    # List available scenarios
    uv run python -m tests.manager_stress --list-scenarios

    # Validate programs
    uv run python -m tests.manager_stress --validate-programs
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import SCENARIOS, get_scenario
from .workload_generator import WorkloadGenerator, create_workload_generator
from .orchestrator import run_stress_test


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce noise from some libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def list_scenarios():
    """Print available scenarios."""
    print("\nAvailable Scenarios:")
    print("=" * 60)

    for name, factory in SCENARIOS.items():
        scenario = factory()
        duration_min = scenario.duration_seconds / 60
        print(f"\n{name}")
        print(f"  {scenario.description}")
        print(f"  Duration: {duration_min:.0f} minutes")
        print(f"  Users: {scenario.total_users}")
        print(f"  Groups:")
        for group in scenario.user_groups:
            print(f"    - {group.name}: {group.count} users, {group.pattern.value} pattern")


def validate_programs():
    """Validate that all expected programs exist."""
    print("\nValidating Programs:")
    print("=" * 60)

    try:
        workload_gen = create_workload_generator()
        missing = workload_gen.validate_programs()

        if missing:
            print("\nMissing programs:")
            for category, programs in missing.items():
                print(f"\n  {category}:")
                for prog in programs:
                    print(f"    - {prog}")
            return False
        else:
            print("\nAll programs found!")
            counts = workload_gen.get_program_count()
            total = sum(counts.values())
            print(f"\nTotal programs: {total}")
            for category, count in sorted(counts.items()):
                print(f"  {category}: {count}")
            return True
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        return False


def show_scenario_details(name: str):
    """Show detailed information about a scenario."""
    try:
        scenario = get_scenario(name)
    except ValueError as e:
        print(f"Error: {e}")
        return

    print(f"\nScenario: {scenario.name}")
    print("=" * 60)
    print(f"Description: {scenario.description}")
    print(f"Duration: {scenario.duration_seconds}s ({scenario.duration_seconds/60:.1f} min)")
    print(f"Total Users: {scenario.total_users}")

    print("\nPool Configuration:")
    config = scenario.test_config
    print(f"  Python: target={config.python_pool.target_ready}, max={config.python_pool.max_sandboxes}")
    print(f"  Node: target={config.node_pool.target_ready}, max={config.node_pool.max_sandboxes}")
    print(f"  Max Total: {config.max_total_sandboxes}")

    print("\nUser Groups:")
    for group in scenario.user_groups:
        min_dur, max_dur = group.task_duration_range
        print(f"\n  {group.name}:")
        print(f"    Count: {group.count}")
        print(f"    Image: {group.image.value}")
        print(f"    Pattern: {group.pattern.value}")
        print(f"    Task Duration: {min_dur}-{max_dur}s")
        print(f"    Categories: {', '.join(group.categories)}")

    if scenario.idle_periods:
        print("\nIdle Periods:")
        for start, duration in scenario.idle_periods:
            print(f"  At {start}s: {duration}s idle")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SandboxManager Stress Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick validation test (5-10 min)
  python -m tests.manager_stress --scenario quick_validation

  # Full stress test (2+ hours)
  python -m tests.manager_stress --scenario full_stress

  # Dry run (no real sandboxes)
  python -m tests.manager_stress --scenario quick_validation --dry-run

  # List available scenarios
  python -m tests.manager_stress --list-scenarios
        """,
    )

    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        help="Scenario to run",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for reports (default: tests/artifacts/stress/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use mock manager (no real sandboxes)",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List available scenarios",
    )
    parser.add_argument(
        "--show-scenario",
        metavar="NAME",
        help="Show detailed info about a scenario",
    )
    parser.add_argument(
        "--validate-programs",
        action="store_true",
        help="Validate that all test programs exist",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Handle info commands
    if args.list_scenarios:
        list_scenarios()
        return 0

    if args.show_scenario:
        show_scenario_details(args.show_scenario)
        return 0

    if args.validate_programs:
        success = validate_programs()
        return 0 if success else 1

    # Require scenario for actual test run
    if not args.scenario:
        parser.print_help()
        print("\nError: --scenario is required to run a test")
        return 1

    # Set up logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Show scenario info
    scenario = get_scenario(args.scenario)
    logger.info("=" * 60)
    logger.info(f"STRESS TEST: {scenario.name}")
    logger.info("=" * 60)
    logger.info(f"Description: {scenario.description}")
    logger.info(f"Duration: {scenario.duration_seconds}s ({scenario.duration_seconds/60:.1f} min)")
    logger.info(f"Users: {scenario.total_users}")
    logger.info(f"Dry run: {args.dry_run}")

    if args.dry_run:
        logger.warning("Running in DRY RUN mode - no real sandboxes will be created")

    # Confirm before long tests
    if scenario.duration_seconds > 1800 and not args.dry_run:
        logger.warning(f"This test will run for {scenario.duration_seconds/60:.0f} minutes")
        try:
            response = input("Continue? [y/N] ")
            if response.lower() != 'y':
                logger.info("Aborted")
                return 0
        except (EOFError, KeyboardInterrupt):
            logger.info("Aborted")
            return 0

    # Run the test
    try:
        result = await run_stress_test(
            scenario_name=args.scenario,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )

        if result['success']:
            logger.info("TEST PASSED")
            return 0
        else:
            logger.error("TEST FAILED - success rate below 95%")
            return 1

    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Test failed with error: {e}")
        return 1


def run():
    """Entry point for running from command line."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    run()
