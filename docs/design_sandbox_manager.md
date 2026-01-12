# SandboxManager Design Document

## Status: Draft
## Author: Design Discussion
## Date: 2026-01-06

---

## 1. Overview

### Problem Statement

Sandbox creation via `Sandbox.create()` takes approximately 30 seconds due to:
1. App Platform deployment (~1s for API call)
2. Container provisioning and startup
3. Readiness polling until `ACTIVE` status (~29s)

For companies running hundreds or thousands of agents, this 30-second cold-start latency on every sandbox acquisition is unacceptable.

### Proposed Solution

Introduce a `SandboxManager` that maintains pre-warmed pools of ready-to-use sandboxes per image. Sandboxes are created in the background and held in a ready state, allowing instant acquisition.

### Use Case

Long-running agent workloads (e.g., Claude Code sandbox) where:
- Sandboxes run for minutes to hours
- Immediate availability is critical for user experience
- Customers are willing to trade some idle sandbox cost for latency reduction

**Not a substitute for:** Lambda-style short-lived functions where cold-start overhead is amortized differently.

---

## 2. Goals and Non-Goals

### Goals

1. **Near-instant sandbox acquisition** - Acquire from pool in O(ms) instead of O(30s)
2. **Per-image pooling** - Separate pools for each customer image
3. **Adaptive scaling** - Scale down to zero when idle, scale up on demand
4. **Cost control** - Configurable limits to prevent runaway costs
5. **Observability** - OpenTelemetry-native metrics for tuning at scale
6. **Resilience** - Handle creation failures, rate limits, and transient errors
7. **Simple API** - Easy to adopt, minimal configuration required

### Non-Goals

1. **Sandbox reuse** - Sandboxes are single-use; no state sharing between acquisitions
2. **Multi-region pools** - V1 targets single-region deployments
3. **Replacing raw API** - `Sandbox.create()` / `delete()` continue to work independently
4. **Predictive scaling** - V1 uses reactive scaling; ML-based prediction is future work

---

## 3. Design

### 3.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SandboxManager                           │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Pool Registry                          │  │
│  │                                                           │  │
│  │   pools: Dict[image_id, SandboxPool]                      │  │
│  │                                                           │  │
│  │   ┌─────────────────┐  ┌─────────────────┐               │  │
│  │   │  Pool: image-a  │  │  Pool: image-b  │  ...          │  │
│  │   │  ┌──┐┌──┐┌──┐   │  │  ┌──┐┌──┐       │               │  │
│  │   │  │██││██││██│   │  │  │██││██│       │               │  │
│  │   │  └──┘└──┘└──┘   │  │  └──┘└──┘       │               │  │
│  │   │  ready: 3       │  │  ready: 2       │               │  │
│  │   └─────────────────┘  └─────────────────┘               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Background Replenisher (async)               │  │
│  │                                                           │  │
│  │   - Monitors pool levels                                  │  │
│  │   - Creates sandboxes to maintain target_ready            │  │
│  │   - Respects max_concurrent_creates rate limit            │  │
│  │   - Handles creation failures with retry                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Idle Monitor / Scale-Down (async)            │  │
│  │                                                           │  │
│  │   - Tracks last acquire time per pool                     │  │
│  │   - Destroys idle sandboxes after idle_timeout            │  │
│  │   - Respects scale_down_delay between destructions        │  │
│  │   - Pauses during cooldown_after_acquire                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Health Monitor (async)                       │  │
│  │                                                           │  │
│  │   - Periodic sandbox.is_ready() checks on pooled sandboxes│  │
│  │   - Removes unhealthy sandboxes (is_ready() == False)     │  │
│  │   - Cycles out sandboxes exceeding max_warm_age           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ acquire(image="image-a")
                              ▼
                        ┌───────────┐
                        │  Sandbox  │  (fully ready, instant)
                        └───────────┘
                              │
                              │ use for long-running task
                              ▼
                        ┌───────────┐
                        │  Destroy  │  (via shutdown() or context manager)
                        └───────────┘
