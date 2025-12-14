"""End-to-end exercise of Python sandbox with Spaces-backed transfer.

Steps:
1) Create sandbox (measure boot time)
2) Install Python if needed (uv python install)
3) Install dependencies (pandas, numpy) to test pip workflow
4) Upload and run a moderately complex Python program
5) Generate a large CSV locally (default 50MB), transfer via Spaces (upload_large)
6) Analyze CSV using pandas/numpy in sandbox

Run with: uv run --extra spaces python -m tests.full_python_sandbox_run --dotenv ../.env
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from do_app_sandbox import Sandbox
from do_app_sandbox.exceptions import FileOperationError
from do_app_sandbox.spaces import create_spaces_config_from_env


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def make_complex_script() -> str:
    return """import json, math, random, statistics, time

def compute():
    random.seed(42)
    data = []
    for i in range(1, 1200):
        vec = [math.sin(i * 0.01 + j) * math.cos(j * 0.2) + random.random() for j in range(24)]
        data.append({
            "idx": i,
            "sum": sum(vec),
            "max": max(vec),
            "min": min(vec),
            "mean": statistics.fmean(vec),
            "p95": statistics.quantiles(vec, n=20)[18],
        })
    sums = [row["sum"] for row in data]
    digest = sum(int(abs(x) * 1000) for x in sums) % 10_000_000
    return {
        "rows": len(data),
        "mean_of_sums": statistics.fmean(sums),
        "max_sum": max(sums),
        "min_sum": min(sums),
        "checksum": digest,
    }

if __name__ == "__main__":
    start = time.perf_counter()
    result = compute()
    result["duration_seconds"] = round(time.perf_counter() - start, 3)
    print(json.dumps(result, indent=2))
"""


def write_csv(path: Path, target_mb: int, seed: int = 7) -> int:
    random.seed(seed)
    written = 0
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "value_a", "value_b", "category"])
        i = 0
        while written < target_mb * 1024 * 1024:
            row = [
                i,
                round(random.random() * 1_000_000, 4),
                round(random.random() * 10_000, 4),
                random.choice(["alpha", "beta", "gamma", "delta"]),
            ]
            writer.writerow(row)
            written = f.tell()
            i += 1
    return written


def ensure_python(sandbox: Sandbox) -> str:
    """Find or install a working python3 binary inside the sandbox."""

    def works(cmd: str) -> bool:
        probe = sandbox.exec(f"{cmd} -c \"import sys; print('py-ok', sys.version)\"")
        return probe.exit_code == 0

    candidates = [
        "python3",
        "/home/sandbox/.local/bin/python3.12",
        "/home/sandbox/.local/bin/python3.13",
    ]
    for candidate in candidates:
        if works(candidate):
            return candidate

    install = sandbox.exec("uv python install 3.12", timeout=600)
    if install.exit_code != 0:
        raise SystemExit(f"uv python install failed: {install.stderr or install.stdout}")

    find = sandbox.exec("uv python find 3.12")
    if find.exit_code != 0:
        raise SystemExit(f"uv python find failed: {find.stderr or find.stdout}")

    python_cmd = find.stdout.strip()
    if not works(python_cmd):
        raise SystemExit("Python installation completed but probe failed.")

    return python_cmd


ANALYZE_SCRIPT = """import json, sys, time
import pandas as pd
import numpy as np

def analyze(path: str):
    # Load CSV using pandas
    df = pd.read_csv(path)

    # Compute statistics using pandas/numpy
    results = {
        "rows": len(df),
        "columns": list(df.columns),
        "a_mean": float(df["value_a"].mean()),
        "a_std": float(df["value_a"].std()),
        "a_p99": float(np.percentile(df["value_a"], 99)),
        "b_mean": float(df["value_b"].mean()),
        "b_std": float(df["value_b"].std()),
        "b_p99": float(np.percentile(df["value_b"], 99)),
        "category_counts": df["category"].value_counts().to_dict(),
        "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
    }
    return results

if __name__ == "__main__":
    path = sys.argv[1]
    start = time.perf_counter()
    res = analyze(path)
    res["duration_seconds"] = round(time.perf_counter() - start, 3)
    print(json.dumps(res, indent=2))
