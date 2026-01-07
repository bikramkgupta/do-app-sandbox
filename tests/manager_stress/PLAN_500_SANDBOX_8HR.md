# 500-Sandbox 8-Hour Comprehensive Stress Test Plan

> **Purpose**: Identify corner cases, failure modes, and operational limits through sustained high-scale testing
> **Scale**: 500 concurrent sandboxes (250 Python + 250 Node)
> **Duration**: 8 hours continuous operation
> **Philosophy**: Think like Anthropic - systematic, thorough, production-hardened

---

## Executive Summary

This plan defines a comprehensive 8-hour stress test at 10x the current maximum scale (50 → 500 sandboxes). The goal is not just to validate functionality but to **discover unknown unknowns** - corner cases that only emerge under sustained high load.

### Key Objectives

1. **Validate Scale Limits**: Can SandboxManager reliably manage 500 concurrent sandboxes?
2. **Identify Memory/Resource Leaks**: 8-hour duration reveals slow leaks
3. **Stress Concurrency**: Race conditions, deadlocks, lock contention
4. **Test Recovery**: How does the system behave after failures?
5. **Measure Degradation**: Does performance degrade over time?
6. **Find API Limits**: DigitalOcean API rate limiting at scale

---

## Corner Case Categories

### Category 1: Resource Exhaustion (Long Duration)

| Corner Case | How It Manifests | Detection Method |
|-------------|------------------|------------------|
| **Memory Leak** | RSS grows unbounded over 8h | Monitor process memory every 60s |
| **File Descriptor Leak** | "Too many open files" | Track `/proc/self/fd` count |
| **Connection Pool Exhaustion** | HTTP requests hang | Monitor asyncio task count |
| **Event Loop Blocking** | Latency spikes | Track event loop lag time |
| **Queue Unbounded Growth** | OOM or slowdown | Monitor `_ready_queue.qsize()` |
| **Latency List Unbounded** | Memory pressure | Check `_acquire_latencies` size |

**Test Programs for Memory Stress:**
```
python/compute/memory_allocator.py    # Allocate/free patterns
python/mixed/gc_pressure.py           # Force GC cycles
node/compute/buffer_churn.js          # Buffer alloc/dealloc
```

### Category 2: Concurrency Bugs

| Corner Case | Scenario | Expected Behavior |
|-------------|----------|-------------------|
| **Race on Acquire** | 50 users acquire same image simultaneously | All get valid sandboxes |
| **Race on Scale-Down** | Scale-down during acquisition burst | No sandbox destroyed mid-acquire |
| **Lock Contention** | 100+ concurrent operations | No deadlocks, <100ms lock wait |
| **Health Check During Drain** | Health check runs while pool draining | No exceptions, clean state |
| **Concurrent Pool Creation** | First acquire for 50 new images | One pool per image, no duplicates |
| **Shutdown During Acquire** | Call shutdown() mid-acquire | PoolShutdownError, clean exit |

**Test Pattern:**
- Burst scenario with 100 users hitting same image simultaneously
- Mixed patterns with random image selection

### Category 3: Timing Edge Cases

| Corner Case | Trigger | Expected Behavior |
|-------------|---------|-------------------|
| **Sandbox Expires During Acquire** | Sandbox at max_warm_age during `_try_acquire_from_pool` | Gracefully skip, get next or cold-start |
| **Health Check Finds All Unhealthy** | Network blip makes all sandboxes appear unhealthy | Replenishment kicks in, no panic |
| **Creation Timeout Cascade** | API slow, all creates timeout | Retry logic prevents total failure |
| **Scale-Down Race** | Acquire at exact moment of scale-down | Acquire wins, scale-down deferred |
| **Cooldown Boundary** | Acquire exactly at cooldown_after_acquire | Correct cooldown reset |
| **Max Age Boundary** | Sandbox acquired at max_warm_age - 1 | Should still be valid |

**Test Configuration:**
```python
# Aggressive timing to trigger edge cases
max_warm_age=300,           # 5 min instead of 30 min
health_check_interval=15,   # Every 15s instead of 60s
idle_timeout=60,            # Quick idle detection
scale_down_delay=10,        # Fast scale-down
```

### Category 4: Failure Modes

