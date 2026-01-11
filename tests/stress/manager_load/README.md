# SandboxManager Stress Testing Framework

> Comprehensive stress testing for sandbox pool management at scale.

## Quick Start

```bash
# List available scenarios
uv run python -m tests.stress.manager_load --list-scenarios

# Run quick validation (10 min)
uv run python -m tests.stress.manager_load --scenario quick_validation

# Run 1-hour 40-sandbox test
uv run python -m tests.stress.manager_load --scenario sandbox_40_1hr

# Run 8-hour stress test (500 sandboxes)
uv run python -m tests.stress.manager_load --scenario mega_stress_8hr

# Dry run (algorithmic simulation, no real sandboxes, no cost)
uv run python -m tests.stress.manager_load --scenario quick_validation --dry-run -v
```

## Running Tests

### Unit Tests (Fast, No Infrastructure)

```bash
# Run manager unit tests
uv run pytest tests/test_manager.py -v

# Run algorithmic simulator tests
uv run pytest tests/manager_stress/test_algorithmic_simulator.py -v

# Run all unit tests
uv run pytest tests/test_manager.py tests/manager_stress/test_algorithmic_simulator.py -v
```

### Dry-Run Mode (Algorithmic Simulation)

Dry-run mode uses an `AlgorithmicMockManager` that faithfully implements the same limit tracking logic as the real manager. This catches algorithmic bugs without real infrastructure.

```bash
# Quick dry-run (validates limit enforcement)
uv run python -m tests.stress.manager_load --scenario quick_validation --dry-run -v

# What dry-run tests:
# - max_total_sandboxes limit enforcement
# - ready + creating + in_use tracking
# - Limit violation detection
# - Pool replenishment logic
```

**Key difference from real tests**: Dry-run completes in seconds/minutes (no ~30s sandbox creation wait).

### Real Sandbox Tests (Requires DIGITALOCEAN_TOKEN)

```bash
# Validate test programs exist
uv run python -m tests.stress.manager_load --validate-programs

# Run quick real test (10 min, ~$0.04)
uv run python -m tests.stress.manager_load --scenario quick_validation -v

# Run 40-sandbox 1-hour test (~$0.80)
uv run python -m tests.stress.manager_load --scenario sandbox_40_1hr -v
```

## Folder Structure

```
tests/manager_stress/
├── README.md                    # ← You are here
├── PLAN.md                      # Original stress test plan
├── PLAN_500_SANDBOX_8HR.md      # 500-sandbox 8-hour test plan
├── PLAN_40_SANDBOX_1HR.md       # 40-sandbox 1-hour test plan
│
├── __main__.py                  # CLI entry point
├── config.py                    # Scenarios & configuration
├── orchestrator.py              # Main test runner
├── user_simulator.py            # Simulated user behavior
├── workload_generator.py        # Program selection
├── metrics_collector.py         # Time-series metrics
├── reporter.py                  # HTML report generation
├── algorithmic_simulator.py     # AlgorithmicMockManager for dry-run
└── test_algorithmic_simulator.py # Unit tests for simulator
```

## Available Scenarios

| Scenario | Duration | Users | Sandboxes | Purpose |
|----------|----------|-------|-----------|---------|
| `quick_validation` | 10 min | 4 | 8 | Smoke test |
| `burst_test` | 30 min | 20 | 30 | Pool exhaustion |
| `sandbox_40_1hr` | 1 hr | 16 | 40 | Medium scale validation |
| `steady_state` | 1 hr | 24 | 40 | Sustained load |
| `scale_cycle` | 90 min | 30 | 40 | Scale up/down |
| `full_stress` | 2h 10m | 50 | 50 | Full stress |
| `corner_case_blitz` | 2 hr | 80 | 100 | Edge cases |
| `scale_boundary` | 4 hr | 150 | 300 | API limits |
| `mega_stress_8hr` | 8 hr | 200 | 500 | Production scale |

## Module Reference

### `config.py` - Configuration

```python
from tests.stress.manager_load.config import get_scenario, SCENARIOS

# Get a scenario
scenario = get_scenario("mega_stress_8hr")
print(f"Users: {scenario.total_users}")
print(f"Duration: {scenario.duration_seconds}s")
```

### `orchestrator.py` - Test Runner

```python
from tests.stress.manager_load.orchestrator import StressTestOrchestrator

orchestrator = StressTestOrchestrator(scenario)
await orchestrator.run()
```

### `metrics_collector.py` - Metrics

```python
from tests.stress.manager_load.metrics_collector import MetricsCollector

collector = MetricsCollector("test", output_dir)
collector.record_acquire(latency_ms=100, from_pool=True)
collector.take_system_snapshot()  # Memory, FDs, asyncio tasks
summary = collector.generate_summary()
```

## Output Artifacts

After a test run, find results in `tests/artifacts/stress/`:

```
tests/artifacts/stress/
├── metrics_20260106T120000Z.csv      # Pool time-series
├── system_20260106T120000Z.csv       # Memory, FDs, GC
├── tasks_20260106T120000Z.json       # Individual task results
├── summary_20260106T120000Z.json     # Aggregate statistics
├── violations_20260106T120000Z.json  # Invariant violations
└── report_20260106T120000Z.html      # Interactive dashboard
```

## Related Files

- **Implementation**: `src/do_app_sandbox/manager.py`
- **Adaptive Scaling**: `src/do_app_sandbox/adaptive_pool.py`
- **Unit Tests**: `tests/test_manager.py`
- **Test Programs**: `sandbox-execution-programs/`

## Cost Estimate

| Scenario | Sandboxes | Duration | Est. Cost |
|----------|-----------|----------|-----------|
| Any scenario (dry-run) | 0 | seconds | $0 |
| quick_validation | 8 | 10 min | ~$0.04 |
| sandbox_40_1hr | 40 | 1 hr | ~$0.80 |
| full_stress | 50 | 2 hr | ~$3 |
| mega_stress_8hr | 500 | 8 hr | ~$120 |

*Based on $0.03/sandbox/hour. Dry-run mode uses no real sandboxes.*
