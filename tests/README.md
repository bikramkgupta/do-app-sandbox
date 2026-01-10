# App Platform Sandbox Testing Guide

This directory contains a comprehensive suite of tests for the `do-app-sandbox` SDK, ranging from unit tests to multi-hour stress tests.

> **For AI Assistants**: See [CLAUDE.md](./CLAUDE.md) for detailed guidance on writing and running tests.

## Quick Start

```bash
# Run fast unit tests (no cloud required)
uv run pytest tests/unit/ -v

# Run API tests (requires running container)
SANDBOX_API_URL=http://localhost:8080 SANDBOX_API_TOKEN=test-token \
  uv run pytest tests/api/ -v

# Run integration tests (requires DIGITALOCEAN_TOKEN)
uv run pytest tests/integration/ -v
```

## Test Categories

| Directory | Duration | Cloud? | Purpose |
|-----------|----------|--------|---------|
| `unit/` | ~10s | No | Fast isolated tests with mocks |
| `api/` | ~1min | Container | Container API endpoint tests |
| `integration/` | ~5min | Yes | Multi-component E2E tests |
| `functional/` | ~10min | Yes | Full workflow tests |
| `stress/` | 10min-8hr | Yes | Load and stress tests |
| `modeling/` | ~1min | No | Algorithmic simulation |
| `benchmarks/` | ~30min | Yes | Performance measurement |
| `perf/` | ~15min | Yes | Lifecycle & file transfer timing |
| `smoke/` | ~2min | Yes | Quick sanity checks |

## Incremental Testing Strategy

Follow this path from fastest to slowest:

### Step 1: Unit Tests (No Network)

Validate internal logic using mocks. Runs in seconds.

```bash
uv run pytest tests/unit/ -v
```

### Step 2: API Tests (Local Docker or Cloud)

Test the FastAPI `sandbox_api` server.

**Option A: Local Docker**
```bash
# Build the image
docker build -t sandbox-api-test -f images/sandbox-python-service/Dockerfile images/

# Run container (use -d for detached mode)
docker run -d --name sandbox-api-test -p 8080:8080 -e SANDBOX_API_TOKEN=test-token sandbox-api-test

# Run tests
SANDBOX_API_URL=http://localhost:8080 SANDBOX_API_TOKEN=test-token \
  uv run pytest tests/api/ -v

# Stop container when done
docker stop sandbox-api-test && docker rm sandbox-api-test
```

**Option B: Cloud Sandbox**
```bash
sandbox create --image python --component-type service
# Note the URL and token

SANDBOX_API_URL=https://your-sandbox.ondigitalocean.app \
SANDBOX_API_TOKEN=your-token \
  uv run pytest tests/api/ -v
```

### Step 3: Integration & Functional Tests

Requires `DIGITALOCEAN_TOKEN` and optionally `SPACES_*` credentials.

```bash
# Integration tests
uv run pytest tests/integration/ -v

# Functional tests
uv run python tests/functional/run_all.py
```

### Step 4: Stress & Performance Tests

Long-running tests for load validation.

```bash
# Quick 10-minute stress test
uv run python -m tests.stress.manager_load --scenario quick_validation

# Pool capacity test (4 hours)
uv run python -m tests.stress.pool_capacity.run

# Dry-run mode (no cloud cost)
uv run python -m tests.stress.manager_load --scenario full_stress --dry-run
```

### Step 5: Modeling (No Cloud)

Algorithmic simulation for pool sizing and parameter tuning.

```bash
# Run pool sizing simulator (shows how to achieve 95%+ hit rate)
cd tests/modeling/pool_simulator && uv run python demand_curves.py

# Or run as module
uv run python -m tests.modeling.pool_simulator.demand_curves

# Run modeling unit tests
uv run pytest tests/modeling/ -v
```

The simulator helps answer: "For X requests/min with Y-minute holds, what pool size gives 95% hit rate?"

Key formula: `concurrent_load = requests_per_minute × avg_hold_minutes`

## Directory Structure

```
tests/
├── CLAUDE.md              # AI guidance
├── README.md              # This file
├── conftest.py            # Root pytest configuration
│
├── unit/                  # Fast isolated tests
├── api/                   # Container API tests
├── integration/           # Multi-component E2E tests
├── functional/            # Full workflow tests
│
├── stress/                # Long-running load tests
│   ├── pool_capacity/     # Hard-cap capacity enforcement
│   ├── manager_load/      # Multi-user simulation
│   └── README.md
│
├── modeling/              # Algorithmic simulation
│   ├── pool_simulator/    # Demand curve testing
│   └── README.md
│
├── benchmarks/            # Performance measurement
├── perf/                  # Lifecycle timing harness
├── smoke/                 # Quick sanity checks
└── artifacts/             # Test outputs (gitignored)
```

## Pytest Markers

Filter tests by type:

```bash
pytest -m unit              # Only unit tests
pytest -m integration       # Only integration tests
pytest -m api               # Only API tests
pytest -m "not slow"        # Skip slow tests
```

## Environment Variables

```bash
# DigitalOcean (required for cloud tests)
DIGITALOCEAN_TOKEN=dop_v1_...
APP_SANDBOX_REGION=syd1

# Container API tests
SANDBOX_API_URL=http://localhost:8080
SANDBOX_API_TOKEN=test-token

# Spaces (for snapshots/large files)
SPACES_BUCKET=your-bucket
SPACES_REGION=nyc3
SPACES_ACCESS_KEY=...
SPACES_SECRET_KEY=...

# Image Registry
GHCR_OWNER=your-username
APP_SANDBOX_REGISTRY=ghcr.io
```

## Building Test Images

For Service/Worker mode testing:

```bash
# Option 1: DigitalOcean Container Registry
doctl registry login
docker build -t registry.digitalocean.com/your-registry/sandbox-python-service:latest \
  -f images/sandbox-python-service/Dockerfile images/
docker push registry.digitalocean.com/your-registry/sandbox-python-service:latest

# Option 2: GHCR
./scripts/build-ghcr.sh
```

## Artifacts

Test outputs are saved to `tests/artifacts/`:
- `stress/` - Stress test reports (HTML, CSV, JSON)
- `pool_capacity/` - Pool capacity test results
- `simulation_*.csv/html` - Modeling outputs
