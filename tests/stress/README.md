# Stress Tests

Long-running load and stress tests for validating system behavior under sustained pressure.

## Test Suites

### pool_capacity/ - Hard-Cap Capacity Enforcement
Validates that the pool never exceeds its configured capacity limits, even under heavy load.

**Duration**: 10 minutes (smoke) to 4 hours (full)

**Key validations**:
- Command correctness: 0% failure tolerance
- Capacity enforcement: Never exceeds hard limit (default: 25 sandboxes)
- Pool effectiveness: Measures pool hits vs cold starts
- Lifecycle robustness: Continuous acquire/release cycles

**Run commands**:
```bash
# 10-minute smoke test
python -m tests.stress.pool_capacity.run --smoke

# Full 4-hour test
python -m tests.stress.pool_capacity.run --duration-seconds 14400

# Custom configuration
python -m tests.stress.pool_capacity.run \
    --duration-seconds 3600 \
    --max-total 25 \
    --concurrency 8 \
    --python-target-ready 5
```

**Output**: `tests/artifacts/rigorous_pool_test/<timestamp>/`

### manager_load/ - Multi-User Load Simulation
Simulates realistic multi-user workloads against SandboxManager.

**Duration**: 10 minutes (quick_validation) to 8 hours (mega_stress)

**Scenarios**:
- `quick_validation` - 10 minute quick test
- `burst_test` - Sudden spike handling
- `sandbox_40_1hr` - 40 sandboxes for 1 hour
- `mega_stress_8hr` - Full 8-hour stress test

**Run commands**:
```bash
# Quick validation (10 min)
python -m tests.stress.manager_load --scenario quick_validation

# With dry-run (no real sandboxes, no cost)
python -m tests.stress.manager_load --scenario full_stress --dry-run

# Custom scenario
python -m tests.stress.manager_load --scenario sandbox_40_1hr
```

**Output**: `tests/artifacts/stress/`

### test_connection_stability.py - WebSocket Stability
Tests WebSocket connection stability over extended periods.

**Duration**: 5 minutes (default) to hours

**Run command**:
```bash
pytest tests/stress/test_connection_stability.py -v
```

## Dry-Run Mode

Both `pool_capacity/` and `manager_load/` support dry-run mode for:
- Testing algorithms without cloud cost
- Validating test configurations
- Fast iteration during development

```bash
# Algorithmic simulation (instant, no cost)
python -m tests.stress.manager_load --dry-run --scenario full_stress
```

## Environment Variables

```bash
DIGITALOCEAN_TOKEN=dop_v1_...  # Required for real tests
APP_SANDBOX_REGION=syd1        # Optional, defaults to region from env
```

## Artifacts

Results are saved to `tests/artifacts/`:
- `pool_metrics.json` - Time-series pool state
- `sessions.csv` - Per-session data
- `commands.csv.gz` - Per-command data (compressed)
- `summary.json` - Pass/fail status and key metrics
- `report_*.html` - Interactive dashboards

## Guidelines for New Stress Tests

1. **Support dry-run mode** when possible for cost-free testing
2. **Include metrics collection** for post-run analysis
3. **Generate reports** in a standard format
4. **Document expected durations** and resource requirements
5. **Handle cleanup gracefully** even on failures
