#!/usr/bin/env python3
"""Snapshot Restore Benchmark.

Measures the time to restore a real application from a snapshot to a
warm-pooled sandbox and verify it's running via HTTP requests.

Prerequisites:
    1. Run scripts/create_snapshots.py first to create snapshots
    2. Ensure DIGITALOCEAN_TOKEN and Spaces credentials are set

Usage:
    python snapshot_restore_benchmark.py                  # Default: 3 iterations
    python snapshot_restore_benchmark.py --iterations 5   # Custom iterations
    python snapshot_restore_benchmark.py --images python  # Single image
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from do_app_sandbox import PoolConfig, Sandbox, SandboxManager
from do_app_sandbox.spaces import create_spaces_config_from_env
from do_app_sandbox.types import SandboxMode, SpacesConfig

# Configuration
BENCHMARK_DIR = Path(__file__).parent
RESULTS_DIR = BENCHMARK_DIR / "results"
CONFIG_FILE = RESULTS_DIR / "snapshot_config.json"


@dataclass
class TimingResult:
    """Timing breakdown for a single benchmark run."""

    pool_acquire_ms: float = 0
    snapshot_restore_ms: float = 0
    app_startup_ms: float = 0
    verification_ms: float = 0
    total_ms: float = 0


@dataclass
class VerificationResult:
    """Result of app verification."""

    status: str = "unknown"
    http_status: int = 0
    response_time_ms: float = 0
    response_valid: bool = False
    error: str | None = None


@dataclass
class BenchmarkResult:
    """Result of a single benchmark iteration."""

    iteration: int
    image: str
    app_id: str | None = None
    timings: TimingResult = field(default_factory=TimingResult)
    verification: VerificationResult = field(default_factory=VerificationResult)
    pool_hit: bool = False
    snapshot_size_bytes: int = 0
    error: str | None = None

    def to_dict(self):
        return {
            "iteration": self.iteration,
            "image": self.image,
            "app_id": self.app_id,
            "timings_ms": asdict(self.timings),
            "verification": asdict(self.verification),
            "pool_hit": self.pool_hit,
            "snapshot_size_bytes": self.snapshot_size_bytes,
            "error": self.error,
        }


def percentile(data: list[float], p: float) -> float:
    """Calculate percentile of a list."""
    if not data:
        return 0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def calculate_stats(values: list[float]) -> dict:
    """Calculate min, max, avg, p50, p95 for a list of values."""
    if not values:
        return {"min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0}
    return {
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "avg": round(mean(values), 1),
        "p50": round(median(values), 1),
        "p95": round(percentile(values, 95), 1),
    }


async def run_single_benchmark(
    manager: SandboxManager,
    image: str,
    snapshot_id: str,
    iteration: int,
    spaces_config: SpacesConfig,
) -> BenchmarkResult:
    """Run a single benchmark iteration."""
    result = BenchmarkResult(iteration=iteration, image=image)
    sandbox = None

    total_start = time.time()

    try:
        # Step 1: Acquire from pool with snapshot restore
        print(f"  [{iteration}] Acquiring sandbox and restoring snapshot...")
        acquire_start = time.time()

        sandbox = await manager.acquire_with_snapshot(
            image=image,
            snapshot_id=snapshot_id,
            timeout=300,
        )

        acquire_end = time.time()
        result.timings.pool_acquire_ms = (acquire_end - acquire_start) * 1000
        result.app_id = sandbox.app_id
        result.pool_hit = getattr(sandbox, "_from_pool", False)

        print(f"  [{iteration}] Acquired {sandbox.app_id} in {result.timings.pool_acquire_ms:.0f}ms")

        # The acquire_with_snapshot already restored the snapshot, so we measure app startup next

        # Step 2: Start the app
        print(f"  [{iteration}] Starting application...")
        startup_start = time.time()

        # Get service client for background execution
        client = sandbox._get_service_client()

        # Start command depends on image - use background API
        if image == "python":
            start_cmd = ". .venv/bin/activate && python app.py"
        else:
            start_cmd = "node app.js"

        pid = client.exec_background(command=start_cmd, cwd="/workspace")
        print(f"  [{iteration}] Started with PID {pid}")
        health_ok = False

        for attempt in range(30):  # 60 second timeout
            try:
                health_result = client.exec("curl -s http://localhost:5000/health", timeout=5)
                if "healthy" in health_result.stdout:
                    health_ok = True
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

        startup_end = time.time()
        result.timings.app_startup_ms = (startup_end - startup_start) * 1000

        if not health_ok:
            raise RuntimeError("App health check failed after 60s")

        print(f"  [{iteration}] App started in {result.timings.app_startup_ms:.0f}ms")

        # Step 3: Full verification
        print(f"  [{iteration}] Verifying application...")
        verify_start = time.time()

        verify_result = client.exec("curl -s http://localhost:5000/verify", timeout=10)

        verify_end = time.time()
        result.timings.verification_ms = (verify_end - verify_start) * 1000

        # Parse verification response
        try:
            verify_data = json.loads(verify_result.stdout)
            result.verification.status = verify_data.get("status", "unknown")
            result.verification.response_valid = verify_data.get("all_ok", False)
            result.verification.http_status = 200
        except json.JSONDecodeError:
            result.verification.status = "parse_error"
            result.verification.error = "Could not parse JSON response"

        result.verification.response_time_ms = result.timings.verification_ms

        print(f"  [{iteration}] Verification: {result.verification.status}")

        # Total time
        result.timings.total_ms = (time.time() - total_start) * 1000

        print(f"  [{iteration}] Total: {result.timings.total_ms:.0f}ms")

    except Exception as e:
        result.error = str(e)
        result.timings.total_ms = (time.time() - total_start) * 1000
        print(f"  [{iteration}] ERROR: {e}")

    finally:
        # Cleanup - just delete the sandbox, which kills all processes
        if sandbox:
            try:
                sandbox.delete()
            except Exception:
                pass

    return result


async def run_benchmark(
    images: list[str],
    iterations: int,
    snapshots: dict,
    spaces_config: SpacesConfig,
) -> dict:
    """Run the full benchmark suite."""
    results = []
    summary = {}

    for image in images:
        if image not in snapshots:
            print(f"Skipping {image}: no snapshot configured")
            continue

        snapshot_info = snapshots[image]
        snapshot_id = snapshot_info["snapshot_id"]

        print(f"\n{'=' * 60}")
        print(f"  Benchmarking {image.upper()}")
        print(f"  Snapshot: {snapshot_id} ({snapshot_info['size_mb']} MB)")
        print(f"{'=' * 60}")

        # Create manager with warm pool
        print("\nCreating pool with target_ready=1...")
        manager = SandboxManager(
            pools={image: PoolConfig(target_ready=1, max_ready=2)},
            sandbox_defaults={
                "mode": SandboxMode.SERVICE,
                "spaces_config": spaces_config,
            },
        )
        await manager.start()

        # Wait for pool to warm up
        print("Waiting for pool warm-up...")
        await manager.warm_up(timeout=180)
        print("Pool ready\n")

        image_results = []

        for i in range(1, iterations + 1):
            result = await run_single_benchmark(
                manager=manager,
                image=image,
                snapshot_id=snapshot_id,
                iteration=i,
                spaces_config=spaces_config,
            )
            result.snapshot_size_bytes = snapshot_info["size_bytes"]
            image_results.append(result)
            results.append(result)

            # Small delay between iterations
            if i < iterations:
                await asyncio.sleep(5)

        # Shutdown manager
        await manager.shutdown()

        # Calculate summary for this image
        successful = [r for r in image_results if not r.error]
        summary[image] = {
            "count": len(image_results),
            "success_count": len(successful),
            "pool_hit_rate": sum(1 for r in successful if r.pool_hit) / len(successful) if successful else 0,
            "snapshot_size_mb": snapshot_info["size_mb"],
            "timings_ms": {
                "pool_acquire": calculate_stats([r.timings.pool_acquire_ms for r in successful]),
                "app_startup": calculate_stats([r.timings.app_startup_ms for r in successful]),
                "verification": calculate_stats([r.timings.verification_ms for r in successful]),
                "total": calculate_stats([r.timings.total_ms for r in successful]),
            },
        }

    return {
        "results": [r.to_dict() for r in results],
        "summary": summary,
    }


def print_summary(summary: dict):
    """Print a formatted summary table."""
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    for image, data in summary.items():
        success_rate = data["success_count"] / data["count"] * 100 if data["count"] else 0
        pool_hit_rate = data["pool_hit_rate"] * 100

        print(
            f"\n{image.upper()} ({data['count']} runs, {data['success_count']} successful, {pool_hit_rate:.0f}% pool hits)"
        )
        print(f"Snapshot size: {data['snapshot_size_mb']} MB")
        print()
        print(f"{'Metric':<15} {'Min':>10} {'Max':>10} {'Avg':>10} {'P50':>10} {'P95':>10}")
        print("-" * 65)

        for metric, label in [
            ("pool_acquire", "Pool Acquire"),
            ("app_startup", "App Startup"),
            ("verification", "Verification"),
            ("total", "TOTAL"),
        ]:
            stats = data["timings_ms"][metric]

            # Convert to seconds for display if > 1000ms
            def fmt(v):
                if v >= 1000:
                    return f"{v/1000:.1f}s"
                return f"{v:.0f}ms"

            print(
                f"{label:<15} {fmt(stats['min']):>10} {fmt(stats['max']):>10} {fmt(stats['avg']):>10} {fmt(stats['p50']):>10} {fmt(stats['p95']):>10}"
            )


def main():
    parser = argparse.ArgumentParser(description="Snapshot Restore Benchmark")
    parser.add_argument("--iterations", type=int, default=3, help="Iterations per image (default: 3)")
    parser.add_argument("--images", nargs="+", default=["python", "node"], help="Images to benchmark")
    parser.add_argument("--output", type=Path, default=None, help="Output directory")
    args = parser.parse_args()

    print("=" * 60)
    print("  SNAPSHOT RESTORE BENCHMARK")
    print("=" * 60)

    # Check credentials
    if not os.environ.get("DIGITALOCEAN_TOKEN"):
        print("ERROR: DIGITALOCEAN_TOKEN not set")
        sys.exit(1)

    spaces_config = create_spaces_config_from_env()
    if not spaces_config:
        print("ERROR: Spaces credentials not configured")
        sys.exit(1)

    # Load snapshot config
    if not CONFIG_FILE.exists():
        print(f"ERROR: Snapshot config not found: {CONFIG_FILE}")
        print("Run scripts/create_snapshots.py first")
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        config = json.load(f)

    snapshots = config.get("snapshots", {})

    print(f"\nIterations: {args.iterations}")
    print(f"Images: {args.images}")
    print("\nSnapshots:")
    for image in args.images:
        if image in snapshots:
            info = snapshots[image]
            print(f"  {image}: {info['snapshot_id']} ({info['size_mb']} MB)")
        else:
            print(f"  {image}: NOT CONFIGURED")

    # Run benchmark
    result_data = asyncio.run(
        run_benchmark(
            images=args.images,
            iterations=args.iterations,
            snapshots=snapshots,
            spaces_config=spaces_config,
        )
    )

    # Add metadata
    output = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iterations_per_image": args.iterations,
            "images": args.images,
        },
        "snapshots": {k: v for k, v in snapshots.items() if k in args.images},
        **result_data,
    }

    # Print summary
    print_summary(result_data["summary"])

    # Save results
    output_dir = args.output or RESULTS_DIR
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    output_file = output_dir / f"snapshot_restore_benchmark_{timestamp}.json"

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
