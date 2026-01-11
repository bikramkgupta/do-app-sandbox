# Modeling & Algorithmic Simulation

Pure algorithmic simulations for deriving optimal pool parameters and comparing scaling algorithms.

**Key benefit**: No cloud resources required. Runs instantly, costs nothing.

## Quick Start: Pool Sizing Calculator

Answer: "What pool size do I need for 95% hit rate?"

```bash
# Run the simulator
cd tests/modeling/pool_simulator && uv run python demand_curves.py
```

**Key formula**: `concurrent_load = requests_per_minute × avg_hold_minutes`

Example: 4 req/min × 10-min avg hold = 40 concurrent sandboxes needed.

## Components

### pool_simulator/ - Pool Sizing & Demand Simulation
Simulates pool behavior under various demand patterns without creating real sandboxes.

**Features**:
- **Pool sizing calculator**: Computes `target_ready` for target hit rate
- **Workload presets**: light_batch, heavy_batch, ai_inference, code_execution, long_running
- Demand pattern generators: steady, spike, ramp, wave, bursty
- Pool state simulation: tracks ready, warming, in-use counts
- 1000x time acceleration: 8-hour simulation in seconds
- Chart and CSV output for analysis

**Run commands**:
```bash
# Run pool sizing simulation (recommended)
cd tests/modeling/pool_simulator && uv run python demand_curves.py

# Or as module
uv run python -m tests.modeling.pool_simulator.demand_curves

# Run unit tests
uv run pytest tests/modeling/ -v
```

**Output**:
- `tests/artifacts/simulation_chart.html` - Interactive visualization
- `tests/artifacts/simulation_log.csv` - Per-interval metrics

## Use Cases

1. **Derive target_ready values**: Run demand simulations to find optimal pool sizes
2. **Validate configurations**: Test pool configurations before production
3. **Cost modeling**: Estimate resource usage for different scenarios

## Demand Patterns

```python
from tests.modeling.pool_simulator.demand_curves import (
    steady_load,      # Constant demand
    sudden_spike,     # Sudden traffic burst
    wave_pattern,     # Sinusoidal oscillation
    bursty,           # Random bursts
    ramp_up_down,     # Gradual increase then decrease
)
```

## Example: Finding Optimal Pool Size

```python
from tests.modeling.pool_simulator.demand_curves import calculate_pool_config

# Calculate pool size for your workload
config = calculate_pool_config(
    requests_per_minute=4.0,      # Expected request rate
    avg_hold_minutes=10.0,        # Average sandbox hold time
    target_hit_rate=0.95,         # Target 95% hit rate
    cold_start_seconds=30.0,      # Time to create sandbox
)

print(f"Recommended target_ready: {config.target_ready}")
print(f"Recommended max_sandboxes: {config.max_sandboxes}")
print(f"Concurrent load: {config.concurrent_load}")
```

### Using Workload Presets

```python
from tests.modeling.pool_simulator.simulation_config import WORKLOAD_PRESETS, list_workload_presets

# See all available presets
list_workload_presets()

# Use a preset
preset = WORKLOAD_PRESETS["ai_inference"]
print(f"Description: {preset.description}")
print(f"Recommended target_ready: {preset.recommended_target_ready}")
```

## Guidelines for New Simulations

1. **Keep simulations pure**: No network calls, no cloud dependencies
2. **Support parameterization**: Allow easy configuration via CLI or code
3. **Generate visualizations**: Charts help understand behavior
4. **Export raw data**: CSV/JSON for further analysis
5. **Document assumptions**: Clearly state timing assumptions (cold/warm start times)
