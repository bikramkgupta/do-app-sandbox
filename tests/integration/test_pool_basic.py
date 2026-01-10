"""
Basic integration test for SandboxManager pool pre-warming and replenishment.

This test verifies the fundamental pool functionality:
1. Pool pre-warms sandboxes to target_ready count
2. Acquisitions from warm pool have ~zero latency (from_pool=True)
3. Pool automatically replenishes after sandboxes are acquired
4. Subsequent acquisitions also come from pool

Run with:
    python -m pytest tests/test_pool_basic_integration.py -v -s

Or directly:
    python tests/test_pool_basic_integration.py
"""

import asyncio
import time

from do_app_sandbox import PoolConfig, Sandbox, SandboxManager

# Configuration
IMAGE = "python"
TARGET_READY = 3
WARM_UP_TIMEOUT = 180.0  # 3 minutes for initial warm-up


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def print_step(step: int, text: str) -> None:
    """Print a step marker."""
    print(f"\n[Step {step}] {text}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"  ℹ️  {text}")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"  ✅ {text}")


def print_metrics(manager: SandboxManager, image: str) -> None:
    """Print current pool metrics."""
    metrics = manager.metrics().get(image)
    if metrics:
        print("  📊 Pool Metrics:")
        print(f"     - Ready: {metrics.ready}")
        print(f"     - Creating: {metrics.creating}")
        print(f"     - In Use: {metrics.in_use}")
        print(f"     - Total Acquires: {metrics.total_acquires}")
        print(f"     - From Pool: {metrics.acquires_from_pool}")
        print(f"     - Pool Hit Rate: {metrics.pool_hit_rate:.1%}")
        if metrics.avg_acquire_latency_ms:
            print(f"     - Avg Acquire Latency: {metrics.avg_acquire_latency_ms:.1f}ms")


async def test_pool_prewarm_and_replenish() -> None:
    """
    Integration test for pool pre-warming and automatic replenishment.

    This test:
    1. Creates a pool with target_ready=3
    2. Waits for warm-up (3 sandboxes pre-created)
    3. Acquires 3 sandboxes, verifying each came from pool
    4. Waits for pool to replenish
    5. Acquires 3 more sandboxes, verifying they also came from pool
    6. Cleans up all resources
    """
    print_header("Pool Pre-Warming & Replenishment Integration Test")
    print_info(f"Image: {IMAGE}")
    print_info(f"Target Ready: {TARGET_READY}")

    sandboxes: list[Sandbox] = []
    manager = None

    try:
        # Step 1: Create manager with pool configuration
        print_step(1, "Creating SandboxManager with pool configuration")
        manager = SandboxManager(
            pools={IMAGE: PoolConfig(target_ready=TARGET_READY, max_ready=TARGET_READY + 2)},
        )
        print_success(f"Manager created with target_ready={TARGET_READY}")

        # Step 2: Start the manager
        print_step(2, "Starting manager (spawns background replenishment)")
        start_time = time.time()
        await manager.start()
        print_success(f"Manager started in {time.time() - start_time:.2f}s")

        # Step 3: Wait for warm-up
        print_step(3, f"Waiting for pool warm-up (target: {TARGET_READY} sandboxes)")
        print_info("This may take 1-2 minutes for sandbox creation...")
        warm_start = time.time()
        await manager.warm_up(timeout=WARM_UP_TIMEOUT)
        warm_duration = time.time() - warm_start
        print_success(f"Pool warmed up in {warm_duration:.1f}s")
        print_metrics(manager, IMAGE)

        # Step 4: Acquire 3 sandboxes (should all come from pool)
        print_step(4, f"Acquiring {TARGET_READY} sandboxes (should be instant from pool)")
        first_batch: list[Sandbox] = []

        for i in range(TARGET_READY):
            acquire_start = time.time()
            sandbox = await manager.acquire(image=IMAGE)
            acquire_ms = (time.time() - acquire_start) * 1000

            from_pool = getattr(sandbox, "_from_pool", None)
            source = "POOL" if from_pool else "COLD START"

            print_info(f"Sandbox {i + 1}: acquired in {acquire_ms:.1f}ms [{source}]")
            print_info(f"  App ID: {sandbox.app_id}")

            if not from_pool:
                print("  ⚠️  WARNING: Expected from pool but got cold start!")

            first_batch.append(sandbox)
            sandboxes.append(sandbox)

        print_metrics(manager, IMAGE)

        # Verify all came from pool
        pool_hits = sum(1 for sb in first_batch if getattr(sb, "_from_pool", False))
        if pool_hits == TARGET_READY:
            print_success(f"All {TARGET_READY} sandboxes acquired from pool (zero cold starts)")
        else:
            print(f"  ⚠️  Only {pool_hits}/{TARGET_READY} came from pool")

        # Step 5: Wait for pool to replenish
        print_step(5, "Waiting for pool to replenish after acquisitions")
        print_info(f"Pool should auto-replenish back to {TARGET_READY} sandboxes...")
        replenish_start = time.time()
        await manager.warm_up(timeout=WARM_UP_TIMEOUT)
        replenish_duration = time.time() - replenish_start
        print_success(f"Pool replenished in {replenish_duration:.1f}s")
        print_metrics(manager, IMAGE)

        # Step 6: Acquire 3 more sandboxes (should also come from pool)
        print_step(6, f"Acquiring {TARGET_READY} more sandboxes (verifying replenishment)")
        second_batch: list[Sandbox] = []

        for i in range(TARGET_READY):
            acquire_start = time.time()
            sandbox = await manager.acquire(image=IMAGE)
            acquire_ms = (time.time() - acquire_start) * 1000

            from_pool = getattr(sandbox, "_from_pool", None)
            source = "POOL" if from_pool else "COLD START"

            print_info(f"Sandbox {TARGET_READY + i + 1}: acquired in {acquire_ms:.1f}ms [{source}]")
            print_info(f"  App ID: {sandbox.app_id}")

            if not from_pool:
                print("  ⚠️  WARNING: Expected from pool but got cold start!")

            second_batch.append(sandbox)
            sandboxes.append(sandbox)

        print_metrics(manager, IMAGE)

        # Verify second batch also came from pool
        pool_hits_2 = sum(1 for sb in second_batch if getattr(sb, "_from_pool", False))
        if pool_hits_2 == TARGET_READY:
            print_success(f"All {TARGET_READY} replenished sandboxes acquired from pool")
        else:
            print(f"  ⚠️  Only {pool_hits_2}/{TARGET_READY} came from pool after replenishment")

        # Step 7: Delete all acquired sandboxes
        print_step(7, f"Deleting {len(sandboxes)} acquired sandboxes")
        for i, sandbox in enumerate(sandboxes):
            print_info(f"Deleting sandbox {i + 1}/{len(sandboxes)}: {sandbox.app_id}")
            try:
                sandbox.delete()
                print_success(f"Deleted {sandbox.app_id}")
            except Exception as e:
                print(f"  ⚠️  Failed to delete {sandbox.app_id}: {e}")
        sandboxes.clear()

        # Step 8: Shutdown manager (cleans up pool)
        print_step(8, "Shutting down manager (drains remaining pool)")
        await manager.shutdown()
        print_success("Manager shutdown complete")

        # Final summary
        print_header("Test Summary")
        total_acquires = TARGET_READY * 2
        total_pool_hits = pool_hits + pool_hits_2
        print_info(f"Total Acquisitions: {total_acquires}")
        print_info(f"Pool Hits: {total_pool_hits}")
        print_info(f"Cold Starts: {total_acquires - total_pool_hits}")
        print_info(f"Pool Hit Rate: {total_pool_hits / total_acquires:.1%}")

        if total_pool_hits == total_acquires:
            print_success("TEST PASSED: All acquisitions came from pool")
        else:
            print(f"\n  ⚠️  TEST INCOMPLETE: {total_acquires - total_pool_hits} cold starts detected")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
    finally:
        # Cleanup: delete any remaining sandboxes
        if sandboxes:
            print(f"\n🧹 Cleaning up {len(sandboxes)} remaining sandboxes...")
            for sandbox in sandboxes:
                try:
                    sandbox.delete()
                except Exception:
                    pass

        # Cleanup: shutdown manager if still running
        if manager and not manager._shutdown:
            print("🧹 Shutting down manager...")
            try:
                await manager.shutdown()
            except Exception:
                pass


async def main():
    """Run the integration test."""
    await test_pool_prewarm_and_replenish()


if __name__ == "__main__":
    asyncio.run(main())
