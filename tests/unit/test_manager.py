"""Unit tests for SandboxManager."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from do_app_sandbox.exceptions import (
    PoolExhaustedError,
    PoolShutdownError,
    WarmUpTimeoutError,
)
from do_app_sandbox.manager import (
    PoolConfig,
    PoolMetrics,
    SandboxManager,
    SandboxPool,
    _PooledSandbox,
)


class TestPoolConfig:
    """Tests for PoolConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PoolConfig()
        assert config.max_ready == 10
        assert config.target_ready == 0
        assert config.idle_timeout == 60
        assert config.scale_down_delay == 60
        assert config.cooldown_after_acquire == 120
        assert config.max_warm_age == 1800
        assert config.health_check_interval == 60
        assert config.on_empty == "create"
        assert config.create_retries == 3
        assert config.create_retry_delay == 5

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PoolConfig(
            max_ready=20,
            target_ready=5,
            idle_timeout=120,
            on_empty="fail",
        )
        assert config.max_ready == 20
        assert config.target_ready == 5
        assert config.idle_timeout == 120
        assert config.on_empty == "fail"

    def test_invalid_on_empty(self):
        """Test that invalid on_empty raises ValueError."""
        with pytest.raises(ValueError, match="on_empty must be"):
            PoolConfig(on_empty="invalid")

    def test_invalid_max_ready(self):
        """Test that negative max_ready raises ValueError."""
        with pytest.raises(ValueError, match="max_ready must be >= 0"):
            PoolConfig(max_ready=-1)

    def test_invalid_target_ready(self):
        """Test that negative target_ready raises ValueError."""
        with pytest.raises(ValueError, match="target_ready must be >= 0"):
            PoolConfig(target_ready=-1)

    def test_target_exceeds_max(self):
        """Test that target_ready > max_ready raises ValueError."""
        with pytest.raises(ValueError, match="target_ready.*cannot exceed max_ready"):
            PoolConfig(max_ready=5, target_ready=10)


class TestPoolMetrics:
    """Tests for PoolMetrics dataclass."""

    def test_default_values(self):
        """Test default metrics values."""
        metrics = PoolMetrics()
        assert metrics.ready == 0
        assert metrics.creating == 0
        assert metrics.in_use == 0
        assert metrics.total_acquires == 0
        assert metrics.pool_hit_rate == 0.0

    def test_custom_values(self):
        """Test setting custom metrics values."""
        metrics = PoolMetrics(
            ready=5,
            creating=2,
            total_acquires=100,
            acquires_from_pool=95,
        )
        assert metrics.ready == 5
        assert metrics.creating == 2
        assert metrics.total_acquires == 100
        assert metrics.acquires_from_pool == 95


class TestPooledSandbox:
    """Tests for _PooledSandbox wrapper."""

    def test_age_calculation(self):
        """Test that age is calculated correctly."""
        mock_sandbox = MagicMock()
        pooled = _PooledSandbox(sandbox=mock_sandbox)

        # Age should be very small (just created)
        assert pooled.age >= 0
        assert pooled.age < 1  # Less than 1 second


class TestSandboxPool:
    """Tests for SandboxPool class."""

    @pytest.fixture
    def pool(self):
        """Create a test pool."""
        config = PoolConfig(target_ready=2, max_ready=5)
        semaphore = asyncio.Semaphore(10)
        return SandboxPool(
            image="test-image",
            config=config,
            sandbox_defaults={},
            create_semaphore=semaphore,
        )

    def test_initialization(self, pool):
        """Test pool initialization."""
        assert pool.image == "test-image"
        assert pool.ready_count == 0
        assert pool.creating_count == 0

    def test_get_metrics(self, pool):
        """Test getting pool metrics."""
        metrics = pool.get_metrics()
        assert isinstance(metrics, PoolMetrics)
        assert metrics.ready == 0
        assert metrics.creating == 0

    @pytest.mark.asyncio
    async def test_acquire_empty_pool_fail(self):
        """Test acquiring from empty pool with on_empty='fail'."""
        config = PoolConfig(target_ready=0, on_empty="fail")
        semaphore = asyncio.Semaphore(10)
        pool = SandboxPool(
            image="test-image",
            config=config,
            sandbox_defaults={},
            create_semaphore=semaphore,
        )

        with pytest.raises(PoolExhaustedError):
            await pool.acquire()

    @pytest.mark.asyncio
    async def test_acquire_shutdown(self, pool):
        """Test acquiring after shutdown raises error."""
        pool._shutdown = True

        with pytest.raises(PoolShutdownError):
            await pool.acquire()

    @pytest.mark.asyncio
    async def test_acquire_from_pool(self, pool):
        """Test acquiring a sandbox from the pool."""
        # Create a mock sandbox
        mock_sandbox = MagicMock()
        mock_sandbox.is_ready.return_value = True
        mock_sandbox.app_id = "test-app-id"

        # Add to pool
        pooled = _PooledSandbox(sandbox=mock_sandbox)
        await pool._ready_queue.put(pooled)

        # Acquire should return the sandbox
        sandbox = await pool.acquire()
        assert sandbox == mock_sandbox
        assert pool.ready_count == 0

    @pytest.mark.asyncio
    async def test_acquire_skips_unhealthy(self, pool):
        """Test that acquire skips unhealthy sandboxes."""
        # Create unhealthy sandbox
        unhealthy = MagicMock()
        unhealthy.is_ready.return_value = False
        unhealthy.app_id = "unhealthy-id"
        unhealthy.delete = MagicMock()

        # Create healthy sandbox
        healthy = MagicMock()
        healthy.is_ready.return_value = True
        healthy.app_id = "healthy-id"

        # Add both to pool
        await pool._ready_queue.put(_PooledSandbox(sandbox=unhealthy))
        await pool._ready_queue.put(_PooledSandbox(sandbox=healthy))

        # Acquire should return healthy sandbox
        sandbox = await pool.acquire()
        assert sandbox == healthy

    @pytest.mark.asyncio
    async def test_stop_drains_pool(self, pool):
        """Test that stop() drains all sandboxes from pool."""
        # Add sandboxes to pool
        for i in range(3):
            mock = MagicMock()
            mock.delete = MagicMock()
            await pool._ready_queue.put(_PooledSandbox(sandbox=mock))

        assert pool.ready_count == 3

        await pool.stop()

        assert pool.ready_count == 0
        assert pool._shutdown is True


