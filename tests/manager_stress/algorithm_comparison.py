"""Compare adaptive pool sizing algorithms.

Simulates various workload patterns and measures how well each algorithm
adapts to demand while optimizing cost (sandboxes created) and latency.

Usage:
    uv run python -m tests.manager_stress.algorithm_comparison
"""

import random
import math
import time
from dataclasses import dataclass
from typing import Callable

from do_app_sandbox.adaptive_pool import (
    AdaptiveConfig,
    ScalingAlgorithm,
    ScalingMetrics,
    create_pool_sizer,
    PoolSizer,
)


@dataclass
class WorkloadPattern:
    """Defines a workload pattern for simulation."""
    name: str
    description: str
    duration_seconds: int
    rate_function: Callable[[float], float]  # time -> arrival rate


@dataclass
class SimulationResult:
    """Results from running a simulation."""
    algorithm: str
    workload: str

    # Cost metrics
    total_sandbox_seconds: float    # Integral of pool size over time
    max_pool_size: int
    avg_pool_size: float

    # Performance metrics
    total_arrivals: int
    pool_hits: int
    cold_starts: int
    pool_hit_rate: float
    avg_cold_start_latency_ms: float

    # Responsiveness
    scale_up_events: int
    scale_down_events: int
    time_to_scale_up_avg_ms: float  # How fast it reacts to bursts

    # Overall score (lower is better)
    cost_score: float              # Normalized cost
    latency_score: float           # Normalized latency penalty
    combined_score: float


# Workload patterns to test
def create_workload_patterns() -> list[WorkloadPattern]:
    """Create standard workload patterns for testing."""

    def steady_rate(t: float) -> float:
        """Constant arrival rate."""
        return 0.1  # 0.1 per second = 6 per minute

    def burst_pattern(t: float) -> float:
        """Regular bursts every 10 minutes."""
        cycle = t % 600  # 10 minute cycle
        if cycle < 60:  # Burst for 1 minute
            return 1.0  # 60 per minute during burst
        return 0.05  # Very low otherwise

    def diurnal_pattern(t: float) -> float:
        """Day/night cycle (compressed to 1 hour)."""
        # Simulate 24-hour pattern in 1 hour
        hour_of_day = (t / 150) % 24  # 150s = 1 simulated hour
        # Peak at noon (12), trough at midnight (0)
        return 0.05 + 0.15 * math.sin(math.pi * (hour_of_day - 6) / 12) ** 2

    def random_spikes(t: float) -> float:
        """Random unpredictable spikes."""
        base = 0.05
        # Use time as seed for reproducibility
        random.seed(int(t / 30))  # Change every 30 seconds
        if random.random() < 0.1:  # 10% chance of spike
            return base * random.uniform(5, 20)
        return base

    def gradual_ramp(t: float) -> float:
        """Gradual increase over time."""
        return 0.02 + 0.002 * t  # Starts at 0.02, increases

    def step_function(t: float) -> float:
        """Step changes in demand."""
        if t < 300:
            return 0.05
        elif t < 600:
            return 0.2
        elif t < 900:
            return 0.1
        elif t < 1200:
            return 0.5
        else:
            return 0.15

    return [
        WorkloadPattern("steady", "Constant arrival rate", 1800, steady_rate),
        WorkloadPattern("burst", "Regular bursts every 10 min", 3600, burst_pattern),
        WorkloadPattern("diurnal", "Day/night pattern", 3600, diurnal_pattern),
        WorkloadPattern("random_spikes", "Unpredictable spikes", 1800, random_spikes),
        WorkloadPattern("gradual_ramp", "Gradually increasing", 1800, gradual_ramp),
        WorkloadPattern("step_function", "Step changes", 1500, step_function),
    ]


