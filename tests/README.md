# Tests and Runners

Utilities under `tests/` rely on `doctl` authentication and (optionally) Spaces configuration. Commands below assume `uv` is installed.

## Environment
- Authenticate doctl (`doctl auth init`). No `DIGITALOCEAN_TOKEN` env var is required if doctl is already configured.
- Optional: `.env` at the repo root for image/Spaces overrides:
  - `GHCR_OWNER` (default: `bikramkgupta`)
  - `GHCR_REGISTRY` (default: `ghcr.io`)
  - `APP_SANDBOX_REGION` (default: `atl1`)
  - Spaces keys: `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_BUCKET`, `SPACES_REGION`, optional `SPACES_ENDPOINT`
- Load the file before running: `set -a && source ../.env && set +a`

## How to Run
- Integration (creates and deletes a sandbox): `uv run --extra dev python -m pytest tests/test_integration.py -s`
- Smoke harness (writes JSON to `tests/artifacts/`): `uv run --extra dev python -m tests.smoke.main --spaces`
- Perf harness (enable large file with `--run-large-file`): `uv run --extra dev python -m tests.perf.main --spaces --run-large-file`
- Spaces presigned probe: `uv run --extra spaces python -m tests.presigned_url_check --dotenv ../.env --expires 900` (add `--file <path>` to upload a specific file, `--keep` to skip cleanup).

## Artifacts
- Smoke/perf JSON outputs live in `tests/artifacts/`.
- Trace logs should be written as `tests/artifacts/trace.log.<timestamp>` when running experiments.
