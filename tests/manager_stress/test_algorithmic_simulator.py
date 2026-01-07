"""
Unit tests for the algorithmic simulator.

These tests verify that:
1. The simulator correctly enforces limits
2. It catches bugs like the _total_sandbox_count bug
3. Dry-run mode provides reliable algorithm validation

Run with: uv run pytest tests/manager_stress/test_algorithmic_simulator.py
Or quick test: uv run python tests/manager_stress/test_algorithmic_simulator.py
"""

import asyncio
import sys
from pathlib import Path

# Make pytest optional for direct execution
try:
    import pytest
except ImportError:
    # Create a dummy pytest module for direct execution
    class DummyPytest:
        class mark:
            @staticmethod
            def asyncio(func):
                return func
    pytest = DummyPytest()

# Handle both package import and direct execution
try:
    from .algorithmic_simulator import (
        AlgorithmicMockManager,
        SimulatedPool,
        SimulatedSandbox,
        SandboxState,
    )
except ImportError:
    # Direct execution - add parent to path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from tests.manager_stress.algorithmic_simulator import (
        AlgorithmicMockManager,
        SimulatedPool,
        SimulatedSandbox,
        SandboxState,
    )


class TestSimulatedPool:
    """Tests for individual pool behavior."""

    @pytest.mark.asyncio
    async def test_pool_counts_in_use(self):
        """Verify pool tracks in_use count correctly."""
        pool = SimulatedPool(
            image="test",
            target_ready=2,
            max_sandboxes=5,
            create_delay=(0.01, 0.02),
        )

        await pool.start()
        try:
            # Initial state
            assert pool.ready_count == 0
            assert pool.in_use_count == 0
            assert pool.total_count == 0

            # Acquire a sandbox
            sandbox = await pool.acquire()
            assert pool.in_use_count == 1
            assert sandbox.state == SandboxState.IN_USE

            # Release it
            pool.release(sandbox)
            assert pool.in_use_count == 0
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_pool_total_includes_all_states(self):
        """Verify total_count = ready + creating + in_use."""
        pool = SimulatedPool(
            image="test",
            target_ready=3,
            max_sandboxes=10,
            create_delay=(0.01, 0.02),
        )

        await pool.start()
        try:
            # Wait for some sandboxes to become ready
            await asyncio.sleep(0.2)

            # Acquire some sandboxes
            acquired = []
            for _ in range(min(2, pool.ready_count)):
                s = await pool.acquire()
                acquired.append(s)

            # Verify invariant
            total = pool.ready_count + pool.creating_count + pool.in_use_count
            assert pool.total_count == total, f"total_count mismatch: {pool.total_count} != {total}"
            assert pool.in_use_count == len(acquired)

            # Release and verify
            for s in acquired:
                pool.release(s)
            assert pool.in_use_count == 0
        finally:
            await pool.stop()


class TestAlgorithmicMockManager:
    """Tests for the full manager."""

    @pytest.mark.asyncio
    async def test_global_limit_enforced(self):
        """Verify max_total_sandboxes is enforced."""
        manager = AlgorithmicMockManager(
            pools={
                'python': {'target_ready': 2, 'max_sandboxes': 5},
                'node': {'target_ready': 2, 'max_sandboxes': 5},
            },
            max_total_sandboxes=6,  # Less than sum of per-pool limits
            create_delay=(0.01, 0.02),
        )

        await manager.start()
        try:
            acquired = []

            # Acquire up to the limit
            for _ in range(6):
                try:
                    image = 'python' if len(acquired) % 2 == 0 else 'node'
                    s = await manager.acquire(image)
                    acquired.append((s, image))
                except Exception:
                    break

            # Try to acquire one more - should fail
            with pytest.raises(Exception, match="Global sandbox limit reached"):
                await manager.acquire('python')

            # Verify no violations
            assert len(manager.get_violations()) == 0
            assert manager._total_sandbox_count() <= 6

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_in_use_counted_in_total(self):
        """Verify in_use sandboxes are counted in _total_sandbox_count()."""
        manager = AlgorithmicMockManager(
            pools={
                'python': {'target_ready': 0, 'max_sandboxes': 10},
            },
            max_total_sandboxes=5,
            create_delay=(0.01, 0.02),
        )

        await manager.start()
        try:
            acquired = []

            # Acquire 5 sandboxes
            for i in range(5):
                s = await manager.acquire('python')
                acquired.append(s)

                # Verify count includes in_use
                total = manager._total_sandbox_count()
                assert total == i + 1, f"After acquire {i+1}, total should be {i+1}, got {total}"

            # Verify we're at the limit
            assert manager._total_sandbox_count() == 5
            assert manager._is_at_global_limit()

            # Release one and verify count drops
            manager.release(acquired[0], 'python')
            assert manager._total_sandbox_count() == 4
            assert not manager._is_at_global_limit()

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_detects_limit_violations(self):
        """Verify violations are detected and recorded."""
        manager = AlgorithmicMockManager(
            pools={
                'python': {'target_ready': 0, 'max_sandboxes': 10},
            },
            max_total_sandboxes=3,
            create_delay=(0.01, 0.02),
        )

        await manager.start()
        try:
            # Normal acquisitions
            acquired = []
            for _ in range(3):
                s = await manager.acquire('python')
                acquired.append(s)

            # This should fail (at limit)
            with pytest.raises(Exception):
                await manager.acquire('python')

            # No violations should be recorded (limit was enforced)
            assert len(manager.get_violations()) == 0

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_release_frees_capacity(self):
        """Verify releasing a sandbox frees capacity for new ones."""
        manager = AlgorithmicMockManager(
            pools={
                'python': {'target_ready': 0, 'max_sandboxes': 10},
            },
            max_total_sandboxes=2,
            create_delay=(0.01, 0.02),
        )

        await manager.start()
        try:
            # Acquire to limit
            s1 = await manager.acquire('python')
            s2 = await manager.acquire('python')

            # Can't acquire more
            with pytest.raises(Exception):
                await manager.acquire('python')

            # Release one
            manager.release(s1, 'python')

            # Now we can acquire again
            s3 = await manager.acquire('python')
            assert s3 is not None

        finally:
            await manager.shutdown()


