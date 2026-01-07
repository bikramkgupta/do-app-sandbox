#!/usr/bin/env python3
"""
Test 2: Benchmark Sandbox Creation with Spaces

Tests sandbox creation performance using credentials from .env file.
Based on tests/benchmarks/sandbox_create_benchmark.py
"""

import asyncio
import os
import sys
import time
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

# Load .env file if dotenv available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from do_app_sandbox import Sandbox
from do_app_sandbox.spaces import SpacesConfig


@dataclass
class BenchmarkResult:
    """Result of a single sandbox creation benchmark."""
    index: int
    image: str
    app_id: Optional[str] = None
    create_time_s: float = 0.0
    exec_time_s: float = 0.0
    delete_time_s: float = 0.0
    total_time_s: float = 0.0
    success: bool = False
    error: Optional[str] = None


@dataclass
class BenchmarkSummary:
    """Summary of all benchmark results."""
    test_name: str = "Sandbox Creation Benchmark"
    num_sandboxes: int = 0
    successful: int = 0
    failed: int = 0
    overall_time_s: float = 0.0
    avg_create_s: float = 0.0
    min_create_s: float = 0.0
    max_create_s: float = 0.0
    median_create_s: float = 0.0
    spaces_enabled: bool = False
    timestamp: str = ""
    results: list = None


def get_spaces_config() -> Optional[SpacesConfig]:
    """Get Spaces config from environment if available."""
    endpoint = os.getenv("SPACES_ENDPOINT")
    access_key = os.getenv("SPACES_ACCESS_KEY")
    secret_key = os.getenv("SPACES_ACCESS_SECRET") or os.getenv("SPACES_SECRET_KEY")

    if endpoint and access_key and secret_key:
        # Parse bucket and region from endpoint
        # Format: https://bucket.region.digitaloceanspaces.com
        parts = endpoint.replace("https://", "").split(".")
        if len(parts) >= 3:
            bucket = parts[0]
            region = parts[1]
            return SpacesConfig(
                bucket=bucket,
                region=region,
                access_key=access_key,
                secret_key=secret_key,
            )
    return None


async def create_and_test_sandbox(
    index: int,
    image: str,
    semaphore: asyncio.Semaphore,
    spaces_config: Optional[SpacesConfig] = None
) -> BenchmarkResult:
    """Create a sandbox, run a command, delete it."""
    result = BenchmarkResult(index=index, image=image)
    start_total = time.time()

    async with semaphore:
        try:
            print(f"[{index:02d}] Creating {image} sandbox...")
            create_start = time.time()

            sandbox = await asyncio.to_thread(
                Sandbox.create,
                image=image,
                wait_ready=True,
                timeout=300,
                region="syd1",
                instance_size="apps-s-1vcpu-2gb",
                spaces_config=spaces_config,
            )

            result.create_time_s = time.time() - create_start
            result.app_id = sandbox.app_id
            print(f"[{index:02d}] Created {sandbox.app_id} in {result.create_time_s:.1f}s")

            # Run simple command
            exec_start = time.time()
            cmd_result = sandbox.exec("echo 'hello'", timeout=30)
            result.exec_time_s = time.time() - exec_start
            print(f"[{index:02d}] Exec completed in {result.exec_time_s:.1f}s")

            # Delete sandbox
            delete_start = time.time()
            sandbox.delete()
            result.delete_time_s = time.time() - delete_start
            print(f"[{index:02d}] Deleted in {result.delete_time_s:.1f}s")

            result.success = True

        except Exception as e:
            result.error = str(e)
            print(f"[{index:02d}] FAILED: {e}")

        result.total_time_s = time.time() - start_total
        return result


async def run_benchmark(num_sandboxes: int = 5, max_concurrent: int = 3) -> BenchmarkSummary:
    """Run the benchmark test."""
    spaces_config = get_spaces_config()

    summary = BenchmarkSummary(
        num_sandboxes=num_sandboxes,
        spaces_enabled=spaces_config is not None,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    print("=" * 60)
    print("TEST 2: SANDBOX CREATION BENCHMARK")
    print("=" * 60)
    print(f"Creating {num_sandboxes} sandboxes")
    print(f"Max concurrent: {max_concurrent}")
    print(f"Region: syd1")
    print(f"Spaces enabled: {summary.spaces_enabled}")
    print("=" * 60)

    semaphore = asyncio.Semaphore(max_concurrent)

    # Create tasks - alternate python/node
    tasks = []
    for i in range(num_sandboxes):
        image = "python" if i % 2 == 0 else "node"
        tasks.append(create_and_test_sandbox(i, image, semaphore, spaces_config))

    # Run all in parallel
    overall_start = time.time()
    results = await asyncio.gather(*tasks)
    summary.overall_time_s = time.time() - overall_start

    # Calculate statistics
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    summary.successful = len(successful)
    summary.failed = len(failed)
    summary.results = [asdict(r) for r in results]

    if successful:
        create_times = [r.create_time_s for r in successful]
        summary.avg_create_s = sum(create_times) / len(create_times)
        summary.min_create_s = min(create_times)
        summary.max_create_s = max(create_times)
        summary.median_create_s = sorted(create_times)[len(create_times) // 2]

    return summary


def main():
    """Main entry point for Test 2."""
    # Smaller default for functional test (vs 25 in full benchmark)
    num_sandboxes = int(os.getenv("BENCHMARK_COUNT", "4"))
    max_concurrent = int(os.getenv("BENCHMARK_CONCURRENT", "2"))

    # Allow command line override
    if len(sys.argv) > 1:
        num_sandboxes = int(sys.argv[1])
    if len(sys.argv) > 2:
        max_concurrent = int(sys.argv[2])

    summary = asyncio.run(run_benchmark(num_sandboxes, max_concurrent))

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total sandboxes: {summary.num_sandboxes}")
    print(f"Successful: {summary.successful}")
    print(f"Failed: {summary.failed}")
    print(f"Overall time: {summary.overall_time_s:.1f}s")

    if summary.successful > 0:
        print(f"\nCreate times:")
        print(f"  Min: {summary.min_create_s:.1f}s")
        print(f"  Max: {summary.max_create_s:.1f}s")
        print(f"  Avg: {summary.avg_create_s:.1f}s")
        print(f"  Median: {summary.median_create_s:.1f}s")

    # Save result to JSON
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    output_file = os.path.join(results_dir, "test_02_result.json")
    with open(output_file, "w") as f:
        # Don't include full results array in summary output
        output = asdict(summary)
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {output_file}")

    print("\n" + "=" * 60)
    status = "PASS" if summary.failed == 0 else "PARTIAL" if summary.successful > 0 else "FAIL"
    print(f"STATUS: {status}")
    print("=" * 60)

    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
