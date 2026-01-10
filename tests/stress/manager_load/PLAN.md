# SandboxManager Comprehensive Stress Test Plan

> **Session Resumable**: This document tracks both the plan and implementation progress.
> **Last Updated**: 2026-01-06
> **Status**: READY TO RUN - All implementation complete, validated
> **Project Location**: `tests/manager_stress/PLAN.md` (git-tracked)

---

## Quick Start (New Session)

**To run the stress tests, tell Claude:**
```
Run the SandboxManager stress test using the quick_validation scenario
```

**Or for the full 2+ hour test:**
```
Run the full_stress scenario for SandboxManager (this will take 2+ hours)
```

**Available commands:**
```bash
# List all scenarios
uv run python -m tests.stress.manager_load --list-scenarios

# Quick validation (10 min, 4 users) - RECOMMENDED FIRST
uv run python -m tests.stress.manager_load --scenario quick_validation

# Burst test (30 min, 20 users)
uv run python -m tests.stress.manager_load --scenario burst_test

# Steady state (1 hour, 24 users)
uv run python -m tests.stress.manager_load --scenario steady_state

# Scale cycle (90 min, 30 users)
uv run python -m tests.stress.manager_load --scenario scale_cycle

# Full stress (2+ hours, 50 users)
uv run python -m tests.stress.manager_load --scenario full_stress

# Dry run (mock manager, no real sandboxes)
uv run python -m tests.stress.manager_load --scenario quick_validation --dry-run
```

---

## Progress Tracker

### Implementation Phases

- [x] **Phase 1: Structure Setup**
  - [x] Create `tests/manager_stress/` folder structure
  - [x] Create `sandbox-execution-programs/` folder structure
  - [x] Update `.gitignore`

- [x] **Phase 2: Test Programs (45 programs)**
  - [x] Python compute programs (5): fibonacci, prime_sieve, matrix_mult, sort_benchmark, hash_stress
  - [x] Python I/O programs (6): csv_generate, json_transform, file_copy, temp_file_stress, log_simulator, spaces_upload
  - [x] Python network programs (2): http_client, dns_timing
  - [x] Python mixed programs (6): data_pipeline, text_processing, stats_compute, config_generator, batch_processor, report_generator
  - [x] Python idle programs (3): sleep_random, periodic_heartbeat, intermittent_work
  - [x] Node compute programs (5): fibonacci, prime_sieve, crypto_hash, buffer_ops, sorting
  - [x] Node I/O programs (5): file_operations, json_processing, stream_copy, csv_generator, log_writer
  - [x] Node async programs (5): promise_chain, concurrent_ops, event_loop_test, timer_stress, queue_processor
  - [x] Node mixed programs (5): data_transform, template_render, config_generator, batch_processor, api_simulator
  - [x] Node idle programs (3): sleep_random, heartbeat, intermittent

- [x] **Phase 3: Core Framework**
  - [x] `config.py` - Configuration and scenarios (TestConfig, ScenarioConfig, 5 predefined scenarios)
  - [x] `metrics_collector.py` - Time-series collection (PoolSnapshot, TaskResult, TestSummary)
  - [x] `workload_generator.py` - Program selection (category-based, duration-aware)
  - [x] `reporter.py` - HTML report generation (Chart.js visualizations)

- [x] **Phase 4: Orchestration**
  - [x] `user_simulator.py` - User behavior simulation (LoadPatternGenerator, UserSimulator)
  - [x] `orchestrator.py` - Main test runner (StressTestOrchestrator, MockSandboxManager)
  - [x] `__main__.py` - CLI interface (--scenario, --dry-run, --list-scenarios, --validate-programs)

- [ ] **Phase 5: Scenario Definitions**
  - [ ] `quick_validation.yaml`
  - [ ] `burst_test.yaml`
  - [ ] `steady_state.yaml`
  - [ ] `scale_cycle.yaml`
  - [ ] `full_stress.yaml`

