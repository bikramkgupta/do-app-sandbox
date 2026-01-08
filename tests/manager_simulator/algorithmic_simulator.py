"""
Algorithmic Simulator for SandboxManager stress tests.

This module provides a MockSandboxManager that faithfully implements the same
limit tracking and pool logic as the real SandboxManager, enabling dry-run tests
that actually catch algorithmic bugs.

Key differences from the basic mock in orchestrator.py:
1. Actually enforces max_total_sandboxes limit
2. Tracks ready, creating, in_use counts accurately
3. Simulates acquire/release lifecycle
4. Detects and reports limit violations
5. Provides invariant checking

The simulator is designed to catch bugs like the _total_sandbox_count bug where
in_use sandboxes were not counted, causing limit violations.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class SandboxState(Enum):
    """State of a simulated sandbox."""
    CREATING = "creating"
    READY = "ready"  # In pool, available for acquisition
    IN_USE = "in_use"  # Acquired by a user
    DELETED = "deleted"


@dataclass
class SimulatedSandbox:
    """Represents a sandbox in the simulation."""
    sandbox_id: str
    image: str
    state: SandboxState
    created_at: float = field(default_factory=time.time)
    acquired_at: Optional[float] = None
    _from_pool: bool = False

    @property
    def age(self) -> float:
        return time.time() - self.created_at


@dataclass
class PoolStats:
    """Statistics for a single pool."""
    ready: int = 0
    creating: int = 0
    in_use: int = 0

    @property
    def total(self) -> int:
        return self.ready + self.creating + self.in_use


@dataclass
class LimitViolation:
    """Records a limit violation event."""
    timestamp: float
    violation_type: str
    limit_name: str
    limit_value: int
    actual_value: int
    details: str


class SimulatedPool:
    """
    Simulates a SandboxPool for a single image.

    This implements the same logic as the real SandboxPool but without
    actual infrastructure, allowing algorithm testing in dry-run mode.
    """

    def __init__(
        self,
        image: str,
        target_ready: int,
        max_sandboxes: int,
        global_limit_callback: Optional[callable] = None,
        create_delay: tuple[float, float] = (1.0, 5.0),  # Simulated creation time
    ):
        self.image = image
        self.target_ready = target_ready
        self.max_sandboxes = max_sandboxes
        self._global_limit_callback = global_limit_callback
        self._create_delay = create_delay

        # State tracking
        self._sandboxes: Dict[str, SimulatedSandbox] = {}
        self._ready_queue: List[str] = []  # IDs of ready sandboxes
        self._creating_count: int = 0
        self._in_use_set: Set[str] = set()  # IDs of in-use sandboxes

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Metrics
        self._total_acquires: int = 0
        self._pool_hits: int = 0
        self._cold_starts: int = 0
        self._limit_violations: List[LimitViolation] = []

        # Background task
        self._replenish_task: Optional[asyncio.Task] = None
        self._shutdown: bool = False

        # Counter for unique IDs
        self._id_counter: int = 0

    @property
    def ready_count(self) -> int:
        return len(self._ready_queue)

    @property
    def creating_count(self) -> int:
        return self._creating_count

    @property
    def in_use_count(self) -> int:
        return len(self._in_use_set)

    @property
    def total_count(self) -> int:
        return self.ready_count + self.creating_count + self.in_use_count

    def get_stats(self) -> PoolStats:
        return PoolStats(
            ready=self.ready_count,
            creating=self.creating_count,
            in_use=self.in_use_count,
        )

    async def start(self):
        """Start background replenishment."""
        self._shutdown = False
        self._replenish_task = asyncio.create_task(self._replenish_loop())

    async def stop(self):
        """Stop and clean up."""
        self._shutdown = True
        if self._replenish_task:
            self._replenish_task.cancel()
            try:
                await self._replenish_task
            except asyncio.CancelledError:
                pass

    async def acquire(self, timeout: Optional[float] = None) -> SimulatedSandbox:
        """Acquire a sandbox from the pool or create on-demand."""
        self._total_acquires += 1

        # Try to get from pool first
        async with self._lock:
            if self._ready_queue:
                sandbox_id = self._ready_queue.pop(0)
                sandbox = self._sandboxes[sandbox_id]
                sandbox.state = SandboxState.IN_USE
                sandbox.acquired_at = time.time()
                sandbox._from_pool = True
                self._in_use_set.add(sandbox_id)
                self._pool_hits += 1
                logger.debug(f"[{self.image}] Acquired from pool: {sandbox_id}")
                return sandbox

        # Check global limit before on-demand creation
        if self._global_limit_callback and self._global_limit_callback():
            raise Exception(f"Global sandbox limit reached, cannot create on-demand for {self.image}")

        # Cold start - create on-demand
        self._cold_starts += 1
        sandbox = await self._create_sandbox()

        async with self._lock:
            sandbox.state = SandboxState.IN_USE
            sandbox.acquired_at = time.time()
            sandbox._from_pool = False
            self._in_use_set.add(sandbox.sandbox_id)

        logger.debug(f"[{self.image}] Created on-demand: {sandbox.sandbox_id}")
        return sandbox

    def release(self, sandbox: SimulatedSandbox):
        """Release a sandbox (decrement in-use count)."""
        if sandbox.sandbox_id in self._in_use_set:
            self._in_use_set.discard(sandbox.sandbox_id)
            sandbox.state = SandboxState.DELETED
            logger.debug(f"[{self.image}] Released: {sandbox.sandbox_id}")
        else:
            logger.warning(f"[{self.image}] Tried to release unknown sandbox: {sandbox.sandbox_id}")

    async def _create_sandbox(self) -> SimulatedSandbox:
        """Simulate creating a sandbox."""
        async with self._lock:
            self._creating_count += 1

        try:
            # Simulate creation delay
            delay = random.uniform(*self._create_delay)
            await asyncio.sleep(delay)

            self._id_counter += 1
            sandbox_id = f"{self.image}-sim-{self._id_counter}"
            sandbox = SimulatedSandbox(
                sandbox_id=sandbox_id,
                image=self.image,
                state=SandboxState.READY,
            )
            self._sandboxes[sandbox_id] = sandbox
            return sandbox
        finally:
            async with self._lock:
                self._creating_count -= 1

    async def _replenish_loop(self):
        """Background loop to maintain target pool size."""
        while not self._shutdown:
            try:
                await self._replenish_once()
                await asyncio.sleep(0.5)  # Check frequently
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.image}] Replenish error: {e}")
                await asyncio.sleep(1)

    async def _replenish_once(self):
        """Check if we need to create more sandboxes."""
        current = self.ready_count + self.creating_count

        # Check if we're below target
        if current >= self.target_ready:
            return

        # Check pool limit
        if self.total_count >= self.max_sandboxes:
            return

        # Check global limit
        if self._global_limit_callback and self._global_limit_callback():
            logger.debug(f"[{self.image}] Global limit reached, not creating")
            return

        # Calculate how many sandboxes to create
        needed = self.target_ready - current
        available = self.max_sandboxes - self.total_count
        to_create = min(needed, available)

        # Start ALL needed creations at once (no artificial throttle)
        for _ in range(to_create):
            asyncio.create_task(self._create_and_add_to_pool())

    async def _create_and_add_to_pool(self):
        """Create a sandbox and add to ready queue."""
        try:
            sandbox = await self._create_sandbox()
            if not self._shutdown:
                async with self._lock:
                    self._ready_queue.append(sandbox.sandbox_id)
                    logger.debug(f"[{self.image}] Added to pool: {sandbox.sandbox_id}, now {self.ready_count} ready")
        except Exception as e:
            logger.error(f"[{self.image}] Failed to create for pool: {e}")


class AlgorithmicMockManager:
    """
    Mock SandboxManager that faithfully implements the algorithm.

    This is designed for comprehensive dry-run testing. It enforces the same
    limits and tracks state exactly as the real SandboxManager would, allowing
    algorithmic bugs to be caught without real infrastructure.

    Key features:
    - Enforces max_total_sandboxes limit
    - Tracks ready + creating + in_use for global limit
    - Detects and logs limit violations
    - Provides detailed statistics for debugging
    """

    def __init__(
        self,
        pools: Dict[str, Dict[str, Any]],
        max_total_sandboxes: Optional[int] = None,
        max_concurrent_creates: int = 10,
        create_delay: tuple[float, float] = (0.5, 2.0),
    ):
        """
        Initialize the mock manager.

        Args:
            pools: Dict mapping image name to pool config dict with:
                - target_ready: int
                - max_sandboxes: int
            max_total_sandboxes: Global limit (None = unlimited)
            max_concurrent_creates: Max parallel creates (simulated)
            create_delay: (min, max) seconds for simulated creation
        """
        self._max_total = max_total_sandboxes
        self._create_delay = create_delay

        # Create pools
        self._pools: Dict[str, SimulatedPool] = {}
        for image, config in pools.items():
            self._pools[image] = SimulatedPool(
                image=image,
                target_ready=config.get('target_ready', 5),
                max_sandboxes=config.get('max_sandboxes', 20),
                global_limit_callback=self._is_at_global_limit,
                create_delay=create_delay,
            )

        # Violation tracking
        self._violations: List[LimitViolation] = []
        self._max_observed_total: int = 0

        # State
        self._started = False
        self._shutdown = False

    def _total_sandbox_count(self) -> int:
        """Get total sandbox count across all pools (ready + creating + in_use)."""
        total = sum(
            p.ready_count + p.creating_count + p.in_use_count
            for p in self._pools.values()
        )
        # Track max observed
        if total > self._max_observed_total:
            self._max_observed_total = total
        return total

    def _total_in_use_count(self) -> int:
        """Get total in-use sandbox count across all pools."""
        return sum(p.in_use_count for p in self._pools.values())

    def _total_ready_count(self) -> int:
        """Get total ready/warm sandbox count across all pools."""
        return sum(p.ready_count for p in self._pools.values())

    def _total_creating_count(self) -> int:
        """Get total creating sandbox count across all pools."""
        return sum(p.creating_count for p in self._pools.values())

    def _is_at_global_limit(self) -> bool:
        """Check if we've reached the global sandbox limit."""
        if self._max_total is None:
            return False
        current = self._total_sandbox_count()
        at_limit = current >= self._max_total

        # Check for violation (if we somehow exceeded)
        if current > self._max_total:
            violation = LimitViolation(
                timestamp=time.time(),
                violation_type="exceeded",
                limit_name="max_total_sandboxes",
                limit_value=self._max_total,
                actual_value=current,
                details=self._get_pool_breakdown(),
            )
            self._violations.append(violation)
            logger.error(f"LIMIT VIOLATION: {current} > {self._max_total}")
            logger.error(f"  Breakdown: {self._get_pool_breakdown()}")

        return at_limit

    def _get_pool_breakdown(self) -> str:
        """Get detailed breakdown of pool counts."""
        parts = []
        for image, pool in self._pools.items():
            parts.append(f"{image}(r={pool.ready_count},c={pool.creating_count},u={pool.in_use_count})")
        return ", ".join(parts)

    async def start(self):
        """Start the manager and all pools."""
        if self._started:
            return
        self._started = True
        self._shutdown = False

        for pool in self._pools.values():
            await pool.start()

        logger.info(f"AlgorithmicMockManager started with {len(self._pools)} pools")
        logger.info(f"  max_total_sandboxes: {self._max_total}")

    async def shutdown(self, timeout: float = 30.0):
        """Shutdown the manager."""
        if self._shutdown:
            return
        self._shutdown = True

        for pool in self._pools.values():
            await pool.stop()

        self._started = False
        logger.info("AlgorithmicMockManager shutdown")

        # Report any violations
        if self._violations:
            logger.error(f"DETECTED {len(self._violations)} LIMIT VIOLATIONS:")
            for v in self._violations:
                logger.error(f"  {v.violation_type}: {v.actual_value} > {v.limit_value}")

    async def warm_up(self, timeout: float = 120.0) -> None:
        """Block until all pools reach their target_ready count.

        This mimics the real SandboxManager.warm_up() behavior, waiting for
        pools to be pre-warmed before accepting traffic.

        Args:
            timeout: Maximum time to wait for warm-up (in real seconds)

        Raises:
            TimeoutError: If timeout is reached before pools are ready
        """
        if not self._started:
            raise RuntimeError("Manager not started")

        start_time = time.time()

        while time.time() - start_time < timeout:
            all_ready = all(
                p.ready_count >= p.target_ready
                for p in self._pools.values()
            )
            if all_ready:
                total_ready = sum(p.ready_count for p in self._pools.values())
                logger.info(f"Warm-up complete: {total_ready} sandboxes ready")
                return
            await asyncio.sleep(0.1)

        # Timeout reached
        status = ", ".join(
            f"{img}: {p.ready_count}/{p.target_ready}"
            for img, p in self._pools.items()
        )
        raise TimeoutError(f"Warm-up timeout after {timeout}s. Status: {status}")

    async def acquire(self, image: str, timeout: Optional[float] = None) -> SimulatedSandbox:
        """Acquire a sandbox for the given image."""
        if not self._started:
            raise RuntimeError("Manager not started")
        if self._shutdown:
            raise RuntimeError("Manager is shutting down")

        if image not in self._pools:
            raise ValueError(f"Unknown image: {image}")

        # Invariant check before acquire
        self._check_invariants("pre-acquire")

        sandbox = await self._pools[image].acquire(timeout=timeout)

        # Invariant check after acquire
        self._check_invariants("post-acquire")

        return sandbox

    def release(self, sandbox: SimulatedSandbox, image: str):
        """Release a sandbox back."""
        if image in self._pools:
            self._pools[image].release(sandbox)

        # Invariant check after release
        self._check_invariants("post-release")

    def _check_invariants(self, context: str):
        """Check invariants and log violations."""
        total = self._total_sandbox_count()

        if self._max_total is not None and total > self._max_total:
            logger.error(f"INVARIANT VIOLATION at {context}: total={total} > max={self._max_total}")
            logger.error(f"  Breakdown: {self._get_pool_breakdown()}")

    def metrics(self) -> Dict[str, PoolStats]:
        """Get current metrics for all pools."""
        return {image: pool.get_stats() for image, pool in self._pools.items()}

    def get_stats(self) -> Dict[str, Any]:
        """Get detailed statistics for metrics collection."""
        stats = {}
        for image, pool in self._pools.items():
            stats[f'{image}_ready'] = pool.ready_count
            stats[f'{image}_creating'] = pool.creating_count
            stats[f'{image}_in_use'] = pool.in_use_count

        stats['total_sandboxes'] = self._total_sandbox_count()
        stats['max_observed'] = self._max_observed_total
        stats['violations'] = len(self._violations)
        return stats

    def get_violations(self) -> List[LimitViolation]:
        """Get all recorded violations."""
        return self._violations.copy()

    def get_max_observed(self) -> int:
        """Get the maximum total sandboxes observed."""
        return self._max_observed_total


def create_algorithmic_mock(scenario_config) -> AlgorithmicMockManager:
    """
    Create an AlgorithmicMockManager from a scenario config.

    Args:
        scenario_config: ScenarioConfig from config.py

    Returns:
        Configured AlgorithmicMockManager
    """
    config = scenario_config.test_config

    pools = {
        'python': {
            'target_ready': config.python_pool.target_ready,
            'max_sandboxes': config.python_pool.max_sandboxes,
        },
        'node': {
            'target_ready': config.node_pool.target_ready,
            'max_sandboxes': config.node_pool.max_sandboxes,
        },
    }

    return AlgorithmicMockManager(
        pools=pools,
        max_total_sandboxes=config.max_total_sandboxes,
        max_concurrent_creates=config.max_concurrent_creates,
        # Faster delays for dry-run testing
        create_delay=(0.1, 0.5),
    )
