# Tests

This directory contains all tests for the `do-app-sandbox` SDK. Tests are organized by type and purpose.

## Prerequisites

- **doctl** installed and authenticated (`doctl auth init`)
- **Python 3.10+** with `uv` package manager
- Optional: `.env` file at repo root for Spaces configuration

## Directory Structure

```
tests/
├── functional/          # End-to-end functional tests
│   ├── run_all.py      # Test runner for all functional tests
│   ├── test_01_existing_app.py  # Connect to existing apps
│   ├── test_02_benchmark.py     # Sandbox creation benchmark
│   ├── test_03_basic_sdk.py     # Core SDK functionality
│   ├── test_04_manager.py       # SandboxManager tests
│   └── results/        # JSON test results
├── benchmarks/         # Performance benchmarks
│   └── sandbox_create_benchmark.py
├── smoke/              # Quick smoke tests
│   └── main.py
├── perf/               # Performance tests with large files
│   └── main.py
├── manager_stress/     # Stress tests for SandboxManager
│   ├── __main__.py
│   ├── orchestrator.py
│   └── ...
├── test_integration.py # Basic integration test (pytest)
├── test_manager.py     # Unit tests for SandboxManager
├── test_pty_leak.py    # PTY leak detection test
├── presigned_url_check.py  # Spaces presigned URL probe
└── artifacts/          # Test output artifacts
```

## Quick Start

### Run Functional Tests (Recommended)

```bash
# Run all functional tests
uv run python tests/functional/run_all.py

# Run specific tests only
uv run python tests/functional/run_all.py --only 3 4

# Skip specific tests
uv run python tests/functional/run_all.py --skip 2
```

### Run Individual Functional Tests

```bash
# Test 1: Connect to existing app
uv run python tests/functional/test_01_existing_app.py <APP_ID> <COMPONENT>

# Test 2: Benchmark (creates sandboxes)
uv run python tests/functional/test_02_benchmark.py <COUNT> <CONCURRENT>

# Test 3: Basic SDK (creates sandbox)
uv run python tests/functional/test_03_basic_sdk.py <IMAGE>

# Test 4: SandboxManager (no network)
uv run python tests/functional/test_04_manager.py
```

### Run Unit Tests with pytest

```bash
uv run --extra dev pytest tests/test_manager.py -v
uv run --extra dev pytest tests/test_integration.py -s
```

## Test Categories

### 1. Functional Tests (`tests/functional/`)

End-to-end tests that verify SDK functionality works correctly.

| Test | Description | Creates Sandboxes | Duration |
|------|-------------|-------------------|----------|
| test_01 | Connect to existing app, run diagnostics | No | ~30s |
| test_02 | Benchmark sandbox creation | Yes (4 default) | ~2-3min |
| test_03 | Full SDK lifecycle (create, exec, files, delete) | Yes (1) | ~2min |
| test_04 | SandboxManager pool management | No | <1s |

### 2. Unit Tests (`test_manager.py`)

Unit tests for `SandboxManager` with mocked dependencies. Fast, no network calls.

```bash
uv run --extra dev pytest tests/test_manager.py -v
```

### 3. Integration Tests (`test_integration.py`)

Basic integration test that creates a real sandbox and tests core operations.

```bash
uv run --extra dev pytest tests/test_integration.py -s
```

### 4. Smoke Tests (`tests/smoke/`)

Quick lifecycle tests for Python/Node images. Writes JSON results to `artifacts/`.

```bash
uv run --extra dev python -m tests.smoke.main --spaces
```

### 5. Performance Tests (`tests/perf/`)

Extended tests including large file transfers via Spaces.

```bash
uv run --extra dev python -m tests.perf.main --spaces --run-large-file
```

### 6. Benchmarks (`tests/benchmarks/`)

Full-scale benchmarks for sandbox creation performance.

```bash
uv run python tests/benchmarks/sandbox_create_benchmark.py
```

### 7. Stress Tests (`tests/manager_stress/`)

Stress testing for SandboxManager under high load.

```bash
uv run python -m tests.manager_stress
```

## Environment Variables

Optional environment variables for tests:

```bash
# Spaces configuration (for large file tests)
SPACES_ACCESS_KEY=...
SPACES_SECRET_KEY=...
SPACES_BUCKET=...
SPACES_REGION=nyc3
SPACES_ENDPOINT=https://...

# Image registry (defaults to GHCR)
GHCR_OWNER=bikramkgupta
GHCR_REGISTRY=ghcr.io

# Default region
APP_SANDBOX_REGION=atl1

# Benchmark configuration
BENCHMARK_COUNT=4
BENCHMARK_CONCURRENT=2
```

Load from `.env` file:

```bash
set -a && source .env && set +a
```

## Test Results

Functional test results are saved to `tests/functional/results/`:

- `test_01_result.json` - Existing app connection
- `test_02_result.json` - Benchmark results
- `test_03_result.json` - Basic SDK test results
- `test_04_result.json` - SandboxManager test results
- `summary.json` - Overall summary

Smoke/perf results are saved to `tests/artifacts/`.

## Writing New Tests

### Functional Test Template

```python
#!/usr/bin/env python3
"""Test description."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from do_app_sandbox import Sandbox

def main():
    # Your test code
    sandbox = Sandbox.create(image="python")
    try:
        result = sandbox.exec("echo hello")
        assert result.success
    finally:
        sandbox.delete()
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Unit Test Template (pytest)

```python
import pytest
from do_app_sandbox import SandboxManager, PoolConfig

def test_pool_config_defaults():
    config = PoolConfig()
    assert config.max_ready == 10

@pytest.mark.asyncio
async def test_manager_lifecycle():
    manager = SandboxManager()
    await manager.start()
    assert manager._started
    await manager.shutdown()
```

## CI/CD Integration

For CI pipelines, run the quick tests:

```bash
# Unit tests only (no network)
uv run --extra dev pytest tests/test_manager.py -v

# Functional test 4 only (no network)
uv run python tests/functional/test_04_manager.py
```

For full integration testing:

```bash
# All functional tests
uv run python tests/functional/run_all.py
```
