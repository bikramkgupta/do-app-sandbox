"""
Demand Curve Simulator for SandboxManager Algorithm Testing.

This module provides deterministic demand curve testing for the SandboxManager
pool algorithm. Instead of probabilistic patterns, you define explicit demand
curves and measure how the algorithm performs.

Usage:
    from tests.manager_stress.demand_curves import (
        steady_load,
        sudden_spike,
        run_simulation,
    )

    # Create a demand curve
    curve = steady_load(requests_per_10s=3, duration_seconds=3600)

    # Run simulation
    result = await run_simulation(
        curve=curve,
        pool_config={"python": {"target_ready": 3, "max_sandboxes": 10}},
        max_total_sandboxes=10,
    )

    print(f"Hit rate: {result.hit_rate:.1%}")
"""

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .algorithmic_simulator import AlgorithmicMockManager, SimulatedSandbox


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class DemandPoint:
    """A single point in a demand curve."""

    time_seconds: float  # When this demand occurs (relative to start)
    request_count: int  # Number of requests at this time
    image: str = "python"  # Image type to request


@dataclass
class DemandCurve:
    """
    A demand curve defining request patterns over time.

    Curves are sequences of DemandPoints specifying when requests arrive.
    Use curve generators (steady_load, sudden_spike, etc.) to create curves
    instead of manually specifying each point.
    """

    name: str
    points: list[DemandPoint]
    interval_seconds: float = 10.0  # Time granularity

    @property
    def duration_seconds(self) -> float:
        """Total duration of the curve."""
        if not self.points:
            return 0
        return max(p.time_seconds for p in self.points) + self.interval_seconds

    @property
    def total_requests(self) -> int:
        """Total number of requests in the curve."""
        return sum(p.request_count for p in self.points)


@dataclass
class AcquireEvent:
    """Record of a single sandbox acquisition."""

    request_id: int  # Sequential request number (1, 2, 3...)
    timestamp: float  # When the acquire was requested (simulation seconds)
    image: str  # Image type
    from_pool: bool  # True if served from warm pool (hit)
    wait_time_ms: float  # How long the caller waited
    success: bool = True  # Whether acquisition succeeded
    error: Optional[str] = None
    release_time: float = 0.0  # When sandbox was released (simulation seconds)
    hold_duration: float = 0.0  # How long sandbox was held (seconds)


@dataclass
class PoolSnapshot:
    """State of pools at a point in time."""

    timestamp: float
    python_ready: int = 0
    python_creating: int = 0
    python_in_use: int = 0
    node_ready: int = 0
    node_creating: int = 0
    node_in_use: int = 0
    total_sandboxes: int = 0


@dataclass
class IntervalMetrics:
    """Metrics for a single time interval (for charting)."""

    timestamp: float  # Interval start time
    requests: int  # Requests in this interval
    pool_hits: int  # Pool hits in this interval
    cold_starts: int  # Cold starts in this interval
    hit_rate: float  # Hit rate for this interval (0-1)
    total_sandboxes: int  # Total sandboxes at this point
    active_sandboxes: int = 0  # Currently in-use sandboxes at this interval
    ready_sandboxes: int = 0  # Free/warm sandboxes in pool at this interval
    creating_sandboxes: int = 0  # Sandboxes being created at this interval


@dataclass
class SimulationResult:
    """Results from running a demand curve simulation."""

    # Curve info
    curve_name: str
    duration_seconds: float

    # Summary metrics
    total_requests: int
    successful_acquires: int
    failed_acquires: int
    pool_hits: int  # Served from warm pool
    cold_starts: int  # Had to create on-demand
    hit_rate: float  # pool_hits / successful_acquires
    avg_wait_time_ms: float
    max_wait_time_ms: float
    min_wait_time_ms: float

    # Pool metrics
    max_sandboxes_observed: int
    limit_violations: int

    # Timing configuration used
    cold_start_time_ms: float = 30000.0  # Default 30s
    warm_start_time_ms: float = 50.0  # Default 50ms

    # Detailed data (for debugging)
    events: list[AcquireEvent] = field(default_factory=list)
    snapshots: list[PoolSnapshot] = field(default_factory=list)

    # Per-interval metrics (for charting)
    interval_metrics: list[IntervalMetrics] = field(default_factory=list)


# =============================================================================
# Curve Generators
# =============================================================================


def steady_load(
    requests_per_10s: int,
    duration_seconds: int,
    image: str = "python",
    interval: float = 10.0,
) -> DemandCurve:
    """
    Generate a steady load curve with constant request rate.

    Args:
        requests_per_10s: Number of requests per interval
        duration_seconds: Total duration
        image: Image type to request
        interval: Time interval in seconds (default 10s)

    Example:
        # 8 hours of steady 3 requests per 10 seconds
        curve = steady_load(requests_per_10s=3, duration_seconds=8*3600)
    """
    points = []
    t = 0.0
    while t < duration_seconds:
        points.append(DemandPoint(time_seconds=t, request_count=requests_per_10s, image=image))
        t += interval
    return DemandCurve(name=f"steady_{requests_per_10s}rps_{duration_seconds}s", points=points, interval_seconds=interval)


