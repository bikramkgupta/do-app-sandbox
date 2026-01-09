"""
Metrics collection and aggregation for rigorous pool testing.
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .session import SessionResult
from .utils import percentile

logger = logging.getLogger("rigorous_pool_test")


@dataclass
class PoolSnapshot:
    """Snapshot of pool state at a point in time."""

    timestamp: datetime
    image: str
    ready: int
    creating: int
    in_use: int
    total: int


@dataclass
class WatchdogMetrics:
    """Metrics from the external watchdog."""

    enabled: bool = True
    violation_detected: bool = False
    max_observed_via_doctl: int = 0
    total_checks: int = 0
    emergency_deletions: int = 0


@dataclass
class TestSummary:
    """Final summary of the test run."""

    test_name: str = "rigorous_pool_test"
    passed: bool = True
    duration_seconds: float = 0
    total_sessions: int = 0
    total_commands: int = 0
    total_command_failures: int = 0

    # Pool metrics
    pool_hit_rate_overall: float = 0.0
    pool_hit_rate_by_image: Dict[str, float] = field(default_factory=dict)
    cold_start_count: int = 0
    failed_creates: int = 0

    # Latency percentiles
    acquire_latency_ms_p50: float = 0.0
    acquire_latency_ms_p90: float = 0.0
    acquire_latency_ms_p99: float = 0.0
    acquire_latency_pool_p50: float = 0.0
    acquire_latency_pool_p90: float = 0.0
    acquire_latency_cold_p50: float = 0.0
    acquire_latency_cold_p90: float = 0.0

    # Capacity
    max_total_sandboxes_observed: int = 0
    capacity_violations: int = 0
    leaked_sandboxes: int = 0

    # Watchdog
    watchdog: WatchdogMetrics = field(default_factory=WatchdogMetrics)

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class MetricsCollector:
    """Thread-safe metrics collection and aggregation."""

    def __init__(self, max_total: int = 25):
        self.max_total = max_total
        self._lock = threading.Lock()
        self._sessions: List[SessionResult] = []
        self._pool_snapshots: List[PoolSnapshot] = []
        self._max_observed_total: int = 0
        self._capacity_violations: int = 0
        self._failed_creates: int = 0
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None

    def start(self):
        """Mark test start time."""
        self._start_time = datetime.now()

    def stop(self):
        """Mark test end time."""
        self._end_time = datetime.now()

    def add_session(self, result: SessionResult):
        """Add a completed session result."""
        with self._lock:
            self._sessions.append(result)

    def record_pool_snapshot(
        self,
        pool_metrics: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ):
        """
        Record a snapshot of pool state.

        Args:
            pool_metrics: Output from manager.metrics()
            timestamp: Optional timestamp (uses now if not provided)
        """
        if timestamp is None:
            timestamp = datetime.now()

        with self._lock:
            total_all = 0

            for image, metrics in pool_metrics.items():
                ready = getattr(metrics, "ready", 0)
                creating = getattr(metrics, "creating", 0)
                in_use = getattr(metrics, "in_use", 0)
                total = ready + creating + in_use
                total_all += total

                snapshot = PoolSnapshot(
                    timestamp=timestamp,
                    image=image,
                    ready=ready,
                    creating=creating,
                    in_use=in_use,
                    total=total,
                )
                self._pool_snapshots.append(snapshot)

                # Track failed creates
                failed = getattr(metrics, "failed_creates", 0)
                if failed > self._failed_creates:
                    self._failed_creates = failed

            # Track max observed
            if total_all > self._max_observed_total:
                self._max_observed_total = total_all

            # Check capacity violation
            if total_all > self.max_total:
                self._capacity_violations += 1
                logger.critical(
                    f"CAPACITY VIOLATION: {total_all} sandboxes (limit: {self.max_total})"
                )

    async def sample_pool_metrics(
        self,
        manager: Any,
        interval: float = 5.0,
        stop_event: asyncio.Event = None,
    ):
        """
        Periodically sample manager.metrics() and track state.

        Args:
            manager: SandboxManager instance
            interval: Sampling interval in seconds
            stop_event: Event to signal termination
        """
        logger.info(f"Starting pool metrics sampling (interval={interval}s)")
        sample_count = 0

        while stop_event is None or not stop_event.is_set():
            try:
                metrics = manager.metrics()
                self.record_pool_snapshot(metrics)
                sample_count += 1

                # Log current state
                total = sum(
                    getattr(m, "ready", 0)
                    + getattr(m, "creating", 0)
                    + getattr(m, "in_use", 0)
                    for m in metrics.values()
                )
                logger.debug(f"Pool snapshot: total={total}, max_observed={self._max_observed_total}")

                # Log overall progress every 60 seconds (12 samples at 5s interval)
                if sample_count % 12 == 0:
                    with self._lock:
                        total_sessions = len(self._sessions)
                        total_commands = sum(s.total_commands_executed for s in self._sessions)
                        total_failures = sum(s.command_failures_count for s in self._sessions)

                    elapsed = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
                    logger.info(
                        f"PROGRESS: {elapsed/60:.1f}m elapsed | "
                        f"sessions={total_sessions} | cmds={total_commands} | "
                        f"failures={total_failures} | sandboxes={total} (max={self._max_observed_total})"
                    )

            except Exception as e:
                logger.error(f"Error sampling pool metrics: {e}")

            # Wait for next interval
            if stop_event:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                    break  # Stop event was set
                except asyncio.TimeoutError:
                    pass  # Continue sampling
            else:
                await asyncio.sleep(interval)

        logger.info("Pool metrics sampling stopped")

    def get_summary(
        self,
        watchdog_metrics: Optional[WatchdogMetrics] = None,
    ) -> TestSummary:
        """
        Compute final summary statistics.

        Args:
            watchdog_metrics: Metrics from external watchdog

        Returns:
            Complete test summary
        """
        with self._lock:
            summary = TestSummary()
            summary.start_time = self._start_time
            summary.end_time = self._end_time

            if self._start_time and self._end_time:
                summary.duration_seconds = (
                    self._end_time - self._start_time
                ).total_seconds()

            # Session counts
            summary.total_sessions = len(self._sessions)
            summary.total_commands = sum(s.total_commands_executed for s in self._sessions)
            summary.total_command_failures = sum(
                s.command_failures_count for s in self._sessions
            )

            # Pool hit rate
            pool_hits = sum(1 for s in self._sessions if s.from_pool)
            if summary.total_sessions > 0:
                summary.pool_hit_rate_overall = pool_hits / summary.total_sessions
            summary.cold_start_count = summary.total_sessions - pool_hits

            # Pool hit rate by image
            for image in set(s.image for s in self._sessions):
                image_sessions = [s for s in self._sessions if s.image == image]
                image_pool_hits = sum(1 for s in image_sessions if s.from_pool)
                if image_sessions:
                    summary.pool_hit_rate_by_image[image] = (
                        image_pool_hits / len(image_sessions)
                    )

            # Latency percentiles
            all_latencies = [s.acquire_latency_ms for s in self._sessions]
            pool_latencies = [
                s.acquire_latency_ms for s in self._sessions if s.from_pool
            ]
            cold_latencies = [
                s.acquire_latency_ms for s in self._sessions if not s.from_pool
            ]

            if all_latencies:
                summary.acquire_latency_ms_p50 = percentile(all_latencies, 50)
                summary.acquire_latency_ms_p90 = percentile(all_latencies, 90)
                summary.acquire_latency_ms_p99 = percentile(all_latencies, 99)

            if pool_latencies:
                summary.acquire_latency_pool_p50 = percentile(pool_latencies, 50)
                summary.acquire_latency_pool_p90 = percentile(pool_latencies, 90)

            if cold_latencies:
                summary.acquire_latency_cold_p50 = percentile(cold_latencies, 50)
                summary.acquire_latency_cold_p90 = percentile(cold_latencies, 90)

            # Capacity metrics
            summary.max_total_sandboxes_observed = self._max_observed_total
            summary.capacity_violations = self._capacity_violations
            summary.failed_creates = self._failed_creates

            # Watchdog metrics
            if watchdog_metrics:
                summary.watchdog = watchdog_metrics

            # Determine pass/fail
            summary.passed = (
                summary.total_command_failures == 0
                and summary.capacity_violations == 0
                and summary.max_total_sandboxes_observed <= self.max_total
                and not (watchdog_metrics and watchdog_metrics.violation_detected)
            )

            return summary

    @property
    def sessions(self) -> List[SessionResult]:
        """Get all session results."""
        with self._lock:
            return list(self._sessions)

    @property
    def max_observed_total(self) -> int:
        """Get maximum observed total sandbox count."""
        with self._lock:
            return self._max_observed_total

    @property
    def capacity_violations(self) -> int:
        """Get number of capacity violations detected."""
        with self._lock:
            return self._capacity_violations
