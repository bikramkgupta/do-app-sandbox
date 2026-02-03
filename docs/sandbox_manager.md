# SandboxManager: Pre-Warmed Sandbox Pools

The `SandboxManager` eliminates the ~30 second cold-start latency by maintaining pools of pre-warmed, ready-to-use sandboxes.

**Best for:** Companies running hundreds or thousands of agents where instant sandbox availability is critical.

## Quick Start

```python
from do_app_sandbox import SandboxManager, PoolConfig

async def main():
    # Configure pools for your images
    manager = SandboxManager(
        pools={
            "python": PoolConfig(target_ready=3),  # Keep 3 Python sandboxes warm
            "node": PoolConfig(target_ready=2),    # Keep 2 Node sandboxes warm
        },
    )

    await manager.start()

    # Instant acquisition - no 30s wait!
    sandbox = await manager.acquire(image="python")

    result = sandbox.exec("python --version")
    print(result.stdout)

    # Sandboxes are single-use - delete when done
    sandbox.delete()

    await manager.shutdown()
```

## Context Manager Usage

```python
async with SandboxManager(pools={"python": PoolConfig(target_ready=3)}) as manager:
    sandbox = await manager.acquire(image="python")
    result = sandbox.exec("echo 'Hello from pool!'")
    sandbox.delete()
```

## Configuration

### PoolConfig Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_ready` | 10 | Maximum sandboxes to keep warming in pool |
| `target_ready` | 0 | **Minimum sandboxes to always maintain** (prevents oscillation) |
| `idle_timeout` | 60 | Seconds of no acquires before pool becomes idle |
| `scale_down_delay` | 60 | Seconds between destructions during scale-down |
| `cooldown_after_acquire` | 120 | Seconds to pause scale-down after an acquire |
| `max_warm_age` | 1800 | Max seconds a sandbox can warm before cycling out |
| `on_empty` | `"create"` | Behavior when empty: `"create"` (fallback) or `"fail"` (fast-fail) |
| `create_retries` | 3 | Retry attempts for failed sandbox creation |
| `create_retry_delay` | 5 | Seconds between creation retries |

**Note:** `target_ready` is the minimum pool size that's always maintained. The pool will never scale below this value.

### SandboxManager Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pools` | `{}` | Per-image pool configurations |
| `default_pool_config` | `PoolConfig()` | Config for images without explicit config |
| `max_total_sandboxes` | `None` | Global limit across all pools (cost ceiling) |
| `max_concurrent_creates` | 10 | Max parallel sandbox creations (API rate limit) |
| `sandbox_defaults` | `{}` | Default kwargs passed to `Sandbox.create()` |

## Adaptive Scaling

The pool maintains `target_ready` sandboxes at all times, preventing the create/delete oscillation that occurs when pools scale to zero.

**Scale-down behavior:**
1. No acquires for `cooldown_after_acquire` seconds → start scaling down
2. Destroy 1 sandbox every `scale_down_delay` seconds
3. **Stop at `target_ready`** - never scale below this value
4. After any acquire, pause scale-down for `cooldown_after_acquire` seconds

**Example:** Set `target_ready` to your desired pool size:

```python
PoolConfig(
    target_ready=5,  # Always keep 5 sandboxes ready
    max_ready=20,    # But never exceed 20
)
```

## Fallback vs Fail-Fast

```python
# Fallback (default): If pool is empty, create on-demand (30s latency)
PoolConfig(on_empty="create")

# Fail-fast: If pool is empty, raise PoolExhaustedError immediately
PoolConfig(on_empty="fail")
```

## Warm-Up Before Production Traffic

```python
manager = SandboxManager(
    pools={"python": PoolConfig(target_ready=5)},
)
await manager.start()

# Block until all pools reach target_ready
await manager.warm_up(timeout=120)

# Now safe to serve traffic with guaranteed low latency
app.state.sandbox_manager = manager
```

## Monitoring with Metrics

```python
# Programmatic access
metrics = manager.metrics()
print(metrics["python"].ready)           # Current warm sandboxes
print(metrics["python"].pool_hit_rate)   # Ratio of instant acquisitions
print(metrics["python"].avg_acquire_latency_ms)
```

### OpenTelemetry Integration

The manager emits OpenTelemetry metrics if the SDK is available:

| Metric | Type | Description |
|--------|------|-------------|
| `sandbox.pool.ready` | Gauge | Ready sandboxes per image |
| `sandbox.pool.creating` | Gauge | Sandboxes being created |
| `sandbox.acquire.total` | Counter | Total acquisitions |
| `sandbox.acquire.latency_ms` | Histogram | Acquisition latency |
| `sandbox.scale.events` | Counter | Scale up/down events |

Configure your exporter as usual:

```python
from opentelemetry.exporter.otlp.proto.grpc import OTLPMetricExporter

exporter = OTLPMetricExporter(endpoint="https://otel.example.com:4317")
# ... standard OTel setup
```

## Health Monitoring

Sandbox health is checked lazily during `acquire()`:

- **On-acquire check**: Each sandbox is verified with `is_ready()` when acquired
- **Age limit**: Sandboxes older than `max_warm_age` are rejected and destroyed
- **Automatic skip**: Unhealthy sandboxes are destroyed and the next one is tried
- **No periodic overhead**: Avoids unnecessary API calls and race conditions

## Error Handling

```python
from do_app_sandbox import PoolExhaustedError, PoolShutdownError, WarmUpTimeoutError

try:
    sandbox = await manager.acquire(image="python")
except PoolExhaustedError:
    # Pool empty and on_empty="fail"
    pass
except PoolShutdownError:
    # Manager is shutting down
    pass

try:
    await manager.warm_up(timeout=60)
except WarmUpTimeoutError:
    # Pools didn't reach target in time
    pass
```

## Example: High-Throughput Agent System

```python
from do_app_sandbox import SandboxManager, PoolConfig

async def run_agent_system():
    manager = SandboxManager(
        pools={
            "python": PoolConfig(
                target_ready=10,       # Keep 10 warm for burst handling
                max_ready=50,          # Never exceed 50 (cost ceiling)
                idle_timeout=60,       # Scale down after 1 min idle
                on_empty="create",     # Fall back to cold start if needed
            ),
        },
        max_total_sandboxes=100,       # Global limit across all images
        max_concurrent_creates=10,     # Don't overwhelm the API
        sandbox_defaults={
            "region": "nyc",
            "instance_size": "apps-s-1vcpu-2gb",
        },
    )

    await manager.start()
    await manager.warm_up(timeout=300)  # Wait for initial pool fill

    # Handle agent requests
    async def handle_agent_task(task):
        sandbox = await manager.acquire(image="python")
        try:
            result = sandbox.exec(f"python /app/run_task.py {task.id}")
            return result
        finally:
            sandbox.delete()  # Single-use: always delete

    # ... run your agent system ...

    await manager.shutdown()
```

## Design Document

For detailed architecture and design decisions, see [docs/design_sandbox_manager.md](design_sandbox_manager.md).