def sudden_spike(
    baseline: int,
    spike: int,
    spike_at: float,
    spike_duration: float,
    total_duration: float,
    image: str = "python",
    interval: float = 10.0,
) -> DemandCurve:
    """
    Generate a curve with a sudden spike in demand.

    Args:
        baseline: Normal request rate (requests per interval)
        spike: Peak request rate during spike
        spike_at: When spike starts (seconds from start)
        spike_duration: How long spike lasts (seconds)
        total_duration: Total curve duration (seconds)
        image: Image type to request
        interval: Time interval (default 10s)

    Example:
        # 30 min of baseline 2 rps, spike to 15 at 10 min for 2 min
        curve = sudden_spike(
            baseline=2, spike=15,
            spike_at=600, spike_duration=120,
            total_duration=1800
        )
    """
    points = []
    t = 0.0
    spike_end = spike_at + spike_duration
    while t < total_duration:
        if spike_at <= t < spike_end:
            count = spike
        else:
            count = baseline
        points.append(DemandPoint(time_seconds=t, request_count=count, image=image))
        t += interval
    return DemandCurve(
        name=f"spike_{baseline}to{spike}_at{spike_at}s",
        points=points,
        interval_seconds=interval,
    )


def gradual_ramp(
    start_rps: int,
    end_rps: int,
    duration_seconds: float,
    image: str = "python",
    interval: float = 10.0,
) -> DemandCurve:
    """
    Generate a curve with gradually increasing/decreasing load.

    Args:
        start_rps: Starting request rate
        end_rps: Ending request rate
        duration_seconds: Total duration
        image: Image type
        interval: Time interval (default 10s)

    Example:
        # Ramp from 1 to 10 rps over 2 hours
        curve = gradual_ramp(start_rps=1, end_rps=10, duration_seconds=7200)
    """
    points = []
    t = 0.0
    num_intervals = int(duration_seconds / interval)
    while t < duration_seconds:
        progress = t / duration_seconds
        count = int(start_rps + (end_rps - start_rps) * progress)
        points.append(DemandPoint(time_seconds=t, request_count=max(0, count), image=image))
        t += interval
    return DemandCurve(
        name=f"ramp_{start_rps}to{end_rps}_{duration_seconds}s",
        points=points,
        interval_seconds=interval,
    )


def wave_pattern(
    min_rps: int,
    max_rps: int,
    period_seconds: float,
    duration_seconds: float,
    image: str = "python",
    interval: float = 10.0,
) -> DemandCurve:
    """
    Generate a sinusoidal wave pattern (simulates daily traffic cycles).

    Args:
        min_rps: Minimum request rate
        max_rps: Maximum request rate
        period_seconds: How long for one complete wave
        duration_seconds: Total duration
        image: Image type
        interval: Time interval (default 10s)

    Example:
        # Wave between 2-12 rps, one cycle per hour, for 8 hours
        curve = wave_pattern(min_rps=2, max_rps=12, period=3600, duration=28800)
    """
    points = []
    t = 0.0
    amplitude = (max_rps - min_rps) / 2
    center = (max_rps + min_rps) / 2
    while t < duration_seconds:
        # Sinusoidal wave: sin goes from -1 to 1
        wave_value = math.sin(2 * math.pi * t / period_seconds)
        count = int(center + amplitude * wave_value)
        points.append(DemandPoint(time_seconds=t, request_count=max(0, count), image=image))
        t += interval
    return DemandCurve(
        name=f"wave_{min_rps}to{max_rps}_period{period_seconds}s",
        points=points,
        interval_seconds=interval,
    )


def bursty(
    burst_size: int,
    burst_interval_seconds: float,
    quiet_duration_seconds: float,
    total_duration_seconds: float,
    image: str = "python",
    interval: float = 10.0,
) -> DemandCurve:
    """
    Generate a bursty pattern with activity followed by quiet periods.

    Args:
        burst_size: Number of requests during burst
        burst_interval_seconds: How often bursts occur
        quiet_duration_seconds: How long quiet periods last
        total_duration_seconds: Total duration
        image: Image type
        interval: Time interval (default 10s)

    Example:
        # 10 requests every 60s, followed by 30s quiet
        curve = bursty(burst_size=10, burst_interval=60, quiet_duration=30, total_duration=1800)
    """
    points = []
    t = 0.0
    cycle_duration = burst_interval_seconds
    active_duration = burst_interval_seconds - quiet_duration_seconds

    while t < total_duration_seconds:
        # Where are we in the current cycle?
        cycle_pos = t % cycle_duration
        if cycle_pos < active_duration:
            count = burst_size
        else:
            count = 0
        points.append(DemandPoint(time_seconds=t, request_count=count, image=image))
        t += interval

    return DemandCurve(
        name=f"bursty_{burst_size}every{burst_interval_seconds}s",
        points=points,
        interval_seconds=interval,
    )