class WorkloadSimulator:
    """Simulates workload and measures algorithm performance."""

    def __init__(
        self,
        creation_latency_ms: float = 60000,  # 60s sandbox creation
        seed: int = 42
    ):
        self.creation_latency_ms = creation_latency_ms
        self.rng = random.Random(seed)

    def _poisson(self, lam: float) -> int:
        """Generate Poisson-distributed random number."""
        if lam <= 0:
            return 0
        # Knuth algorithm for small lambda
        if lam < 30:
            L = math.exp(-lam)
            k = 0
            p = 1.0
            while p > L:
                k += 1
                p *= self.rng.random()
            return k - 1
        # Normal approximation for large lambda
        return max(0, int(lam + self.rng.gauss(0, math.sqrt(lam))))

    def run_simulation(
        self,
        sizer: PoolSizer,
        workload: WorkloadPattern,
        algorithm_name: str
    ) -> SimulationResult:
        """Run a complete simulation."""
        # State tracking
        pool_size = 0
        in_use = 0
        total_sandbox_seconds = 0.0
        pool_sizes = []

        total_arrivals = 0
        pool_hits = 0
        cold_starts = 0

        scale_up_events = 0
        scale_down_events = 0
        last_target = 0
        scale_up_times = []

        # Run simulation at 1-second resolution
        dt = 1.0
        current_time = 0.0

        while current_time < workload.duration_seconds:
            # Get arrival rate for this time
            rate = workload.rate_function(current_time)

            # Generate arrivals (Poisson process)
            expected_arrivals = rate * dt
            arrivals = self._poisson(expected_arrivals)

            # Record events
            for _ in range(arrivals):
                sizer.record_event("acquire", current_time)
                total_arrivals += 1

                # Determine if pool hit or cold start
                if pool_size > 0:
                    pool_hits += 1
                    pool_size -= 1
                    in_use += 1
                else:
                    cold_starts += 1
                    in_use += 1

            # Release some sandboxes (average 2-minute usage)
            releases = self._poisson(in_use * dt / 120)
            releases = min(releases, in_use)
            in_use -= releases

            # Get scaling decision
            metrics = ScalingMetrics(
                timestamp=current_time,
                arrival_rate=rate,
                pool_hit_rate=pool_hits / max(1, total_arrivals),
                avg_latency_ms=100 if pool_size > 0 else self.creation_latency_ms,
                current_ready=pool_size,
                current_in_use=in_use,
                cold_start_rate=cold_starts / max(1, current_time)
            )

            decision = sizer.calculate_target(metrics)
            new_target = decision.target_ready

            # Track scale events
            if new_target > last_target:
                scale_up_events += 1
                if rate > workload.rate_function(current_time - 60):  # Rate increased
                    scale_up_times.append(current_time)
            elif new_target < last_target:
                scale_down_events += 1
            last_target = new_target

            # Adjust pool (simplified: instant scaling)
            pool_size = max(0, new_target - in_use)

            # Track metrics
            total_sandbox_seconds += (pool_size + in_use) * dt
            pool_sizes.append(pool_size + in_use)

            current_time += dt

        # Calculate results
        max_pool = max(pool_sizes) if pool_sizes else 0
        avg_pool = sum(pool_sizes) / len(pool_sizes) if pool_sizes else 0
        hit_rate = pool_hits / max(1, total_arrivals)

        # Cost score (normalized to 0-100)
        cost_score = total_sandbox_seconds / workload.duration_seconds

        # Latency score (penalize cold starts)
        latency_penalty = cold_starts * self.creation_latency_ms / 1000  # In seconds
        latency_score = latency_penalty / max(1, total_arrivals)

        # Combined score (weighted)
        # Lower is better: cost matters, but latency matters more
        combined = cost_score * 0.3 + latency_score * 0.7 * 10

        return SimulationResult(
            algorithm=algorithm_name,
            workload=workload.name,
            total_sandbox_seconds=total_sandbox_seconds,
            max_pool_size=max_pool,
            avg_pool_size=avg_pool,
            total_arrivals=total_arrivals,
            pool_hits=pool_hits,
            cold_starts=cold_starts,
            pool_hit_rate=hit_rate,
            avg_cold_start_latency_ms=self.creation_latency_ms,
            scale_up_events=scale_up_events,
            scale_down_events=scale_down_events,
            time_to_scale_up_avg_ms=0,  # Would need more detailed tracking
            cost_score=cost_score,
            latency_score=latency_score,
            combined_score=combined,
        )


