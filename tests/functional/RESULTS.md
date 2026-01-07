# do-app-sandbox v0.1.4 Functional Test Results

**Test Date:** 2026-01-07
**SDK Version:** 0.1.4
**Overall Status:** ALL TESTS PASSED

---

## Summary

| Test | Description | Status | Duration |
|------|-------------|--------|----------|
| Test 1 | Connect to Existing App | PASS | ~30s |
| Test 2 | Sandbox Creation Benchmark | PASS | 144.4s |
| Test 3 | Basic Sandbox SDK | PASS | 128.6s |
| Test 4 | SandboxManager SDK | PASS | <1s |

**Total Tests Run:** 4 categories, 26 individual test cases
**Pass Rate:** 100%

---

## Test 1: Connect to Existing App and Troubleshoot

Tests the SDK's ability to connect to an existing App Platform app and run diagnostic commands.

**App ID:** `057623bb-7434-4706-bb76-af6834681f33`
**Component:** `debug`
**Status:** PASS

### Diagnostics Retrieved:
- **User:** debuguser
- **Working Dir:** /app
- **OS:** Linux x86_64 GNU/Linux
- **Environment Variables:** 62
- **Files in /app:** scripts, startup.sh

### Commands Tested:
- `whoami` - User identification
- `pwd` - Current directory
- `uname -a` - System information
- `ps aux` - Process listing
- `df -h` - Disk usage
- `env` - Environment variables
- `filesystem.list_dir()` - File operations API

---

## Test 2: Sandbox Creation Benchmark

Tests sandbox creation performance with parallel creates.

**Configuration:**
- Sandboxes: 4 (2 Python, 2 Node)
- Max Concurrent: 2
- Region: syd1
- Instance Size: apps-s-1vcpu-2gb

**Status:** PASS (4/4 successful)

### Timing Results:

| Metric | Time |
|--------|------|
| Min Create | 43.1s |
| Max Create | 94.8s |
| Avg Create | 66.0s |
| Median Create | 79.8s |
| Overall | 144.4s |

### Individual Results:

| # | Image | Create | Exec | Delete | Total |
|---|-------|--------|------|--------|-------|
| 0 | python | 43.1s | 2.6s | 0.5s | 46.3s |
| 1 | node | 46.3s | 6.5s | 0.5s | 53.3s |
| 2 | python | 94.8s | 2.6s | 0.8s | 144.4s |
| 3 | node | 79.8s | 7.3s | 0.7s | 141.1s |

---

## Test 3: Basic Sandbox SDK

Tests core SDK functionality including lifecycle, commands, and file operations.

**Image:** python
**Status:** PASS (10/10 tests)
**Duration:** 128.6s

### Test Cases:

| Test | Status | Duration | Details |
|------|--------|----------|---------|
| create_sandbox | PASS | 54.2s | Created successfully |
| exec_echo | PASS | 1.9s | stdout: hello world |
| exec_exit_code | PASS | <1ms | exit_code: 42 (expected) |
| runtime_version | PASS | 1.8s | Python 3.13.11 |
| write_file | PASS | 5.8s | File written |
| read_file | PASS | 1.8s | Content matches |
| list_dir | PASS | 2.3s | Found 2 files |
| file_exists | PASS | 1.8s | exists: True |
| rm_file | PASS | 1.9s | File removed |
| delete_sandbox | PASS | 0.5s | Deleted successfully |

---

## Test 4: SandboxManager SDK

Tests the pool management functionality (no network calls required).

**Status:** PASS (8/8 tests)
**Duration:** <1ms

### Test Cases:

| Test | Status | Details |
|------|--------|---------|
| poolconfig_defaults | PASS | max_ready=10, target_ready=0 |
| poolconfig_custom | PASS | on_empty=fail, idle_timeout=120 |
| poolconfig_validation | PASS | Correctly rejected invalid on_empty |
| manager_init | PASS | max_total=10 |
| manager_lifecycle | PASS | start/shutdown OK |
| context_manager | PASS | async with works |
| metrics | PASS | 2 pools tracked |
| acquire_fail_mode | PASS | PoolExhaustedError raised |

---

## How to Run Tests

```bash
# Run all tests
uv run python tests/functional/run_all.py

# Run individual tests
uv run python tests/functional/test_01_existing_app.py <APP_ID> <COMPONENT>
uv run python tests/functional/test_02_benchmark.py <COUNT> <CONCURRENT>
uv run python tests/functional/test_03_basic_sdk.py <IMAGE>
uv run python tests/functional/test_04_manager.py

# Skip specific tests
uv run python tests/functional/run_all.py --skip 2

# Run only specific tests
uv run python tests/functional/run_all.py --only 3 4
```

---

## Files

```
tests/functional/
├── __init__.py
├── run_all.py              # Test runner
├── test_01_existing_app.py # Connect to existing app
├── test_02_benchmark.py    # Sandbox creation benchmark
├── test_03_basic_sdk.py    # Basic SDK functionality
├── test_04_manager.py      # SandboxManager tests
├── RESULTS.md              # This file
└── results/
    ├── test_01_result.json
    ├── test_02_result.json
    ├── test_03_result.json
    └── test_04_result.json
```
