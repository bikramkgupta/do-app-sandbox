"""SandboxManager for maintaining pools of pre-warmed sandboxes.

This module provides a pool-based sandbox manager that eliminates cold-start
latency by maintaining pre-warmed sandboxes per image.

Example usage:
    >>> from do_app_sandbox import SandboxManager, PoolConfig
    >>>
    >>> manager = SandboxManager(
    ...     pools={"my-image": PoolConfig(target_ready=3)},
    ... )
    >>> await manager.start()
    >>>
    >>> # Instant acquisition from pool
    >>> sandbox = await manager.acquire(image="my-image")
    >>> result = sandbox.exec("python --version")
    >>> sandbox.delete()
    >>>
    >>> await manager.shutdown()
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from .async_sandbox import AsyncSandbox
from .exceptions import (
    PoolExhaustedError,
    PoolShutdownError,
    SandboxCreationError,
    WarmUpTimeoutError,
)
from .sandbox import Sandbox
from .types import SpacesConfig

logger = logging.getLogger(__name__)

# Try to import OpenTelemetry, but make it optional
try:
    from opentelemetry import metrics

    _otel_available = True
except ImportError:
    _otel_available = False
    metrics = None


@dataclass
class PoolConfig:
    """Configuration for a sandbox pool.

    Attributes:
        max_ready: Maximum sandboxes to keep warming in pool (default: 10)
        target_ready: Target number of ready sandboxes when pool is active (default: 0)
        idle_timeout: Seconds of no acquires before scaling down (default: 60)
        scale_down_delay: Seconds between sandbox destructions during scale-down (default: 60)
        cooldown_after_acquire: Seconds to pause scale-down after an acquire (default: 120)
        max_warm_age: Max seconds a sandbox can warm before being cycled out (default: 1800)
        health_check_interval: Seconds between health checks, 0 to disable (default: 60)
        on_empty: Behavior when pool is empty: "create" or "fail" (default: "create")
        create_retries: Number of retries for failed sandbox creation (default: 3)
        create_retry_delay: Seconds between creation retries (default: 5)
    """

    max_ready: int = 10
    target_ready: int = 0
    idle_timeout: int = 60
    scale_down_delay: int = 60
    cooldown_after_acquire: int = 120
    max_warm_age: int = 1800
    health_check_interval: int = 60
    on_empty: str = "create"  # "create" or "fail"
    create_retries: int = 3
    create_retry_delay: int = 5

    def __post_init__(self):
        if self.on_empty not in ("create", "fail"):
            raise ValueError(f"on_empty must be 'create' or 'fail', got {self.on_empty!r}")
        if self.max_ready < 0:
            raise ValueError(f"max_ready must be >= 0, got {self.max_ready}")
        if self.target_ready < 0:
            raise ValueError(f"target_ready must be >= 0, got {self.target_ready}")
        if self.target_ready > self.max_ready:
            raise ValueError(
                f"target_ready ({self.target_ready}) cannot exceed max_ready ({self.max_ready})"
            )


@dataclass
class PoolMetrics:
    """Metrics for a sandbox pool.

    Attributes:
        ready: Current number of ready sandboxes in pool
        creating: Number of sandboxes currently being created
        in_use: Number of sandboxes currently acquired (tracked externally)
        total_acquires: Total number of successful acquisitions
        acquires_from_pool: Acquisitions served from pool (instant)
        acquires_cold_start: Acquisitions that required cold start
        pool_hit_rate: Ratio of pool hits to total acquires
        avg_acquire_latency_ms: Average acquisition latency in milliseconds
        scale_up_events: Number of scale up events
        scale_down_events: Number of scale down events
        failed_creates: Number of failed sandbox creations
        health_check_removals: Number of sandboxes removed due to health checks
    """

    ready: int = 0
    creating: int = 0
    in_use: int = 0
    total_acquires: int = 0
    acquires_from_pool: int = 0
    acquires_cold_start: int = 0
    pool_hit_rate: float = 0.0
    avg_acquire_latency_ms: float = 0.0
    scale_up_events: int = 0
    scale_down_events: int = 0
    failed_creates: int = 0
    health_check_removals: int = 0


@dataclass
class _PooledSandbox:
    """Internal wrapper for a sandbox in the pool with metadata."""

    sandbox: Sandbox
    created_at: float = field(default_factory=time.time)

    @property
    def age(self) -> float:
        """Age of the sandbox in seconds."""
        return time.time() - self.created_at


class SandboxPool:
    """Manages a pool of sandboxes for a single image.

    This class handles the lifecycle of sandboxes for one specific image,
    including creation, pooling, health checks, and cleanup.
    """

    def __init__(
        self,
        image: str,
        config: PoolConfig,
        sandbox_defaults: Dict[str, Any],
        create_semaphore: asyncio.Semaphore,
        total_limit_callback: Optional[Callable[[], bool]] = None,
    ):
        """Initialize a sandbox pool.

        Args:
            image: The image identifier for this pool
            config: Pool configuration
            sandbox_defaults: Default kwargs for Sandbox.create()
            create_semaphore: Semaphore to limit concurrent creations globally
            total_limit_callback: Callback that returns True if global limit reached
        """
        self.image = image
        self.config = config
        self._sandbox_defaults = sandbox_defaults
        self._create_semaphore = create_semaphore
        self._total_limit_callback = total_limit_callback

        # Pool state
        self._ready_queue: asyncio.Queue[_PooledSandbox] = asyncio.Queue()
        self._creating_count: int = 0
        self._in_use_count: int = 0  # Track sandboxes that have been acquired
        self._lock = asyncio.Lock()

        # Tracking
        self._last_acquire_time: Optional[float] = None
        self._last_scale_down_time: Optional[float] = None
        self._is_active: bool = False
        self._shutdown: bool = False

        # Metrics
        self._metrics = PoolMetrics()
        self._acquire_latencies: List[float] = []

        # Background tasks
        self._replenish_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None

    @property
    def ready_count(self) -> int:
        """Number of sandboxes ready in the pool."""
        return self._ready_queue.qsize()

    @property
    def creating_count(self) -> int:
        """Number of sandboxes currently being created."""
        return self._creating_count

    @property
    def in_use_count(self) -> int:
        """Number of sandboxes currently in use (acquired but not released)."""
        return self._in_use_count

    def get_metrics(self) -> PoolMetrics:
        """Get current pool metrics."""
        self._metrics.ready = self.ready_count
        self._metrics.creating = self._creating_count
        self._metrics.in_use = self._in_use_count
        if self._metrics.total_acquires > 0:
            self._metrics.pool_hit_rate = (
                self._metrics.acquires_from_pool / self._metrics.total_acquires
            )
        if self._acquire_latencies:
            self._metrics.avg_acquire_latency_ms = (
                sum(self._acquire_latencies) / len(self._acquire_latencies)
            )
        return self._metrics

    async def start(self) -> None:
        """Start background tasks for this pool."""
        self._shutdown = False
        self._replenish_task = asyncio.create_task(self._replenish_loop())
        if self.config.health_check_interval > 0:
            self._health_task = asyncio.create_task(self._health_check_loop())

    async def stop(self) -> None:
        """Stop background tasks and clean up."""
        self._shutdown = True

        # Cancel background tasks
        if self._replenish_task:
            self._replenish_task.cancel()
            try:
                await self._replenish_task
            except asyncio.CancelledError:
                pass

        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Destroy all pooled sandboxes
        await self._drain_pool()

    async def _drain_pool(self) -> None:
        """Destroy all sandboxes in the pool."""
        while not self._ready_queue.empty():
            try:
                pooled = self._ready_queue.get_nowait()
                await self._destroy_sandbox(pooled.sandbox)
            except asyncio.QueueEmpty:
                break

    async def acquire(self, timeout: Optional[float] = None) -> Sandbox:
        """Acquire a sandbox from the pool.

        Args:
            timeout: Maximum time to wait for a sandbox (only applies to cold start)

        Returns:
            A ready Sandbox instance

        Raises:
            PoolShutdownError: If the pool is shutting down
            PoolExhaustedError: If pool is empty and on_empty='fail'
        """
        if self._shutdown:
            raise PoolShutdownError("Pool is shutting down")

        start_time = time.time()
        sandbox = await self._try_acquire_from_pool()

        if sandbox is not None:
            # Got from pool - instant!
            latency_ms = (time.time() - start_time) * 1000
            self._record_acquire(from_pool=True, latency_ms=latency_ms)
            sandbox._from_pool = True  # Mark for external tracking
            self._in_use_count += 1  # Track in-use sandbox
            return sandbox

        # Pool empty - handle based on config
        if self.config.on_empty == "fail":
            raise PoolExhaustedError(f"Pool for image '{self.image}' is exhausted")

        # Check global limit before on-demand creation
        if self._total_limit_callback and self._total_limit_callback():
            raise PoolExhaustedError(
                f"Global sandbox limit reached, cannot create on-demand for {self.image}"
            )

        # Fall back to cold start
        logger.info(f"Pool empty for {self.image}, creating sandbox on-demand")
        sandbox = await self._create_sandbox_with_retry(timeout=timeout)
        latency_ms = (time.time() - start_time) * 1000
        self._record_acquire(from_pool=False, latency_ms=latency_ms)
        sandbox._from_pool = False  # Mark for external tracking
        self._in_use_count += 1  # Track in-use sandbox
        return sandbox

    def release(self, sandbox: Sandbox) -> None:
        """Release a sandbox back (decrement in-use count).

        Call this when done with a sandbox to update the in-use count.
        The sandbox itself should be deleted separately if not being reused.

        Args:
            sandbox: The sandbox to release
        """
        if self._in_use_count > 0:
            self._in_use_count -= 1

    async def _try_acquire_from_pool(self) -> Optional[Sandbox]:
        """Try to get a sandbox from the pool without blocking."""
        async with self._lock:
            self._last_acquire_time = time.time()
            self._is_active = True

        while not self._ready_queue.empty():
            try:
                pooled = self._ready_queue.get_nowait()

                # Check if sandbox is too old
                if pooled.age > self.config.max_warm_age:
                    logger.debug(f"Sandbox {pooled.sandbox.app_id} too old, destroying")
                    await self._destroy_sandbox(pooled.sandbox)
                    self._metrics.health_check_removals += 1
                    continue

                # Quick health check
                if not pooled.sandbox.is_ready():
                    logger.debug(f"Sandbox {pooled.sandbox.app_id} not ready, destroying")
                    await self._destroy_sandbox(pooled.sandbox)
                    self._metrics.health_check_removals += 1
                    continue

                return pooled.sandbox
            except asyncio.QueueEmpty:
                break

        return None

    def _record_acquire(self, from_pool: bool, latency_ms: float) -> None:
        """Record metrics for an acquire operation."""
        self._metrics.total_acquires += 1
        if from_pool:
            self._metrics.acquires_from_pool += 1
        else:
            self._metrics.acquires_cold_start += 1
        self._acquire_latencies.append(latency_ms)
        # Keep only last 1000 latencies
        if len(self._acquire_latencies) > 1000:
            self._acquire_latencies = self._acquire_latencies[-1000:]

    async def _create_sandbox_with_retry(
        self, timeout: Optional[float] = None
    ) -> Sandbox:
        """Create a sandbox with retry logic."""
        last_error: Optional[Exception] = None

        for attempt in range(self.config.create_retries):
            try:
                async with self._create_semaphore:
                    async with self._lock:
                        self._creating_count += 1
                    try:
                        sandbox = await asyncio.to_thread(
                            Sandbox.create,
                            image=self.image,
                            wait_ready=True,
                            timeout=timeout or 600,
                            **self._sandbox_defaults,
                        )
                        return sandbox
                    finally:
                        async with self._lock:
                            self._creating_count -= 1
            except SandboxCreationError as e:
                last_error = e
                self._metrics.failed_creates += 1
                logger.warning(
                    f"Sandbox creation attempt {attempt + 1}/{self.config.create_retries} "
                    f"failed for {self.image}: {e}"
                )
                if attempt < self.config.create_retries - 1:
                    await asyncio.sleep(self.config.create_retry_delay)

        raise SandboxCreationError(
            f"Failed to create sandbox for {self.image} after "
            f"{self.config.create_retries} attempts: {last_error}"
        )

    async def _destroy_sandbox(self, sandbox: Sandbox) -> None:
        """Destroy a sandbox safely."""
        try:
            await asyncio.to_thread(sandbox.delete)
        except Exception as e:
            logger.warning(f"Error destroying sandbox {sandbox.app_id}: {e}")

    async def _replenish_loop(self) -> None:
        """Background task to maintain target pool size."""
        while not self._shutdown:
            try:
                await self._replenish_once()
                await asyncio.sleep(1)  # Check every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in replenish loop for {self.image}: {e}")
                await asyncio.sleep(5)

    async def _replenish_once(self) -> None:
        """Single replenishment check."""
        # Check if we should scale down
        if await self._should_scale_down():
            await self._scale_down_one()
            return

        # Check if we need to replenish
        target = self.config.target_ready if self._is_active else 0
        current = self.ready_count + self._creating_count

        if current < target:
            # Check global limit
            if self._total_limit_callback and self._total_limit_callback():
                logger.debug(f"Global sandbox limit reached, not creating for {self.image}")
                return

            # Check pool limit
            if current >= self.config.max_ready:
                return

            # Create one sandbox
            asyncio.create_task(self._create_and_add_to_pool())
            self._metrics.scale_up_events += 1

    async def _should_scale_down(self) -> bool:
        """Check if we should scale down the pool."""
        if not self._is_active:
            return self.ready_count > 0

        if self._last_acquire_time is None:
            return False

        time_since_acquire = time.time() - self._last_acquire_time

        # Check cooldown
        if time_since_acquire < self.config.cooldown_after_acquire:
            return False

        # Check idle timeout
        if time_since_acquire < self.config.idle_timeout:
            return False

        # Check scale down delay
        if self._last_scale_down_time is not None:
            time_since_scale_down = time.time() - self._last_scale_down_time
            if time_since_scale_down < self.config.scale_down_delay:
                return False

        return self.ready_count > 0

    async def _scale_down_one(self) -> None:
        """Remove one sandbox from the pool."""
        try:
            pooled = self._ready_queue.get_nowait()
            await self._destroy_sandbox(pooled.sandbox)
            self._last_scale_down_time = time.time()
            self._metrics.scale_down_events += 1
            logger.debug(f"Scaled down pool for {self.image}, now {self.ready_count} ready")

            # Check if pool is now empty
            if self.ready_count == 0:
                self._is_active = False
        except asyncio.QueueEmpty:
            pass

    async def _create_and_add_to_pool(self) -> None:
        """Create a sandbox and add it to the pool."""
        try:
            sandbox = await self._create_sandbox_with_retry()
            if not self._shutdown:
                await self._ready_queue.put(_PooledSandbox(sandbox=sandbox))
                logger.debug(
                    f"Added sandbox to pool for {self.image}, now {self.ready_count} ready"
                )
        except Exception as e:
            logger.error(f"Failed to create sandbox for pool {self.image}: {e}")

    async def _health_check_loop(self) -> None:
        """Background task to check health of pooled sandboxes."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._health_check_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop for {self.image}: {e}")
                await asyncio.sleep(5)

    async def _health_check_once(self) -> None:
        """Single health check pass."""
        # Move all items to a temp list, check them, and re-add healthy ones
        healthy: List[_PooledSandbox] = []
        unhealthy_count = 0

        while not self._ready_queue.empty():
            try:
                pooled = self._ready_queue.get_nowait()

                # Check age
                if pooled.age > self.config.max_warm_age:
                    await self._destroy_sandbox(pooled.sandbox)
                    unhealthy_count += 1
                    continue

                # Check health
                is_ready = await asyncio.to_thread(pooled.sandbox.is_ready)
                if not is_ready:
                    await self._destroy_sandbox(pooled.sandbox)
                    unhealthy_count += 1
                    continue

                healthy.append(pooled)
            except asyncio.QueueEmpty:
                break

        # Re-add healthy sandboxes
        for pooled in healthy:
            await self._ready_queue.put(pooled)

        if unhealthy_count > 0:
            self._metrics.health_check_removals += unhealthy_count
            logger.info(
                f"Health check removed {unhealthy_count} sandboxes from {self.image} pool"
            )