def run_comparison() -> dict[str, list[SimulationResult]]:
    """Run comparison across all algorithms and workloads."""
    algorithms = [
        (ScalingAlgorithm.FIXED, "Fixed (target=10)"),
        (ScalingAlgorithm.EMA, "EMA"),
        (ScalingAlgorithm.PID, "PID Controller"),
        (ScalingAlgorithm.PREDICTIVE, "Predictive"),
        (ScalingAlgorithm.QUEUING, "Queuing Theory"),
        (ScalingAlgorithm.HYBRID, "Hybrid Adaptive"),
    ]

    workloads = create_workload_patterns()

    config = AdaptiveConfig(
        min_ready=1,
        max_ready=50,
        target_hit_rate=0.9,
        target_latency_ms=500,
    )

    simulator = WorkloadSimulator(seed=42)
    results: dict[str, list[SimulationResult]] = {name: [] for _, name in algorithms}

    print("=" * 80)
    print("ADAPTIVE POOL ALGORITHM COMPARISON")
    print("=" * 80)
    print()

    for workload in workloads:
        print(f"\n{'='*60}")
        print(f"Workload: {workload.name} - {workload.description}")
        print(f"Duration: {workload.duration_seconds}s")
        print(f"{'='*60}")
        print()
        print(f"{'Algorithm':<20} {'Hit Rate':>10} {'Cold Starts':>12} {'Avg Pool':>10} {'Cost':>10} {'Score':>10}")
        print("-" * 72)

        for algo_type, algo_name in algorithms:
            sizer = create_pool_sizer(algo_type, config, fixed_target=10)
            result = simulator.run_simulation(sizer, workload, algo_name)
            results[algo_name].append(result)

            print(f"{algo_name:<20} {result.pool_hit_rate:>9.1%} {result.cold_starts:>12} "
                  f"{result.avg_pool_size:>10.1f} {result.cost_score:>10.1f} {result.combined_score:>10.2f}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: Average Scores Across All Workloads (lower is better)")
    print("=" * 80)
    print()
    print(f"{'Algorithm':<20} {'Avg Hit Rate':>12} {'Avg Cost':>12} {'Avg Score':>12}")
    print("-" * 56)

    summary = []
    for algo_name, algo_results in results.items():
        avg_hit = sum(r.pool_hit_rate for r in algo_results) / len(algo_results)
        avg_cost = sum(r.cost_score for r in algo_results) / len(algo_results)
        avg_score = sum(r.combined_score for r in algo_results) / len(algo_results)
        summary.append((algo_name, avg_hit, avg_cost, avg_score))

    # Sort by score (lower is better)
    summary.sort(key=lambda x: x[3])

    for rank, (name, hit, cost, score) in enumerate(summary, 1):
        marker = " ← BEST" if rank == 1 else ""
        print(f"{name:<20} {hit:>11.1%} {cost:>12.1f} {score:>12.2f}{marker}")

    return results


def recommend_algorithm(workload_type: str) -> str:
    """Recommend the best algorithm for a given workload type."""
    recommendations = {
        "steady": "EMA or Fixed - Simple workloads don't need complex algorithms",
        "burst": "Hybrid - Combines prediction with reactive burst handling",
        "diurnal": "Predictive - Historical patterns help anticipate demand",
        "random_spikes": "PID or EMA - React quickly to unpredictable changes",
        "gradual_ramp": "EMA - Smooth tracking of gradual changes",
        "step_function": "PID - Fast response to discrete changes",
        "mixed": "Hybrid - Best all-around performance",
    }
    return recommendations.get(workload_type, "Hybrid - Safe default choice")


if __name__ == "__main__":
    results = run_comparison()

    print("\n" + "=" * 80)
    print("RECOMMENDATIONS BY WORKLOAD TYPE")
    print("=" * 80)
    for pattern in create_workload_patterns():
        print(f"\n{pattern.name}: {recommend_algorithm(pattern.name)}")

    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    print("""
For production 500-sandbox pools with bursty workloads:

1. **Hybrid Adaptive** is recommended for most cases:
   - Combines time-series prediction (handles known patterns)
   - With reactive EMA scaling (handles unexpected bursts)
   - Asymmetric scaling: fast up, slow down

2. **Key parameters to tune:**
   - min_ready: Minimum pool size (cost floor)
   - ema_alpha: Reactivity (0.3 = balanced, 0.5 = very reactive)
   - base_capacity_ratio: How much to trust predictions

3. **Cost optimization:**
   - Scale down slowly (5 min cooldown)
   - Don't maintain 500 sandboxes 24/7
   - Target 70-80% pool hit rate (allows some cold starts)
""")