| Failure Mode | Injection Method | Expected Recovery |
|--------------|------------------|-------------------|
| **API Rate Limiting** | 500 concurrent creates | Semaphore limits to 10-15, retries succeed |
| **Partial Pool Failure** | 10% of creates fail | Retry logic fills pool, metrics accurate |
| **Cascade Failure** | API returns 500s for 5 minutes | Pool drains, recovers when API returns |
| **Stale Sandbox** | Sandbox deleted externally | Health check removes, pool replenishes |
| **Network Partition** | Sandbox can't reach is_ready() | Health check removes within interval |

**Chaos Engineering Patterns:**
- Periodically inject failures into mock API
- Test with `on_empty="fail"` to see PoolExhaustedError handling

### Category 5: State Consistency

| Invariant | Verification |
|-----------|--------------|
| `ready_count + creating_count + in_use == total` | Periodic assertion |
| `metrics.total_acquires == sum(task results)` | End-of-test validation |
| `pool_hit_rate = acquires_from_pool / total_acquires` | Mathematical check |
| No orphaned sandboxes after shutdown | Count API sandboxes vs expected |
| Metrics monotonically increasing (counters) | Track counter decreases as error |

### Category 6: Scale Limits

| Limit | Current Value | Test Target | Risk |
|-------|---------------|-------------|------|
| **max_concurrent_creates** | 10 | Test with 15, 20, 25 | API rate limiting |
| **max_total_sandboxes** | 50 | 500 | Cost, API limits |
| **target_ready per pool** | 5 | 100 | Pre-warm time, cost |
| **Queue size** | unbounded | Test with 500+ items | Memory |
| **Concurrent users** | 50 | 200 | Event loop saturation |

---

## Test Phases

### Phase 1: Warm-Up (0-30 min)

**Objective**: Bring pool to full capacity, establish baseline

```yaml
phase: warm_up
duration: 30 min
users: 50 (25P, 25N)
pattern: steady
target_ready:
  python: 100
  node: 100
max_sandboxes:
  python: 250
  node: 250
```

**Metrics to Capture:**
- Time to reach target_ready
- Creation success rate
- API rate limit errors
- Memory baseline

### Phase 2: Sustained Load (30 min - 4 hr)

**Objective**: Steady-state operation, reveal slow leaks

```yaml
phase: sustained_load
duration: 3.5 hours
users: 150 (75P, 75N)
patterns:
  - steady: 100 users (50P, 50N)
  - random: 30 users (15P, 15N)
  - peak_hours: 20 users (10P, 10N)
task_duration: 120-1800s (2-30 min)
```

**Corner Cases Tested:**
- Pool cycling (max_warm_age)
- Health check removals
- Memory stability
- Latency consistency

### Phase 3: Burst Stress (4 hr - 5.5 hr)

**Objective**: Extreme concurrency, pool exhaustion

```yaml
phase: burst_stress
duration: 1.5 hours
users: 200 (100P, 100N)
patterns:
  - burst: 150 users (75P, 75N)
  - steady: 50 users (25P, 25N)
task_duration: 30-300s (short tasks = high churn)
```

**Corner Cases Tested:**
- Pool exhaustion → cold start fallback
- Concurrent acquisition race conditions
- Lock contention under load
- Scale-up during burst

### Phase 4: Chaos (5.5 hr - 6.5 hr)

**Objective**: Failure injection, recovery testing

```yaml
phase: chaos
duration: 1 hour
users: 150
inject_failures: true
failure_rate: 10%  # 10% of sandbox operations fail
patterns: mixed
```

**Injected Failures:**
- Random sandbox creation failures
- Simulated API timeouts (5s delay)
- Forced health check failures
- Shutdown/restart cycles (2 times)

### Phase 5: Idle & Recovery (6.5 hr - 7.5 hr)

**Objective**: Test scale-down, verify no resource leaks

```yaml
phase: idle_recovery
duration: 1 hour
sub_phases:
  - idle_period: 15 min (0 users)
  - recovery_burst: 15 min (100 users, burst)
  - idle_period: 15 min (0 users)
  - final_burst: 15 min (50 users, steady)
```

**Corner Cases Tested:**
- Full scale-down to 0
- Scale-up from cold
- Memory after idle (should be lower)
- File descriptors release

### Phase 6: Drain & Shutdown (7.5 hr - 8 hr)

**Objective**: Clean shutdown, resource cleanup

```yaml
phase: shutdown
duration: 30 min
users: 20 (wind down)
final: graceful_shutdown
```

**Verifications:**
- All pooled sandboxes destroyed
- No orphaned sandboxes on DO account
- Memory returned to baseline
- File descriptors at baseline
- Metrics consistency check

---

## New Test Scenarios

