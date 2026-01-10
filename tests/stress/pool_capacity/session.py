"""
Session worker logic for rigorous pool testing.

Handles the full lifecycle of a sandbox session:
1. Acquire sandbox from pool
2. Execute commands at controlled rate
3. Hold for specified duration
4. Delete sandbox
5. Return metrics
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .commands import build_command_list, get_command_budget
from .config import RetryConfig, TestConfig
from .utils import (
    generate_command_delay,
    generate_hold_time_from_config,
    generate_session_id,
    truncate_string,
)

logger = logging.getLogger("rigorous_pool_test")


async def get_current_sandbox_count() -> int:
    """
    Get current sandbox count via doctl apps list.

    Returns the actual number of sandbox apps on DigitalOcean.
    This is the ground truth for capacity enforcement.

    Returns:
        Number of sandbox apps, or -1 on error
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "doctl",
            "apps",
            "list",
            "--output",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(f"doctl apps list failed: {stderr.decode()}")
            return -1

        apps = json.loads(stdout.decode())
        count = sum(1 for app in apps if "sandbox" in app.get("spec", {}).get("name", "").lower())
        return count
    except Exception as e:
        logger.warning(f"Failed to get sandbox count: {e}")
        return -1


@dataclass
class CommandRecord:
    """Record of a single command execution."""

    session_id: str
    command_index: int
    command: str
    exit_code: int
    duration_ms: float
    stdout_snippet: str
    stderr_snippet: str
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0


@dataclass
class FailureInfo:
    """Information about the first command failure."""

    command_index: int
    command: str
    exit_code: int
    stderr_snippet: str
    timestamp: datetime


@dataclass
class SessionResult:
    """Complete result of a session."""

    session_id: str
    image: str
    from_pool: bool
    acquire_latency_ms: float
    sandbox_id: str
    app_id: str
    region: str
    hold_seconds_planned: float
    hold_seconds_actual: float
    total_commands_planned: int
    total_commands_executed: int
    command_failures_count: int
    first_failure: FailureInfo | None
    delete_latency_ms: float
    commands: list[CommandRecord] = field(default_factory=list)
    error: str | None = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None


