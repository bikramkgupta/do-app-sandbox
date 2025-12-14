"""Smoke runner for App Platform Sandbox.

Runs lightweight lifecycle + exec checks for python/node images and
emits JSON results to a file for quick inspection.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from do_app_sandbox import Sandbox
from do_app_sandbox.spaces import create_spaces_config_from_env


@dataclass
class SmokeResult:
    image: str
    app_id: Optional[str]
    url: Optional[str]
    create_seconds: Optional[float]
    delete_seconds: Optional[float]
    echo_stdout: Optional[str]
    echo_exit: Optional[int]
    version_stdout: Optional[str]
    version_exit: Optional[int]
    error: Optional[str] = None


def run_smoke(image: str, registry: str, region: str, spaces: bool) -> SmokeResult:
    app_id = None
    url = None
    create_seconds = None
    delete_seconds = None
    echo_stdout = None
    echo_exit = None
    version_stdout = None
    version_exit = None
    error = None

    spaces_config = create_spaces_config_from_env() if spaces else None

    name = f"smoke-{image}-{int(time.time())}"
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
        create_seconds = time.perf_counter() - start

        app_id = sandbox.app_id
        url = sandbox.get_url()

        # basic transport test
        echo_res = sandbox.exec("echo transport-ok")
        echo_stdout = echo_res.stdout
        echo_exit = echo_res.exit_code

        # interpreter version test per image
        version_cmd = "python3 --version" if image == "python" else "node --version"
        ver_res = sandbox.exec(version_cmd)
        version_stdout = ver_res.stdout
        version_exit = ver_res.exit_code

    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    finally:
        if app_id:
            try:
                start = time.perf_counter()
                sandbox.delete()
                delete_seconds = time.perf_counter() - start
            except Exception as exc:  # noqa: BLE001
                # best-effort cleanup; keep the error text
                if error:
                    error = f"{error}; cleanup: {exc}"
                else:
                    error = f"cleanup: {exc}"

    return SmokeResult(
        image=image,
        app_id=app_id,
        url=url,
        create_seconds=create_seconds,
        delete_seconds=delete_seconds,
        echo_stdout=echo_stdout,
        echo_exit=echo_exit,
        version_stdout=version_stdout,
        version_exit=version_exit,
        error=error,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="App Platform Sandbox smoke tests")
    parser.add_argument(
        "--images",
        nargs="+",
        default=["python", "node"],
        help="Images to test (default: python node)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/artifacts")
        / f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
        help="Path to write JSON results",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="App Platform region (lower-case). Defaults to APP_SANDBOX_REGION or 'nyc'",
    )
    parser.add_argument(
        "--spaces",
        action="store_true",
        help="Enable Spaces config from env for large-file paths",
    )
    args = parser.parse_args()

    registry = os.environ.get("APP_SANDBOX_REGISTRY")
    if not registry:
        raise SystemExit("APP_SANDBOX_REGISTRY env var is required for smoke tests")

    region = (args.region or os.environ.get("APP_SANDBOX_REGION") or "nyc").lower()

    results: List[Dict[str, Any]] = []
    for image in args.images:
        res = run_smoke(image, registry, region, spaces=args.spaces)
        results.append(asdict(res))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "results": results,
            },
            indent=2,
        )
    )
    print(f"Wrote smoke results to {args.output}")


if __name__ == "__main__":
    main()