### Scenario: `mega_stress_8hr`

```python
def get_mega_stress_8hr() -> ScenarioConfig:
    """8-hour mega stress test with 500 sandboxes."""
    return ScenarioConfig(
        name="mega_stress_8hr",
        description="8-hour stress test - 200 users, 500 sandbox pool, comprehensive corner case testing",
        duration_seconds=28800,  # 8 hours
        user_groups=[
            # === SUSTAINED LOAD USERS (100 users) ===
            UserGroupConfig(
                name="python_sustained_heavy",
                count=20,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(600, 1800),  # 10-30 min
                categories=["compute", "mixed"],
            ),
            UserGroupConfig(
                name="python_sustained_medium",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 900),  # 5-15 min
                categories=["io", "network", "mixed"],
            ),
            UserGroupConfig(
                name="python_sustained_light",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.RANDOM,
                task_duration_range=(60, 300),  # 1-5 min
                categories=["compute", "io", "idle"],
            ),
            UserGroupConfig(
                name="node_sustained_heavy",
                count=20,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(600, 1800),
                categories=["compute", "mixed"],
            ),
            UserGroupConfig(
                name="node_sustained_medium",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 900),
                categories=["async", "io", "mixed"],
            ),
            UserGroupConfig(
                name="node_sustained_light",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.RANDOM,
                task_duration_range=(60, 300),
                categories=["compute", "io", "idle"],
            ),

            # === BURST USERS (60 users) ===
            UserGroupConfig(
                name="python_burst_fast",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(30, 180),  # 30s-3 min (high churn)
                categories=["compute", "io"],
            ),
            UserGroupConfig(
                name="python_burst_medium",
                count=15,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),  # 2-10 min
                categories=["mixed", "network"],
            ),
            UserGroupConfig(
                name="node_burst_fast",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(30, 180),
                categories=["async", "io"],
            ),
            UserGroupConfig(
                name="node_burst_medium",
                count=15,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),
                categories=["mixed", "compute"],
            ),

            # === PEAK HOURS USERS (40 users) ===
            UserGroupConfig(
                name="python_peak",
                count=20,
                image=ImageType.PYTHON,
                pattern=LoadPattern.PEAK_HOURS,
                task_duration_range=(180, 900),  # 3-15 min
                categories=["compute", "io", "mixed", "idle"],
            ),
            UserGroupConfig(
                name="node_peak",
                count=20,
                image=ImageType.NODE,
                pattern=LoadPattern.PEAK_HOURS,
                task_duration_range=(180, 900),
                categories=["compute", "async", "mixed", "idle"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=50, max_sandboxes=250),
            node_pool=PoolConfig(ImageType.NODE, target_ready=50, max_sandboxes=250),
            max_total_sandboxes=500,
            max_concurrent_creates=15,  # Slightly higher for scale
            idle_timeout=180,           # 3 min before scale-down (longer for stability)
            scale_down_delay=30,        # 30s between destructions
            cooldown_after_acquire=300, # 5 min cooldown
            max_warm_age=1200,          # 20 min max age (more cycling)
        ),
        idle_periods=[
            # Regular idle periods to test scale-down
            (7200, 900),    # 15 min idle at 2 hr mark
            (14400, 900),   # 15 min idle at 4 hr mark
            (21600, 900),   # 15 min idle at 6 hr mark
            (25200, 1800),  # 30 min idle at 7 hr mark (wind-down)
        ],
    )
```

### Scenario: `corner_case_blitz`

```python
def get_corner_case_blitz() -> ScenarioConfig:
    """Aggressive corner case testing with rapid timing."""
    return ScenarioConfig(
        name="corner_case_blitz",
        description="2-hour aggressive corner case testing with tight timing parameters",
        duration_seconds=7200,  # 2 hours
        user_groups=[
            # High-frequency short tasks (maximize pool churn)
            UserGroupConfig(
                name="python_rapid",
                count=30,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(15, 60),  # 15s-1min
                categories=["compute", "io"],
            ),
            UserGroupConfig(
                name="node_rapid",
                count=30,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(15, 60),
                categories=["async", "io"],
            ),
            # Long-running to test max_warm_age expiry
            UserGroupConfig(
                name="python_long",
                count=10,
                image=ImageType.PYTHON,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 400),  # ~5-6 min (around max_warm_age)
                categories=["mixed", "idle"],
            ),
            UserGroupConfig(
                name="node_long",
                count=10,
                image=ImageType.NODE,
                pattern=LoadPattern.STEADY,
                task_duration_range=(300, 400),
                categories=["mixed", "idle"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=10, max_sandboxes=50),
            node_pool=PoolConfig(ImageType.NODE, target_ready=10, max_sandboxes=50),
            max_total_sandboxes=100,
            max_concurrent_creates=10,
            idle_timeout=30,            # 30s (aggressive)
            scale_down_delay=5,         # 5s (very aggressive)
            cooldown_after_acquire=60,  # 1 min
            max_warm_age=300,           # 5 min (trigger cycling)
            health_check_interval=10,   # 10s (very frequent)
        ),
        idle_periods=[
            (1800, 300),   # 5 min idle at 30 min
            (3600, 300),   # 5 min idle at 60 min
            (5400, 300),   # 5 min idle at 90 min
        ],
    )
```