async def execute_command_with_retry(
    sandbox: Any,
    command: str,
    session_id: str,
    command_index: int,
    retry_config: RetryConfig,
) -> CommandRecord:
    """
    Execute a single command with retry logic.

    Args:
        sandbox: AsyncSandbox instance
        command: Command string to execute
        session_id: Current session ID
        command_index: Index of this command in the session
        retry_config: Retry configuration

    Returns:
        CommandRecord with execution results
    """
    last_error = None
    retry_count = 0

    for attempt in range(retry_config.exec_retries + 1):
        start_time = time.perf_counter()
        try:
            # Sandbox.exec() is synchronous - wrap in to_thread for async context
            result = await asyncio.to_thread(sandbox.exec, command)
            duration_ms = (time.perf_counter() - start_time) * 1000

            return CommandRecord(
                session_id=session_id,
                command_index=command_index,
                command=command,
                exit_code=result.exit_code,
                duration_ms=duration_ms,
                stdout_snippet=truncate_string(result.stdout),
                stderr_snippet=truncate_string(result.stderr),
                retry_count=retry_count,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            last_error = str(e)
            retry_count += 1

            if attempt < retry_config.exec_retries:
                logger.warning(f"Command retry {attempt + 1}/{retry_config.exec_retries}: {command[:50]}... - {e}")
                await asyncio.sleep(retry_config.exec_retry_delay)

    # All retries exhausted
    return CommandRecord(
        session_id=session_id,
        command_index=command_index,
        command=command,
        exit_code=-1,
        duration_ms=duration_ms,
        stdout_snippet="",
        stderr_snippet=f"EXCEPTION: {last_error}",
        retry_count=retry_count,
    )


async def delete_sandbox_with_retry(
    sandbox: Any,
    retry_config: RetryConfig,
) -> tuple[bool, float]:
    """
    Delete a sandbox with retry logic.

    Args:
        sandbox: AsyncSandbox instance
        retry_config: Retry configuration

    Returns:
        Tuple of (success, duration_ms)
    """
    last_error = None

    for attempt in range(retry_config.delete_retries + 1):
        start_time = time.perf_counter()
        try:
            # Sandbox.delete() is synchronous - wrap in to_thread for async context
            await asyncio.to_thread(sandbox.delete)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return True, duration_ms

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            last_error = str(e)

            if attempt < retry_config.delete_retries:
                logger.warning(f"Delete retry {attempt + 1}/{retry_config.delete_retries}: {e}")
                await asyncio.sleep(retry_config.delete_retry_delay)

    logger.error(f"Failed to delete sandbox after retries: {last_error}")
    return False, duration_ms


async def run_session(
    manager: Any,
    image: str,
    session_id: str,
    hold_time_sec: int,
    config: TestConfig,
    retry_config: RetryConfig,
    stop_event: asyncio.Event,
) -> SessionResult:
    """
    Run a complete sandbox session.

    Args:
        manager: SandboxManager instance
        image: Image name (python/node)
        session_id: Unique session identifier
        hold_time_sec: How long to hold the sandbox
        config: Test configuration
        retry_config: Retry configuration
        stop_event: Event to signal early termination

    Returns:
        SessionResult with all metrics
    """
    result = SessionResult(
        session_id=session_id,
        image=image,
        from_pool=False,
        acquire_latency_ms=0,
        sandbox_id="",
        app_id="",
        region=config.region,
        hold_seconds_planned=hold_time_sec,
        hold_seconds_actual=0,
        total_commands_planned=get_command_budget(hold_time_sec),
        total_commands_executed=0,
        command_failures_count=0,
        first_failure=None,
        delete_latency_ms=0,
    )

    sandbox = None
    session_start = time.perf_counter()

    try:
        # 1. Check capacity before acquiring (ground truth from doctl)
        max_sandboxes = config.max_total_sandboxes
        max_wait_seconds = 60  # Max time to wait for capacity
        wait_start = time.perf_counter()

        while True:
            current_count = await get_current_sandbox_count()
            if current_count < 0:
                # doctl failed, proceed anyway (let SDK handle it)
                logger.warning(f"Session {session_id}: Could not check capacity, proceeding")
                break
            elif current_count < max_sandboxes:
                # Capacity available
                logger.debug(f"Session {session_id}: Capacity OK ({current_count}/{max_sandboxes})")
                break
            else:
                # At capacity - wait and retry
                waited = time.perf_counter() - wait_start
                if waited > max_wait_seconds:
                    logger.warning(
                        f"Session {session_id}: Capacity wait timeout ({current_count}/{max_sandboxes}), "
                        f"skipping this acquire"
                    )
                    result.error = f"Capacity wait timeout ({current_count}/{max_sandboxes})"
                    result.end_time = datetime.now()
                    return result

                if stop_event.is_set():
                    result.error = "Stopped while waiting for capacity"
                    result.end_time = datetime.now()
                    return result

                logger.debug(f"Session {session_id}: At capacity ({current_count}/{max_sandboxes}), waiting 2s...")
                await asyncio.sleep(2)

        # 2. Acquire sandbox
        acquire_start = time.perf_counter()
        sandbox = await manager.acquire(image)
        result.acquire_latency_ms = (time.perf_counter() - acquire_start) * 1000

        # Record sandbox info
        result.from_pool = getattr(sandbox, "_from_pool", False)
        result.sandbox_id = getattr(sandbox, "component", "unknown")
        result.app_id = getattr(sandbox, "app_id", "unknown")

        source = "POOL" if result.from_pool else "COLD"
        logger.info(
            f"Worker {session_id.split('_')[0]}: Acquired {source} sandbox ({result.acquire_latency_ms:.0f}ms) "
            f"for session {session_id}"
        )

        # 3. Build command list
        commands = build_command_list(
            image=image,
            total_commands=result.total_commands_planned,
            enable_network=config.enable_network_commands,
        )

        # 4. Execute commands at controlled rate
        command_start_time = time.perf_counter()
        hold_deadline = command_start_time + hold_time_sec

        logger.info(
            f"Worker {session_id.split('_')[0]}: Running session {session_id} "
            f"(hold={hold_time_sec}s, cmds={len(commands)})"
        )

        for i, command in enumerate(commands):
            # Check for early termination
            if stop_event.is_set():
                logger.info(f"Session {session_id}: Early termination at command {i}")
                break

            # Check if we've exceeded hold time
            if time.perf_counter() > hold_deadline:
                logger.debug(f"Session {session_id}: Hold time exceeded at command {i}/{len(commands)}")
                break

            # Execute command
            cmd_record = await execute_command_with_retry(
                sandbox=sandbox,
                command=command,
                session_id=session_id,
                command_index=i,
                retry_config=retry_config,
            )
            result.commands.append(cmd_record)
            result.total_commands_executed += 1

            # Track failures
            if cmd_record.exit_code != 0:
                result.command_failures_count += 1
                if result.first_failure is None:
                    result.first_failure = FailureInfo(
                        command_index=i,
                        command=command,
                        exit_code=cmd_record.exit_code,
                        stderr_snippet=cmd_record.stderr_snippet,
                        timestamp=datetime.now(),
                    )
                    logger.warning(
                        f"Session {session_id}: Command failure at index {i}: "
                        f"exit_code={cmd_record.exit_code}, cmd={command[:50]}..."
                    )

            # Log progress every 50 commands
            if (i + 1) % 50 == 0:
                logger.info(
                    f"Session {session_id}: Progress {i + 1}/{len(commands)} commands "
                    f"({result.command_failures_count} failures)"
                )

            # Random delay between commands
            if i < len(commands) - 1:
                delay = generate_command_delay()
                await asyncio.sleep(delay)

        # 5. Hold remaining time if we finished commands early
        remaining_time = hold_deadline - time.perf_counter()
        if remaining_time > 0 and not stop_event.is_set():
            logger.debug(f"Session {session_id}: Holding for {remaining_time:.1f}s more")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=remaining_time)
            except asyncio.TimeoutError:
                pass  # Normal - hold time elapsed

        result.hold_seconds_actual = time.perf_counter() - session_start

    except Exception as e:
        result.error = str(e)
        logger.error(f"Session {session_id}: Error - {e}")

    finally:
        # 6. Delete sandbox
        if sandbox is not None:
            success, delete_latency = await delete_sandbox_with_retry(sandbox, retry_config)
            result.delete_latency_ms = delete_latency
            if not success:
                result.error = (result.error or "") + "; Delete failed"

            # CRITICAL: Release the quota in the manager
            # This decrements the in-use counter so new sandboxes can be created
            manager.release(sandbox, image)

            logger.info(
                f"Worker {session_id.split('_')[0]}: Released sandbox for session {session_id} "
                f"(held {result.hold_seconds_actual:.1f}s)"
            )

        result.end_time = datetime.now()

    # logger.info(
    #    f"Session {session_id}: Completed - "
    #    f"commands={result.total_commands_executed}/{result.total_commands_planned}, "
    #    f"failures={result.command_failures_count}, "
    #    f"hold={result.hold_seconds_actual:.1f}s/{result.hold_seconds_planned}s"
    # )

    return result