```

### 3.2 Sandbox Lifecycle in Pool

```
                    Background Replenisher
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   CREATE ──► WAIT_READY ──► IN_POOL ──► ACQUIRED ──► DESTROY│
│     │            │            │            │                │
│    ~1s         ~29s        (idle)     (in use)              │
│                             │                               │
│                      Health checks                          │
│                      Age monitoring                         │
│                             │                               │
│                      ┌──────┴──────┐                        │
│                      ▼             ▼                        │
│                  HEALTHY      UNHEALTHY/STALE               │
│                  (keep)         (destroy)                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Pool States

The pool always maintains `target_ready` sandboxes, preventing the create/delete oscillation pattern.

```
                         acquire()
              ┌────────────────────────────┐
              ▼                            │
         ┌─────────┐    idle_timeout   ┌───┴─────┐
         │  IDLE   │ ◄──────────────── │  ACTIVE │
         │(target  │                   │ (target │
         │ ready)  │                   │  ready) │
         └─────────┘                   └─────────┘
              │                             ▲
              │     acquire() triggers      │
              │     activity tracking       │
              └─────────────────────────────┘
```

**Key:** Both IDLE and ACTIVE states maintain `target_ready` sandboxes. The pool never scales below this value.

---

## 4. API Design

### 4.1 Configuration

```python
from do_sandbox import SandboxManager, PoolConfig

manager = SandboxManager(
    # Global settings
    max_total_sandboxes=100,       # Cost ceiling across all pools
    max_concurrent_creates=10,     # Rate limit for API calls

    # Default config for pools not explicitly configured
    default_pool_config=PoolConfig(
        target_ready=0,            # On-demand by default
        on_empty="create",         # Fallback to cold-start
    ),

    # Per-image pool configuration
    pools={
        "registry.do.com/my-image:v1": PoolConfig(
            # Sizing
            max_ready=20,              # Never exceed 20 warming
            target_ready=5,            # Maintain 5 ready when active

            # Adaptive scaling
            idle_timeout=60,           # 1 min no acquires → start scaling down
            scale_down_delay=60,       # Destroy 1 per minute when idle
            cooldown_after_acquire=120,# Pause scale-down 2 min after acquire

            # Health (lazy check during acquire)
            max_warm_age=1800,         # Cycle out after 30 min warming

            # Behavior
            on_empty="create",         # "create" (fallback) | "fail" (fast-fail)

            # Reliability
            create_retries=3,          # Retry failed creations
            create_retry_delay=5,      # Seconds between retries
        ),
    },

    # Sandbox creation defaults (passed to Sandbox.create)
    sandbox_defaults={
        "region": "nyc",
        "instance_size": "basic-xxs",
    },
)
```

### 4.2 Core Operations

```python
# Async API (primary)
class SandboxManager:
    async def start(self) -> None:
        """Start background workers (replenisher, etc.)."""

    async def acquire(
        self,
        image: str,
        *,
        timeout: Optional[float] = None,  # Max wait time
    ) -> Sandbox:
        """
        Acquire a ready sandbox for the given image.

        - If pool has ready sandboxes: returns immediately
        - If pool is empty and on_empty="create": creates on-demand (30s)
        - If pool is empty and on_empty="fail": raises PoolExhaustedError
        """

    async def shutdown(
        self,
        timeout: float = 30.0,
        wait_for_active: bool = True,
    ) -> None:
        """
        Graceful shutdown.

        - Stops background workers
        - Destroys all pooled (warming) sandboxes
        - If wait_for_active: waits for in-use sandboxes to be released
        """

    def metrics(self) -> Dict[str, PoolMetrics]:
        """Get current metrics for all pools."""

    async def warm_up(
        self,
        timeout: float = 120.0,
    ) -> None:
        """
        Block until all pools reach their target_ready count.
        Useful for waiting before accepting production traffic.
        """
```

### 4.3 Usage Patterns

#### Basic Usage

```python
async def main():
    manager = SandboxManager(
        pools={
            "my-image": PoolConfig(target_ready=3),
        }
    )

    await manager.start()

    try:
        # Instant acquisition from pool
        sandbox = await manager.acquire(image="my-image")

        try:
            # Long-running work
            result = sandbox.exec("python train_model.py")
            print(result.stdout)
        finally:
            # Sandbox is single-use; destroy when done
            sandbox.delete()
    finally:
        await manager.shutdown()
```

#### Context Manager Pattern

