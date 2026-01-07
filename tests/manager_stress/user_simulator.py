"""
User simulator module for SandboxManager stress tests.

Simulates user behavior patterns for acquiring and using sandboxes.
"""

import asyncio
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config import LoadPattern, UserGroupConfig, ImageType
from .metrics_collector import MetricsCollector, TaskResult
from .workload_generator import WorkloadGenerator, ProgramSpec

logger = logging.getLogger(__name__)


@dataclass
class UserState:
    """State of a simulated user."""
    user_id: str
    group: UserGroupConfig
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_task_time: float = 0
    is_active: bool = True


class LoadPatternGenerator:
    """Generates wait times based on load patterns."""

    def __init__(self, pattern: LoadPattern, test_duration: float):
        self.pattern = pattern
        self.test_duration = test_duration
        self.start_time = time.time()

    def get_next_wait(self) -> float:
        """Get the next wait time in seconds before acquiring a sandbox."""
        if self.pattern == LoadPattern.BURST:
            return self._burst_wait()
        elif self.pattern == LoadPattern.STEADY:
            return self._steady_wait()
        elif self.pattern == LoadPattern.RANDOM:
            return self._random_wait()
        elif self.pattern == LoadPattern.PEAK_HOURS:
            return self._peak_hours_wait()
        else:
            return self._steady_wait()

    def _burst_wait(self) -> float:
        """Burst pattern: 10% chance of quick succession, 90% quiet."""
        if random.random() < 0.1:
            return random.uniform(0.1, 1.0)  # Quick burst
        else:
            return random.uniform(30, 120)  # Quiet period

    def _steady_wait(self) -> float:
        """Steady pattern: consistent rate with ±20% jitter."""
        base_interval = 30.0  # Base interval in seconds
        jitter = base_interval * 0.2
        return base_interval + random.uniform(-jitter, jitter)

    def _random_wait(self) -> float:
        """Random pattern: exponential distribution (Poisson-like)."""
        # Mean arrival rate: 1 every 45 seconds
        return random.expovariate(1.0 / 45.0)

    def _peak_hours_wait(self) -> float:
        """Peak hours pattern: higher rate during 30-70% of test duration."""
        elapsed = time.time() - self.start_time
        progress = elapsed / self.test_duration if self.test_duration > 0 else 0

        if 0.3 <= progress <= 0.7:
            # Peak period - 2x normal rate
            base_interval = 15.0
        else:
            # Off-peak - 0.5x normal rate
            base_interval = 60.0

        jitter = base_interval * 0.2
        return base_interval + random.uniform(-jitter, jitter)