class SandboxManager:
    """Manager for pools of pre-warmed sandboxes.

    The SandboxManager maintains pools of ready-to-use sandboxes per image,
    eliminating the ~30 second cold-start latency for sandbox creation.

    Example:
        >>> manager = SandboxManager(
        ...     pools={"my-image": PoolConfig(target_ready=3)},
        ... )
        >>> await manager.start()
        >>>
        >>> # Instant acquisition
        >>> sandbox = await manager.acquire(image="my-image")
        >>> result = sandbox.exec("python --version")
        >>> sandbox.delete()
        >>>
        >>> await manager.shutdown()

    Context manager usage:
        >>> async with SandboxManager(pools={"my-image": PoolConfig(target_ready=3)}) as manager:
        ...     sandbox = await manager.acquire(image="my-image")
        ...     # use sandbox
        ...     sandbox.delete()
    """

    def __init__(
        self,
        pools: Optional[Dict[str, PoolConfig]] = None,
        default_pool_config: Optional[PoolConfig] = None,
        max_total_sandboxes: Optional[int] = None,
        max_concurrent_creates: int = 10,
        sandbox_defaults: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the SandboxManager.

        Args:
            pools: Per-image pool configurations. Keys are image identifiers.
            default_pool_config: Default config for images without explicit config.
                If None, uses PoolConfig() defaults.
            max_total_sandboxes: Global limit across all pools (None = unlimited)
            max_concurrent_creates: Max parallel sandbox creations (default: 10)
            sandbox_defaults: Default kwargs passed to Sandbox.create() for all pools
        """
        self._pool_configs = pools or {}
        self._default_config = default_pool_config or PoolConfig()
        self._max_total = max_total_sandboxes
        self._sandbox_defaults = sandbox_defaults or {}

        # Concurrency control
        self._create_semaphore = asyncio.Semaphore(max_concurrent_creates)

        # Pools
        self._pools: Dict[str, SandboxPool] = {}
        self._pools_lock = asyncio.Lock()

        # State
        self._started = False
        self._shutdown = False

        # Metrics - OpenTelemetry
        self._meter = None
        self._otel_gauges: Dict[str, Any] = {}
        self._otel_counters: Dict[str, Any] = {}
        self._otel_histograms: Dict[str, Any] = {}
        self._setup_otel_metrics()

    def _setup_otel_metrics(self) -> None:
        """Set up OpenTelemetry metrics if available."""
        if not _otel_available:
            return

        try:
            self._meter = metrics.get_meter("do_app_sandbox.manager")

            # Gauges
            self._otel_gauges["pool_ready"] = self._meter.create_observable_gauge(
                "sandbox.pool.ready",
                callbacks=[self._observe_pool_ready],
                description="Number of ready sandboxes in pool",
            )
            self._otel_gauges["pool_creating"] = self._meter.create_observable_gauge(
                "sandbox.pool.creating",
                callbacks=[self._observe_pool_creating],
                description="Number of sandboxes being created",
            )

            # Counters
            self._otel_counters["acquire_total"] = self._meter.create_counter(
                "sandbox.acquire.total",
                description="Total sandbox acquisitions",
            )
            self._otel_counters["create_total"] = self._meter.create_counter(
                "sandbox.create.total",
                description="Total sandbox creation attempts",
            )
            self._otel_counters["scale_events"] = self._meter.create_counter(
                "sandbox.scale.events",
                description="Pool scale events",
            )

            # Histograms
            self._otel_histograms["acquire_latency"] = self._meter.create_histogram(
                "sandbox.acquire.latency_ms",
                description="Sandbox acquisition latency in milliseconds",
            )
        except Exception as e:
            logger.warning(f"Failed to set up OpenTelemetry metrics: {e}")

    def _observe_pool_ready(self, options):
        """Observable callback for pool ready gauge."""
        for image, pool in self._pools.items():
            yield metrics.Observation(pool.ready_count, {"image": image})

    def _observe_pool_creating(self, options):
        """Observable callback for pool creating gauge."""
        for image, pool in self._pools.items():
            yield metrics.Observation(pool.creating_count, {"image": image})

    def _total_sandbox_count(self) -> int:
        """Get total sandbox count across all pools (ready + creating + in_use)."""
        return sum(
            p.ready_count + p.creating_count + p.in_use_count
            for p in self._pools.values()
        )

    def _is_at_global_limit(self) -> bool:
        """Check if we've reached the global sandbox limit."""
        if self._max_total is None:
            return False
        return self._total_sandbox_count() >= self._max_total

    async def _get_or_create_pool(self, image: str) -> SandboxPool:
        """Get or create a pool for an image."""
        async with self._pools_lock:
            if image not in self._pools:
                config = self._pool_configs.get(image, self._default_config)
                pool = SandboxPool(
                    image=image,
                    config=config,
                    sandbox_defaults=self._sandbox_defaults,
                    create_semaphore=self._create_semaphore,
                    total_limit_callback=self._is_at_global_limit,
                )
                self._pools[image] = pool
                if self._started:
                    await pool.start()
            return self._pools[image]

    async def start(self) -> None:
        """Start the manager and all configured pools.

        This starts background tasks for replenishment and health checking.
        Must be called before acquire().
        """
        if self._started:
            return

        self._shutdown = False
        self._started = True

        # Start pools for pre-configured images
        for image, config in self._pool_configs.items():
            pool = await self._get_or_create_pool(image)
            await pool.start()

        logger.info(
            f"SandboxManager started with {len(self._pool_configs)} configured pools"
        )

    async def acquire(
        self,
        image: str,
        *,
        timeout: Optional[float] = None,
    ) -> Sandbox:
        """Acquire a ready sandbox for the given image.

        If the pool has ready sandboxes, returns immediately.
        If the pool is empty and on_empty='create', creates on-demand (~30s).
        If the pool is empty and on_empty='fail', raises PoolExhaustedError.

        Args:
            image: The image identifier
            timeout: Maximum time to wait for sandbox creation (cold start only)

        Returns:
            A ready Sandbox instance

        Raises:
            PoolShutdownError: If the manager is shutting down
            PoolExhaustedError: If pool is empty and on_empty='fail'
            SandboxCreationError: If sandbox creation fails
        """
        if self._shutdown:
            raise PoolShutdownError("Manager is shutting down")

        if not self._started:
            raise RuntimeError("SandboxManager.start() must be called before acquire()")

        pool = await self._get_or_create_pool(image)
        return await pool.acquire(timeout=timeout)

    def release(self, sandbox: Sandbox, image: str) -> None:
        """Release a sandbox (decrement in-use count for the pool).

        Call this when done with a sandbox to update tracking.
        This allows the global limit to correctly account for available capacity.

        Args:
            sandbox: The sandbox to release
            image: The image identifier for the sandbox
        """
        if image in self._pools:
            self._pools[image].release(sandbox)

    async def shutdown(
        self,
        timeout: float = 30.0,
        wait_for_active: bool = False,
    ) -> None:
        """Graceful shutdown of the manager.

        Stops all background tasks and destroys all pooled sandboxes.

        Args:
            timeout: Maximum time to wait for shutdown
            wait_for_active: If True, wait for in-use sandboxes (not implemented)
        """
        if self._shutdown:
            return

        self._shutdown = True
        logger.info("SandboxManager shutting down...")

        # Stop all pools
        stop_tasks = [pool.stop() for pool in self._pools.values()]
        if stop_tasks:
            await asyncio.wait_for(
                asyncio.gather(*stop_tasks, return_exceptions=True),
                timeout=timeout,
            )

        self._started = False
        logger.info("SandboxManager shutdown complete")

    async def warm_up(self, timeout: float = 120.0) -> None:
        """Wait for all pools to reach their target_ready count.

        This is useful for waiting before accepting production traffic.

        Args:
            timeout: Maximum time to wait for warm-up

        Raises:
            WarmUpTimeoutError: If timeout is reached before pools are ready
        """
        if not self._started:
            raise RuntimeError("SandboxManager.start() must be called before warm_up()")

        start_time = time.time()

        while True:
            all_ready = True
            for image, pool in self._pools.items():
                config = self._pool_configs.get(image, self._default_config)
                if pool.ready_count < config.target_ready:
                    all_ready = False
                    break

            if all_ready:
                logger.info("All pools warmed up")
                return

            if time.time() - start_time > timeout:
                status = {
                    img: f"{p.ready_count}/{self._pool_configs.get(img, self._default_config).target_ready}"
                    for img, p in self._pools.items()
                }
                raise WarmUpTimeoutError(
                    f"Warm-up timeout after {timeout}s. Pool status: {status}"
                )

            await asyncio.sleep(1)

    def metrics(self) -> Dict[str, PoolMetrics]:
        """Get current metrics for all pools.

        Returns:
            Dictionary mapping image names to their PoolMetrics
        """
        return {image: pool.get_metrics() for image, pool in self._pools.items()}

    async def __aenter__(self) -> "SandboxManager":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.shutdown()