### Scenario: `scale_boundary`

```python
def get_scale_boundary() -> ScenarioConfig:
    """Test scale boundaries and limits."""
    return ScenarioConfig(
        name="scale_boundary",
        description="4-hour test pushing scale boundaries",
        duration_seconds=14400,  # 4 hours
        user_groups=[
            # All users burst at start to test max creation
            UserGroupConfig(
                name="python_all",
                count=75,
                image=ImageType.PYTHON,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),
                categories=["compute", "io", "mixed"],
            ),
            UserGroupConfig(
                name="node_all",
                count=75,
                image=ImageType.NODE,
                pattern=LoadPattern.BURST,
                task_duration_range=(120, 600),
                categories=["compute", "async", "mixed"],
            ),
        ],
        test_config=TestConfig(
            python_pool=PoolConfig(ImageType.PYTHON, target_ready=75, max_sandboxes=150),
            node_pool=PoolConfig(ImageType.NODE, target_ready=75, max_sandboxes=150),
            max_total_sandboxes=300,
            max_concurrent_creates=20,  # Test higher concurrency
        ),
        idle_periods=[
            (3600, 1200),   # 20 min idle at 1 hr (full scale-down test)
            (7200, 1200),   # 20 min idle at 2 hr
            (10800, 1200),  # 20 min idle at 3 hr
        ],
    )
```

---

## Metrics Collection

### System Metrics (Every 30s)

```python
@dataclass
class SystemSnapshot:
    timestamp: float
    process_rss_mb: float           # Memory usage
    process_fd_count: int           # File descriptors
    asyncio_task_count: int         # Active tasks
    event_loop_lag_ms: float        # Event loop responsiveness
    gc_collections: Dict[int, int]  # GC stats per generation
```

### Pool Metrics (Every 10s)

```python
@dataclass
class PoolSnapshot:
    timestamp: float
    image: str
    ready: int
    creating: int
    in_use: int
    total_acquires: int
    pool_hits: int
    cold_starts: int
    avg_latency_ms: float
    scale_up_events: int
    scale_down_events: int
    failed_creates: int
    health_removals: int
```

### Invariant Checks (Every 60s)

```python
def check_invariants(manager: SandboxManager) -> List[str]:
    violations = []

    for image, pool in manager._pools.items():
        metrics = pool.get_metrics()

        # Ready + Creating should never exceed max
        if metrics.ready + metrics.creating > pool.config.max_ready:
            violations.append(f"{image}: ready+creating ({metrics.ready + metrics.creating}) > max_ready ({pool.config.max_ready})")

        # Counters should be monotonic
        # (check against previous snapshot)

        # Pool hit rate should be valid
        if metrics.pool_hit_rate < 0 or metrics.pool_hit_rate > 1:
            violations.append(f"{image}: invalid pool_hit_rate {metrics.pool_hit_rate}")

    return violations
```

---

## Success Criteria

### Hard Requirements (Must Pass)

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| **Uptime** | 100% | No crashes during 8 hours |
| **Task Success Rate** | ≥ 98% | Completed tasks / Total tasks |
| **No Memory Leak** | RSS growth < 20% over 8hr | Start vs End memory |
| **No FD Leak** | FD count returns to baseline | During idle periods |
| **Pool Consistency** | 0 invariant violations | Continuous checks |
| **Clean Shutdown** | All sandboxes destroyed | API count after shutdown |

### Soft Targets (Should Achieve)