async def session_worker(
    worker_id: int,
    manager: Any,
    image: str,
    config: TestConfig,
    retry_config: RetryConfig,
    stop_event: asyncio.Event,
    results_callback: callable,
) -> int:
    """
    Worker loop that continuously runs sessions until stop_event is set.

    Args:
        worker_id: Unique worker identifier
        manager: SandboxManager instance
        image: Image name to use
        config: Test configuration
        retry_config: Retry configuration
        stop_event: Event to signal termination
        results_callback: Callback to report session results

    Returns:
        Number of sessions completed
    """
    session_num = 0
    logger.info(f"Worker {worker_id}: Starting")

    while not stop_event.is_set():
        session_num += 1
        session_id = generate_session_id(worker_id, session_num)
        hold_time = generate_hold_time_from_config(config.hold_time_min, config.hold_time_max)

        logger.info(
            f"Worker {worker_id}: Starting session {session_id} "
            f"(hold={hold_time}s, budget={get_command_budget(hold_time)} cmds)"
        )

        result = await run_session(
            manager=manager,
            image=image,
            session_id=session_id,
            hold_time_sec=hold_time,
            config=config,
            retry_config=retry_config,
            stop_event=stop_event,
        )

        results_callback(result)

    logger.info(f"Worker {worker_id}: Stopped after {session_num} sessions")
    return session_num