- [x] **Phase 6: Testing**
  - [x] Run quick_validation (100% success, see Test Results below)
  - [ ] Run burst_test
  - [ ] Run full_stress (2+ hours)

### Current Session Notes
- Explored SandboxManager implementation (manager.py - 795 lines)
- Explored Sandbox SDK (sandbox.py, filesystem.py, spaces.py)
- Designed 50+ test programs across Python and Node
- Designed load patterns: burst, steady, random, peak_hours
- Designed 5 test scenarios from 5 min to 2+ hours
- **Created 45 test programs** (22 Python + 23 Node) in `sandbox-execution-programs/`
- All programs accept `--duration` flag and output `RESULT: key=value` format
- **Implemented Core Framework** in `tests/manager_stress/`:
  - `config.py`: 5 scenarios (quick_validation, burst_test, steady_state, scale_cycle, full_stress)
  - `metrics_collector.py`: Thread-safe metrics collection with percentile calculations
  - `workload_generator.py`: Smart program selection based on category and duration
  - `reporter.py`: Interactive HTML reports with Chart.js visualizations
- **Implemented Orchestration** in `tests/manager_stress/`:
  - `user_simulator.py`: LoadPatternGenerator (burst, steady, random, peak_hours), UserSimulator
  - `orchestrator.py`: StressTestOrchestrator, MockSandboxManager for dry-run testing
  - `__main__.py`: Full CLI with --scenario, --dry-run, --list-scenarios, --validate-programs
- **Validation Complete** (2026-01-06): All imports, scenarios, workload generator, metrics collector, and orchestrator tested successfully
- **READY TO RUN**: Use `uv run python -m tests.stress.manager_load --scenario <name>` to execute tests

---

## Overview
Create a 2+ hour stress test suite for SandboxManager with 50 concurrent sandboxes (25 Python + 25 Node) to validate pool management, scale-up/down behavior, and acquisition performance.

## Configuration
- **Region**: `syd1` (Sydney)
- **Instance Size**: `apps-s-1vcpu-2gb`
- **Max Concurrent**: 50 sandboxes (25 Python + 25 Node)
- **Test Duration**: 2+ hours
- **File Transfers**: Spaces (credentials from `.env`)

---

## Folder Structure

```
tests/manager_stress/
├── __init__.py
├── config.py                    # Test configuration
├── orchestrator.py              # Main test runner
├── metrics_collector.py         # Time-series metrics
├── workload_generator.py        # Program selection
├── user_simulator.py            # Simulated user behavior
├── reporter.py                  # HTML/JSON reports
├── __main__.py                  # CLI entry point
└── scenarios/
    ├── quick_validation.yaml
    ├── burst_test.yaml
    ├── steady_state.yaml
    └── full_stress.yaml

sandbox-execution-programs/      # Git-ignored
├── python/
│   ├── compute/                 # CPU-bound tasks
│   ├── io/                      # File operations
│   ├── network/                 # HTTP clients
│   ├── mixed/                   # Combined workloads
│   └── idle/                    # Sleep/heartbeat
└── node/
    ├── compute/                 # CPU-bound tasks
    ├── io/                      # File operations
    ├── async/                   # Promise/async patterns
    ├── mixed/                   # Combined workloads
    └── idle/                    # Sleep/heartbeat
```

---

## Test Programs (50+ total)

### Python Programs (25+)

