"""Session management for persistent shell contexts.

Provides isolated shell sessions that maintain state (environment,
working directory, shell history) across multiple exec calls.
"""

import os
import pty
import select
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class Session:
    """A persistent shell session."""

    id: str
    pid: int
    master_fd: int
    env: dict[str, str]
    cwd: str
    created_at: float = field(default_factory=time.time)


class SessionManager:
    """Manages persistent shell sessions."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, session_id: str, env: dict[str, str] | None = None, cwd: str = "/workspace") -> Session:
        """Create a new session with persistent bash shell.

        Args:
            session_id: Unique identifier for the session
            env: Additional environment variables
            cwd: Initial working directory

        Returns:
            Session object

        Raises:
            ValueError: If session already exists
        """
        if session_id in self._sessions:
            raise ValueError(f"Session {session_id} already exists")

        master, slave = pty.openpty()

        session_env = os.environ.copy()
        if env:
            session_env.update(env)
        # Set a known prompt for reliable detection
        session_env["PS1"] = "SANDBOX_PROMPT$ "

        # Start bash in interactive mode
        proc = subprocess.Popen(
            ["/bin/bash", "--norc", "--noprofile", "-i"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=session_env,
            preexec_fn=os.setsid,
        )

        os.close(slave)

        session = Session(id=session_id, pid=proc.pid, master_fd=master, env=env or {}, cwd=cwd)
        self._sessions[session_id] = session

        # Wait for shell prompt
        self._read_until_prompt(master)

        return session

    def get(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        return session_id in self._sessions

    def exec_in_session(self, session_id: str, command: str, timeout: int = 120) -> str:
        """Execute command in session's persistent shell.

        Args:
            session_id: Session identifier
            command: Command to execute
            timeout: Maximum time to wait for output

        Returns:
            Command output

        Raises:
            ValueError: If session not found
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Send command
        os.write(session.master_fd, f"{command}\n".encode())

        # Read output until next prompt
        output = self._read_until_prompt(session.master_fd, timeout)

        # Remove command echo and prompt from output
        lines = output.split("\n")
        if lines and command in lines[0]:
            lines = lines[1:]

        return "\n".join(lines).strip()

    def _read_until_prompt(self, fd: int, timeout: int = 30) -> str:
        """Read from PTY until shell prompt appears.

        Args:
            fd: File descriptor to read from
            timeout: Maximum time to wait

        Returns:
            Accumulated output
        """
        output = []
        start_time = time.time()
        prompt_marker = "SANDBOX_PROMPT$ "

        while time.time() - start_time < timeout:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                # Check if we've seen our known prompt
                full_output = "".join(output)
                if prompt_marker in full_output:
                    break
                continue

            try:
                data = os.read(fd, 4096)
                if not data:
                    break
                decoded = data.decode(errors="replace")
                output.append(decoded)

                # Check for our known prompt
                if prompt_marker in decoded:
                    break
            except OSError:
                break

        return "".join(output)

    def close(self, session_id: str) -> bool:
        """Close a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was closed, False if not found
        """
        session = self._sessions.pop(session_id, None)
        if session:
            try:
                os.close(session.master_fd)
            except OSError:
                pass
            try:
                os.kill(session.pid, 9)
            except OSError:
                pass
            return True
        return False

    def list_sessions(self) -> list:
        """List all active sessions."""
        result = []
        for session_id, session in self._sessions.items():
            # Check if process is still running
            try:
                os.kill(session.pid, 0)
                status = "running"
            except OSError:
                status = "stopped"

            result.append(
                {
                    "session_id": session.id,
                    "pid": session.pid,
                    "cwd": session.cwd,
                    "env": session.env,
                    "status": status,
                    "created_at": session.created_at,
                }
            )
        return result

    def close_all(self):
        """Close all sessions."""
        for session_id in list(self._sessions.keys()):
            self.close(session_id)


# Global session manager instance
sessions = SessionManager()