class UserSimulator:
    """
    Simulates a single user interacting with the sandbox system.

    Each user:
    1. Waits based on load pattern
    2. Acquires a sandbox
    3. Uploads and runs a program
    4. Releases the sandbox
    5. Repeats until test ends
    """

    def __init__(
        self,
        user_id: str,
        group: UserGroupConfig,
        workload_gen: WorkloadGenerator,
        metrics: MetricsCollector,
        manager: Any,  # SandboxManager
        test_duration: float,
    ):
        self.user_id = user_id
        self.group = group
        self.workload_gen = workload_gen
        self.metrics = metrics
        self.manager = manager
        self.test_duration = test_duration

        self.state = UserState(user_id=user_id, group=group)
        self.pattern_gen = LoadPatternGenerator(group.pattern, test_duration)
        self._stop_event = asyncio.Event()

    async def run(self, end_time: float):
        """Run the user simulation until end_time."""
        logger.info(f"User {self.user_id} ({self.group.name}) starting")

        while time.time() < end_time and not self._stop_event.is_set():
            try:
                # Wait based on load pattern
                wait_time = self.pattern_gen.get_next_wait()
                remaining = end_time - time.time()

                if wait_time > remaining:
                    logger.debug(f"User {self.user_id}: not enough time for next task, stopping")
                    break

                await asyncio.sleep(min(wait_time, remaining))

                if time.time() >= end_time or self._stop_event.is_set():
                    break

                # Execute a task
                await self._execute_task()

            except asyncio.CancelledError:
                logger.info(f"User {self.user_id} cancelled")
                break
            except Exception as e:
                logger.error(f"User {self.user_id} error: {e}")
                self.state.tasks_failed += 1
                await asyncio.sleep(5)  # Back off on error

        logger.info(f"User {self.user_id} finished: {self.state.tasks_completed} tasks, {self.state.tasks_failed} failed")

    async def _execute_task(self):
        """Execute a single task: acquire, run program, release."""
        task_id = str(uuid.uuid4())[:8]

        # Select a program
        program = self.workload_gen.select_program_for_duration(
            image=self.group.image,
            categories=self.group.categories,
            duration_seconds=random.randint(*self.group.task_duration_range),
        )

        if not program:
            logger.warning(f"User {self.user_id}: no suitable program found")
            return

        # Determine task duration
        min_dur, max_dur = self.group.task_duration_range
        task_duration = random.randint(min_dur, max_dur)

        started_at = time.time()
        sandbox = None
        from_pool = False
        error = None
        program_output = {}

        try:
            # Acquire sandbox
            acquire_start = time.time()
            sandbox, from_pool = await self._acquire_sandbox()
            acquire_latency_ms = (time.time() - acquire_start) * 1000

            # Record acquisition
            self.metrics.record_acquire(acquire_latency_ms, from_pool)

            logger.debug(
                f"User {self.user_id}: acquired sandbox "
                f"({'pool' if from_pool else 'cold'}) in {acquire_latency_ms:.0f}ms"
            )

            # Upload and run program
            program_output = await self._run_program(sandbox, program, task_duration)

            self.state.tasks_completed += 1
            success = True

        except Exception as e:
            logger.error(f"User {self.user_id} task {task_id} failed: {e}")
            error = str(e)
            success = False
            self.state.tasks_failed += 1
            acquire_latency_ms = (time.time() - started_at) * 1000

        finally:
            # Release sandbox
            if sandbox:
                try:
                    await self._release_sandbox(sandbox)
                except Exception as e:
                    logger.error(f"User {self.user_id}: failed to release sandbox: {e}")

        ended_at = time.time()

        # Record task result
        result = TaskResult(
            task_id=task_id,
            user_id=self.user_id,
            user_group=self.group.name,
            image=self.group.image.value,
            program=program.name,
            category=program.category,
            started_at=started_at,
            ended_at=ended_at,
            acquire_latency_ms=acquire_latency_ms,
            execution_duration_s=ended_at - started_at,
            success=success,
            from_pool=from_pool,
            error=error,
            program_output=program_output,
        )
        self.metrics.record_task_result(result)

        self.state.last_task_time = ended_at

    async def _acquire_sandbox(self) -> tuple[Any, bool]:
        """Acquire a sandbox from the manager."""
        # This integrates with SandboxManager.acquire()
        image_name = self.group.image.value

        if hasattr(self.manager, 'acquire'):
            # Real SandboxManager
            sandbox = await self.manager.acquire(image_name)
            # Check if it was from pool (manager should provide this info)
            from_pool = getattr(sandbox, '_from_pool', False)
            return sandbox, from_pool
        else:
            # Mock for testing
            await asyncio.sleep(random.uniform(0.5, 2.0))
            return MockSandbox(image_name), random.random() > 0.3

    async def _release_sandbox(self, sandbox: Any):
        """Release a sandbox - sandboxes are single-use, so we delete them."""
        # First, notify the manager that we're releasing (to update in_use_count)
        image_name = self.group.image.value
        if hasattr(self.manager, 'release'):
            try:
                self.manager.release(sandbox, image_name)
            except Exception as e:
                logger.warning(f"Failed to call manager.release: {e}")

        # SandboxManager sandboxes are single-use - delete when done
        # The pool replenishes by creating new sandboxes
        if hasattr(sandbox, 'delete'):
            try:
                # Run delete in thread to avoid blocking event loop
                await asyncio.to_thread(sandbox.delete)
            except Exception as e:
                logger.warning(f"Failed to delete sandbox: {e}")
        elif hasattr(sandbox, 'close'):
            await sandbox.close()

    async def _run_program(
        self,
        sandbox: Any,
        program: ProgramSpec,
        duration: int,
    ) -> dict:
        """Upload and run a program in the sandbox."""
        # Upload program file
        if hasattr(sandbox, 'filesystem'):
            program_content = program.path.read_text()
            upload_path = program.get_upload_path()
            # Run file upload in thread to avoid blocking event loop
            await asyncio.to_thread(
                sandbox.filesystem.write_file, upload_path, program_content
            )

            # Run program in thread to avoid blocking event loop
            command = program.get_command(duration)
            result = await asyncio.to_thread(
                sandbox.exec,
                f"cd /home/sandbox/app && {command}",
                timeout=duration + 60,
            )

            # Parse output
            return self._parse_program_output(result.stdout if hasattr(result, 'stdout') else str(result))
        else:
            # Mock execution
            await asyncio.sleep(min(duration, 10))  # Cap mock duration
            return {"mock": True, "duration": duration}

    def _parse_program_output(self, output: str) -> dict:
        """Parse RESULT: key=value output from program."""
        result = {}
        for line in output.split('\n'):
            if line.startswith('RESULT:'):
                parts = line[7:].strip().split()
                for part in parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        try:
                            # Try to convert to number
                            if '.' in value:
                                result[key] = float(value)
                            else:
                                result[key] = int(value)
                        except ValueError:
                            result[key] = value
        return result

    def stop(self):
        """Signal the user to stop."""
        self._stop_event.set()


class MockSandbox:
    """Mock sandbox for testing without real infrastructure."""

    def __init__(self, image: str):
        self.image = image
        self._from_pool = random.random() > 0.3

    async def close(self):
        await asyncio.sleep(0.1)


async def run_user_group(
    group: UserGroupConfig,
    workload_gen: WorkloadGenerator,
    metrics: MetricsCollector,
    manager: Any,
    end_time: float,
) -> list[UserSimulator]:
    """Run all users in a group concurrently."""
    users = []
    tasks = []

    for i in range(group.count):
        user_id = f"{group.name}_{i+1}"
        user = UserSimulator(
            user_id=user_id,
            group=group,
            workload_gen=workload_gen,
            metrics=metrics,
            manager=manager,
            test_duration=end_time - time.time(),
        )
        users.append(user)
        tasks.append(asyncio.create_task(user.run(end_time)))

    # Wait for all users to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    return users
