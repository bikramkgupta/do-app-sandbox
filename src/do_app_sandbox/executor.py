"""Enhanced command executor for DigitalOcean App Platform console sessions.

This module provides the core command execution functionality using pexpect
to connect to App Platform containers via `doctl apps console`.
"""

import os
import re
import shlex
import time
from typing import Optional

import pexpect

from .exceptions import CommandExecutionError, CommandTimeoutError, ConnectionError
from .types import CommandResult

# Marker used to extract exit code from command output
EXIT_CODE_MARKER = "___EXIT_CODE___"

# Prompt patterns for different container configurations
# The sandbox containers use a 'sandbox' user
PROMPT_PATTERNS = [
    re.compile(rb"sandbox@[^:]+:[^$]+\$ "),
    re.compile(rb"devcontainer@[^:]+:[^$]+\$ "),
    re.compile(rb"[a-zA-Z0-9_-]+@[^:]+:[^$#]+[$#] "),
]


class Executor:
    """Executes commands on a remote App Platform container via doctl console."""

    def __init__(self, app_id: str, component: str = "sandbox"):
        """Initialize the executor.

        Args:
            app_id: The App Platform application ID
            component: The component/service name within the app
        """
        self.app_id = app_id
        self.component = component
        self._child: Optional[pexpect.spawn] = None

    def _get_doctl_command(self) -> str:
        """Build the doctl console command."""
        return f"doctl apps console {self.app_id} {self.component}"

    def _connect(self, timeout: int = 30) -> pexpect.spawn:
        """Establish a connection to the container console.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            The pexpect child process

        Raises:
            ConnectionError: If connection fails
        """
        doctl_cmd = self._get_doctl_command()

        try:
            child = pexpect.spawn(doctl_cmd, timeout=timeout)
            child.setecho(False)
            child.delayafterread = 0.05
            child.delayafterwrite = 0.05

            # Wait for the initial shell prompt
            child.expect(PROMPT_PATTERNS, timeout=timeout)

            return child

        except pexpect.exceptions.TIMEOUT:
            raise ConnectionError(
                f"Timed out waiting for shell prompt on {self.component}"
            )
        except pexpect.exceptions.EOF:
            raise ConnectionError(
                f"Connection closed unexpectedly while connecting to {self.component}"
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {self.component}: {e}")

    def _disconnect(self, child: pexpect.spawn) -> None:
        """Close the console connection."""
        try:
            child.sendline("exit")
            child.close()
        except Exception:
            pass  # Best effort cleanup

    def _build_command(
        self,
        command: str,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> str:
        """Build the full command with environment variables and working directory.

        Args:
            command: The base command to execute
            env: Environment variables to set
            cwd: Working directory to change to

        Returns:
            The full command string
        """
        parts = []

        # Add working directory change
        if cwd:
            parts.append(f"cd {shlex.quote(cwd)}")

        # Build the main command with environment variables
        if env:
            exports = "; ".join(f"export {k}={shlex.quote(v)}" for k, v in env.items())
            parts.append(f"{exports}; {command}")
        else:
            parts.append(command)

        # Join with && to ensure proper sequencing
        if len(parts) > 1:
            return " && ".join(parts)
        return parts[0]

    def _wrap_command_for_capture(self, command: str) -> str:
        """Wrap a command to capture exit code and separate stderr.

        The wrapped command:
        1. Redirects stderr to a temp file
        2. Runs the original command
        3. Captures the exit code
        4. Outputs a marker with the exit code
        5. Outputs stderr content with a marker
        6. Cleans up the temp file

        Args:
            command: The command to wrap

        Returns:
            The wrapped command string
        """
        # Generate a unique stderr file based on timestamp
        stderr_file = f"/tmp/stderr_{os.getpid()}_{int(time.time() * 1000)}.txt"

        # Wrap the command to capture exit code and stderr
        # Format: run command with stderr redirected, capture exit code, output markers
        wrapped = (
            f"({command}) 2>{stderr_file}; "
            f'_ec=$?; echo "{EXIT_CODE_MARKER}:$_ec"; '
            f'echo "___STDERR_START___"; cat {stderr_file} 2>/dev/null; echo "___STDERR_END___"; '
            f"rm -f {stderr_file} 2>/dev/null"
        )

        return wrapped

    def _parse_output(self, raw_output: str, command: str) -> CommandResult:
        """Parse the raw output to extract stdout, stderr, and exit code.

        Args:
            raw_output: The raw output from the console
            command: The original command (for cleaning)

        Returns:
            CommandResult with parsed values
        """
        # Remove bracketed-paste/ANSI/OSC control sequences that appear on some shells
        cleaned_output = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw_output)
        cleaned_output = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)?", "", cleaned_output)
        cleaned_output = cleaned_output.replace("\r", "")

        lines = cleaned_output.split("\n")

        exit_code = 0
        stdout_lines = []
        stderr_lines = []
        in_stderr = False
        found_exit_code = False

        stderr_marker = "/tmp/stderr_"

        for line in lines:
            if not line.strip():
                continue

            # Skip echoed wrapper/redirect lines entirely
            if stderr_marker in line and ("echo" in line or "_ec=$?" in line or "cat" in line):
                continue

            # Check for exit code marker
            if EXIT_CODE_MARKER in line:
                # Extract any content BEFORE the marker on the same line
                marker_pos = line.find(EXIT_CODE_MARKER)
                if marker_pos > 0:
                    content_before = line[:marker_pos]
                    if content_before.strip():
                        stdout_lines.append(content_before)

                try:
                    exit_code = int(line.split(":")[-1].strip())
                    found_exit_code = True
                except (ValueError, IndexError):
                    pass
                continue

            # Check for stderr markers
            if "___STDERR_START___" in line:
                in_stderr = True
                continue
            if "___STDERR_END___" in line:
                in_stderr = False
                continue

            # Collect output
            if in_stderr:
                stderr_lines.append(line)
            elif not found_exit_code:
                # Only collect stdout before exit code marker
                stdout_lines.append(line)

        stdout = "\n".join(stdout_lines).strip()

        stderr = "\n".join(stderr_lines).strip()

        return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code)

    def execute(
        self,
        command: str,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: int = 120,
    ) -> CommandResult:
        """Execute a command on the remote container.

        Args:
            command: The command to execute
            env: Environment variables to set for this command
            cwd: Working directory for the command
            timeout: Command timeout in seconds

        Returns:
            CommandResult with stdout, stderr, and exit code

        Raises:
            CommandTimeoutError: If the command times out
            CommandExecutionError: If execution fails
            ConnectionError: If connection fails
        """
        # Build the full command
        full_command = self._build_command(command, env, cwd)

        # Wrap for exit code and stderr capture
        wrapped_command = self._wrap_command_for_capture(full_command)

        child = None
        try:
            # Connect to the container
            child = self._connect(timeout=min(timeout, 60))

            # Send the wrapped command
            child.sendline(wrapped_command)

            # Wait for the command to complete
            child.expect(PROMPT_PATTERNS, timeout=timeout)

            # Get the raw output
            raw_output = child.before.decode("utf-8", errors="ignore")

            # Parse and return the result
            return self._parse_output(raw_output, command)

        except pexpect.exceptions.TIMEOUT:
            raise CommandTimeoutError(
                f"Command timed out after {timeout} seconds: {command[:100]}..."
            )
        except pexpect.exceptions.EOF:
            # Try to capture partial output
            partial = ""
            if child and hasattr(child, "before") and child.before:
                partial = child.before.decode("utf-8", errors="ignore")
            raise CommandExecutionError(
                f"Connection closed during command execution. Partial output: {partial[:200]}"
            )
        except ConnectionError:
            raise
        except Exception as e:
            raise CommandExecutionError(f"Command execution failed: {e}")
        finally:
            if child:
                self._disconnect(child)

    def execute_raw(self, command: str, timeout: int = 120) -> str:
        """Execute a command and return raw output without parsing.

        This is useful for commands where you need the exact output
        without any processing.

        Args:
            command: The command to execute
            timeout: Command timeout in seconds

        Returns:
            The raw output string

        Raises:
            CommandTimeoutError: If the command times out
            CommandExecutionError: If execution fails
        """
        child = None
        try:
            child = self._connect(timeout=min(timeout, 60))
            child.sendline(command)
            child.expect(PROMPT_PATTERNS, timeout=timeout)

            raw_output = child.before.decode("utf-8", errors="ignore")

            # Clean up the output - remove the echoed command
            lines = raw_output.split("\n")
            if lines and command in lines[0]:
                raw_output = "\n".join(lines[1:])

            return raw_output.strip()

        except pexpect.exceptions.TIMEOUT:
            raise CommandTimeoutError(f"Command timed out after {timeout} seconds")
        except pexpect.exceptions.EOF:
            partial = ""
            if child and hasattr(child, "before") and child.before:
                partial = child.before.decode("utf-8", errors="ignore")
            raise CommandExecutionError(f"Connection closed. Partial: {partial[:200]}")
        finally:
            if child:
                self._disconnect(child)
