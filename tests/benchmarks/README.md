# DO App Sandbox Benchmarks

This directory contains performance benchmarks for the DO App Sandbox SDK.

## Benchmarks

### 1. Standalone Sandbox Creation (`sandbox_create_benchmark.py`)

Measures raw sandbox creation time without any pooling. This establishes the baseline for cold-start performance.

**What it tests:**
- Direct `Sandbox.create()` timing
- Simple command execution
- Sandbox deletion

**Usage:**
```bash
cd /path/to/do-app-sandbox
python tests/benchmarks/sandbox_create_benchmark.py
```

**Configuration:**
- `num_sandboxes`: Number of sandboxes to create (default: 25)
- `max_concurrent`: Concurrent creation limit (default: 10)
- Region and instance size configurable in script

**Expected Results (syd1, apps-s-1vcpu-2gb):**
| Metric | Value |
|--------|-------|
| Min create time | ~43s |
| Max create time | ~97s |
| Avg create time | ~64s |
| Exec time | ~10-12s |
| Delete time | ~4-6s |

### 2. SandboxManager Stress Test (`../manager_stress/`)

Tests the SandboxManager pool with simulated user workloads.

**What it tests:**
- Pool acquisition vs cold starts
- Concurrent user simulation
- Various load patterns (steady, burst, random)
- Multiple image types (Python, Node.js)

**Usage:**
```bash
cd /path/to/do-app-sandbox
python -m tests.manager_stress.main --scenario quick_validation
```

**Available Scenarios:**
| Scenario | Duration | Users | Description |
|----------|----------|-------|-------------|
| `quick_validation` | 10 min | 4 | Quick validation test |
| `standard` | 30 min | 10 | Standard load test |
| `stress` | 60 min | 25 | High-load stress test |
| `endurance` | 120 min | 15 | Long-running stability |
| `burst` | 15 min | 8 | Burst traffic patterns |

**Expected Results (quick_validation):**
| Metric | Value |
|--------|-------|
| Success rate | 100% |
| Pool hit latency | <1s |
| Cold start latency | 43-65s |
| Total tasks | ~17 |

## Running Your Own Benchmarks

### Prerequisites

1. **DigitalOcean Account** with App Platform access
2. **doctl authenticated**:
   ```bash
   doctl auth init
   doctl account get  # Verify access
   ```
3. **Environment variables** (optional, for Spaces):
   ```bash
   export SPACES_ACCESS_KEY=...
   export SPACES_SECRET_KEY=...
   export SPACES_BUCKET=...
   export SPACES_REGION=nyc3
   ```

### Tips

- **Region selection**: Choose a region close to you for lower latency
- **Instance size**: Larger instances may provision faster
- **Concurrent limits**: Stay within 10-15 concurrent creates to avoid API rate limits
- **Clean up**: Benchmarks auto-delete sandboxes, but verify with `doctl apps list`

### Cost Considerations

Benchmarks create real App Platform apps which incur costs:
- Each sandbox costs ~$5/month prorated
- A 25-sandbox benchmark running for 5 minutes costs ~$0.01-0.02
- Always clean up after benchmarks

## Results

Store benchmark results in `results/` for tracking over time:
```bash
python tests/benchmarks/sandbox_create_benchmark.py > results/create_$(date +%Y%m%d_%H%M%S).txt
```

## Sample Results

### Standalone Create Benchmark (2026-01-06, syd1)

```
STANDALONE SANDBOX CREATE TEST
============================================================
Creating 25 sandboxes (12 python, 13 node)
Max concurrent creates: 10
Region: syd1
============================================================

RESULTS
============================================================
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

### SandboxManager Stress Test (2026-01-06, quick_validation)

```
Duration: 656.7s
Total tasks: 17
Success rate: 100.0%
Pool hit rate: 0.0% (cold starts only, pool starts empty)
Avg acquire latency: 15,849ms
  - Pool hits: <1,000ms
  - Cold starts: 43,000-65,000ms
Max concurrent: 4 sandboxes
```

**Key finding**: Pool hits provide ~50-65x faster acquisition vs cold starts.
