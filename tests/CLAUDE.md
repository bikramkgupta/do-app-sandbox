# Test Suite Guide for AI Assistants

## Quick Reference

| What to Test | Where to Add | How to Run |
|-------------|--------------|------------|
| Pure logic, mocked | `unit/` | `pytest tests/unit/` |
| API endpoints | `api/` | `pytest tests/api/` |
| Real DO infra | `integration/` | `pytest tests/integration/` |
| Full workflows | `functional/` | `python tests/functional/run_all.py` |
| Load/stress | `stress/` | See `stress/README.md` |
| Algorithm analysis | `modeling/` | `python -m tests.modeling.pool_simulator` |
| Performance | `benchmarks/` or `perf/` | See below |

## Test Categories Explained

### unit/ - Fast, Isolated, Mocked (~10s)
- **Purpose**: Test internal logic without external dependencies
- **Dependencies**: None (all mocked)
- **Key patterns**: `@patch`, `MagicMock`, isolated function testing
- **Examples**: PoolConfig defaults, exception hierarchy, state machine transitions

### api/ - Container API Tests (~1min)
- **Purpose**: Test the FastAPI `sandbox_api` server that runs inside Service-mode containers
- **Dependencies**: `SANDBOX_API_URL`, `SANDBOX_API_TOKEN`
- **Can run against**: Local Docker container OR deployed cloud sandbox
- **Examples**: `/api/exec`, `/api/files`, `/api/sessions` endpoints

### integration/ - Real DO Infrastructure (~5min)
- **Purpose**: Test components working together with real App Platform resources
- **Dependencies**: `DIGITALOCEAN_TOKEN`, optionally `SPACES_*`
- **Examples**: Snapshots, hibernation, service mode, git checkout

### functional/ - End-to-End Features (~10min)
- **Purpose**: Complete workflows from user perspective
- **Dependencies**: `DIGITALOCEAN_TOKEN`, `SPACES_*`
- **Numbered tests**: Run in sequence via `run_all.py`
- **Examples**: Full Python sandbox lifecycle with file transfers

### stress/ - Long-Running Load Tests (10min - 8hr)
- **Purpose**: Validate system under sustained load
- **Two main suites**:
  - `pool_capacity/` - Hard-cap capacity enforcement (25 sandboxes, 4 hours)
  - `manager_load/` - Multi-user simulation with configurable scenarios
- **Dry-run mode**: Use `--dry-run` for algorithmic simulation without cloud cost
- **Dependencies**: `DIGITALOCEAN_TOKEN` (unless dry-run)

### modeling/ - Algorithmic Simulation (seconds to minutes)
- **Purpose**: Derive optimal pool parameters, compare scaling algorithms
- **Dependencies**: None (pure simulation)
- **Output**: Charts, CSV exports, parameter recommendations
- **Key files**:
  - `pool_simulator/demand_curves.py` - Pool sizing calculator and demand simulation
  - `pool_simulator/simulation_config.py` - Workload presets (light_batch, heavy_batch, ai_inference, etc.)

**Pool Sizing Calculator**: Answers "What pool size for 95% hit rate?"
```python
from tests.modeling.pool_simulator.demand_curves import calculate_pool_config

config = calculate_pool_config(
    requests_per_minute=4.0,
    avg_hold_minutes=10.0,
    target_hit_rate=0.95,
)
print(f"target_ready={config.target_ready}")  # ~100 for this example
```

**Key formula**: `concurrent_load = requests_per_minute × avg_hold_minutes`

**Run the simulator**:
```bash
cd tests/modeling/pool_simulator && uv run python demand_curves.py
```

### benchmarks/ - Performance Measurement (~30min)
- **Purpose**: Measure parallel sandbox creation timing
- **Dependencies**: `DIGITALOCEAN_TOKEN`
- **Output**: Timing reports in `results/`

### perf/ - Performance Harness (~15min)
- **Purpose**: Comprehensive performance measurement
- **Tests**: Lifecycle timing, small uploads (1-4MB), large transfers (100MB via Spaces)
- **Dependencies**: `DIGITALOCEAN_TOKEN`, optionally `SPACES_*` for large files

### smoke/ - Quick Sanity Check (~2min)
- **Purpose**: Lightweight lifecycle validation
- **Dependencies**: `DIGITALOCEAN_TOKEN`
- **Use**: Before deploying, after major changes

## Writing New Tests

### Adding a Unit Test
```python
# tests/unit/test_mymodule.py
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_my_function():
    with patch('do_app_sandbox.mymodule.external_call') as mock:
        mock.return_value = 'mocked'
        result = my_function()
        assert result == 'expected'
```

### Adding an Integration Test
```python
# tests/integration/test_myfeature.py
import pytest

@pytest.mark.integration
def test_my_feature(cleanup_sandboxes):
    # cleanup_sandboxes fixture auto-deletes after test
    sandbox = Sandbox.create(image="python")
    result = sandbox.exec("echo hello")
    assert result.exit_code == 0
```

### Adding a Stress Test
1. Add to `tests/stress/` appropriate subdirectory
2. Document in `tests/stress/README.md`
3. Support `--dry-run` mode for cost-free testing
4. Include metrics collection and reporting

## Pytest Markers

```bash
# Run specific test types
pytest -m unit              # Only unit tests
pytest -m integration       # Only integration tests
pytest -m api               # Only API tests
pytest -m "not slow"        # Skip slow tests

# Combine markers
pytest -m "unit or api"     # Unit and API tests
pytest -m "integration and not slow"  # Fast integration tests
```

## Environment Variables

```bash
# DigitalOcean (required for most cloud tests)
DIGITALOCEAN_TOKEN=dop_v1_...
APP_SANDBOX_REGION=syd1

# Container API tests
SANDBOX_API_URL=https://your-sandbox.ondigitalocean.app
SANDBOX_API_TOKEN=your-token

# Spaces (required for snapshots, large files)
SPACES_BUCKET=your-bucket
SPACES_REGION=nyc3
SPACES_ACCESS_KEY=...
SPACES_SECRET_KEY=...

# Image registry
GHCR_OWNER=your-username
APP_SANDBOX_REGISTRY=ghcr.io
```

## Common Patterns

### Cleanup Fixtures
All integration and functional tests should use cleanup fixtures:
```python
def test_something(cleanup_sandboxes):
    sandbox = Sandbox.create(...)
    # Test logic
    # cleanup_sandboxes auto-deletes on teardown
```

### Skipping Tests
```python
@pytest.mark.skipif(not os.environ.get("SPACES_BUCKET"),
                    reason="Spaces not configured")
def test_large_file_transfer():
    ...
```

### Timeout Handling
```python
@pytest.mark.timeout(300)  # 5 minute timeout
def test_slow_operation():
    ...
```

## Test Discovery

```bash
# See what tests would run
pytest tests/ --collect-only

# Filter by marker
pytest tests/ -m unit --collect-only

# Filter by name pattern
pytest tests/ -k "snapshot" --collect-only
```

## Artifacts

Test outputs are saved to `tests/artifacts/`:
- `stress/` - Stress test reports (HTML, CSV, JSON)
- `pool_capacity/` - Pool capacity test results
- `*.csv`, `*.html` - Simulation outputs

This directory is gitignored; results are ephemeral.