def random_bounded(
    min_rps: int,
    max_rps: int,
    duration_seconds: float,
    image: str = "python",
    interval: float = 10.0,
    seed: Optional[int] = None,
) -> DemandCurve:
    """
    Generate random demand within bounds (reproducible with seed).

    Args:
        min_rps: Minimum request rate
        max_rps: Maximum request rate
        duration_seconds: Total duration
        image: Image type
        interval: Time interval (default 10s)
        seed: Random seed for reproducibility

    Example:
        # Random 2-8 rps for 2 hours, reproducible
        curve = random_bounded(min_rps=2, max_rps=8, duration=7200, seed=42)
    """
    rng = random.Random(seed)
    points = []
    t = 0.0
    while t < duration_seconds:
        count = rng.randint(min_rps, max_rps)
        points.append(DemandPoint(time_seconds=t, request_count=count, image=image))
        t += interval
    return DemandCurve(
        name=f"random_{min_rps}to{max_rps}_{duration_seconds}s",
        points=points,
        interval_seconds=interval,
    )


def multi_image_curve(
    curves: dict[str, DemandCurve],
) -> DemandCurve:
    """
    Combine curves for different image types into one.

    Args:
        curves: Dict mapping image name to its demand curve

    Example:
        curve = multi_image_curve({
            "python": steady_load(5, 3600),
            "node": bursty(8, 120, 60, 3600),
        })
    """
    all_points = []
    max_duration = 0.0

    for image, curve in curves.items():
        for point in curve.points:
            all_points.append(
                DemandPoint(
                    time_seconds=point.time_seconds,
                    request_count=point.request_count,
                    image=image,
                )
            )
        max_duration = max(max_duration, curve.duration_seconds)

    # Sort by time
    all_points.sort(key=lambda p: p.time_seconds)

    return DemandCurve(
        name=f"multi_image_{len(curves)}_types",
        points=all_points,
        interval_seconds=10.0,  # Default
    )


def composite_curve(
    segments: list[tuple[float, float, DemandCurve]],
) -> DemandCurve:
    """
    Combine multiple curve segments into one.

    Args:
        segments: List of (start_time, end_time, curve) tuples

    Example:
        curve = composite_curve([
            (0, 1800, steady_load(3, 1800)),      # 0-30 min: steady
            (1800, 2100, steady_load(15, 300)),   # 30-35 min: spike
            (2100, 3600, gradual_ramp(15, 3, 1500)),  # 35-60 min: recover
        ])
    """
    all_points = []

    for start, end, curve in segments:
        for point in curve.points:
            # Shift points to their segment's time range
            adjusted_time = start + point.time_seconds
            if adjusted_time >= end:
                break
            all_points.append(
                DemandPoint(
                    time_seconds=adjusted_time,
                    request_count=point.request_count,
                    image=point.image,
                )
            )

    # Sort by time and remove duplicates at same timestamp
    all_points.sort(key=lambda p: (p.time_seconds, p.image))

    return DemandCurve(
        name="composite_curve",
        points=all_points,
        interval_seconds=10.0,
    )


# =============================================================================
# Simulation Engine
# =============================================================================


