"""
Metrics collection module for SandboxManager stress tests.

Collects time-series metrics from the SandboxManager and task results.
Includes system metrics (memory, FDs, asyncio tasks) for long-running tests.
"""

import asyncio
import csv
import gc
import json
import os
import resource
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import threading


@dataclass
class SystemSnapshot:
    """System-level metrics for long-running tests."""
    timestamp: float
    elapsed_seconds: float

    # Memory metrics (in MB)
    process_rss_mb: float = 0.0          # Resident Set Size
    process_vms_mb: float = 0.0          # Virtual Memory Size
    process_data_mb: float = 0.0         # Data segment size

    # File descriptors
    fd_count: int = 0                    # Open file descriptors
    fd_soft_limit: int = 0               # Soft limit
    fd_hard_limit: int = 0               # Hard limit

    # Asyncio metrics
    asyncio_task_count: int = 0          # Active asyncio tasks
    asyncio_running_task_count: int = 0  # Currently running tasks

    # GC metrics
    gc_gen0_collections: int = 0
    gc_gen1_collections: int = 0
    gc_gen2_collections: int = 0
    gc_objects_tracked: int = 0          # Objects tracked by GC

    # Event loop metrics (if available)
    event_loop_lag_ms: float = 0.0       # Event loop responsiveness


@dataclass
class PoolSnapshot:
    """Snapshot of pool state at a point in time."""
    timestamp: float
    elapsed_seconds: float

    # Pool counts
    python_ready: int = 0
    python_creating: int = 0
    python_in_use: int = 0
    node_ready: int = 0
    node_creating: int = 0
    node_in_use: int = 0

    # Totals
    total_sandboxes: int = 0
    total_ready: int = 0
    total_creating: int = 0
    total_in_use: int = 0

    # Cumulative counters
    total_acquires: int = 0
    pool_hits: int = 0
    cold_starts: int = 0
    scale_up_events: int = 0
    scale_down_events: int = 0
    failed_creates: int = 0
    health_check_removals: int = 0

    # Derived metrics
    pool_hit_rate: float = 0.0
    avg_acquire_latency_ms: float = 0.0


@dataclass
class TaskResult:
    """Result of a single task execution."""
    task_id: str
    user_id: str
    user_group: str
    image: str
    program: str
    category: str

    # Timing
    started_at: float
    ended_at: float
    acquire_latency_ms: float
    execution_duration_s: float

    # Status
    success: bool
    from_pool: bool
    error: Optional[str] = None

    # Program output
    program_output: dict = field(default_factory=dict)


@dataclass
class TestSummary:
    """Summary of entire test run."""
    scenario_name: str
    started_at: str
    ended_at: str
    duration_seconds: float

    # Task stats
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 0.0

    # Acquisition stats
    total_acquires: int = 0
    pool_hits: int = 0
    cold_starts: int = 0
    pool_hit_rate: float = 0.0

    # Latency stats
    avg_acquire_latency_ms: float = 0.0
    avg_pool_hit_latency_ms: float = 0.0
    avg_cold_start_latency_ms: float = 0.0
    min_acquire_latency_ms: float = 0.0
    max_acquire_latency_ms: float = 0.0
    p50_acquire_latency_ms: float = 0.0
    p95_acquire_latency_ms: float = 0.0
    p99_acquire_latency_ms: float = 0.0

    # Concurrency stats
    max_concurrent_sandboxes: int = 0
    max_concurrent_python: int = 0
    max_concurrent_node: int = 0

    # Scale events
    scale_up_events: int = 0
    scale_down_events: int = 0

    # By category
    tasks_by_category: dict = field(default_factory=dict)
    tasks_by_image: dict = field(default_factory=dict)
    tasks_by_user_group: dict = field(default_factory=dict)

    # System metrics (for leak detection)
    start_rss_mb: float = 0.0
    end_rss_mb: float = 0.0
    rss_growth_mb: float = 0.0
    rss_growth_percent: float = 0.0
    max_rss_mb: float = 0.0
    start_fd_count: int = 0
    end_fd_count: int = 0
    max_fd_count: int = 0
    max_asyncio_tasks: int = 0

    # Invariant violations (corner case detection)
    invariant_violations: list = field(default_factory=list)