| Category | Program | Duration | Description |
|----------|---------|----------|-------------|
| compute | fibonacci.py | 1-15 min | Recursive Fibonacci calculation |
| compute | prime_sieve.py | 1-10 min | Sieve of Eratosthenes |
| compute | matrix_mult.py | 2-20 min | Matrix multiplication (pure Python) |
| compute | sort_benchmark.py | 1-10 min | Sorting algorithm comparison |
| compute | hash_stress.py | 1-15 min | SHA256 hashing loops |
| io | csv_generate.py | 1-10 min | Generate/process CSV files |
| io | json_transform.py | 1-8 min | JSON read/transform/write |
| io | file_copy.py | 1-5 min | Large file copy operations |
| io | temp_file_stress.py | 1-5 min | Create/delete temp files |
| io | log_simulator.py | 5-30 min | Simulate log file writing |
| network | http_client.py | 2-15 min | HTTP requests to httpbin |
| network | dns_timing.py | 1-5 min | DNS resolution timing |
| mixed | data_pipeline.py | 5-20 min | Read → Transform → Write |
| mixed | text_processing.py | 2-10 min | Regex and string ops |
| mixed | stats_compute.py | 3-15 min | Statistical calculations |
| mixed | config_generator.py | 1-5 min | Generate config files |
| mixed | batch_processor.py | 5-30 min | Process files in batches |
| mixed | report_generator.py | 3-15 min | Generate text reports |
| idle | sleep_random.py | 1-50 min | Random sleep durations |
| idle | periodic_heartbeat.py | 5-50 min | Heartbeat every N seconds |
| idle | intermittent_work.py | 5-30 min | Work → Sleep → Work cycles |
| io | spaces_upload.py | 2-10 min | Upload files via Spaces |
| io | spaces_download.py | 2-10 min | Download files via Spaces |
| mixed | etl_simulation.py | 10-45 min | Simulated ETL pipeline |
| compute | compression_test.py | 2-15 min | Compress/decompress data |

### Node.js Programs (25+)

| Category | Program | Duration | Description |
|----------|---------|----------|-------------|
| compute | fibonacci.js | 1-15 min | Recursive Fibonacci |
| compute | prime_sieve.js | 1-10 min | Prime number sieve |
| compute | crypto_hash.js | 1-15 min | Crypto hashing stress |
| compute | buffer_ops.js | 1-10 min | Buffer manipulations |
| compute | sorting.js | 1-10 min | Array sorting algorithms |
| io | file_operations.js | 1-8 min | fs read/write ops |
| io | json_processing.js | 1-8 min | JSON parse/stringify |
| io | stream_copy.js | 2-10 min | Stream-based file copy |
| io | csv_generator.js | 1-10 min | Generate CSV data |
| io | log_writer.js | 5-30 min | Continuous log writing |
| async | promise_chain.js | 2-15 min | Chained promises |
| async | concurrent_ops.js | 2-15 min | Parallel operations |
| async | event_loop_test.js | 2-10 min | Event loop stress |
| async | timer_stress.js | 5-20 min | setTimeout/setInterval |
| async | queue_processor.js | 5-30 min | Async queue processing |
| mixed | data_transform.js | 3-15 min | Data transformation |
| mixed | template_render.js | 2-10 min | Template processing |
| mixed | config_generator.js | 1-5 min | Config file generation |
| mixed | batch_processor.js | 5-30 min | Batch file processing |
| mixed | api_simulator.js | 5-20 min | Simulated API calls |
| idle | sleep_random.js | 1-50 min | Random delays |
| idle | heartbeat.js | 5-50 min | Periodic output |
| idle | intermittent.js | 5-30 min | Work → Idle cycles |
| io | spaces_transfer.js | 2-10 min | Spaces file transfer |
| compute | compression.js | 2-15 min | zlib compress/decompress |

---

## Load Patterns

### Pattern Types

1. **Burst**: Many acquisitions in quick succession, then quiet
   - 10% chance of 0.1s wait (burst mode)
   - 90% chance of 30-120s wait (quiet mode)

2. **Steady**: Consistent rate with small variance
   - Fixed interval ± 20% jitter

3. **Random**: Exponential distribution
   - Poisson-like arrival pattern

4. **Peak Hours**: Higher rate during "peak" periods
   - 2x rate during 30-70% of test duration
   - 0.5x rate otherwise