async def run_simulation(
    curve: DemandCurve,
    pool_config: dict[str, dict[str, Any]],
    max_total_sandboxes: int,
    cold_start_time_seconds: float = 30.0,
    warm_start_time_seconds: float = 0.05,
    min_hold_time_seconds: float = 300.0,
    max_hold_time_seconds: float = 3600.0,
    collect_detailed: bool = True,
    snapshot_interval: float = 10.0,
    time_acceleration: float = 1000.0,
) -> SimulationResult:
    """
    Run a demand curve simulation against the pool algorithm.

    This uses the AlgorithmicMockManager to simulate pool behavior without
    creating real sandboxes. The simulation runs in accelerated time.

    Sandboxes are single-use and disposable:
    - Each sandbox is held for a random duration between min/max hold times
    - When released, the sandbox is destroyed (not returned to pool)
    - Pool replenishment creates NEW sandboxes to maintain target_ready

    Args:
        curve: The demand curve to simulate
        pool_config: Pool configuration dict, e.g.:
            {"python": {"target_ready": 3, "max_sandboxes": 10}}
        max_total_sandboxes: Global sandbox limit
        cold_start_time_seconds: Time to create a new sandbox (default 30s)
        warm_start_time_seconds: Time to acquire from warm pool (default 50ms)
        min_hold_time_seconds: Minimum time sandbox is held before release (default 5 min)
        max_hold_time_seconds: Maximum time sandbox is held before release (default 1 hour)
        collect_detailed: Whether to collect detailed event timeline
        snapshot_interval: How often to snapshot pool state
        time_acceleration: How much faster than real-time to run (default 1000x)

    Returns:
        SimulationResult with metrics and optional detailed data

    Example:
        # Simulate with realistic timing
        result = await run_simulation(
            curve=my_curve,
            pool_config={"python": {"target_ready": 5, "max_sandboxes": 20}},
            max_total_sandboxes=20,
            cold_start_time_seconds=30.0,  # Real-world cold start
            warm_start_time_seconds=0.05,  # 50ms warm start
            min_hold_time_seconds=300.0,   # 5 min minimum hold
            max_hold_time_seconds=1800.0,  # 30 min maximum hold
        )
    """
    # Convert to accelerated simulation time
    sim_cold_start = cold_start_time_seconds / time_acceleration
    sim_warm_start = warm_start_time_seconds / time_acceleration

    # Initialize manager with accelerated timing
    manager = AlgorithmicMockManager(
        pools=pool_config,
        max_total_sandboxes=max_total_sandboxes,
        create_delay=(sim_cold_start * 0.9, sim_cold_start * 1.1),  # ±10% variance
    )

    # Results tracking
    events: list[AcquireEvent] = []
    snapshots: list[PoolSnapshot] = []
    interval_metrics: list[IntervalMetrics] = []

    # Scheduled releases - track by simulation time when each sandbox should be released
    # Format: list of (release_sim_time, sandbox, image)
    scheduled_releases: list[tuple[float, SimulatedSandbox, str]] = []

    def _process_releases(current_sim_time: float):
        """Release all sandboxes whose hold time has expired."""
        nonlocal scheduled_releases
        still_pending = []
        for release_time, sandbox, image in scheduled_releases:
            if release_time <= current_sim_time:
                manager.release(sandbox, image)
            else:
                still_pending.append((release_time, sandbox, image))
        scheduled_releases = still_pending

    # Per-interval tracking
    current_interval_hits = 0
    current_interval_cold = 0
    current_interval_requests = 0
    last_interval_time = 0.0

    # Metrics
    total_requests = 0
    successful = 0
    failed = 0
    pool_hits = 0
    cold_starts = 0
    wait_times: list[float] = []
    request_counter = 0  # Sequential request ID

    try:
        await manager.start()

        # Pre-warm the pool before accepting traffic (mimics real-world usage)
        target_warm = sum(cfg.get('target_ready', 5) for cfg in pool_config.values())
        print(f"Pre-warming pool to {target_warm} sandboxes...")
        try:
            await manager.warm_up(timeout=60.0)
            print(f"  Pool warmed: {target_warm} sandboxes ready")
        except TimeoutError as e:
            print(f"  Warmup warning: {e}")

        # Group points by time to batch concurrent requests
        time_batches: dict[float, list[DemandPoint]] = {}
        for point in curve.points:
            if point.time_seconds not in time_batches:
                time_batches[point.time_seconds] = []
            time_batches[point.time_seconds].append(point)

        sorted_times = sorted(time_batches.keys())
        last_snapshot_time = -snapshot_interval

        for sim_time in sorted_times:
            points = time_batches[sim_time]

            # Process any releases due at or before this simulation time
            _process_releases(sim_time)

            # Record interval metrics when moving to new interval
            if sim_time >= last_interval_time + snapshot_interval:
                if current_interval_requests > 0:
                    interval_hit_rate = current_interval_hits / current_interval_requests
                else:
                    interval_hit_rate = 0.0

                interval_metrics.append(
                    IntervalMetrics(
                        timestamp=last_interval_time,
                        requests=current_interval_requests,
                        pool_hits=current_interval_hits,
                        cold_starts=current_interval_cold,
                        hit_rate=interval_hit_rate,
                        total_sandboxes=manager._total_sandbox_count(),
                        active_sandboxes=manager._total_in_use_count(),
                        ready_sandboxes=manager._total_ready_count(),
                        creating_sandboxes=manager._total_creating_count(),
                    )
                )
                # Reset interval counters
                current_interval_hits = 0
                current_interval_cold = 0
                current_interval_requests = 0
                last_interval_time = sim_time

            # Take snapshot if needed
            if collect_detailed and sim_time - last_snapshot_time >= snapshot_interval:
                snapshot = _take_snapshot(manager, sim_time)
                snapshots.append(snapshot)
                last_snapshot_time = sim_time

            # Process all requests at this time point
            for point in points:
                for _ in range(point.request_count):
                    total_requests += 1
                    current_interval_requests += 1
                    start_time = time.perf_counter()

                    try:
                        sandbox = await manager.acquire(point.image)
                        wait_time_ms = (time.perf_counter() - start_time) * 1000

                        # Track if it was a pool hit
                        from_pool = getattr(sandbox, "_from_pool", False)
                        if from_pool:
                            pool_hits += 1
                            current_interval_hits += 1
                            # Simulate warm start time
                            wait_time_ms = warm_start_time_seconds * 1000
                        else:
                            cold_starts += 1
                            current_interval_cold += 1
                            # Simulate cold start time
                            wait_time_ms = cold_start_time_seconds * 1000

                        successful += 1
                        wait_times.append(wait_time_ms)

                        # Schedule release at future simulation time (random hold duration)
                        hold_duration = random.uniform(min_hold_time_seconds, max_hold_time_seconds)
                        release_sim_time = sim_time + hold_duration
                        scheduled_releases.append((release_sim_time, sandbox, point.image))

                        # Track per-request event
                        request_counter += 1
                        if collect_detailed:
                            events.append(
                                AcquireEvent(
                                    request_id=request_counter,
                                    timestamp=sim_time,
                                    image=point.image,
                                    from_pool=from_pool,
                                    wait_time_ms=wait_time_ms,
                                    success=True,
                                    release_time=release_sim_time,
                                    hold_duration=hold_duration,
                                )
                            )

                    except Exception as e:
                        wait_time_ms = (time.perf_counter() - start_time) * 1000
                        failed += 1
                        current_interval_cold += 1  # Failed counts as cold
                        wait_times.append(wait_time_ms)

                        # Track failed request
                        request_counter += 1
                        if collect_detailed:
                            events.append(
                                AcquireEvent(
                                    request_id=request_counter,
                                    timestamp=sim_time,
                                    image=point.image,
                                    from_pool=False,
                                    wait_time_ms=wait_time_ms,
                                    success=False,
                                    error=str(e),
                                    release_time=0.0,  # Failed requests have no release
                                    hold_duration=0.0,
                                )
                            )

            # Small delay between time intervals (for responsiveness)
            await asyncio.sleep(0.001)

        # Record final interval
        if current_interval_requests > 0:
            interval_metrics.append(
                IntervalMetrics(
                    timestamp=last_interval_time,
                    requests=current_interval_requests,
                    pool_hits=current_interval_hits,
                    cold_starts=current_interval_cold,
                    hit_rate=current_interval_hits / current_interval_requests,
                    total_sandboxes=manager._total_sandbox_count(),
                    active_sandboxes=manager._total_in_use_count(),
                    ready_sandboxes=manager._total_ready_count(),
                    creating_sandboxes=manager._total_creating_count(),
                )
            )

        # Final snapshot
        if collect_detailed:
            final_snapshot = _take_snapshot(manager, curve.duration_seconds)
            snapshots.append(final_snapshot)

    finally:
        # Release any sandboxes that were still scheduled (simulation ended)
        # These are sandboxes whose hold time extends past the simulation duration
        for release_time, sandbox, image in scheduled_releases:
            manager.release(sandbox, image)
        await manager.shutdown()

    # Calculate results
    hit_rate = pool_hits / successful if successful > 0 else 0.0
    avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0
    max_wait = max(wait_times) if wait_times else 0.0
    min_wait = min(wait_times) if wait_times else 0.0

    return SimulationResult(
        curve_name=curve.name,
        duration_seconds=curve.duration_seconds,
        total_requests=total_requests,
        successful_acquires=successful,
        failed_acquires=failed,
        pool_hits=pool_hits,
        cold_starts=cold_starts,
        hit_rate=hit_rate,
        avg_wait_time_ms=avg_wait,
        max_wait_time_ms=max_wait,
        min_wait_time_ms=min_wait,
        max_sandboxes_observed=manager.get_max_observed(),
        limit_violations=len(manager.get_violations()),
        cold_start_time_ms=cold_start_time_seconds * 1000,
        warm_start_time_ms=warm_start_time_seconds * 1000,
        events=events if collect_detailed else [],
        snapshots=snapshots if collect_detailed else [],
        interval_metrics=interval_metrics,
    )


