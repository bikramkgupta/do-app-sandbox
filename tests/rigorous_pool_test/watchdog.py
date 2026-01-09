"""
External sandbox watchdog for rigorous pool testing.

Monitors actual live sandbox count via `doctl apps list`,
completely independent of SandboxManager internals.

Provides a fail-safe to ensure we NEVER exceed the sandbox limit.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from .config import WatchdogConfig
from .metrics import WatchdogMetrics

logger = logging.getLogger("rigorous_pool_test")


class SandboxWatchdog:
    """
    External watchdog that monitors `doctl apps list` for sandbox count.

    Runs independently of SandboxManager - uses actual DO API state.
    If count exceeds limit, triggers emergency shutdown.
    """

    def __init__(
        self,
        config: WatchdogConfig,
        on_violation: Callable[[], None],
        on_emergency_cleanup: Optional[Callable[[List[str]], None]] = None,
    ):
        """
        Initialize the watchdog.

        Args:
            config: Watchdog configuration
            on_violation: Callback to trigger test shutdown
            on_emergency_cleanup: Optional callback to delete excess sandboxes
        """
        self.config = config
        self.on_violation = on_violation
        self.on_emergency_cleanup = on_emergency_cleanup

        self._running = False
        self._violation_detected = False
        self._max_observed = 0
        self._check_count = 0
        self._emergency_deletions = 0
        self._last_count = 0

    async def get_sandbox_count(self) -> Tuple[int, List[dict]]:
        """
        Run `doctl apps list --output json` and count sandbox apps.

        Returns:
            Tuple of (count, list_of_app_dicts)
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "doctl", "apps", "list", "--output", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"doctl apps list failed: {stderr.decode()}")
                return -1, []

            apps = json.loads(stdout.decode())

            # Filter to sandbox apps only
            sandbox_apps = []
            for app in apps:
                spec = app.get("spec", {})
                name = spec.get("name", "").lower()
                if self.config.sandbox_name_pattern.lower() in name:
                    sandbox_apps.append(app)

            return len(sandbox_apps), sandbox_apps

        except FileNotFoundError:
            logger.error("doctl not found - watchdog disabled")
            return -1, []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse doctl output: {e}")
            return -1, []
        except Exception as e:
            logger.error(f"Watchdog check failed: {e}")
            return -1, []

    async def emergency_delete(self, apps: List[dict], keep_count: int = 25):
        """
        Emergency deletion of excess sandboxes.

        Deletes oldest sandboxes first until we're at keep_count.

        Args:
            apps: List of app dicts from doctl
            keep_count: Number of sandboxes to keep
        """
        excess = len(apps) - keep_count
        if excess <= 0:
            return

        logger.critical(f"EMERGENCY: Deleting {excess} excess sandboxes")

        # Sort by created_at to delete oldest first
        sorted_apps = sorted(
            apps,
            key=lambda a: a.get("created_at", ""),
        )

        for app in sorted_apps[:excess]:
            app_id = app.get("id")
            app_name = app.get("spec", {}).get("name", "unknown")

            try:
                logger.warning(f"Emergency deleting: {app_name} ({app_id})")

                proc = await asyncio.create_subprocess_exec(
                    "doctl", "apps", "delete", app_id, "--force",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

                if proc.returncode == 0:
                    self._emergency_deletions += 1
                    logger.warning(f"Emergency deleted: {app_name}")
                else:
                    logger.error(f"Failed to delete {app_name}")

            except Exception as e:
                logger.error(f"Exception deleting {app_name}: {e}")

    async def run(self, stop_event: asyncio.Event):
        """
        Main watchdog loop. Runs until stop_event is set.

        Args:
            stop_event: Event to signal termination
        """
        self._running = True
        logger.info(
            f"Watchdog started: monitoring for max {self.config.max_sandboxes} sandboxes "
            f"(pattern={self.config.sandbox_name_pattern}, interval={self.config.poll_interval}s, "
            f"grace={self.config.grace_period})"
        )

        while not stop_event.is_set() and self._running:
            try:
                count, apps = await self.get_sandbox_count()
                self._check_count += 1

                if count >= 0:  # Valid count
                    self._last_count = count
                    self._max_observed = max(self._max_observed, count)

                    hard_limit = self.config.max_sandboxes + self.config.grace_period

                    if count > hard_limit:
                        # CRITICAL VIOLATION - trigger emergency shutdown
                        logger.critical(
                            f"WATCHDOG VIOLATION: {count} sandboxes detected "
                            f"(limit: {self.config.max_sandboxes}, grace: {self.config.grace_period})"
                        )
                        self._violation_detected = True

                        # Trigger test shutdown
                        self.on_violation()

                        # Emergency cleanup if configured
                        if self.on_emergency_cleanup:
                            await self.emergency_delete(apps, self.config.max_sandboxes)

                        # Continue monitoring to track cleanup

                    elif count > self.config.max_sandboxes:
                        # Warning - over limit but within grace period
                        logger.warning(
                            f"Watchdog warning: {count} sandboxes "
                            f"(limit: {self.config.max_sandboxes}+{self.config.grace_period})"
                        )
                    else:
                        # Normal - under limit
                        if self._check_count % 6 == 0:  # Log every ~minute
                            logger.info(f"Watchdog: {count} sandboxes OK (max observed: {self._max_observed})")

            except Exception as e:
                logger.error(f"Watchdog iteration failed: {e}")

            # Wait for next poll
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self.config.poll_interval,
                )
            except asyncio.TimeoutError:
                pass  # Normal - continue polling

        self._running = False
        logger.info(
            f"Watchdog stopped. Max observed: {self._max_observed}, "
            f"Checks: {self._check_count}, Emergency deletions: {self._emergency_deletions}"
        )

    def stop(self):
        """Signal the watchdog to stop."""
        self._running = False

    @property
    def violation_detected(self) -> bool:
        """Whether a violation was detected."""
        return self._violation_detected

    @property
    def max_observed(self) -> int:
        """Maximum sandbox count observed."""
        return self._max_observed

    @property
    def check_count(self) -> int:
        """Number of checks performed."""
        return self._check_count

    @property
    def emergency_deletions(self) -> int:
        """Number of emergency deletions performed."""
        return self._emergency_deletions

    @property
    def last_count(self) -> int:
        """Last observed sandbox count."""
        return self._last_count

    def get_metrics(self) -> WatchdogMetrics:
        """Get current watchdog metrics."""
        return WatchdogMetrics(
            enabled=True,
            violation_detected=self._violation_detected,
            max_observed_via_doctl=self._max_observed,
            total_checks=self._check_count,
            emergency_deletions=self._emergency_deletions,
        )


class DisabledWatchdog:
    """Placeholder watchdog when monitoring is disabled."""

    def __init__(self):
        pass

    async def run(self, stop_event: asyncio.Event):
        """No-op run."""
        logger.info("Watchdog disabled - not monitoring")
        await stop_event.wait()

    def stop(self):
        pass

    @property
    def violation_detected(self) -> bool:
        return False

    @property
    def max_observed(self) -> int:
        return 0

    @property
    def check_count(self) -> int:
        return 0

    @property
    def emergency_deletions(self) -> int:
        return 0

    def get_metrics(self) -> WatchdogMetrics:
        return WatchdogMetrics(enabled=False)