```python
async def main():
    async with SandboxManager(pools={"my-image": PoolConfig(target_ready=3)}) as manager:
        async with manager.acquire(image="my-image") as sandbox:
            result = sandbox.exec("python train_model.py")
            # sandbox.delete() called automatically
```

#### Warm-Up Before Production Traffic

```python
async def main():
    manager = SandboxManager(...)
    await manager.start()

    # Wait for pools to fill before accepting requests
    await manager.warm_up(timeout=120)

    # Now safe to serve traffic with low latency
    app.state.sandbox_manager = manager
    await app.serve()
```

---

## 5. Configuration Reference

### 5.1 PoolConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_ready` | int | 10 | Maximum sandboxes to keep warming in pool |
| `target_ready` | int | 0 | **Minimum sandboxes to always maintain** (prevents oscillation) |
| `idle_timeout` | int | 60 | Seconds of no acquires before pool becomes idle |
| `scale_down_delay` | int | 60 | Seconds between sandbox destructions during scale-down |
| `cooldown_after_acquire` | int | 120 | Seconds to pause scale-down after an acquire |
| `max_warm_age` | int | 1800 | Max seconds a sandbox can warm before being cycled out |
| `on_empty` | str | "create" | Behavior when pool is empty: "create" or "fail" |
| `create_retries` | int | 3 | Number of retries for failed sandbox creation |
| `create_retry_delay` | int | 5 | Seconds between creation retries |

**Note:** `target_ready` is the minimum pool size that's always maintained. The pool will never scale below this value, preventing the create/delete oscillation pattern.

### 5.2 SandboxManager Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_total_sandboxes` | int | None | Global limit across all pools (None = unlimited) |
| `max_concurrent_creates` | int | 10 | Max parallel sandbox creations (rate limit) |
| `pools` | Dict | {} | Per-image pool configurations |
| `default_pool_config` | PoolConfig | PoolConfig() | Config for images without explicit pool config |
| `sandbox_defaults` | Dict | {} | Default kwargs passed to Sandbox.create() |

---

## 6. Observability

### 6.1 OpenTelemetry Metrics

The manager emits metrics via OpenTelemetry SDK. Customers configure their own exporters (OpenSearch, Prometheus, Datadog, etc.).

#### Gauges

| Metric | Labels | Description |
|--------|--------|-------------|
| `sandbox.pool.ready` | image | Current ready sandboxes in pool |
| `sandbox.pool.creating` | image | Sandboxes currently being created |
| `sandbox.pool.in_use` | image | Sandboxes currently acquired |

#### Counters

| Metric | Labels | Description |
|--------|--------|-------------|
| `sandbox.acquire.total` | image, source | Total acquisitions (source: pool/cold_start) |
| `sandbox.create.total` | image, status | Creation attempts (status: success/failure) |
| `sandbox.scale.events` | image, direction | Scale events (direction: up/down) |
| `sandbox.health.removed` | image, reason | Sandboxes removed (reason: unhealthy/stale) |

#### Histograms

| Metric | Labels | Description |
|--------|--------|-------------|
| `sandbox.acquire.latency_ms` | image, source | Time to acquire sandbox |
| `sandbox.warm.age_s` | image | Age of sandbox when acquired from pool |

### 6.2 Metrics API

```python
# Programmatic access
metrics = manager.metrics()
# {
#   "my-image": PoolMetrics(
#       ready=5,
#       creating=1,
#       in_use=3,
#       total_acquires=1523,
#       pool_hit_rate=0.97,
#       avg_acquire_latency_ms=45.2,
#   )
# }
```

### 6.3 OpenTelemetry Integration Example

```python
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# Customer configures their exporter
exporter = OTLPMetricExporter(endpoint="https://otel-collector.example.com:4317")
reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60000)
provider = MeterProvider(metric_readers=[reader])
metrics.set_meter_provider(provider)

# SandboxManager automatically uses the configured provider
manager = SandboxManager(...)
```

---

## 7. Error Handling

### 7.1 Exceptions

```python
class PoolExhaustedError(SandboxError):
    """Raised when pool is empty and on_empty="fail"."""
    pass

class PoolShutdownError(SandboxError):
    """Raised when acquire() called after shutdown initiated."""
    pass

class WarmUpTimeoutError(SandboxError):
    """Raised when warm_up() times out before pools reach target."""
    pass
```