def _take_snapshot(manager: AlgorithmicMockManager, timestamp: float) -> PoolSnapshot:
    """Take a snapshot of current pool state."""
    metrics = manager.metrics()

    python_stats = metrics.get("python")
    node_stats = metrics.get("node")

    return PoolSnapshot(
        timestamp=timestamp,
        python_ready=python_stats.ready if python_stats else 0,
        python_creating=python_stats.creating if python_stats else 0,
        python_in_use=python_stats.in_use if python_stats else 0,
        node_ready=node_stats.ready if node_stats else 0,
        node_creating=node_stats.creating if node_stats else 0,
        node_in_use=node_stats.in_use if node_stats else 0,
        total_sandboxes=manager._total_sandbox_count(),
    )


# =============================================================================
# Convenience Functions
# =============================================================================


def print_result(result: SimulationResult) -> None:
    """Pretty-print simulation results."""
    print(f"\n{'='*60}")
    print(f"Simulation: {result.curve_name}")
    print(f"{'='*60}")
    print(f"Duration: {result.duration_seconds:.0f}s ({result.duration_seconds/60:.1f} min)")
    print(f"\nRequests:")
    print(f"  Total:      {result.total_requests}")
    print(f"  Successful: {result.successful_acquires}")
    print(f"  Failed:     {result.failed_acquires}")
    print(f"\nPool Performance:")
    print(f"  Pool hits:   {result.pool_hits}")
    print(f"  Cold starts: {result.cold_starts}")
    print(f"  Hit rate:    {result.hit_rate:.1%}")
    print(f"\nWait Times:")
    print(f"  Average: {result.avg_wait_time_ms:.1f}ms")
    print(f"  Min:     {result.min_wait_time_ms:.1f}ms")
    print(f"  Max:     {result.max_wait_time_ms:.1f}ms")
    print(f"\nResource Usage:")
    print(f"  Max sandboxes: {result.max_sandboxes_observed}")
    print(f"  Violations:    {result.limit_violations}")
    print(f"{'='*60}\n")


# =============================================================================
# Visualization
# =============================================================================