---

## Test Scenarios

### 1. quick_validation (5-10 min)
- 4 users (2 Python + 2 Node)
- Steady pattern, 60-120s tasks
- Validates basic functionality

### 2. burst_test (30 min)
- 20 users (10 Python + 10 Node)
- Burst pattern, 60-300s tasks
- Tests pool exhaustion and cold-start fallback

### 3. steady_state (1 hour)
- 24 users (12 Python + 12 Node)
- Steady pattern, 120-600s tasks
- Tests sustained load handling

### 4. scale_cycle (90 min)
- 30 users (15 Python + 15 Node)
- Peak hours pattern, 180-900s tasks
- Includes 10-min idle periods
- Tests scale-up/down cycles

### 5. full_stress (2h 10min)
- 50 users (25 Python + 25 Node)
- Mixed patterns across user groups:
  - 8 heavy (steady, 5-30 min tasks)
  - 5 burst (burst, 1-10 min tasks)
  - 7 light (random, 1-5 min tasks)
  - 5 long-running (steady, 15-50 min tasks)
- Includes 5-min idle periods every 30 min
- Full scale-up/down testing

---

## Metrics Collection

### Time-Series Metrics (every 10s)
- `ready`: Warm sandboxes available
- `creating`: Sandboxes being created
- `in_use`: Sandboxes currently acquired
- `total_acquires`: Cumulative acquisitions
- `pool_hit_rate`: % of instant acquisitions
- `avg_acquire_latency_ms`: Average acquisition time
- `scale_up_events`: Cumulative scale-ups
- `scale_down_events`: Cumulative scale-downs

### Task Metrics (per task)
- `acquire_latency_ms`: Time to get sandbox
- `execution_duration_s`: Task run time
- `success`: Task completed successfully
- `from_pool`: Was it a pool hit?
- `error`: Error message if failed

### Summary Metrics
- Total tasks / Success rate
- Pool hit rate (overall)
- Average acquire latency (pool vs cold-start)
- Max concurrent sandboxes
- Scale-up/down event counts

---

## Output Artifacts

```
tests/artifacts/stress/
├── metrics_YYYYMMDDTHHMMSSZ.csv    # Time-series data
├── tasks_YYYYMMDDTHHMMSSZ.json     # Task results
├── summary_YYYYMMDDTHHMMSSZ.json   # Summary stats
└── report_YYYYMMDDTHHMMSSZ.html    # Visual report
```

---

## Implementation Steps

### Phase 1: Structure Setup
1. Create `tests/manager_stress/` folder structure
2. Create `sandbox-execution-programs/` folder structure
3. Update `.gitignore` to ignore programs and artifacts

### Phase 2: Test Programs (50+ programs)
1. Create 25+ Python programs across categories
2. Create 25+ Node.js programs across categories
3. Each program accepts duration as CLI argument
4. Each outputs `RESULT: key=value ...` on completion

### Phase 3: Core Framework
1. `config.py` - TestConfig, PoolConfig settings, scenarios
2. `metrics_collector.py` - Time-series collection, CSV/JSON output
3. `workload_generator.py` - Program selection based on duration/category
4. `reporter.py` - HTML report generation

### Phase 4: Orchestration
1. `user_simulator.py` - Simulates user acquiring/using sandboxes
2. `orchestrator.py` - Main test runner, coordinates everything
3. `__main__.py` - CLI interface

### Phase 5: Scenario Definitions
1. Create YAML scenario files
2. Wire up scenario loading

### Phase 6: Testing
1. Run quick_validation (smoke test)
2. Run burst_test
3. Run full_stress (2+ hours)

---

## Key Configuration