### 7.2 Failure Modes

| Scenario | Behavior |
|----------|----------|
| Pool empty, on_empty="create" | Falls back to cold-start (30s latency) |
| Pool empty, on_empty="fail" | Raises `PoolExhaustedError` immediately |
| Creation failure during replenishment | Retry with backoff, log error, continue |
| Rate limited (429) | Backoff and retry |
| Sandbox unhealthy in pool | Remove from pool, trigger replenishment |
| shutdown() called | Stop accepting acquires, drain pools |

---

## 8. Implementation Notes

### 8.1 Concurrency Model

- **asyncio-native**: Manager uses asyncio for all background tasks
- **Per-pool locks**: Avoid global lock contention at scale
- **asyncio.Queue**: Thread-safe pool storage
- **Semaphore**: Limit concurrent sandbox creations

### 8.2 Key Implementation Details

```python
class SandboxPool:
    def __init__(self, image: str, config: PoolConfig):
        self.image = image
        self.config = config
        self._ready_queue: asyncio.Queue[Sandbox] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._last_acquire_time: Optional[float] = None
        self._creating_count: int = 0

    async def acquire(self, timeout: Optional[float] = None) -> Optional[Sandbox]:
        """Get a sandbox from pool, or None if empty."""
        try:
            sandbox = self._ready_queue.get_nowait()
            self._last_acquire_time = time.time()
            return sandbox
        except asyncio.QueueEmpty:
            return None
```

### 8.3 Background Tasks

1. **Replenisher**: Runs per-pool, maintains `target_ready` count
2. **Idle Monitor**: Runs globally, checks all pools for idle timeout

**Note:** Health checks are performed lazily during `acquire()` rather than periodically. This avoids unnecessary API calls and race conditions where periodic health checks could temporarily drain the pool.

### 8.4 Graceful Shutdown Sequence

1. Stop accepting new `acquire()` calls
2. Cancel background replenisher tasks
3. Destroy all sandboxes in ready queues
4. Optionally wait for in-use sandboxes to be released
5. Cancel remaining background tasks

---

## 9. Testing Strategy

### 9.1 Unit Tests

- Pool state management (acquire, replenish, scale-down)
- Configuration validation
- Timeout handling
- Error scenarios (creation failure, health check failure)

### 9.2 Integration Tests

- End-to-end acquire from warm pool
- Fallback to cold-start when pool empty
- Scale-down after idle timeout
- Graceful shutdown

### 9.3 Load Tests

- Concurrent acquire from multiple coroutines
- Burst handling (100+ simultaneous acquires)
- Sustained throughput at scale

---

## 10. Future Considerations

### 10.1 Potential Enhancements (Not in V1)

1. **Predictive scaling**: Use historical patterns to pre-warm before demand spikes
2. **Multi-region pools**: Geo-distributed pools with affinity
3. **Priority queues**: Different SLAs for different callers
4. **Sandbox recycling**: Clean and reuse sandboxes (requires careful state isolation)
5. **Cost reporting**: Integration with billing APIs for cost visibility

### 10.2 Resolved Design Decisions

1. **Idle timeout default**: 60 seconds before scale-down begins
2. **Max concurrent creates**: 10 parallel sandbox creations allowed
3. **Health check implementation**: Use simple `sandbox.is_ready()` - lightweight and sufficient

---

## 11. Appendix

### A. Comparison with Existing Patterns

| Pattern | Similarity | Difference |
|---------|------------|------------|
| Connection Pool (DB) | Pre-warm resources, acquire/release | Sandboxes are single-use, not returned |
| Thread Pool | Fixed workers, task queue | Sandbox is the unit of work, not thread |
| K8s HPA | Adaptive scaling based on metrics | We scale pool, not pods directly |
| Serverless warm pool | Pre-warmed instances | Our instances are customer-controlled images |

### B. Related SDK Code

- `Sandbox.create()`: `do_sandbox/sandbox.py:235-344`
- `Sandbox.wait_ready()`: `do_sandbox/sandbox.py:543-579`
- `Sandbox.is_ready()`: `do_sandbox/sandbox.py:535-541`
- `AsyncSandbox`: `do_sandbox/async_sandbox.py`
- `Deployer.wait_ready()`: `do_sandbox/deployer.py:318-360`
