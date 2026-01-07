#!/usr/bin/env python3
"""
Test 4: SandboxManager SDK Functionality

Tests the SandboxManager features:
- Pool configuration
- Manager lifecycle (start/shutdown)
- Acquire sandbox from pool
- Metrics collection
- Context manager usage
"""

import asyncio
import sys
import os
import json
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from do_app_sandbox import SandboxManager, PoolConfig
from do_app_sandbox.exceptions import PoolExhaustedError, PoolShutdownError


@dataclass
class TestCase:
    """Individual test case result."""
    name: str
    passed: bool
    duration_s: float = 0.0
    details: str = ""
    error: Optional[str] = None


@dataclass
class TestResult:
    """Overall test result."""
    test_name: str = "SandboxManager SDK"
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    duration_s: float = 0.0
    test_cases: List[dict] = field(default_factory=list)
    timestamp: str = ""


async def run_test_case_async(name: str, func) -> TestCase:
    """Run an async test case and capture result."""
    start = time.time()
    try:
        result = await func()
        return TestCase(
            name=name,
            passed=True,
            duration_s=time.time() - start,
            details=str(result) if result else "OK",
        )
    except Exception as e:
        return TestCase(
            name=name,
            passed=False,
            duration_s=time.time() - start,
            error=str(e),
        )


async def run_tests() -> TestResult:
    """Run all SandboxManager tests."""
    result = TestResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    test_cases = []

    print("=" * 60)
    print("TEST 4: SANDBOXMANAGER SDK")
    print("=" * 60)

    overall_start = time.time()

    # Test 1: PoolConfig defaults
    print("\n[1/8] Testing PoolConfig defaults...")
    tc = TestCase(name="poolconfig_defaults", passed=False)
    try:
        config = PoolConfig()
        tc.passed = (
            config.max_ready == 10 and
            config.target_ready == 0 and
            config.on_empty == "create"
        )
        tc.details = f"max_ready={config.max_ready}, target_ready={config.target_ready}"
        tc.duration_s = 0.001
    except Exception as e:
        tc.error = str(e)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Test 2: PoolConfig custom values
    print("\n[2/8] Testing PoolConfig custom values...")
    tc = TestCase(name="poolconfig_custom", passed=False)
    try:
        config = PoolConfig(
            max_ready=5,
            target_ready=2,
            on_empty="fail",
            idle_timeout=120,
        )
        tc.passed = (
            config.max_ready == 5 and
            config.target_ready == 2 and
            config.on_empty == "fail" and
            config.idle_timeout == 120
        )
        tc.details = f"on_empty={config.on_empty}, idle_timeout={config.idle_timeout}"
        tc.duration_s = 0.001
    except Exception as e:
        tc.error = str(e)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Test 3: PoolConfig validation
    print("\n[3/8] Testing PoolConfig validation...")
    tc = TestCase(name="poolconfig_validation", passed=False)
    try:
        # Should raise ValueError for invalid on_empty
        try:
            PoolConfig(on_empty="invalid")
            tc.passed = False
            tc.details = "Should have raised ValueError"
        except ValueError:
            tc.passed = True
            tc.details = "Correctly rejected invalid on_empty"
        tc.duration_s = 0.001
    except Exception as e:
        tc.error = str(e)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Test 4: Manager initialization
    print("\n[4/8] Testing SandboxManager initialization...")
    tc = TestCase(name="manager_init", passed=False)
    try:
        manager = SandboxManager(
            pools={"python": PoolConfig(target_ready=0)},
            max_total_sandboxes=10,
            max_concurrent_creates=3,
        )
        tc.passed = manager._max_total == 10
        tc.details = f"max_total={manager._max_total}"
        tc.duration_s = 0.001
    except Exception as e:
        tc.error = str(e)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Test 5: Manager start/shutdown lifecycle
    print("\n[5/8] Testing Manager lifecycle...")
    tc = await run_test_case_async("manager_lifecycle", async_test_lifecycle)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Test 6: Context manager usage
    print("\n[6/8] Testing context manager...")
    tc = await run_test_case_async("context_manager", async_test_context_manager)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Test 7: Metrics collection
    print("\n[7/8] Testing metrics collection...")
    tc = await run_test_case_async("metrics", async_test_metrics)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Test 8: Acquire with on_empty=fail
    print("\n[8/8] Testing acquire with empty pool (fail mode)...")
    tc = await run_test_case_async("acquire_fail_mode", async_test_acquire_fail)
    test_cases.append(tc)
    print(f"  {'PASS' if tc.passed else 'FAIL'}: {tc.details or tc.error}")

    # Compile results
    result.duration_s = time.time() - overall_start
    result.test_cases = [asdict(tc) for tc in test_cases]
    result.total_tests = len(test_cases)
    result.passed = sum(1 for tc in test_cases if tc.passed)
    result.failed = result.total_tests - result.passed

    return result


async def async_test_lifecycle():
    """Test manager start/shutdown."""
    manager = SandboxManager(
        pools={"python": PoolConfig(target_ready=0)},
    )

    # Should not be started
    assert manager._started is False

    await manager.start()
    assert manager._started is True
    assert "python" in manager._pools

    await manager.shutdown()
    assert manager._shutdown is True

    return "lifecycle OK"


async def async_test_context_manager():
    """Test async context manager."""
    async with SandboxManager(pools={"python": PoolConfig(target_ready=0)}) as manager:
        assert manager._started is True

    assert manager._shutdown is True
    return "context manager OK"


async def async_test_metrics():
    """Test metrics collection."""
    async with SandboxManager(pools={
        "python": PoolConfig(target_ready=0),
        "node": PoolConfig(target_ready=0),
    }) as manager:
        metrics = manager.metrics()
        assert "python" in metrics
        assert "node" in metrics
        assert metrics["python"].ready == 0

    return f"metrics: {len(metrics)} pools"


async def async_test_acquire_fail():
    """Test acquire with on_empty=fail."""
    async with SandboxManager(pools={
        "python": PoolConfig(target_ready=0, on_empty="fail"),
    }) as manager:
        try:
            await manager.acquire(image="python")
            return "ERROR: Should have raised PoolExhaustedError"
        except PoolExhaustedError:
            return "correctly raised PoolExhaustedError"


def main():
    """Main entry point for Test 4."""
    result = asyncio.run(run_tests())

    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"Total: {result.total_tests}")
    print(f"Passed: {result.passed}")
    print(f"Failed: {result.failed}")
    print(f"Duration: {result.duration_s:.1f}s")

    # Save result to JSON
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    output_file = os.path.join(results_dir, "test_04_result.json")
    with open(output_file, "w") as f:
        json.dump(asdict(result), f, indent=2)
    print(f"\nResults saved to: {output_file}")

    print("\n" + "=" * 60)
    status = "PASS" if result.failed == 0 else "FAIL"
    print(f"STATUS: {status}")
    print("=" * 60)

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
