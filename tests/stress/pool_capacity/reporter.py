"""
Report generation for rigorous pool testing.

Generates:
- summary.json: Overall pass/fail and key stats
- summary.txt: Human-readable summary
- sessions.csv: Per-session data
- commands.csv.gz: Per-command data (compressed)
- pool_metrics.json: Raw pool metrics
"""

import csv
import gzip
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .metrics import TestSummary
from .session import SessionResult
from .utils import format_duration

logger = logging.getLogger("rigorous_pool_test")


class Reporter:
    """Handles all report generation."""

    def __init__(self, report_dir: str):
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Report directory: {self.report_dir}")

    def write_summary_json(self, summary: TestSummary):
        """Write summary.json with pass/fail and key stats."""
        path = self.report_dir / "summary.json"

        data = {
            "test_name": summary.test_name,
            "pass": summary.passed,
            "duration_seconds": summary.duration_seconds,
            "total_sessions": summary.total_sessions,
            "total_commands": summary.total_commands,
            "total_command_failures": summary.total_command_failures,
            "pool_hit_rate_overall": round(summary.pool_hit_rate_overall, 4),
            "pool_hit_rate_by_image": {k: round(v, 4) for k, v in summary.pool_hit_rate_by_image.items()},
            "cold_start_count": summary.cold_start_count,
            "acquire_latency_ms": {
                "p50": round(summary.acquire_latency_ms_p50, 1),
                "p90": round(summary.acquire_latency_ms_p90, 1),
                "p99": round(summary.acquire_latency_ms_p99, 1),
            },
            "acquire_latency_pool_ms": {
                "p50": round(summary.acquire_latency_pool_p50, 1),
                "p90": round(summary.acquire_latency_pool_p90, 1),
            },
            "acquire_latency_cold_ms": {
                "p50": round(summary.acquire_latency_cold_p50, 1),
                "p90": round(summary.acquire_latency_cold_p90, 1),
            },
            "max_total_sandboxes_observed": summary.max_total_sandboxes_observed,
            "capacity_violations": summary.capacity_violations,
            "failed_creates": summary.failed_creates,
            "leaked_sandboxes": summary.leaked_sandboxes,
            "watchdog": {
                "enabled": summary.watchdog.enabled,
                "violation_detected": summary.watchdog.violation_detected,
                "max_observed_via_doctl": summary.watchdog.max_observed_via_doctl,
                "total_checks": summary.watchdog.total_checks,
                "emergency_deletions": summary.watchdog.emergency_deletions,
            },
            "start_time": summary.start_time.isoformat() if summary.start_time else None,
            "end_time": summary.end_time.isoformat() if summary.end_time else None,
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Wrote {path}")

    def write_summary_txt(self, summary: TestSummary):
        """Write human-readable summary.txt."""
        path = self.report_dir / "summary.txt"

        lines = [
            "=" * 60,
            "RIGOROUS POOL TEST SUMMARY",
            "=" * 60,
            "",
            f"Result: {'PASS' if summary.passed else 'FAIL'}",
            f"Duration: {format_duration(summary.duration_seconds)}",
            "",
            "--- Sessions ---",
            f"Total sessions: {summary.total_sessions}",
            f"Pool hits: {summary.total_sessions - summary.cold_start_count} ({summary.pool_hit_rate_overall * 100:.1f}%)",
            f"Cold starts: {summary.cold_start_count}",
            "",
            "--- Commands ---",
            f"Total commands: {summary.total_commands}",
            f"Command failures: {summary.total_command_failures}",
            f"Failure rate: {summary.total_command_failures / max(summary.total_commands, 1) * 100:.2f}%",
            "",
            "--- Acquire Latency ---",
            f"Overall p50/p90/p99: {summary.acquire_latency_ms_p50:.0f}ms / {summary.acquire_latency_ms_p90:.0f}ms / {summary.acquire_latency_ms_p99:.0f}ms",
            f"Pool hits p50/p90: {summary.acquire_latency_pool_p50:.0f}ms / {summary.acquire_latency_pool_p90:.0f}ms",
            f"Cold starts p50/p90: {summary.acquire_latency_cold_p50:.0f}ms / {summary.acquire_latency_cold_p90:.0f}ms",
            "",
            "--- Capacity ---",
            f"Max sandboxes observed: {summary.max_total_sandboxes_observed}",
            f"Capacity violations: {summary.capacity_violations}",
            f"Failed creates: {summary.failed_creates}",
            "",
            "--- Watchdog ---",
            f"Enabled: {summary.watchdog.enabled}",
            f"Violation detected: {summary.watchdog.violation_detected}",
            f"Max observed via doctl: {summary.watchdog.max_observed_via_doctl}",
            f"Total checks: {summary.watchdog.total_checks}",
            "",
            "=" * 60,
        ]

        with open(path, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Wrote {path}")

    def write_sessions_csv(self, sessions: list[SessionResult]):
        """Write sessions.csv with per-session data."""
        path = self.report_dir / "sessions.csv"

        fieldnames = [
            "session_id",
            "image",
            "from_pool",
            "acquire_latency_ms",
            "sandbox_id",
            "app_id",
            "region",
            "hold_seconds_planned",
            "hold_seconds_actual",
            "total_commands_planned",
            "total_commands_executed",
            "command_failures_count",
            "delete_latency_ms",
            "error",
            "start_time",
            "end_time",
        ]

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for session in sessions:
                writer.writerow(
                    {
                        "session_id": session.session_id,
                        "image": session.image,
                        "from_pool": session.from_pool,
                        "acquire_latency_ms": round(session.acquire_latency_ms, 1),
                        "sandbox_id": session.sandbox_id,
                        "app_id": session.app_id,
                        "region": session.region,
                        "hold_seconds_planned": session.hold_seconds_planned,
                        "hold_seconds_actual": round(session.hold_seconds_actual, 1),
                        "total_commands_planned": session.total_commands_planned,
                        "total_commands_executed": session.total_commands_executed,
                        "command_failures_count": session.command_failures_count,
                        "delete_latency_ms": round(session.delete_latency_ms, 1),
                        "error": session.error or "",
                        "start_time": session.start_time.isoformat(),
                        "end_time": session.end_time.isoformat() if session.end_time else "",
                    }
                )

        logger.info(f"Wrote {path} ({len(sessions)} sessions)")

    def write_commands_csv(
        self,
        sessions: list[SessionResult],
        compress: bool = True,
    ):
        """
        Write commands.csv with per-command data.

        Args:
            sessions: List of session results
            compress: Whether to gzip the output
        """
        filename = "commands.csv.gz" if compress else "commands.csv"
        path = self.report_dir / filename

        fieldnames = [
            "session_id",
            "command_index",
            "command",
            "exit_code",
            "duration_ms",
            "stdout_snippet",
            "stderr_snippet",
            "retry_count",
            "timestamp",
        ]

        total_commands = 0
        open_func = gzip.open if compress else open
        mode = "wt" if compress else "w"

        with open_func(path, mode, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for session in sessions:
                for cmd in session.commands:
                    writer.writerow(
                        {
                            "session_id": cmd.session_id,
                            "command_index": cmd.command_index,
                            "command": cmd.command,
                            "exit_code": cmd.exit_code,
                            "duration_ms": round(cmd.duration_ms, 1),
                            "stdout_snippet": cmd.stdout_snippet,
                            "stderr_snippet": cmd.stderr_snippet,
                            "retry_count": cmd.retry_count,
                            "timestamp": cmd.timestamp.isoformat(),
                        }
                    )
                    total_commands += 1

        logger.info(f"Wrote {path} ({total_commands} commands)")

    def write_pool_metrics_json(
        self,
        raw_metrics: dict[str, Any],
        max_observed: int,
    ):
        """Write pool_metrics.json with raw manager metrics."""
        path = self.report_dir / "pool_metrics.json"

        # Convert PoolMetrics objects to dicts
        data = {
            "timestamp": datetime.now().isoformat(),
            "max_observed_total": max_observed,
            "pools": {},
        }

        for image, metrics in raw_metrics.items():
            data["pools"][image] = {
                "ready": getattr(metrics, "ready", 0),
                "creating": getattr(metrics, "creating", 0),
                "in_use": getattr(metrics, "in_use", 0),
                "total_acquires": getattr(metrics, "total_acquires", 0),
                "acquires_from_pool": getattr(metrics, "acquires_from_pool", 0),
                "acquires_cold_start": getattr(metrics, "acquires_cold_start", 0),
                "pool_hit_rate": getattr(metrics, "pool_hit_rate", 0),
                "avg_acquire_latency_ms": getattr(metrics, "avg_acquire_latency_ms", 0),
                "scale_up_events": getattr(metrics, "scale_up_events", 0),
                "scale_down_events": getattr(metrics, "scale_down_events", 0),
                "failed_creates": getattr(metrics, "failed_creates", 0),
                "health_check_removals": getattr(metrics, "health_check_removals", 0),
            }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Wrote {path}")

    def write_all(
        self,
        summary: TestSummary,
        sessions: list[SessionResult],
        raw_pool_metrics: dict[str, Any],
        max_observed: int,
    ):
        """Write all reports."""
        self.write_summary_json(summary)
        self.write_summary_txt(summary)
        self.write_sessions_csv(sessions)
        self.write_commands_csv(sessions, compress=True)
        self.write_pool_metrics_json(raw_pool_metrics, max_observed)

        # Print summary to console
        print("\n" + "=" * 60)
        print(f"TEST {'PASSED' if summary.passed else 'FAILED'}")
        print("=" * 60)
        print(f"Duration: {format_duration(summary.duration_seconds)}")
        print(f"Sessions: {summary.total_sessions}")
        print(f"Commands: {summary.total_commands}")
        print(f"Failures: {summary.total_command_failures}")
        print(f"Pool hit rate: {summary.pool_hit_rate_overall * 100:.1f}%")
        print(f"Max sandboxes: {summary.max_total_sandboxes_observed}")
        print(f"Reports: {self.report_dir}")
        print("=" * 60)
