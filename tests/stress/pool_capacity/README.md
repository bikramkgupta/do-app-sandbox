# Rigorous Pool Test - Command Reference

A comprehensive stress test for the `do-app-sandbox` Python SDK.

## Quick Start

```bash
# Navigate to the SDK directory
cd /Users/bgupta/Documents/Builder/sandbox-stress/do-app-sandbox-main

# Run smoke test (10 minutes, 5 sandboxes)
uv run python -m tests.stress.pool_capacity.run_25cap_4hr --smoke
```

---

## Test Commands

### 1. Smoke Test (Recommended First)
Quick validation of environment, credentials, and basic functionality.

```bash
uv run python -m tests.stress.pool_capacity.run_25cap_4hr --smoke
```

**Parameters:** 10 minutes, 5 max sandboxes, 4 workers, target_ready=3

---

### 2. Main 4-Hour Run
Full stress test as specified in Task.md requirements.

```bash
uv run python -m tests.stress.pool_capacity.run_25cap_4hr \
    --duration-seconds 14400 \
    --max-total 25 \
    --concurrency 12 \
    --python-target-ready 12 \
    --region syd1
```

**Parameters:** 4 hours, 25 max sandboxes, 12 workers, target_ready=12

---

### 3. Pool Starvation Test
Forces cold starts by keeping pool target low with high demand.

```bash
uv run python -m tests.stress.pool_capacity.run_25cap_4hr \
    --duration-seconds 1800 \
    --max-total 25 \
    --concurrency 16 \
    --python-target-ready 2
```

**Parameters:** 30 minutes, 25 max sandboxes, 16 workers (high demand), target_ready=2 (low pool)

---

### 4. Custom Configuration
Full list of available options:

```bash
uv run python -m tests.stress.pool_capacity.run_25cap_4hr \
    --duration-seconds 3600 \      # Test duration (seconds)
    --max-total 15 \               # Max sandboxes (HARD LIMIT)
    --region syd1 \                # Sandbox region
    --instance-size basic-xxs \    # Instance size
    --concurrency 8 \              # Number of virtual users
    --python-target-ready 6 \      # Pool target ready count
    --python-max-ready 10 \        # Pool max ready count
    --watchdog-interval 10 \       # doctl polling interval (seconds)
    --watchdog-grace 2 \           # Grace period for brief overage
    --enable-emergency-cleanup \   # Auto-delete excess sandboxes
    --debug                        # Enable debug logging
```

---

### 5. Without Watchdog
Disable external doctl-based monitoring (not recommended):

```bash
uv run python -m tests.stress.pool_capacity.run_25cap_4hr \
    --smoke \
    --disable-watchdog
```

---

### 6. With Emergency Cleanup
Enable automatic deletion of excess sandboxes on watchdog violation:

```bash
uv run python -m tests.stress.pool_capacity.run_25cap_4hr \
    --smoke \
    --enable-emergency-cleanup
```

---

### 7. Disable Network Commands
Skip commands that require network access (DNS lookups):

```bash
uv run python -m tests.stress.pool_capacity.run_25cap_4hr \
    --smoke \
    --disable-network-commands
```

---

## CLI Options Reference

| Option | Default | Description |
|--------|---------|-------------|
| `--smoke` | false | Run smoke test preset (10min, 5 sandboxes) |
| `--duration-seconds` | 14400 | Test duration in seconds |
| `--max-total` | 25 | Maximum sandboxes (HARD LIMIT) |
| `--region` | syd1 | Sandbox region |
| `--instance-size` | basic-xxs | Sandbox instance size |
| `--concurrency` | 12 | Number of virtual users (workers) |
| `--python-target-ready` | 12 | Python pool target ready count |
| `--python-max-ready` | 15 | Python pool max ready count |
| `--node-target-ready` | 0 | Node pool target ready (0 = disabled) |
| `--report-dir` | auto | Report output directory |
| `--watchdog-interval` | 10.0 | doctl polling interval (seconds) |
| `--watchdog-grace` | 2 | Grace period for brief overage |
| `--disable-watchdog` | false | Disable external monitoring |
| `--enable-emergency-cleanup` | false | Auto-delete excess sandboxes |
| `--disable-network-commands` | false | Skip network-dependent commands |
| `--debug` | false | Enable debug logging |

---

## Output Reports

Reports are written to `tests/artifacts/rigorous_pool_test/<timestamp>/`:

| File | Description |
|------|-------------|
| `summary.json` | Pass/fail status and key metrics |
| `summary.txt` | Human-readable summary |
| `sessions.csv` | Per-session data |
| `commands.csv.gz` | Per-command data (compressed) |
| `pool_metrics.json` | Raw pool metrics from SDK |
| `test.log` | Full test log |

---

## Checking Results

```bash
# View summary
cat tests/artifacts/rigorous_pool_test/*/summary.txt

# Check if test passed
jq '.pass' tests/artifacts/rigorous_pool_test/*/summary.json

# View watchdog metrics
jq '.watchdog' tests/artifacts/rigorous_pool_test/*/summary.json

# Count command failures
jq '.total_command_failures' tests/artifacts/rigorous_pool_test/*/summary.json
```

---

## Manual Cleanup

If tests are interrupted, manually check for orphaned sandboxes:

```bash
# List all sandbox apps
doctl apps list | grep -i sandbox

# Delete specific app
doctl apps delete <app-id> --force

# Delete all sandbox apps (USE WITH CAUTION)
doctl apps list --format ID,Spec.Name --no-header | grep -i sandbox | awk '{print $1}' | xargs -I {} doctl apps delete {} --force
```

---

## Test Objectives (from Task.md)

- **Command Correctness:** 0% failure rate for `sandbox.exec()` calls
- **Pool Effectiveness:** Track pool hit rate vs cold starts
- **Capacity Enforcement:** Never exceed 25 sandboxes
- **Lifecycle Robustness:** Clean create/delete cycles over 4 hours
