#!/usr/bin/env python3
"""
Standalone test to measure sandbox creation time.
Creates 25 sandboxes in parallel, runs a simple command, deletes them.
"""

import asyncio
import time
import sys
from dataclasses import dataclass
from typing import Optional

# Add src to path
sys.path.insert(0, "src")

from do_app_sandbox import Sandbox


@dataclass
class CreateResult:
    """Result of a single sandbox creation."""
    index: int
    image: str
    app_id: Optional[str] = None
    create_time_s: float = 0.0
    exec_time_s: float = 0.0
    delete_time_s: float = 0.0
    total_time_s: float = 0.0
    success: bool = False
    error: Optional[str] = None


async def create_and_test_sandbox(index: int, image: str, semaphore: asyncio.Semaphore) -> CreateResult:
    """Create a sandbox, run a command, delete it."""
    result = CreateResult(index=index, image=image)
    start_total = time.time()

    async with semaphore:
        try:
            # Create sandbox
            print(f"[{index:02d}] Creating {image} sandbox...")
            create_start = time.time()

            sandbox = await asyncio.to_thread(
                Sandbox.create,
                image=image,
                wait_ready=True,
                timeout=300,
                region="syd1",
                instance_size="apps-s-1vcpu-2gb",
            )

            result.create_time_s = time.time() - create_start
            result.app_id = sandbox.app_id
            print(f"[{index:02d}] Created {sandbox.app_id} in {result.create_time_s:.1f}s")

            # Run simple command
            exec_start = time.time()
            cmd_result = sandbox.exec("echo 'hello'", timeout=30)
            result.exec_time_s = time.time() - exec_start
            print(f"[{index:02d}] Exec completed in {result.exec_time_s:.1f}s: {cmd_result.stdout}")

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


async def main():
    num_sandboxes = 25
    max_concurrent = 10  # Limit concurrent creates to avoid overwhelming API

    print("=" * 60)
    print("STANDALONE SANDBOX CREATE TEST")
    print("=" * 60)
    print(f"Creating {num_sandboxes} sandboxes ({num_sandboxes // 2} python, {num_sandboxes - num_sandboxes // 2} node)")
    print(f"Max concurrent creates: {max_concurrent}")
    print(f"Region: syd1")
    print("=" * 60)

    semaphore = asyncio.Semaphore(max_concurrent)

    # Create tasks - alternate python/node
    tasks = []
    for i in range(num_sandboxes):
        image = "python" if i % 2 == 0 else "node"
        tasks.append(create_and_test_sandbox(i, image, semaphore))

    # Run all in parallel
    overall_start = time.time()
    results = await asyncio.gather(*tasks)
    overall_time = time.time() - overall_start

    # Print summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print(f"\nTotal sandboxes: {num_sandboxes}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Overall time: {overall_time:.1f}s")

    if successful:
        create_times = [r.create_time_s for r in successful]
        exec_times = [r.exec_time_s for r in successful]
        delete_times = [r.delete_time_s for r in successful]

        print(f"\nCreate times:")
        print(f"  Min: {min(create_times):.1f}s")
        print(f"  Max: {max(create_times):.1f}s")
        print(f"  Avg: {sum(create_times) / len(create_times):.1f}s")
        print(f"  Median: {sorted(create_times)[len(create_times)//2]:.1f}s")

        print(f"\nExec times:")
        print(f"  Min: {min(exec_times):.1f}s")
        print(f"  Max: {max(exec_times):.1f}s")
        print(f"  Avg: {sum(exec_times) / len(exec_times):.1f}s")

        print(f"\nDelete times:")
        print(f"  Min: {min(delete_times):.1f}s")
        print(f"  Max: {max(delete_times):.1f}s")
        print(f"  Avg: {sum(delete_times) / len(delete_times):.1f}s")

        # Print individual results
        print(f"\nIndividual results:")
        print(f"{'#':>3} {'Image':>7} {'Create':>8} {'Exec':>6} {'Delete':>6} {'Total':>8} {'App ID'}")
        print("-" * 70)
        for r in sorted(results, key=lambda x: x.index):
            if r.success:
                print(f"{r.index:>3} {r.image:>7} {r.create_time_s:>7.1f}s {r.exec_time_s:>5.1f}s {r.delete_time_s:>5.1f}s {r.total_time_s:>7.1f}s {r.app_id[:20]}...")
            else:
                print(f"{r.index:>3} {r.image:>7} FAILED: {r.error[:40]}...")

    if failed:
        print(f"\nFailed sandboxes:")
        for r in failed:
            print(f"  [{r.index}] {r.image}: {r.error}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
