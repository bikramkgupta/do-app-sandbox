"""
Utility functions for rigorous pool testing.
"""

import logging
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import HoldTimeConfig


def setup_logging(
    report_dir: str,
    level: int = logging.INFO,
    console: bool = True,
) -> logging.Logger:
    """
    Set up logging for the test run.

    Args:
        report_dir: Directory for log file
        level: Logging level
        console: Whether to also log to console

    Returns:
        Configured logger
    """
    Path(report_dir).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("rigorous_pool_test")
    logger.setLevel(level)
    logger.handlers.clear()

    # File handler
    log_file = Path(report_dir) / "test.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


@dataclass
class TimingResult:
    """Result of a timed operation."""

    duration_ms: float
    start_time: datetime
    end_time: datetime


@contextmanager
def timed_operation():
    """
    Context manager for timing operations.

    Yields a TimingResult that gets populated on exit.

    Usage:
        with timed_operation() as timing:
            # do something
        print(f"Took {timing.duration_ms}ms")
    """
    result = TimingResult(
        duration_ms=0,
        start_time=datetime.now(),
        end_time=datetime.now(),
    )
    start = time.perf_counter()
    try:
        yield result
    finally:
        end = time.perf_counter()
        result.duration_ms = (end - start) * 1000
        result.end_time = datetime.now()


async def timed_async_operation():
    """
    Async context manager for timing operations.

    Usage:
        async with timed_async_operation() as timing:
            await do_something()
        print(f"Took {timing.duration_ms}ms")
    """

    class AsyncTimedContext:
        def __init__(self):
            self.result = TimingResult(
                duration_ms=0,
                start_time=datetime.now(),
                end_time=datetime.now(),
            )
            self._start = 0

        async def __aenter__(self):
            self.result.start_time = datetime.now()
            self._start = time.perf_counter()
            return self.result

        async def __aexit__(self, *args):
            end = time.perf_counter()
            self.result.duration_ms = (end - self._start) * 1000
            self.result.end_time = datetime.now()

    return AsyncTimedContext()


def generate_hold_time(config: HoldTimeConfig | None = None) -> int:
    """
    Generate a random hold time based on distribution.

    Args:
        config: Hold time configuration (uses defaults if None)

    Returns:
        Hold time in seconds
    """
    if config is None:
        config = HoldTimeConfig()

    # Roll for distribution bucket
    roll = random.random()

    if roll < config.short_weight:
        # Short hold (40%): 5-10 minutes
        return random.randint(config.short_min, config.short_max)
    elif roll < config.short_weight + config.medium_weight:
        # Medium hold (40%): 10-20 minutes
        return random.randint(config.medium_min, config.medium_max)
    else:
        # Long hold (20%): 20-60 minutes
        return random.randint(config.long_min, config.long_max)


def generate_hold_time_from_config(hold_min: int, hold_max: int) -> int:
    """
    Generate a random hold time between min and max.

    Args:
        hold_min: Minimum hold time in seconds
        hold_max: Maximum hold time in seconds

    Returns:
        Hold time in seconds
    """
    return random.randint(hold_min, hold_max)


def generate_command_delay() -> float:
    """
    Generate a random delay between commands.

    Returns:
        Delay in seconds (0.5-2.0)
    """
    return random.uniform(0.5, 2.0)


def truncate_string(s: str, max_len: int = 200) -> str:
    """Truncate a string to max length with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def generate_session_id(worker_id: int, session_num: int) -> str:
    """Generate a unique session ID."""
    timestamp = datetime.now().strftime("%H%M%S")
    return f"w{worker_id:02d}_s{session_num:04d}_{timestamp}"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.2f}h"


def percentile(data: list, p: float) -> float:
    """
    Calculate percentile of a list of numbers.

    Args:
        data: List of numbers
        p: Percentile (0-100)

    Returns:
        Value at the given percentile
    """
    if not data:
        return 0.0

    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f

    if f == c:
        return sorted_data[f]

    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)
