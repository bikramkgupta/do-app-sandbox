"""CLI entry point for running as a module.

Allows running the CLI as: python -m do_app_sandbox
"""

from .cli import main

if __name__ == "__main__":
    exit(main())