class MetricsCollector:
    """Collects and stores metrics during stress test execution."""

    def __init__(self, scenario_name: str, output_dir: Path):
        self.scenario_name = scenario_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.start_time = time.time()
        self.snapshots: list[PoolSnapshot] = []
        self.system_snapshots: list[SystemSnapshot] = []
        self.task_results: list[TaskResult] = []
        self.invariant_violations: list[dict] = []

        # Cumulative counters (thread-safe)
        self._lock = threading.Lock()
        self._total_acquires = 0
        self._pool_hits = 0
        self._cold_starts = 0
        self._scale_up_events = 0
        self._scale_down_events = 0
        self._failed_creates = 0
        self._health_check_removals = 0
        self._acquire_latencies: list[float] = []
        self._pool_hit_latencies: list[float] = []
        self._cold_start_latencies: list[float] = []

        # Generate timestamp for file names
        self._timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        # Capture baseline system metrics
        self._baseline_system = self._capture_system_metrics()
        self._last_event_loop_check = time.time()

    def record_acquire(self, latency_ms: float, from_pool: bool):
        """Record a sandbox acquisition."""
        with self._lock:
            self._total_acquires += 1
            self._acquire_latencies.append(latency_ms)
            if from_pool:
                self._pool_hits += 1
                self._pool_hit_latencies.append(latency_ms)
            else:
                self._cold_starts += 1
                self._cold_start_latencies.append(latency_ms)

    def record_scale_up(self):
        """Record a scale-up event."""
        with self._lock:
            self._scale_up_events += 1

    def record_scale_down(self):
        """Record a scale-down event."""
        with self._lock:
            self._scale_down_events += 1

    def record_failed_create(self):
        """Record a failed sandbox creation."""
        with self._lock:
            self._failed_creates += 1

    def record_health_check_removal(self):
        """Record a sandbox removed by health check."""
        with self._lock:
            self._health_check_removals += 1

    def record_invariant_violation(self, violation: str, context: dict = None):
        """Record an invariant violation (corner case detection)."""
        with self._lock:
            self.invariant_violations.append({
                'timestamp': time.time(),
                'elapsed_seconds': time.time() - self.start_time,
                'violation': violation,
                'context': context or {},
            })

    def _capture_system_metrics(self) -> dict:
        """Capture current system metrics."""
        # Memory from /proc/self/status or resource module
        try:
            rusage = resource.getrusage(resource.RUSAGE_SELF)
            rss_mb = rusage.ru_maxrss / 1024  # Convert KB to MB on Linux
        except Exception:
            rss_mb = 0.0

        # Try to get more detailed memory from /proc
        vms_mb = 0.0
        data_mb = 0.0
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        rss_mb = int(line.split()[1]) / 1024
                    elif line.startswith('VmSize:'):
                        vms_mb = int(line.split()[1]) / 1024
                    elif line.startswith('VmData:'):
                        data_mb = int(line.split()[1]) / 1024
        except Exception:
            pass

        # File descriptors
        fd_count = 0
        try:
            fd_count = len(os.listdir('/proc/self/fd'))
        except Exception:
            pass

        fd_soft, fd_hard = 1024, 1024
        try:
            fd_soft, fd_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        except Exception:
            pass

        # Asyncio tasks
        task_count = 0
        running_count = 0
        try:
            all_tasks = asyncio.all_tasks()
            task_count = len(all_tasks)
            running_count = sum(1 for t in all_tasks if not t.done())
        except Exception:
            pass

        # GC stats
        gc_stats = gc.get_stats()
        gc_counts = gc.get_count()

        return {
            'rss_mb': rss_mb,
            'vms_mb': vms_mb,
            'data_mb': data_mb,
            'fd_count': fd_count,
            'fd_soft_limit': fd_soft,
            'fd_hard_limit': fd_hard,
            'asyncio_task_count': task_count,
            'asyncio_running_task_count': running_count,
            'gc_gen0_collections': gc_stats[0]['collections'] if gc_stats else 0,
            'gc_gen1_collections': gc_stats[1]['collections'] if len(gc_stats) > 1 else 0,
            'gc_gen2_collections': gc_stats[2]['collections'] if len(gc_stats) > 2 else 0,
            'gc_objects_tracked': sum(gc_counts),
        }

    async def _measure_event_loop_lag(self) -> float:
        """Measure event loop lag (responsiveness)."""
        start = time.time()
        await asyncio.sleep(0)  # Yield to event loop
        return (time.time() - start) * 1000  # Convert to ms

    def take_system_snapshot(self) -> SystemSnapshot:
        """Take a snapshot of system metrics."""
        now = time.time()
        elapsed = now - self.start_time
        metrics = self._capture_system_metrics()

        snapshot = SystemSnapshot(
            timestamp=now,
            elapsed_seconds=elapsed,
            process_rss_mb=metrics['rss_mb'],
            process_vms_mb=metrics['vms_mb'],
            process_data_mb=metrics['data_mb'],
            fd_count=metrics['fd_count'],
            fd_soft_limit=metrics['fd_soft_limit'],
            fd_hard_limit=metrics['fd_hard_limit'],
            asyncio_task_count=metrics['asyncio_task_count'],
            asyncio_running_task_count=metrics['asyncio_running_task_count'],
            gc_gen0_collections=metrics['gc_gen0_collections'],
            gc_gen1_collections=metrics['gc_gen1_collections'],
            gc_gen2_collections=metrics['gc_gen2_collections'],
            gc_objects_tracked=metrics['gc_objects_tracked'],
            event_loop_lag_ms=0.0,  # Filled by async caller if needed
        )

        with self._lock:
            self.system_snapshots.append(snapshot)

        return snapshot

    def record_task_result(self, result: TaskResult):
        """Record a task completion."""
        with self._lock:
            self.task_results.append(result)

    def take_snapshot(self, manager) -> PoolSnapshot:
        """Take a snapshot of current pool state."""
        now = time.time()
        elapsed = now - self.start_time

        # Get pool states from manager
        # This assumes manager has a get_pool_stats() method or similar
        try:
            stats = manager.get_stats() if hasattr(manager, 'get_stats') else {}
        except Exception:
            stats = {}

        with self._lock:
            pool_hit_rate = (
                self._pool_hits / self._total_acquires * 100
                if self._total_acquires > 0 else 0.0
            )
            avg_latency = (
                sum(self._acquire_latencies) / len(self._acquire_latencies)
                if self._acquire_latencies else 0.0
            )

            snapshot = PoolSnapshot(
                timestamp=now,
                elapsed_seconds=elapsed,
                python_ready=stats.get('python_ready', 0),
                python_creating=stats.get('python_creating', 0),
                python_in_use=stats.get('python_in_use', 0),
                node_ready=stats.get('node_ready', 0),
                node_creating=stats.get('node_creating', 0),
                node_in_use=stats.get('node_in_use', 0),
                total_sandboxes=stats.get('total_sandboxes', 0),
                total_ready=stats.get('python_ready', 0) + stats.get('node_ready', 0),
                total_creating=stats.get('python_creating', 0) + stats.get('node_creating', 0),
                total_in_use=stats.get('python_in_use', 0) + stats.get('node_in_use', 0),
                total_acquires=self._total_acquires,
                pool_hits=self._pool_hits,
                cold_starts=self._cold_starts,
                scale_up_events=self._scale_up_events,
                scale_down_events=self._scale_down_events,
                failed_creates=self._failed_creates,
                health_check_removals=self._health_check_removals,
                pool_hit_rate=pool_hit_rate,
                avg_acquire_latency_ms=avg_latency,
            )

            self.snapshots.append(snapshot)
            return snapshot

    def calculate_percentile(self, values: list[float], percentile: float) -> float:
        """Calculate percentile from list of values."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * (percentile / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_values) else f
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f]) if f != c else sorted_values[f]

    def generate_summary(self) -> TestSummary:
        """Generate test summary from collected data."""
        end_time = time.time()

        with self._lock:
            # Basic stats
            total_tasks = len(self.task_results)
            successful = sum(1 for r in self.task_results if r.success)
            failed = total_tasks - successful

            # Latency stats
            latencies = self._acquire_latencies.copy()
            pool_latencies = self._pool_hit_latencies.copy()
            cold_latencies = self._cold_start_latencies.copy()

            # Concurrency stats from snapshots
            max_total = max((s.total_sandboxes for s in self.snapshots), default=0)
            max_python = max((s.python_ready + s.python_creating + s.python_in_use for s in self.snapshots), default=0)
            max_node = max((s.node_ready + s.node_creating + s.node_in_use for s in self.snapshots), default=0)

            # By category/image/group
            by_category: dict[str, dict] = {}
            by_image: dict[str, dict] = {}
            by_group: dict[str, dict] = {}

            for result in self.task_results:
                # By category
                if result.category not in by_category:
                    by_category[result.category] = {'total': 0, 'success': 0}
                by_category[result.category]['total'] += 1
                if result.success:
                    by_category[result.category]['success'] += 1

                # By image
                if result.image not in by_image:
                    by_image[result.image] = {'total': 0, 'success': 0}
                by_image[result.image]['total'] += 1
                if result.success:
                    by_image[result.image]['success'] += 1

                # By user group
                if result.user_group not in by_group:
                    by_group[result.user_group] = {'total': 0, 'success': 0}
                by_group[result.user_group]['total'] += 1
                if result.success:
                    by_group[result.user_group]['success'] += 1

            # System metrics for leak detection
            start_rss = self._baseline_system.get('rss_mb', 0.0)
            end_metrics = self._capture_system_metrics()
            end_rss = end_metrics.get('rss_mb', 0.0)
            max_rss = max((s.process_rss_mb for s in self.system_snapshots), default=start_rss)
            max_fd = max((s.fd_count for s in self.system_snapshots), default=0)
            max_tasks = max((s.asyncio_task_count for s in self.system_snapshots), default=0)

            rss_growth = end_rss - start_rss
            rss_growth_pct = (rss_growth / start_rss * 100) if start_rss > 0 else 0.0

            summary = TestSummary(
                scenario_name=self.scenario_name,
                started_at=datetime.fromtimestamp(self.start_time).isoformat(),
                ended_at=datetime.fromtimestamp(end_time).isoformat(),
                duration_seconds=end_time - self.start_time,
                total_tasks=total_tasks,
                successful_tasks=successful,
                failed_tasks=failed,
                success_rate=successful / total_tasks * 100 if total_tasks > 0 else 0.0,
                total_acquires=self._total_acquires,
                pool_hits=self._pool_hits,
                cold_starts=self._cold_starts,
                pool_hit_rate=self._pool_hits / self._total_acquires * 100 if self._total_acquires > 0 else 0.0,
                avg_acquire_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
                avg_pool_hit_latency_ms=sum(pool_latencies) / len(pool_latencies) if pool_latencies else 0.0,
                avg_cold_start_latency_ms=sum(cold_latencies) / len(cold_latencies) if cold_latencies else 0.0,
                min_acquire_latency_ms=min(latencies) if latencies else 0.0,
                max_acquire_latency_ms=max(latencies) if latencies else 0.0,
                p50_acquire_latency_ms=self.calculate_percentile(latencies, 50),
                p95_acquire_latency_ms=self.calculate_percentile(latencies, 95),
                p99_acquire_latency_ms=self.calculate_percentile(latencies, 99),
                max_concurrent_sandboxes=max_total,
                max_concurrent_python=max_python,
                max_concurrent_node=max_node,
                scale_up_events=self._scale_up_events,
                scale_down_events=self._scale_down_events,
                tasks_by_category=by_category,
                tasks_by_image=by_image,
                tasks_by_user_group=by_group,
                # System metrics
                start_rss_mb=start_rss,
                end_rss_mb=end_rss,
                rss_growth_mb=rss_growth,
                rss_growth_percent=rss_growth_pct,
                max_rss_mb=max_rss,
                start_fd_count=self._baseline_system.get('fd_count', 0),
                end_fd_count=end_metrics.get('fd_count', 0),
                max_fd_count=max_fd,
                max_asyncio_tasks=max_tasks,
                invariant_violations=self.invariant_violations.copy(),
            )

            return summary

    def save_metrics_csv(self) -> Path:
        """Save time-series metrics to CSV."""
        filepath = self.output_dir / f"metrics_{self._timestamp}.csv"

        with open(filepath, 'w', newline='') as f:
            if self.snapshots:
                fieldnames = list(asdict(self.snapshots[0]).keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for snapshot in self.snapshots:
                    writer.writerow(asdict(snapshot))

        return filepath

    def save_tasks_json(self) -> Path:
        """Save task results to JSON."""
        filepath = self.output_dir / f"tasks_{self._timestamp}.json"

        with open(filepath, 'w') as f:
            json.dump([asdict(r) for r in self.task_results], f, indent=2)

        return filepath

    def save_summary_json(self) -> Path:
        """Save test summary to JSON."""
        filepath = self.output_dir / f"summary_{self._timestamp}.json"
        summary = self.generate_summary()

        with open(filepath, 'w') as f:
            json.dump(asdict(summary), f, indent=2)

        return filepath

    def save_system_csv(self) -> Path:
        """Save system metrics time-series to CSV."""
        filepath = self.output_dir / f"system_{self._timestamp}.csv"

        with open(filepath, 'w', newline='') as f:
            if self.system_snapshots:
                fieldnames = list(asdict(self.system_snapshots[0]).keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for snapshot in self.system_snapshots:
                    writer.writerow(asdict(snapshot))

        return filepath

    def save_violations_json(self) -> Path:
        """Save invariant violations to JSON."""
        filepath = self.output_dir / f"violations_{self._timestamp}.json"

        with open(filepath, 'w') as f:
            json.dump(self.invariant_violations, f, indent=2)

        return filepath

    def save_all(self) -> dict[str, Path]:
        """Save all metrics files."""
        return {
            'metrics_csv': self.save_metrics_csv(),
            'system_csv': self.save_system_csv(),
            'tasks_json': self.save_tasks_json(),
            'summary_json': self.save_summary_json(),
            'violations_json': self.save_violations_json(),
        }