class TestSandboxManager:
    """Tests for SandboxManager class."""

    def test_initialization_default(self):
        """Test default initialization."""
        manager = SandboxManager()
        assert manager._pool_configs == {}
        assert manager._max_total is None
        assert manager._started is False
        assert manager._shutdown is False

    def test_initialization_with_config(self):
        """Test initialization with configuration."""
        pools = {
            "image-a": PoolConfig(target_ready=3),
            "image-b": PoolConfig(target_ready=5),
        }
        manager = SandboxManager(
            pools=pools,
            max_total_sandboxes=50,
            max_concurrent_creates=5,
        )
        assert len(manager._pool_configs) == 2
        assert manager._max_total == 50

    @pytest.mark.asyncio
    async def test_start_creates_pools(self):
        """Test that start() creates pools for configured images."""
        pools = {
            "image-a": PoolConfig(target_ready=0),
            "image-b": PoolConfig(target_ready=0),
        }
        manager = SandboxManager(pools=pools)

        await manager.start()

        assert manager._started is True
        assert "image-a" in manager._pools
        assert "image-b" in manager._pools

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_before_start_raises(self):
        """Test that acquire() before start() raises RuntimeError."""
        manager = SandboxManager()

        with pytest.raises(RuntimeError, match="start\\(\\) must be called"):
            await manager.acquire(image="test")

    @pytest.mark.asyncio
    async def test_acquire_after_shutdown_raises(self):
        """Test that acquire() after shutdown raises PoolShutdownError."""
        manager = SandboxManager()
        await manager.start()
        await manager.shutdown()

        with pytest.raises(PoolShutdownError):
            await manager.acquire(image="test")

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        """Test that shutdown() can be called multiple times."""
        manager = SandboxManager()
        await manager.start()

        await manager.shutdown()
        await manager.shutdown()  # Should not raise

        assert manager._shutdown is True

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager usage."""
        pools = {"image-a": PoolConfig(target_ready=0)}

        async with SandboxManager(pools=pools) as manager:
            assert manager._started is True

        assert manager._shutdown is True

    def test_metrics_empty(self):
        """Test metrics() with no pools."""
        manager = SandboxManager()
        metrics = manager.metrics()
        assert metrics == {}

    @pytest.mark.asyncio
    async def test_metrics_with_pools(self):
        """Test metrics() returns metrics for all pools."""
        pools = {
            "image-a": PoolConfig(target_ready=0),
            "image-b": PoolConfig(target_ready=0),
        }
        manager = SandboxManager(pools=pools)
        await manager.start()

        metrics = manager.metrics()
        assert "image-a" in metrics
        assert "image-b" in metrics
        assert isinstance(metrics["image-a"], PoolMetrics)

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_warm_up_timeout(self):
        """Test warm_up() timeout."""
        pools = {"image-a": PoolConfig(target_ready=5)}
        manager = SandboxManager(pools=pools)
        await manager.start()

        # warm_up should timeout since no sandboxes can be created
        with pytest.raises(WarmUpTimeoutError):
            await manager.warm_up(timeout=0.1)

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_warm_up_before_start_raises(self):
        """Test warm_up() before start() raises RuntimeError."""
        manager = SandboxManager()

        with pytest.raises(RuntimeError, match="start\\(\\) must be called"):
            await manager.warm_up()

    def test_is_at_global_limit(self):
        """Test global limit checking."""
        manager = SandboxManager(max_total_sandboxes=10)

        # Initially not at limit
        assert manager._is_at_global_limit() is False

    def test_is_at_global_limit_none(self):
        """Test global limit when None (unlimited)."""
        manager = SandboxManager(max_total_sandboxes=None)

        # Should never be at limit
        assert manager._is_at_global_limit() is False


class TestIntegration:
    """Integration tests for SandboxManager with mocked Sandbox."""

    @pytest.mark.asyncio
    async def test_acquire_creates_on_demand(self):
        """Test that acquire creates sandbox on-demand when pool is empty."""
        manager = SandboxManager(
            pools={"test-image": PoolConfig(target_ready=0, on_empty="create")},
        )

        mock_sandbox = MagicMock()
        mock_sandbox.is_ready.return_value = True
        mock_sandbox.app_id = "test-app"
        mock_sandbox.delete = MagicMock()

        with patch("do_app_sandbox.manager.Sandbox") as MockSandbox:
            MockSandbox.create.return_value = mock_sandbox

            await manager.start()

            sandbox = await manager.acquire(image="test-image")

            assert sandbox == mock_sandbox
            MockSandbox.create.assert_called_once()

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_pool_reuses_existing(self):
        """Test that multiple acquires for same image use same pool."""
        manager = SandboxManager()
        await manager.start()

        # Get or create pool twice
        pool1 = await manager._get_or_create_pool("test-image")
        pool2 = await manager._get_or_create_pool("test-image")

        assert pool1 is pool2

        await manager.shutdown()
