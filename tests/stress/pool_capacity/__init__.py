"""
Rigorous Pool Test for do-app-sandbox SDK.

A comprehensive 4-hour stress test that validates:
- Command correctness (0 failure tolerance)
- Pool effectiveness (pool hits vs cold starts)
- Capacity enforcement (never exceed 25 sandboxes)
- Lifecycle robustness

Run with:
    uv run python -m tests.stress.pool_capacity.run_25cap_4hr --help
"""

__version__ = "1.0.0"
