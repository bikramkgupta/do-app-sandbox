# Integration Tests Plan

Tests requiring real DigitalOcean credentials and Spaces.
These are slower but validate actual behavior.

## Prerequisites

```bash
export DIGITALOCEAN_TOKEN="your-token"
export SPACES_BUCKET="your-bucket"
export SPACES_REGION="nyc3"
export SPACES_ACCESS_KEY="your-key"
export SPACES_SECRET_KEY="your-secret"
```

## test_service_mode.py - Service Mode E2E Tests

| Test | Description | Time |
|------|-------------|------|
| `test_create_service_mode_sandbox` | Create sandbox with mode=SERVICE | ~60s |
| `test_service_mode_exec` | exec() works via HTTP API | ~5s |
| `test_service_mode_exec_stream` | exec_stream() yields SSE events | ~10s |
| `test_service_mode_stream_stdout_stderr` | Streaming captures both streams | ~5s |
| `test_service_mode_background_process` | Background exec returns pid | ~5s |
| `test_service_mode_process_logs` | Can retrieve process logs | ~5s |
| `test_service_mode_port_exposure` | expose_port() returns valid URL | ~2s |
| `test_service_mode_port_proxy` | Port proxy actually works | ~10s |
| `test_service_mode_sessions` | Session create/exec/close flow | ~10s |

## test_snapshots.py - Snapshot E2E Tests

| Test | Description | Time |
|------|-------------|------|
| `test_create_snapshot_basic` | Create snapshot of /workspace | ~30s |
| `test_create_snapshot_custom_paths` | Snapshot with custom paths | ~30s |
| `test_create_snapshot_with_deps` | Snapshot includes node_modules | ~45s |
| `test_snapshot_metadata_stored` | Metadata retrievable from Spaces | ~5s |
| `test_restore_snapshot_basic` | Restore snapshot to new sandbox | ~30s |
| `test_restore_preserves_files` | Restored files match original | ~10s |
| `test_list_snapshots` | List returns created snapshots | ~5s |
| `test_list_snapshots_filter_image` | Filter snapshots by image | ~5s |
| `test_delete_snapshot` | Delete removes from Spaces | ~5s |
| `test_snapshot_not_found` | Restore non-existent raises error | ~2s |

## test_hibernation.py - Hibernate/Wake E2E Tests

| Test | Description | Time |
|------|-------------|------|
| `test_hibernate_creates_snapshot` | hibernate() creates snapshot | ~45s |
| `test_hibernate_deletes_sandbox` | hibernate() deletes the app | ~10s |
| `test_hibernate_returns_reference` | Returns HibernatedSandbox | ~2s |
| `test_wake_creates_new_sandbox` | wake() creates new sandbox | ~60s |
| `test_wake_restores_state` | wake() restores files | ~30s |
| `test_wake_with_pool` | wake() with pool is faster | ~15s |
| `test_double_hibernate_error` | Can't hibernate twice | ~2s |
| `test_exec_on_hibernated_error` | exec() on hibernated raises | ~2s |

## test_git_checkout.py - Git Operations Tests

| Test | Description | Time |
|------|-------------|------|
| `test_git_checkout_public_repo` | Clone public GitHub repo | ~15s |
| `test_git_checkout_branch` | Clone specific branch | ~15s |
| `test_git_checkout_shallow` | Shallow clone (depth=1) | ~10s |
| `test_git_checkout_with_token` | Clone with PAT (private repo) | ~15s |
| `test_git_checkout_custom_path` | Clone to custom path | ~15s |

## test_manager_snapshots.py - Pool + Snapshot Tests

| Test | Description | Time |
|------|-------------|------|
| `test_acquire_with_snapshot` | Pool acquire + restore | ~20s |
| `test_wake_hibernated_via_pool` | wake_hibernated() with pool | ~20s |
| `test_acquire_snapshot_not_found` | Error on missing snapshot | ~5s |
| `test_acquire_spaces_not_configured` | Error without Spaces config | ~2s |
