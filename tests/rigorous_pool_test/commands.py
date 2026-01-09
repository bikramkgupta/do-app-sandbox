"""
Command suite generation for rigorous pool testing.

Generates deterministic command bundles with variation per iteration.
"""

from typing import List


def build_python_command_bundle(iteration: int, enable_network: bool = True) -> List[str]:
    """
    Build a bundle of Python sandbox commands for one iteration.

    Args:
        iteration: Current iteration number (used for unique file names)
        enable_network: Whether to include network-dependent commands

    Returns:
        List of command strings to execute
    """
    commands = [
        # 1. Version check
        "python --version",
        # 2. Basic print
        'python -c "print(\'hello\')"',
        # 3. Working directory
        'python -c "import os; print(os.getcwd())"',
        # 4. Platform info
        'python -c "import platform; print(platform.platform())"',
        # 5. Brief sleep (test timing)
        'python -c "import time; time.sleep(0.1); print(\'slept\')"',
        # 6. CPU-bound work (hashing)
        'python -c "import hashlib; print(hashlib.sha256(b\'x\'*100000).hexdigest())"',
        # 7. JSON output with iteration
        f'python -c "import json; print(json.dumps({{\'i\': {iteration}}}))"',
        # 8. File write
        f'bash -lc "echo test_{iteration} > /tmp/t_{iteration}.txt"',
        # 9. File read/size
        f'bash -lc "wc -c /tmp/t_{iteration}.txt"',
        # 10. Directory listing
        'bash -lc "ls -la /tmp | head"',
        # 11. System info
        'bash -lc "uname -a"',
    ]

    # 12. Network command (optional)
    if enable_network:
        commands.append(
            'python -c "import socket; print(socket.gethostbyname(\'example.com\'))"'
        )

    return commands


def build_node_command_bundle(iteration: int, enable_network: bool = True) -> List[str]:
    """
    Build a bundle of Node sandbox commands for one iteration.

    Args:
        iteration: Current iteration number
        enable_network: Whether to include network-dependent commands

    Returns:
        List of command strings to execute
    """
    commands = [
        # 1. Version check
        "node --version",
        # 2. Basic console log
        'node -e "console.log(\'hi\')"',
        # 3. CPU-bound work (hashing)
        'node -e "const crypto=require(\'crypto\'); console.log(crypto.createHash(\'sha256\').update(\'x\'.repeat(1e5)).digest(\'hex\'))"',
        # 4. JSON output with iteration
        f'node -e "console.log(JSON.stringify({{i: {iteration}}}))"',
        # 5. File operations via bash
        f'bash -lc "echo node_test_{iteration} > /tmp/node_{iteration}.txt"',
        f'bash -lc "cat /tmp/node_{iteration}.txt"',
        # 6. System info
        'bash -lc "uname -a"',
    ]

    return commands


def build_process_management_bundle(iteration: int) -> List[tuple[str, str]]:
    """
    Build process management commands (spawn + kill).

    Returns list of (command, description) tuples.
    Only run every ~25 iterations.
    """
    if iteration % 25 != 0:
        return []

    return [
        ('bash -lc "sleep 30 & echo $!"', "spawn_background_process"),
        # Note: The PID from the above command needs to be captured
        # and used to kill the process. This is handled in session.py
    ]


def build_filesystem_test_bundle(iteration: int) -> List[tuple[str, str]]:
    """
    Build filesystem API test commands (via SDK, not exec).

    Returns list of (operation, path, content) tuples for SDK filesystem calls.
    Only run every ~10 iterations.
    """
    if iteration % 10 != 0:
        return []

    return [
        ("write", f"/tmp/sdk_test_{iteration}.txt", f"sdk content {iteration}"),
        ("read", f"/tmp/sdk_test_{iteration}.txt", None),
        ("exists", f"/tmp/sdk_test_{iteration}.txt", None),
        ("list", "/tmp", None),
    ]


def get_command_budget(hold_time_seconds: int) -> int:
    """
    Calculate command budget based on hold time.

    Target: ~25 commands per 5 minutes (5 commands/min).

    Args:
        hold_time_seconds: Planned hold time in seconds

    Returns:
        Number of commands to execute during the session
    """
    hold_minutes = hold_time_seconds / 60
    return min(500, max(10, int(hold_minutes * 5)))


def build_command_list(
    image: str,
    total_commands: int,
    enable_network: bool = True,
) -> List[str]:
    """
    Build a list of commands for a session.

    Args:
        image: Sandbox image ("python" or "node")
        total_commands: Total number of commands to generate
        enable_network: Whether to include network-dependent commands

    Returns:
        List of command strings to execute
    """
    commands = []
    iteration = 0

    while len(commands) < total_commands:
        if image == "python":
            bundle = build_python_command_bundle(iteration, enable_network)
        elif image == "node":
            bundle = build_node_command_bundle(iteration, enable_network)
        else:
            raise ValueError(f"Unknown image: {image}")

        commands.extend(bundle)
        iteration += 1

    # Trim to exact count
    return commands[:total_commands]
