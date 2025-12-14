"""Performance harness skeleton for App Platform Sandbox.

This runner can time lifecycle, exec throughput, and (optionally) large-file
transfers and app boot flows. Heavy scenarios are opt-in via flags so default
execution stays light.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from do_app_sandbox import Sandbox
from do_app_sandbox.spaces import create_spaces_config_from_env


@dataclass
class PerfCaseResult:
    name: str
    status: str  # success|error|skipped
    metrics: Dict[str, Any]
    error: Optional[str] = None


def time_create_delete(image: str, registry: str, region: str, spaces: bool) -> PerfCaseResult:
    spaces_config = create_spaces_config_from_env() if spaces else None
    name = f"perf-{image}-{int(time.time())}"

    metrics: Dict[str, Any] = {}
    sandbox = None
    try:
        start = time.perf_counter()
        sandbox = Sandbox.create(
            registry=registry,
            image=image,
            name=name,
            region=region,
            wait_ready=True,
            timeout=900,
            spaces_config=spaces_config,
        )
        metrics["create_seconds"] = time.perf_counter() - start

        echo = sandbox.exec("echo perf-ok")
        metrics["echo_exit"] = echo.exit_code
        metrics["echo_stdout"] = echo.stdout

        return PerfCaseResult(name=f"lifecycle-{image}", status="success", metrics=metrics)
    except Exception as exc:  # noqa: BLE001
        return PerfCaseResult(name=f"lifecycle-{image}", status="error", metrics=metrics, error=str(exc))
    finally:
        if sandbox:
            start = time.perf_counter()
            try:
                sandbox.delete()
                metrics["delete_seconds"] = time.perf_counter() - start
            except Exception as exc:  # noqa: BLE001
                metrics["delete_error"] = str(exc)


def time_small_uploads(registry: str, region: str) -> List[PerfCaseResult]:
    """Measure small uploads over the console transport (websocket)."""

    sizes = [(1, 1 * 1024 * 1024), (4, 4 * 1024 * 1024)]  # MB, bytes
    results: List[PerfCaseResult] = []

    sandbox = None
    try:
        sandbox = Sandbox.create(
            registry=registry,
            image="python",
            region=region,
            wait_ready=True,
            timeout=900,
        )

        for label, size_bytes in sizes:
            metrics: Dict[str, Any] = {"size_mb": label}
            try:
                # Generate random content
                fd, tmp_path_str = tempfile.mkstemp()
                os.close(fd)
                tmp_path = Path(tmp_path_str)
                tmp_path.write_bytes(os.urandom(size_bytes))

                start = time.perf_counter()
                sandbox.filesystem.upload_file(str(tmp_path), f"/tmp/small-{label}mb.bin")
                metrics["upload_seconds"] = time.perf_counter() - start

                # Verify size on remote
                size_remote = sandbox.filesystem.get_size(f"/tmp/small-{label}mb.bin")
                metrics["remote_size"] = size_remote

                results.append(
                    PerfCaseResult(
                        name=f"small-upload-{label}mb",
                        status="success",
                        metrics=metrics,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    PerfCaseResult(
                        name=f"small-upload-{label}mb",
                        status="error",
                        metrics=metrics,
                        error=str(exc),
                    )
                )
    except Exception as exc:  # noqa: BLE001
        results.append(
            PerfCaseResult(
                name="small-uploads",
                status="error",
                metrics={},
                error=str(exc),
            )
        )
    finally:
        if sandbox:
            try:
                sandbox.delete()
            except Exception:
                pass

    return results


def run_large_file(registry: str, region: str, size_mb: int) -> PerfCaseResult:
    spaces_config = create_spaces_config_from_env()
    if not spaces_config:
        return PerfCaseResult(
            name="large-file",
            status="skipped",
            metrics={"reason": "Spaces env not configured"},
        )

    sandbox = None
    metrics: Dict[str, Any] = {"size_mb": size_mb}
    try:
        sandbox = Sandbox.create(
            registry=registry,
            image="python",
            region=region,
            wait_ready=True,
            timeout=900,
            spaces_config=spaces_config,
        )

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(os.urandom(size_mb * 1024 * 1024))
            tmp_path = Path(tmp.name)

        start = time.perf_counter()
        sandbox.filesystem.upload_large(str(tmp_path), "/tmp/perf.bin", cleanup=True)
        metrics["upload_seconds"] = time.perf_counter() - start

        start = time.perf_counter()
        sandbox.filesystem.download_large("/tmp/perf.bin", str(tmp_path) + ".dl", cleanup=True)
        metrics["download_seconds"] = time.perf_counter() - start

        return PerfCaseResult(name="large-file", status="success", metrics=metrics)
    except Exception as exc:  # noqa: BLE001
        return PerfCaseResult(name="large-file", status="error", metrics=metrics, error=str(exc))
    finally:
        if sandbox:
            try:
                sandbox.delete()
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="App Platform Sandbox perf harness")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/artifacts")
        / f"perf-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    )
    parser.add_argument("--region", default=None, help="App Platform region (lower-case)")
    parser.add_argument("--images", nargs="+", default=["python", "node"], help="Images for lifecycle timing")
    parser.add_argument("--run-large-file", action="store_true", help="Run 100MB Spaces transfer test")
    parser.add_argument("--large-file-mb", type=int, default=100, help="Size for large-file test (MB)")
    parser.add_argument("--spaces", action="store_true", help="Use Spaces env for lifecycle runs too")
    args = parser.parse_args()

    registry = os.environ.get("APP_SANDBOX_REGISTRY")
    if not registry:
        raise SystemExit("APP_SANDBOX_REGISTRY env var is required for perf tests")

    region = (args.region or os.environ.get("APP_SANDBOX_REGION") or "nyc").lower()

    results: List[Dict[str, Any]] = []

    for image in args.images:
        results.append(asdict(time_create_delete(image, registry, region, spaces=args.spaces)))

    # Small console uploads
    for res in time_small_uploads(registry, region):
        results.append(asdict(res))

    if args.run_large_file:
        results.append(asdict(run_large_file(registry, region, args.large_file_mb)))
    else:
        results.append(
            {
                "name": "large-file",
                "status": "skipped",
                "metrics": {"reason": "pass --run-large-file to enable"},
                "error": None,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region": region,
                "results": results,
            },
            indent=2,
        )
    )
    print(f"Wrote perf results to {args.output}")


if __name__ == "__main__":
    main()