def generate_chart_html(
    result: SimulationResult,
    output_path: str = "simulation_chart.html",
    title: Optional[str] = None,
) -> str:
    """
    Generate an interactive HTML page with two charts.

    Chart 1: Demand & Performance
    - Stacked bars: Pool Hits (green) + Cold Starts (red) = Total Requests
    - Line: Hit Rate % (right axis)

    Chart 2: Pool State
    - Stacked area: Active (purple) + Ready (green) + Creating (orange)

    Args:
        result: SimulationResult with interval_metrics
        output_path: Where to save the HTML file
        title: Chart title (defaults to curve name)

    Returns:
        Path to the generated HTML file
    """
    if not result.interval_metrics:
        raise ValueError("No interval metrics available. Run simulation with collect_detailed=True")

    chart_title = title or f"Simulation: {result.curve_name}"

    # Prepare data for Chart.js
    labels = []
    requests_data = []
    pool_hits_data = []
    hit_rate_data = []
    cold_starts_data = []
    active_sandboxes_data = []
    ready_sandboxes_data = []
    creating_sandboxes_data = []

    for m in result.interval_metrics:
        # Format time as HH:MM:SS or MM:SS depending on duration
        hours = int(m.timestamp // 3600)
        minutes = int((m.timestamp % 3600) // 60)
        seconds = int(m.timestamp % 60)

        if result.duration_seconds >= 3600:
            labels.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            labels.append(f"{minutes:02d}:{seconds:02d}")

        requests_data.append(m.requests)
        pool_hits_data.append(m.pool_hits)
        # Only show hit rate when there are requests (avoid misleading 0%)
        if m.requests > 0:
            hit_rate_data.append(round(m.hit_rate * 100, 1))
        else:
            hit_rate_data.append(None)  # null in JS = no point shown
        cold_starts_data.append(m.cold_starts)
        active_sandboxes_data.append(m.active_sandboxes)
        ready_sandboxes_data.append(m.ready_sandboxes)
        creating_sandboxes_data.append(m.creating_sandboxes)

    # Calculate summary stats
    avg_hit_rate = result.hit_rate * 100
    total_time_str = _format_duration(result.duration_seconds)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{chart_title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-bottom: 10px;
            font-size: 18px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .stat {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #2563eb;
        }}
        .stat-label {{
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }}
        .chart-container {{
            position: relative;
            height: 350px;
            margin-top: 15px;
        }}
        .config {{
            background: #e8f4fd;
            padding: 10px 15px;
            border-radius: 6px;
            margin-top: 15px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{chart_title}</h1>
        <p>Duration: {total_time_str} | Generated at: <span id="timestamp"></span></p>

        <div class="summary">
            <div class="stat">
                <div class="stat-value">{result.total_requests:,}</div>
                <div class="stat-label">Total Requests</div>
            </div>
            <div class="stat">
                <div class="stat-value">{avg_hit_rate:.1f}%</div>
                <div class="stat-label">Overall Hit Rate</div>
            </div>
            <div class="stat">
                <div class="stat-value">{result.pool_hits:,}</div>
                <div class="stat-label">Pool Hits (Warm)</div>
            </div>
            <div class="stat">
                <div class="stat-value">{result.cold_starts:,}</div>
                <div class="stat-label">Cold Starts</div>
            </div>
            <div class="stat">
                <div class="stat-value">{result.avg_wait_time_ms/1000:.1f}s</div>
                <div class="stat-label">Avg Wait Time</div>
            </div>
            <div class="stat">
                <div class="stat-value">{result.max_sandboxes_observed}</div>
                <div class="stat-label">Max Sandboxes</div>
            </div>
        </div>

        <div class="config">
            <strong>Configuration:</strong>
            Cold start: {result.cold_start_time_ms/1000:.1f}s |
            Warm start: {result.warm_start_time_ms:.0f}ms |
            Intervals: {len(result.interval_metrics)}
        </div>
    </div>

    <!-- Chart 1: Demand & Performance -->
    <div class="container">
        <h2>Chart 1: Demand & Performance</h2>
        <p style="color: #666; font-size: 14px;">Stacked bars show Pool Hits (green) + Cold Starts (red). Line shows Hit Rate %.</p>
        <div class="chart-container">
            <canvas id="demandChart"></canvas>
        </div>
    </div>

    <!-- Chart 2: Pool State -->
    <div class="container">
        <h2>Chart 2: Pool State Over Time</h2>
        <p style="color: #666; font-size: 14px;">Shows Active (in-use), Ready (warm pool), and Creating sandboxes.</p>
        <div class="chart-container">
            <canvas id="poolChart"></canvas>
        </div>
    </div>

    <script>
        document.getElementById('timestamp').textContent = new Date().toLocaleString();

        const labels = {labels};
        const poolHitsData = {pool_hits_data};
        const coldStartsData = {cold_starts_data};
        const hitRateData = {hit_rate_data};
        const activeData = {active_sandboxes_data};
        const readyData = {ready_sandboxes_data};
        const creatingData = {creating_sandboxes_data};

        // Chart 1: Demand & Performance
        const ctx1 = document.getElementById('demandChart').getContext('2d');
        new Chart(ctx1, {{
            type: 'bar',
            data: {{
                labels: labels,
                datasets: [
                    {{
                        label: 'Pool Hits (Warm)',
                        data: poolHitsData,
                        backgroundColor: 'rgba(16, 185, 129, 0.8)',
                        borderColor: 'rgba(16, 185, 129, 1)',
                        borderWidth: 1,
                        stack: 'requests',
                        yAxisID: 'y',
                        order: 2
                    }},
                    {{
                        label: 'Cold Starts',
                        data: coldStartsData,
                        backgroundColor: 'rgba(239, 68, 68, 0.8)',
                        borderColor: 'rgba(239, 68, 68, 1)',
                        borderWidth: 1,
                        stack: 'requests',
                        yAxisID: 'y',
                        order: 3
                    }},
                    {{
                        label: 'Hit Rate %',
                        data: hitRateData,
                        type: 'line',
                        borderColor: 'rgba(59, 130, 246, 1)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 3,
                        fill: false,
                        tension: 0.3,
                        pointRadius: 0,
                        yAxisID: 'y1',
                        spanGaps: true,
                        order: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{
                    mode: 'index',
                    intersect: false,
                }},
                plugins: {{
                    legend: {{
                        position: 'top',
                    }},
                    tooltip: {{
                        callbacks: {{
                            afterBody: function(context) {{
                                const idx = context[0].dataIndex;
                                const total = poolHitsData[idx] + coldStartsData[idx];
                                return 'Total requests: ' + total;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        title: {{ display: true, text: 'Time' }},
                        ticks: {{ maxRotation: 45, autoSkip: true, maxTicksLimit: 30 }}
                    }},
                    y: {{
                        type: 'linear',
                        display: true,
                        position: 'left',
                        stacked: true,
                        title: {{ display: true, text: 'Requests per Interval' }},
                        beginAtZero: true
                    }},
                    y1: {{
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {{ display: true, text: 'Hit Rate %' }},
                        min: 0,
                        max: 100,
                        grid: {{ drawOnChartArea: false }}
                    }}
                }}
            }}
        }});

        // Chart 2: Pool State
        const ctx2 = document.getElementById('poolChart').getContext('2d');
        new Chart(ctx2, {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [
                    {{
                        label: 'Active (In-Use)',
                        data: activeData,
                        borderColor: 'rgba(124, 58, 237, 1)',
                        backgroundColor: 'rgba(124, 58, 237, 0.3)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    }},
                    {{
                        label: 'Ready (Warm Pool)',
                        data: readyData,
                        borderColor: 'rgba(16, 185, 129, 1)',
                        backgroundColor: 'rgba(16, 185, 129, 0.3)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    }},
                    {{
                        label: 'Creating',
                        data: creatingData,
                        borderColor: 'rgba(245, 158, 11, 1)',
                        backgroundColor: 'rgba(245, 158, 11, 0.3)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{
                    mode: 'index',
                    intersect: false,
                }},
                plugins: {{
                    legend: {{
                        position: 'top',
                    }},
                    tooltip: {{
                        callbacks: {{
                            afterBody: function(context) {{
                                const idx = context[0].dataIndex;
                                const total = activeData[idx] + readyData[idx] + creatingData[idx];
                                return 'Total sandboxes: ' + total;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        title: {{ display: true, text: 'Time' }},
                        ticks: {{ maxRotation: 45, autoSkip: true, maxTicksLimit: 30 }}
                    }},
                    y: {{
                        type: 'linear',
                        display: true,
                        title: {{ display: true, text: 'Sandbox Count' }},
                        beginAtZero: true
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""

    # Write to file
    with open(output_path, 'w') as f:
        f.write(html_content)

    return output_path


def _format_duration(seconds: float) -> str:
    """Format duration as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f} seconds"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} minutes"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} hours"


def export_csv(result: SimulationResult, output_path: str = "simulation_log.csv") -> str:
    """
    Export interval metrics to a CSV file for detailed analysis.

    Each row represents one time interval with columns:
    - time: Timestamp in HH:MM:SS format
    - time_seconds: Raw timestamp in seconds
    - requests: Total requests in this interval
    - pool_hits: Requests served from warm pool
    - cold_starts: Requests that required cold start
    - hit_rate: Pool hit percentage (0-100)
    - active: Sandboxes currently in-use
    - ready: Sandboxes in warm pool (available)
    - creating: Sandboxes being created
    - total: Total sandboxes (active + ready + creating)

    Args:
        result: SimulationResult with interval_metrics
        output_path: Where to save the CSV file

    Returns:
        Path to the generated CSV file
    """
    import csv

    if not result.interval_metrics:
        raise ValueError("No interval metrics available")

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'time', 'time_seconds', 'requests', 'pool_hits', 'cold_starts',
            'hit_rate_pct', 'active', 'ready', 'creating', 'total'
        ])

        # Data rows
        for m in result.interval_metrics:
            hours = int(m.timestamp // 3600)
            minutes = int((m.timestamp % 3600) // 60)
            seconds = int(m.timestamp % 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            hit_rate_pct = round(m.hit_rate * 100, 1) if m.requests > 0 else 0.0

            writer.writerow([
                time_str,
                m.timestamp,
                m.requests,
                m.pool_hits,
                m.cold_starts,
                hit_rate_pct,
                m.active_sandboxes,
                m.ready_sandboxes,
                m.creating_sandboxes,
                m.total_sandboxes
            ])

    return output_path


def export_request_log(events: list[AcquireEvent], output_path: str = "simulation_requests.csv") -> str:
    """
    Export per-request log to CSV for detailed analysis.

    Each row represents one sandbox request with columns:
    - request_id: Sequential request number
    - time: When request arrived (HH:MM:SS)
    - time_seconds: Raw timestamp in seconds
    - image: Image type (python, node, etc.)
    - source: "pool_hit" or "cold_start"
    - wait_ms: Time to acquire sandbox
    - success: Whether request succeeded
    - release_time: When sandbox was released (HH:MM:SS)
    - release_seconds: Raw release timestamp
    - hold_duration_s: How long sandbox was held

    Args:
        events: List of AcquireEvent from simulation
        output_path: Where to save the CSV file

    Returns:
        Path to the generated CSV file
    """
    import csv

    if not events:
        raise ValueError("No events to export")

    def format_time(seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'request_id', 'time', 'time_seconds', 'image', 'source',
            'wait_ms', 'success', 'release_time', 'release_seconds', 'hold_duration_s'
        ])

        # Data rows
        for e in events:
            source = "pool_hit" if e.from_pool else "cold_start"
            writer.writerow([
                e.request_id,
                format_time(e.timestamp),
                round(e.timestamp, 1),
                e.image,
                source,
                round(e.wait_time_ms, 1),
                e.success,
                format_time(e.release_time) if e.release_time > 0 else "",
                round(e.release_time, 1) if e.release_time > 0 else "",
                round(e.hold_duration, 1) if e.hold_duration > 0 else ""
            ])

    return output_path


# =============================================================================
# Quick Test
# =============================================================================

if __name__ == "__main__":
    async def quick_demo():
        print("Running demand curve simulation demo...")
        print("=" * 60)

        # Create an 8-hour wave pattern (simulates realistic daily traffic)
        # Using 1-minute intervals for realistic granularity
        curve = wave_pattern(
            min_rps=2,       # 2 requests per minute at low point
            max_rps=6,       # 6 requests per minute at peak
            period_seconds=7200,   # One wave every 2 hours (4 cycles in 8 hours)
            duration_seconds=28800,  # 8 hours
            interval=60.0,   # 1-minute intervals
        )
        print(f"Curve: {curve.name}")
        print(f"Duration: {curve.duration_seconds/3600:.1f} hours ({curve.duration_seconds/60:.0f} minutes)")
        print(f"Total intervals: {len(curve.points)}")
        print(f"Total requests: {curve.total_requests}")

        # Configuration for realistic 8-hour simulation
        # Hold times: 5 minutes to 4 hours (typical for long-running tasks)
        # With avg ~2 hour hold and ~4 req/min, expect ~480 active sandboxes at steady state
        # target_ready=100 provides sufficient buffer for demand bursts
        pool_config = {
            "python": {"target_ready": 100, "max_sandboxes": 600},
        }
        max_total = 600
        cold_start = 30.0     # 30 second cold start
        warm_start = 0.05     # 50ms warm start
        min_hold = 300.0      # 5 minute minimum hold
        max_hold = 14400.0    # 4 hour maximum hold

        # Run simulation with realistic timing
        print("\nRunning simulation with:")
        print(f"  - Cold start time: {cold_start} seconds")
        print(f"  - Warm start time: {warm_start*1000}ms")
        print(f"  - Hold time: {min_hold/60:.0f} min - {max_hold/3600:.0f} hours (random)")
        print(f"  - Pool config: {pool_config}")
        print("\nNOTE: Sandboxes are single-use (destroyed after release)")
        print()

        result = await run_simulation(
            curve=curve,
            pool_config=pool_config,
            max_total_sandboxes=max_total,
            cold_start_time_seconds=cold_start,
            warm_start_time_seconds=warm_start,
            min_hold_time_seconds=min_hold,
            max_hold_time_seconds=max_hold,
            snapshot_interval=60.0,  # 1-minute intervals
        )

        print_result(result)

        # Generate chart and CSV logs
        import os
        artifact_dir = "tests/artifacts"
        os.makedirs(artifact_dir, exist_ok=True)

        chart_path = f"{artifact_dir}/simulation_chart.html"
        csv_path = f"{artifact_dir}/simulation_log.csv"
        requests_path = f"{artifact_dir}/simulation_requests.csv"

        try:
            generate_chart_html(result, chart_path, "8-Hour Sandbox Pool Simulation")
            print(f"Chart generated: {chart_path}")
        except Exception as e:
            print(f"Could not generate chart: {e}")

        try:
            export_csv(result, csv_path)
            print(f"Per-interval CSV log: {csv_path}")
        except Exception as e:
            print(f"Could not generate interval CSV: {e}")

        try:
            export_request_log(result.events, requests_path)
            print(f"Per-request CSV log: {requests_path}")
        except Exception as e:
            print(f"Could not generate request CSV: {e}")

        print("\nOpen the chart in a browser to view interactive charts.")
        print("Open the interval CSV to analyze per-interval metrics.")
        print("Open the request CSV to analyze individual sandbox lifecycles.")

    asyncio.run(quick_demo())
