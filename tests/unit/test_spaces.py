"""Upload a file to DigitalOcean Spaces and verify presigned access with curl."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import boto3
import botocore.config

REQUIRED_ENV_VARS = ["SPACES_ACCESS_KEY", "SPACES_SECRET_KEY", "SPACES_BUCKET", "SPACES_REGION"]
DEFAULT_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv(path: Path) -> dict[str, str]:
    """Load a minimal .env file into the current environment without overriding set vars."""
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def ensure_required_env() -> None:
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        missing_str = ", ".join(missing)
        raise SystemExit(f"Missing required Spaces environment variables: {missing_str}")


def prepare_payload(file_arg: str | None) -> tuple[Path, bool]:
    """Return the payload path and whether it should be cleaned up."""
    if file_arg:
        file_path = Path(file_arg).expanduser()
        if not file_path.is_file():
            raise SystemExit(f"Provided file does not exist: {file_path}")
        return file_path, False

    # Default: create a small temporary file for the probe.
    temp_dir = Path(tempfile.gettempdir())
    file_path = temp_dir / f"spaces-presigned-{uuid.uuid4().hex}.txt"
    file_path.write_text(f"spaces presigned probe {uuid.uuid4().hex}\n")
    return file_path, True


def resolve_endpoint(bucket: str, region: str) -> tuple[str, str]:
    """Return endpoint URL and addressing style for the provided bucket/region."""
    endpoint_env = os.environ.get("SPACES_ENDPOINT")
    if endpoint_env:
        endpoint_env = endpoint_env.rstrip("/")
        parsed = urlparse(endpoint_env)
        host_parts = parsed.netloc.split(".")

        # If the provided endpoint already includes the bucket name, strip it off to avoid double-prefixing.
        if host_parts and host_parts[0] == bucket and len(host_parts) > 1:
            netloc = ".".join(host_parts[1:])
            endpoint = f"{parsed.scheme}://{netloc}"
        else:
            endpoint = endpoint_env
        addressing = "virtual"
    else:
        endpoint = f"https://{region}.digitaloceanspaces.com"
        addressing = "virtual"
    return endpoint, addressing


def build_spaces_client(bucket: str, region: str) -> tuple[boto3.session.Session.client, str]:
    endpoint, addressing_style = resolve_endpoint(bucket, region)

    session = boto3.session.Session()
    client = session.client(
        "s3",
        endpoint_url=endpoint,
        config=botocore.config.Config(s3={"addressing_style": addressing_style}),
        region_name=region,
        aws_access_key_id=os.environ["SPACES_ACCESS_KEY"],
        aws_secret_access_key=os.environ["SPACES_SECRET_KEY"],
    )
    return client, endpoint


def run_curl_probe(url: str, timeout: int) -> tuple[int, str, int]:
    """Issue a GET request with curl and return status_code, combined_output, return_code."""
    curl_cmd = [
        "curl",
        "--location",
        "--max-time",
        str(timeout),
        "--silent",
        "--show-error",
        "--dump-header",
        "-",
        "--output",
        "/dev/null",
        "--write-out",
        "HTTP_STATUS:%{http_code}\\n",
        url,
    ]
    proc = subprocess.run(curl_cmd, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    status_line = next((line for line in output.splitlines() if line.startswith("HTTP_STATUS:")), None)
    status_code = int(status_line.split(":", 1)[1]) if status_line else 0
    return status_code, output, proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload to Spaces and verify presigned URL reachability.")
    parser.add_argument("--file", help="Path to an existing file to upload. Defaults to a generated temp file.")
    parser.add_argument(
        "--expires",
        type=int,
        default=900,
        help="Presigned URL expiry in seconds (default: 900 / 15 minutes).",
    )
    parser.add_argument("--key", help="Optional object key to use. Defaults to presigned-tests/<uuid>-<filename>.")
    parser.add_argument("--keep", action="store_true", help="Skip deleting the uploaded object for debugging.")
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=DEFAULT_DOTENV_PATH,
        help=f"Path to .env file with Spaces config (default: {DEFAULT_DOTENV_PATH}).",
    )
    parser.add_argument(
        "--curl-timeout",
        type=int,
        default=15,
        help="Timeout in seconds for the curl verification call.",
    )
    args = parser.parse_args()

    dotenv_loaded = load_dotenv(args.dotenv)
    if dotenv_loaded:
        print(f"Loaded {len(dotenv_loaded)} values from {args.dotenv}")
    else:
        print(f"No .env values loaded from {args.dotenv} (file missing or keys already set)")

    ensure_required_env()
    bucket = os.environ["SPACES_BUCKET"]
    region = os.environ["SPACES_REGION"].lower()

    client, endpoint = build_spaces_client(bucket, region)

    payload_path, cleanup_payload = prepare_payload(args.file)
    object_key = args.key or f"presigned-tests/{uuid.uuid4().hex}-{payload_path.name}"

    print(f"Using endpoint {endpoint}")
    print(f"Uploading {payload_path} to s3://{bucket}/{object_key}")
    client.upload_file(str(payload_path), bucket, object_key)
    print("Upload complete.")

    presigned_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_key},
        ExpiresIn=args.expires,
    )
    print(f"Presigned URL (expires in {args.expires}s): {presigned_url}")

    if not shutil.which("curl"):
        raise SystemExit("curl is required for verification but was not found in PATH.")

    status_code, curl_output, curl_rc = run_curl_probe(presigned_url, args.curl_timeout)
    print("curl output:")
    print(curl_output.rstrip())

    if curl_rc != 0:
        raise SystemExit(f"curl exited with code {curl_rc}")
    if status_code < 200 or status_code >= 400:
        raise SystemExit(f"Presigned URL returned HTTP {status_code}")

    print(f"Presigned URL is active (HTTP {status_code}).")

    if not args.keep:
        try:
            client.delete_object(Bucket=bucket, Key=object_key)
            print("Uploaded object deleted.")
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: failed to delete object: {exc}")

    if cleanup_payload:
        try:
            payload_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
