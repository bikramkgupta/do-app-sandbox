# App Platform Sandbox Testing Guide

This directory contains a comprehensive suite of tests for the `do-app-sandbox` SDK, ranging from unit tests to multi-hour stress tests.

## 🚀 Incremental Testing Strategy

To ensure stability and catch bugs early, follow this incremental testing path:

### Step 1: Unit Tests (Fast, No Network)
Validate internal logic, type safety, and state machine transitions using mocks.
```bash
uv run --extra dev pytest tests/unit/ -v
```

### Step 2: Container API Tests (Local Docker)
Validate the FastAPI `sandbox_api` server that runs inside "Service Mode" containers.
1. Build and run the test container locally:
   ```bash
   docker build -t sandbox-api-test -f images/sandbox-python-service/Dockerfile images/
   docker run -p 8080:8080 -e SANDBOX_API_TOKEN=test-token sandbox-api-test
   ```
2. Run the tests against the local container:
   ```bash
   SANDBOX_API_URL=http://localhost:8080 SANDBOX_API_TOKEN=test-token pytest tests/container/
   ```

#### Running Against a Cloud Sandbox (Alternative)
Container tests can also run against a deployed Service sandbox for true E2E validation through real DigitalOcean ingress/load balancers.

1. Create a Service sandbox:
   ```bash
   sandbox create --image python --component-type service
   ```
   Note the URL (e.g., `https://my-sandbox-xxxxx.ondigitalocean.app`).

2. Run tests targeting the cloud sandbox:
   ```bash
   export SANDBOX_API_URL="https://your-sandbox-url.ondigitalocean.app"
   export SANDBOX_API_TOKEN="your-token-value"
   uv run pytest tests/container/ -v
   ```

**Note:** Unit tests (`tests/unit/`) cannot run in the cloud - they test internal Python logic using mocks and must run locally.

### Step 3: Functional & Integration Tests (Real Infrastructure)
Validate end-to-end flows on DigitalOcean App Platform. Requires `DIGITALOCEAN_TOKEN` and Spaces configuration.
```bash
# Basic SDK lifecycle
uv run python tests/functional/test_03_basic_sdk.py

# Integration tests (Service mode, Snapshots, Hibernation)
uv run --extra dev pytest tests/integration/ -v
```

### Step 4: Stress & Performance Tests
Validate system behavior under heavy load and long durations.
```bash
# 10-minute smoke stress test
uv run python -m tests.manager_stress --scenario quick_validation

# 4-hour rigorous pool test (Hard Cap 25)
uv run python -m tests.rigorous_pool_test.run_25cap_4hr
```

---

## 🛠 Building Images for Testing

Since GitHub Actions only run on the `main` branch, you must build and push images manually to test the new Service/Worker mode features.

### Option 1: Push to DigitalOcean Container Registry (DOCR)
Recommended for testing on App Platform.
1. Login to your registry: `doctl registry login`
2. Run the build script (updates coming soon) or use Docker:
   ```bash
   export REGISTRY="registry.digitalocean.com/your-registry"
   docker build -t $REGISTRY/sandbox-python-service:latest -f images/sandbox-python-service/Dockerfile images/
   docker push $REGISTRY/sandbox-python-service:latest
   ```

### Option 2: Use the Build Script
Update your `.env` with `GHCR_OWNER` and use the provided script to build all images:
```bash
./scripts/build-ghcr.sh
```

---

## 📂 Test Suites Reference

| Directory | Type | Purpose |
|-----------|------|---------|
| `unit/` | Unit | Fast tests for types, logic, and mocks. |
| `container/` | API | Validates the FastAPI agent inside the sandbox. |
| `integration/` | E2E | Tests real DO/Spaces integration (Mode, Snapshots). |
| `functional/` | E2E | High-level functional flow benchmarks. |
| `manager_stress/` | Stress | Multi-user load simulation for SandboxManager. |
| `manager_simulator/`| Algo | Accelerated algorithmic simulation (no cost). |
| `rigorous_pool_test/`| Stress | 4-hour hard-cap capacity enforcement test. |

---

## ⚙️ Configuration

Tests use environment variables defined in your `.env` file:

```bash
# DigitalOcean
DIGITALOCEAN_TOKEN=dop_v1_...
APP_SANDBOX_REGION=syd1

# DigitalOcean Spaces (Required for Snapshots/Large Files)
SPACES_BUCKET=your-bucket
SPACES_REGION=nyc3
SPACES_ACCESS_KEY=...
SPACES_SECRET_KEY=...

# Image Registry
GHCR_OWNER=your-username
APP_SANDBOX_REGISTRY=ghcr.io  # Or your DOCR host
```

---

## 📊 Results & Artifacts

Test results and reports are saved to `tests/artifacts/`:
- **Stress Reports**: `tests/artifacts/stress/report_*.html`
- **Pool Metrics**: `tests/artifacts/stress/metrics_*.csv`
- **Rigorous Summary**: `tests/artifacts/rigorous_pool_test/*/summary.txt`