# Sandbox Reference Tables

Quick lookup for supported SDK and CLI entry points, their parameters, and what they return. Uses the maintained Python and Node images from GHCR (defaults to `ghcr.io/bikramkgupta`; override with `GHCR_OWNER`/`GHCR_REGISTRY`). Custom images and setup steps are intentionally out of scope. doctl must be installed and authenticated (`doctl auth init`); there is no API-only path.

## Lifecycle
| Action | SDK (sync/async) | CLI | Output / Return |
| --- | --- | --- | --- |
| Create sandbox | `Sandbox.create(image*, name?, region?, instance_size?, component_type?, api_token?, wait_ready?, timeout?, spaces_config?)` / `await AsyncSandbox.create(...)` | `sandbox create --image <python|node> [--name --region --instance-size --component-type <service|worker> --no-wait --registry HOST]` | SDK returns a `Sandbox` ready for use (has `app_id`, `status`, `get_url()`); CLI prints ID/URL/status; exit code 0 on success. Workers have no URL. |
| Connect to existing sandbox | `Sandbox.get_from_id(app_id, component?, api_token?, spaces_config?)` / `await AsyncSandbox.get_from_id(...)` | No dedicated command; use `sandbox exec --id <app-id> ...` or `sandbox list` to discover IDs. | SDK returns a `Sandbox` attached to the existing app. |
| List sandboxes | No helper (use CLI/doctl). | `sandbox list [--json] [--registry HOST]` | Table of NAME/ID/STATUS/REGION/URL or JSON; exit code 0 on success, 1 on error. |
| Readiness / status | `sandbox.status`, `sandbox.is_ready()`, `sandbox.wait_ready(timeout?, poll_interval?)` | Status surfaced via `sandbox create` output and `sandbox list`. | Status string (`ACTIVE`, `DEPLOYING`, etc.); `wait_ready` raises on timeout/failure. |
| Delete sandbox | `sandbox.delete()` | `sandbox delete <name> [--id APP_ID] [--all] [--force] [--registry HOST]` | SDK returns `None` after deletion; CLI prints confirmation; exit code 0 on success. |

## Command Execution and Processes
| Action | SDK (sync/async) | CLI | Output / Return |
| --- | --- | --- | --- |
| Run a command | `sandbox.exec(command, env?, cwd?, timeout?)` / `await AsyncSandbox.exec(...)` | `sandbox exec <name|id> "<command>" [--id] [--timeout SECONDS] [--registry HOST]` | SDK returns `CommandResult(stdout, stderr, exit_code, success property)`; CLI streams stdout/stderr and exits with the command's exit code (or 1 on errors). |
| Launch background process | `sandbox.launch_process(command, cwd?, env?)` | Not available directly. | PID of launched process. |
| List processes | `sandbox.list_processes(pattern?)` | Not available directly. | `list[ProcessInfo(pid, command, status, cpu?, memory?)]`. |
| Kill process / all | `sandbox.kill_process(pid) -> bool`; `sandbox.kill_all_processes() -> int` | Not available directly. | `bool` for single kill; count of processes terminated for `kill_all_processes`. |
| Get sandbox URL | `sandbox.get_url()` | Included in `sandbox create` and `sandbox list` output. | Public HTTPS URL string. |

## Files and Transfers (SDK)
| Operation | SDK call (sync/async) | Output / Return |
| --- | --- | --- |
| Read file | `filesystem.read_file(path, binary=False)` / `await AsyncSandbox.filesystem.read_file(...)` | File contents (`str` or `bytes`). |
| Write / append | `filesystem.write_file(path, content, binary=False)`; `filesystem.append_file(path, content)` | `None`; raises `FileOperationError` on failure. |
| Upload / download | `filesystem.upload_file(local, remote)`; `filesystem.download_file(remote, local)` | `None`. |
| Directory and metadata | `filesystem.list_dir(path=".") -> list[FileInfo]`; `mkdir(path, recursive=True)`; `rm(path, recursive=False, force=True)`; `exists(path)`; `is_file(path)`; `is_dir(path)`; `get_size(path)` | Booleans for existence checks, `int` for size, otherwise `None`. |
| Move / copy / permissions | `filesystem.copy(src, dst, recursive=False)`; `filesystem.move(src, dst)`; `filesystem.chmod(path, mode)` | `None`. |
| Large files via Spaces | `filesystem.upload_large(local, remote, progress_callback?, cleanup=False)`; `filesystem.download_large(remote, local, progress_callback?, cleanup=False)` | `None`; uses `SpacesConfig` when configured; falls back to regular transfer for small files. |
| Spaces availability | `filesystem.has_spaces` | `bool` indicating Spaces is configured. |

Note: The CLI does not expose dedicated file/process helpers; use `sandbox exec` with shell commands for those tasks.
