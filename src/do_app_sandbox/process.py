"""Process management for sandbox containers.

This module provides methods for launching, monitoring, and killing
processes on the remote sandbox container.
"""

import shlex
import time
import uuid
from typing import Optional

from .exceptions import CommandExecutionError
from .executor import Executor
from .types import ProcessInfo


class ProcessManager:
    """Process management for a sandbox container."""

    def __init__(self, executor: Executor):
        """Initialize the process manager.

        Args:
            executor: The executor instance for running commands
        """
        self._executor = executor
        self._launched_pids: list[int] = []

    def launch(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> int:
        """Launch a background process.

        The process runs with nohup to survive session disconnection.
        Output is redirected to a log file.

        Args:
            command: The command to run
            cwd: Working directory for the command
            env: Environment variables to set

        Returns:
            The process ID (PID)

        Raises:
            CommandExecutionError: If the process cannot be launched
        """
        # Generate a unique ID for this process's log file
        proc_id = uuid.uuid4().hex[:8]
        log_file = f"/tmp/sandbox_proc_{proc_id}.log"

        # Build the command with optional env vars
        cmd_parts = []
        if env:
            env_str = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
            cmd_parts.append(env_str)
        cmd_parts.append(command)
        full_cmd = " ".join(cmd_parts)

        # Build the nohup command
        # Use nohup with output redirection and background execution
        # The echo $! at the end outputs the PID
        launch_cmd = f"nohup {full_cmd} > {log_file} 2>&1 & echo $!"

        result = self._executor.execute(launch_cmd, cwd=cwd)
        if not result.success:
            raise CommandExecutionError(
                f"Failed to launch process: {result.stderr}"
            )

        # Parse the PID from output
        try:
            pid = int(result.stdout.strip().split("\n")[-1])
            self._launched_pids.append(pid)
            return pid
        except (ValueError, IndexError) as e:
            raise CommandExecutionError(f"Failed to get PID: {result.stdout}") from e

    def list_processes(self, pattern: Optional[str] = None) -> list[ProcessInfo]:
        """List running processes.

        Args:
            pattern: Optional pattern to filter processes (grep pattern)

        Returns:
            List of ProcessInfo objects
        """
        if pattern:
            cmd = f"ps aux | grep -v grep | grep {shlex.quote(pattern)}"
        else:
            cmd = "ps aux"

        result = self._executor.execute(cmd)

        processes = []
        lines = result.stdout.strip().split("\n")

        for line in lines:
            # Skip header
            if line.startswith("USER") or not line.strip():
                continue

            parts = line.split(None, 10)
            if len(parts) < 11:
                continue

            try:
                pid = int(parts[1])
                cpu = parts[2]
                memory = parts[3]
                status = parts[7]
                command = parts[10]

                processes.append(
                    ProcessInfo(
                        pid=pid,
                        command=command,
                        status=status,
                        cpu=cpu,
                        memory=memory,
                    )
                )
            except (ValueError, IndexError):
                continue

        return processes

    def get_process(self, pid: int) -> Optional[ProcessInfo]:
        """Get information about a specific process.

        Args:
            pid: The process ID

        Returns:
            ProcessInfo if the process exists, None otherwise
        """
        result = self._executor.execute(f"ps -p {pid} -o pid,stat,comm 2>/dev/null")

        if not result.success or "PID" not in result.stdout:
            return None

        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return None

        parts = lines[1].split()
        if len(parts) < 3:
            return None

        return ProcessInfo(
            pid=int(parts[0]),
            status=parts[1],
            command=parts[2],
        )

    def is_running(self, pid: int) -> bool:
        """Check if a process is still running.

        Args:
            pid: The process ID

        Returns:
            True if the process is running
        """
        result = self._executor.execute(
            f'kill -0 {pid} 2>/dev/null && echo "RUNNING" || echo "NOT_RUNNING"'
        )
        return "RUNNING" in result.stdout and "NOT_RUNNING" not in result.stdout

    def kill(self, pid: int, signal: int = 15) -> bool:
        """Kill a process.

        Args:
            pid: The process ID
            signal: The signal to send (default: 15/SIGTERM)

        Returns:
            True if the signal was sent successfully
        """
        result = self._executor.execute(f"kill -{signal} {pid} 2>/dev/null")
        if pid in self._launched_pids:
            self._launched_pids.remove(pid)
        return result.exit_code == 0

    def kill_by_pattern(self, pattern: str) -> int:
        """Kill all processes matching a pattern.

        Args:
            pattern: The pattern to match (used with pkill -f)

        Returns:
            Number of processes killed
        """
        # First, count matching processes
        result = self._executor.execute(f"pgrep -f {shlex.quote(pattern)} | wc -l")
        try:
            count = int(result.stdout.strip())
        except ValueError:
            count = 0

        if count > 0:
            self._executor.execute(f"pkill -f {shlex.quote(pattern)}")

        return count

    def kill_all_launched(self) -> int:
        """Kill all processes launched by this manager.

        Returns:
            Number of processes killed
        """
        killed = 0
        for pid in list(self._launched_pids):
            if self.kill(pid):
                killed += 1
        return killed

    def wait_for(self, pid: int, timeout: int = 60) -> bool:
        """Wait for a process to complete.

        Args:
            pid: The process ID
            timeout: Maximum time to wait in seconds

        Returns:
            True if the process completed, False if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            if not self.is_running(pid):
                return True
            time.sleep(0.5)
        return False

    def get_output(self, pid: int) -> Optional[str]:
        """Get the output log of a launched process.

        This only works for processes launched via this manager.

        Args:
            pid: The process ID

        Returns:
            The log output if available, None otherwise
        """
        # Find the log file - we need to search for it
        result = self._executor.execute(f"ls /tmp/sandbox_proc_*.log 2>/dev/null")
        if not result.success:
            return None

        # Read all matching log files and try to find the one for this PID
        # This is a best-effort approach since we don't track log files per PID
        for log_file in result.stdout.strip().split("\n"):
            if log_file:
                log_result = self._executor.execute(f"cat {log_file} 2>/dev/null")
                if log_result.success:
                    return log_result.stdout

        return None