class TestBugDetection:
    """
    Tests that verify the simulator would catch the _total_sandbox_count bug.

    The original bug was that _total_sandbox_count() only counted ready + creating,
    not in_use sandboxes. This caused the global limit to not be enforced.
    """

    @pytest.mark.asyncio
    async def test_would_catch_missing_in_use_tracking(self):
        """
        Simulate what happens if in_use is not tracked.

        This test demonstrates that with proper tracking, the limit is enforced.
        The original bug would have allowed unlimited acquisitions.
        """
        manager = AlgorithmicMockManager(
            pools={
                'python': {'target_ready': 0, 'max_sandboxes': 100},
                'node': {'target_ready': 0, 'max_sandboxes': 100},
            },
            max_total_sandboxes=10,  # Limit should be enforced
            create_delay=(0.01, 0.02),
        )

        await manager.start()
        try:
            acquired = []

            # Try to acquire many sandboxes
            for i in range(20):
                try:
                    image = 'python' if i % 2 == 0 else 'node'
                    s = await manager.acquire(image)
                    acquired.append((s, image))
                except Exception as e:
                    # Should hit limit at 10
                    assert len(acquired) == 10, f"Expected to hit limit at 10, but got {len(acquired)}"
                    break

            # Verify we stopped at the limit
            assert len(acquired) == 10
            assert manager._total_sandbox_count() == 10

            # The original bug would have allowed all 20 acquisitions
            # because in_use wasn't counted

        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_acquisitions_respect_limit(self):
        """Test that concurrent acquisitions respect the limit."""
        manager = AlgorithmicMockManager(
            pools={
                'python': {'target_ready': 0, 'max_sandboxes': 50},
                'node': {'target_ready': 0, 'max_sandboxes': 50},
            },
            max_total_sandboxes=8,
            create_delay=(0.05, 0.1),
        )

        await manager.start()
        try:
            async def acquire_many(image: str, count: int):
                acquired = []
                for _ in range(count):
                    try:
                        s = await manager.acquire(image)
                        acquired.append(s)
                    except Exception:
                        break
                return acquired

            # Launch concurrent acquisitions
            results = await asyncio.gather(
                acquire_many('python', 10),
                acquire_many('node', 10),
            )

            total_acquired = len(results[0]) + len(results[1])

            # Should not exceed the limit
            assert total_acquired <= 8, f"Acquired {total_acquired} > limit 8"
            assert manager._total_sandbox_count() <= 8

            # Should have no violations
            assert len(manager.get_violations()) == 0

        finally:
            await manager.shutdown()


# Quick verification that can be run directly
if __name__ == "__main__":
    async def quick_test():
        print("Running quick algorithmic simulator test...")

        manager = AlgorithmicMockManager(
            pools={
                'python': {'target_ready': 2, 'max_sandboxes': 10},
                'node': {'target_ready': 2, 'max_sandboxes': 10},
            },
            max_total_sandboxes=8,
            create_delay=(0.01, 0.02),
        )

        await manager.start()
        try:
            acquired = []
            images = ['python', 'node'] * 10

            for image in images:
                try:
                    s = await manager.acquire(image)
                    acquired.append((s, image))
                    total = manager._total_sandbox_count()
                    print(f"Acquired {len(acquired)}: total={total}")
                except Exception as e:
                    print(f"Limit reached after {len(acquired)}: {e}")
                    break

            print(f"\nFinal stats:")
            print(f"  Acquired: {len(acquired)}")
            print(f"  Total count: {manager._total_sandbox_count()}")
            print(f"  Max observed: {manager.get_max_observed()}")
            print(f"  Violations: {len(manager.get_violations())}")

            if len(manager.get_violations()) > 0:
                print("\nVIOLATIONS DETECTED - BUG FOUND!")
                for v in manager.get_violations():
                    print(f"  {v}")
            else:
                print("\nNo violations - limit enforcement working correctly")

        finally:
            await manager.shutdown()

    asyncio.run(quick_test())