"""


@dataclass
class StepResult:
    name: str
    duration_seconds: float
    details: Dict[str, object]
    error: Optional[str] = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Full Python sandbox run with Spaces CSV analysis.")
    parser.add_argument("--dotenv", type=Path, default=Path(__file__).resolve().parent.parent / ".env")
    parser.add_argument("--csv-mb", type=int, default=50, help="Target CSV size in MB (default: 50).")
    parser.add_argument("--name", help="Sandbox name (default: auto with timestamp).")
    parser.add_argument("--keep-sandbox", action="store_true", help="Skip sandbox deletion for debugging.")
    parser.add_argument("--keep-spaces", action="store_true", help="Keep file in Spaces after transfer (for verification).")
    args = parser.parse_args()

    load_dotenv(args.dotenv)
    spaces_config = create_spaces_config_from_env()
    if not spaces_config:
        raise SystemExit("Spaces config missing; set SPACES_BUCKET and SPACES_REGION (and keys).")

    results: list[StepResult] = []
    sandbox = None

    print(f"[{utc_now()}] Starting run")

    # Boot sandbox
    name = args.name or f"full-run-{int(time.time())}"
    boot_start = time.perf_counter()
    sandbox = Sandbox.create(
        image="python",
        name=name,
        spaces_config=spaces_config,
        wait_ready=True,
        timeout=900,
    )
    boot_end = time.perf_counter()
    results.append(
        StepResult(
            name="boot",
            duration_seconds=boot_end - boot_start,
            details={"app_id": sandbox.app_id, "url": sandbox.get_url(), "name": name},
        )
    )
    print(f"[{utc_now()}] Sandbox ready: {sandbox.app_id} ({name})")

    # Resolve or install python
    py_start = time.perf_counter()
    python_cmd = ensure_python(sandbox)
    py_end = time.perf_counter()
    results.append(
        StepResult(
            name="python_bootstrap",
            duration_seconds=py_end - py_start,
            details={"python_cmd": python_cmd},
        )
    )
    print(f"[{utc_now()}] Python ready: {python_cmd}")

    # Install dependencies (pandas, numpy) in a virtual environment
    deps_start = time.perf_counter()
    # Create venv and install packages
    venv_cmd = "cd /tmp && uv venv --quiet && uv pip install pandas numpy --quiet"
    deps_res = sandbox.exec(venv_cmd, timeout=300)
    deps_end = time.perf_counter()
    results.append(
        StepResult(
            name="install_dependencies",
            duration_seconds=deps_end - deps_start,
            details={
                "command": venv_cmd,
                "exit_code": deps_res.exit_code,
                "packages": ["pandas", "numpy"],
            },
            error=deps_res.stderr.strip() or None if deps_res.exit_code != 0 else None,
        )
    )
    if deps_res.exit_code != 0:
        print(f"[{utc_now()}] WARNING: Dependency install failed: {deps_res.stderr or deps_res.stdout}")
    else:
        print(f"[{utc_now()}] Dependencies installed (pandas, numpy)")
        # Update python_cmd to use the venv
        python_cmd = "/tmp/.venv/bin/python"

    # Complex Python script
    complex_path = "/tmp/complex.py"
    sandbox.filesystem.write_file(complex_path, make_complex_script())
    run_start = time.perf_counter()
    exec_res = sandbox.exec(f"{python_cmd} {complex_path}")
    run_end = time.perf_counter()
    results.append(
        StepResult(
            name="complex_script",
            duration_seconds=run_end - run_start,
            details={"exit_code": exec_res.exit_code, "stdout": exec_res.stdout.strip()},
            error=exec_res.stderr.strip() or None if exec_res.exit_code != 0 else None,
        )
    )
    print(f"[{utc_now()}] Complex script exit: {exec_res.exit_code}")

    # Large CSV generation locally
    csv_path = Path(tempfile.gettempdir()) / "sandbox-large.csv"
    csv_bytes = write_csv(csv_path, args.csv_mb)
    print(f"[{utc_now()}] Generated CSV locally: {csv_bytes} bytes")

    # Transfer CSV via Spaces into sandbox
    upload_start = time.perf_counter()
    cleanup_spaces = not args.keep_spaces  # If --keep-spaces, don't cleanup
    try:
        sandbox.filesystem.upload_large(str(csv_path), "/tmp/data.csv", cleanup=cleanup_spaces)
    except FileOperationError as exc:
        # Occasionally the existence check reports false negatives; verify manually before failing.
        exists_res = sandbox.exec("stat /tmp/data.csv")
        if exists_res.exit_code != 0:
            raise
        else:
            # Treat as success; log the spurious error detail.
            results.append(
                StepResult(
                    name="upload_large_csv_check_override",
                    duration_seconds=0.0,
                    details={"note": "upload_large reported missing file but stat succeeded"},
                    error=str(exc),
                )
            )
    upload_end = time.perf_counter()
    try:
        remote_size = sandbox.filesystem.get_size("/tmp/data.csv")
    except FileOperationError:
        stat_res = sandbox.exec("stat -c%s /tmp/data.csv")
        if stat_res.exit_code != 0 or not stat_res.stdout.strip().isdigit():
            raise
        remote_size = int(stat_res.stdout.strip())
    results.append(
        StepResult(
            name="upload_large_csv",
            duration_seconds=upload_end - upload_start,
            details={"local_bytes": csv_bytes, "remote_bytes": remote_size},
        )
    )
    print(f"[{utc_now()}] CSV transferred to sandbox ({remote_size} bytes)")

    # Analyze CSV inside sandbox
    analyze_path = "/tmp/analyze_csv.py"
    sandbox.filesystem.write_file(analyze_path, ANALYZE_SCRIPT)
    analyze_start = time.perf_counter()
    analyze_res = sandbox.exec(f"{python_cmd} {analyze_path} /tmp/data.csv")
    analyze_end = time.perf_counter()
    results.append(
        StepResult(
            name="analyze_csv",
            duration_seconds=analyze_end - analyze_start,
            details={"exit_code": analyze_res.exit_code, "stdout": analyze_res.stdout.strip()},
            error=analyze_res.stderr.strip() or None if analyze_res.exit_code != 0 else None,
        )
    )
    print(f"[{utc_now()}] CSV analysis exit: {analyze_res.exit_code}")

    # Cleanup
    if not args.keep_sandbox and sandbox:
        delete_start = time.perf_counter()
        sandbox.delete()
        delete_end = time.perf_counter()
        results.append(
            StepResult(
                name="delete_sandbox",
                duration_seconds=delete_end - delete_start,
                details={"app_id": sandbox.app_id},
            )
        )
        print(f"[{utc_now()}] Sandbox deleted ({delete_end - delete_start:.2f}s)")

    # Remove local temp
    try:
        csv_path.unlink()
    except FileNotFoundError:
        pass

    # Print detailed summary
    print("\n" + "=" * 60)
    print("COMPREHENSIVE SANDBOX TEST REPORT")
    print("=" * 60)
    print(f"Timestamp: {utc_now()}")
    print(f"CSV Size: {args.csv_mb} MB")
    print()
    print("--- Timing Summary ---")
    total_time = sum(r.duration_seconds for r in results)
    for res in results:
        status = "OK" if res.error is None else "ERROR"
        print(f"  {res.name}: {res.duration_seconds:.2f}s [{status}]")
    print(f"  TOTAL: {total_time:.2f}s")
    print()

    # Print detailed results
    print("--- Step Details ---")
    for res in results:
        print(f"\n[{res.name}]")
        print(f"  Duration: {res.duration_seconds:.2f}s")
        for key, value in res.details.items():
            # Truncate long values
            val_str = str(value)
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            print(f"  {key}: {val_str}")
        if res.error:
            print(f"  ERROR: {res.error}")

    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)

    # Print retention info if keeping resources
    if args.keep_sandbox or args.keep_spaces:
        print("\n--- Resources Retained ---")
        if args.keep_sandbox:
            print(f"  Sandbox kept: {name}")
            print(f"  URL: {results[0].details.get('url', 'N/A')}")
            print(f"  To delete: sandbox delete {name} --registry $APP_SANDBOX_REGISTRY --force")
        if args.keep_spaces:
            print(f"  Spaces file kept in bucket: {spaces_config.bucket}")
            print(f"  To list: s3cmd ls s3://{spaces_config.bucket}/sandbox-*/")
            print(f"  To delete: s3cmd del s3://{spaces_config.bucket}/sandbox-*/ --recursive")


if __name__ == "__main__":
    main()