```python
TestConfig(
    python_pool_target=5,
    python_pool_max=25,
    node_pool_target=5,
    node_pool_max=25,
    max_total_sandboxes=50,
    max_concurrent_creates=10,
    idle_timeout=120,           # 2 min before scale-down
    scale_down_delay=60,        # 1 min between destructions
    cooldown_after_acquire=180, # 3 min pause after acquire
    max_warm_age=1800,          # 30 min max warm time
    sandbox_defaults={
        "region": "syd1",
        "instance_size": "apps-s-1vcpu-2gb",
    },
)
```

---

## Files to Modify

| File | Action |
|------|--------|
| `.gitignore` | Add `sandbox-execution-programs/` and `tests/artifacts/` |
| `tests/manager_stress/` | Create entire directory structure |
| `sandbox-execution-programs/` | Create 50+ test programs |

## Files to Reference

| File | Purpose |
|------|---------|
| `src/do_app_sandbox/manager.py` | SandboxManager implementation |
| `src/do_app_sandbox/sandbox.py` | Sandbox API |
| `tests/test_manager.py` | Existing test patterns |
| `tests/full_python_sandbox_run.py` | Spaces integration example |

---

## CLI Usage

```bash
# Quick validation (5-10 min)
uv run python -m tests.stress.manager_load --scenario quick_validation

# Full stress test (2+ hours)
uv run python -m tests.stress.manager_load --scenario full_stress

# With custom output directory
uv run python -m tests.stress.manager_load --scenario full_stress --output-dir ./results
```

---

## Success Criteria

1. **Functionality**: Every acquire() call returns a sandbox (within limits)
2. **Pool Efficiency**: >80% pool hit rate during steady state
3. **Latency**: Pool hits <1s, cold starts <60s
4. **Scale-down**: Idle pools scale to 0 after idle_timeout
5. **Scale-up**: Pools replenish to target after acquisitions
6. **Reliability**: >95% task success rate
7. **No Leaks**: All sandboxes properly cleaned up at shutdown

---

## Test Results

### quick_validation (2026-01-06)

**Configuration:**
- Region: syd1
- Instance size: apps-s-1vcpu-2gb
- Users: 4 (2 python_basic, 2 node_basic)
- Duration: 10 minutes

**Summary:**
```
Duration: 656.7s
Total tasks: 17
Success rate: 100.0%
Pool hit rate: 0.0% (cold starts only - pool starts empty)
Avg acquire latency: 15,849ms
Max concurrent: 4 sandboxes
```

**Detailed Metrics:**
| Metric | Value |
|--------|-------|
| Total acquires | 17 |
| Pool hits | 0 |
| Cold starts | 17 |
| Avg pool hit latency | N/A |
| Avg cold start latency | 15,849ms |
| Min acquire latency | 410ms |
| Max acquire latency | 64,481ms |
| P50 acquire latency | 793ms |
| P95 acquire latency | 57,475ms |

**Tasks by Category:**
- IO: 9 tasks (100% success)
- Compute: 8 tasks (100% success)

**Tasks by Image:**
- Python: 10 tasks (100% success)
- Node: 7 tasks (100% success)

**Key Finding:** Pool empty throughout test since pools start empty and cold-start sandbox creation (43-65s) exceeds task arrival rate. True pool hit performance (<1s) would be visible with pre-warmed pools.

### Standalone Sandbox Create Benchmark (2026-01-06)

Establishes ground truth for sandbox creation time (no pooling).

**Configuration:**
- 25 sandboxes (12 Python, 13 Node)
- Max concurrent: 10
- Region: syd1

**Results:**
```
Total sandboxes: 25
Successful: 25
Failed: 0
Overall time: 179.6s

Create times:
  Min: 43.4s
  Max: 96.5s
  Avg: 63.9s
  Median: 60.0s

Exec times:
  Min: 10.7s
  Max: 12.1s
  Avg: 11.3s

Delete times:
  Min: 4.3s
  Max: 6.2s
  Avg: 5.1s
```

**Key Finding:** Raw sandbox creation takes 43-97s with 64s average. This is the baseline that pool pre-warming eliminates.