| Criterion | Target | Acceptable |
|-----------|--------|------------|
| **Pool Hit Rate** | ≥ 70% | ≥ 50% |
| **Avg Pool Hit Latency** | < 500ms | < 1000ms |
| **Avg Cold Start Latency** | < 90s | < 120s |
| **P99 Latency** | < 120s | < 180s |
| **Scale-Up Time** | < 5 min to target | < 10 min |
| **Scale-Down Completeness** | 100% to 0 in idle | 90% in idle |

### Performance Regression Detection

Compare against baseline (quick_validation results):
- Pool hit latency should not degrade > 2x
- Creation time should not degrade > 1.5x
- No new error categories

---

## Operational Considerations

### Cost Estimate

```
500 sandboxes × $0.03/hour × 8 hours = $120 per run
Buffer for churn (2x creation) = $240 total
```

### Monitoring During Test

1. **Real-time Dashboard**
   - Pool sizes (ready, creating, in_use)
   - Latency histograms
   - Error rates
   - Memory usage

2. **Alerts**
   - Memory > 2GB
   - Error rate > 5%
   - Pool empty for > 5 min
   - Event loop lag > 1s

3. **Checkpoints**
   - Save state every hour
   - Export metrics CSV every 30 min
   - Screenshot dashboard at each phase

### Failure Recovery

If test fails mid-run:
1. Capture all metrics/logs up to failure
2. Trigger emergency shutdown
3. Wait 5 min for cleanup
4. Verify no orphaned sandboxes
5. Analyze root cause before retry

---

## Implementation Checklist

### Pre-Test

- [ ] Update `config.py` with new scenarios
- [ ] Add system metrics collection (RSS, FD, tasks)
- [ ] Add invariant checking to orchestrator
- [ ] Verify DO API token has sufficient permissions
- [ ] Estimate cost and get approval
- [ ] Set up monitoring dashboard
- [ ] Reserve 8+ hour block for test

### During Test

- [ ] Monitor real-time dashboard
- [ ] Check metrics export every 30 min
- [ ] Note any anomalies in log
- [ ] Be prepared for emergency shutdown

### Post-Test

- [ ] Generate comprehensive HTML report
- [ ] Analyze memory graphs for leaks
- [ ] Review all invariant violations
- [ ] Verify sandbox cleanup
- [ ] Document findings
- [ ] File issues for any bugs found

---

## Running the Test

### Full 8-Hour Test

```bash
# Recommended: Run in tmux or screen for persistence
tmux new -s stress_test

# Full 8-hour mega stress test
uv run python -m tests.manager_stress \
    --scenario mega_stress_8hr \
    --output-dir ./results/mega_stress_$(date +%Y%m%d) \
    -v

# In another pane: Monitor resources
watch -n 30 'ps -o rss,vsz,nlwp -p $(pgrep -f manager_stress)'
```

### Corner Case Blitz (2 hours)

```bash
# Quicker corner case test
uv run python -m tests.manager_stress \
    --scenario corner_case_blitz \
    -v
```

### Dry Run Validation

```bash
# Validate configuration without real sandboxes
uv run python -m tests.manager_stress \
    --scenario mega_stress_8hr \
    --dry-run \
    -v
```

---

## Expected Findings

Based on implementation analysis, likely corner cases to discover:

1. **`_acquire_latencies` unbounded growth** - List grows forever, should cap
2. **Lock contention at 500 scale** - May need per-pool locks optimization
3. **API rate limiting at max_concurrent_creates=15** - DO may throttle
4. **Health check storm** - 500 sandboxes × 60s checks = significant load
5. **Scale-down cascade** - Aggressive settings may cause thrashing
6. **Memory growth from metrics** - PoolMetrics objects accumulate

---

## Appendix: Quick Reference

### Scenario Summary

| Scenario | Duration | Users | Sandboxes | Focus |
|----------|----------|-------|-----------|-------|
| `mega_stress_8hr` | 8 hr | 200 | 500 | Full scale, all corner cases |
| `corner_case_blitz` | 2 hr | 80 | 100 | Aggressive timing |
| `scale_boundary` | 4 hr | 150 | 300 | Max limits |
| `full_stress` | 2h10m | 50 | 50 | Existing baseline |

### Key Parameters for Corner Cases

```python
# Tight timing (reveals race conditions)
max_warm_age=300
health_check_interval=10
scale_down_delay=5

# High scale (reveals resource limits)
max_total_sandboxes=500
max_concurrent_creates=15
target_ready=50

# Long duration (reveals leaks)
duration_seconds=28800
```

---

*Document Version: 1.0*
*Created: 2026-01-06*
*Author: Claude (for Anthropic-level testing rigor)*
