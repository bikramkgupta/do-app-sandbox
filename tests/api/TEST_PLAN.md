# Container API Tests Plan

Tests for the FastAPI sandbox_api server running inside containers.
Can run locally with Docker or against a deployed service.

## Running Locally

```bash
# Build and run the container
docker build -t sandbox-api-test -f images/sandbox-python-service/Dockerfile images/
docker run -p 8080:8080 -e SANDBOX_API_TOKEN=test-token sandbox-api-test

# Run tests
SANDBOX_API_URL=http://localhost:8080 SANDBOX_API_TOKEN=test-token pytest tests/container/
```

## test_health.py - Health Check Tests

| Test | Description |
|------|-------------|
| `test_health_endpoint` | GET /health returns 200 |
| `test_health_response_format` | Response has status and mode |
| `test_health_no_auth_required` | /health works without token |

## test_exec.py - Command Execution Tests

| Test | Description |
|------|-------------|
| `test_exec_simple_command` | POST /api/exec runs command |
| `test_exec_returns_stdout` | Captures stdout correctly |
| `test_exec_returns_stderr` | Captures stderr correctly |
| `test_exec_returns_exit_code` | Returns correct exit code |
| `test_exec_with_env` | Environment variables work |
| `test_exec_with_cwd` | Working directory works |
| `test_exec_timeout` | Times out long commands |
| `test_exec_requires_auth` | Returns 401 without token |
| `test_exec_invalid_token` | Returns 403 with bad token |

## test_exec_stream.py - Streaming Execution Tests

| Test | Description |
|------|-------------|
| `test_exec_stream_returns_sse` | Response is text/event-stream |
| `test_exec_stream_stdout_events` | Yields stdout events |
| `test_exec_stream_stderr_events` | Yields stderr events |
| `test_exec_stream_exit_event` | Yields exit event at end |
| `test_exec_stream_interleaved` | stdout/stderr interleaved correctly |
| `test_exec_stream_no_buffering` | Events arrive in real-time |

## test_background.py - Background Process Tests

| Test | Description |
|------|-------------|
| `test_exec_background_returns_pid` | Returns process ID |
| `test_exec_background_process_runs` | Process actually runs |
| `test_list_processes` | GET /api/processes lists them |
| `test_process_status_running` | Shows running status |
| `test_process_status_stopped` | Shows stopped after exit |
| `test_get_process_logs` | GET /api/processes/{pid}/logs |
| `test_get_process_logs_tail` | Tail parameter works |
| `test_stream_process_logs` | SSE log streaming works |
| `test_kill_process` | POST /api/processes/{pid}/kill |
| `test_kill_process_signal` | Custom signal works |

## test_sessions.py - Session Management Tests

| Test | Description |
|------|-------------|
| `test_create_session` | POST /api/sessions creates session |
| `test_create_session_with_env` | Session has custom env vars |
| `test_create_session_with_cwd` | Session has custom cwd |
| `test_list_sessions` | GET /api/sessions lists all |
| `test_get_session` | GET /api/sessions/{id} returns info |
| `test_session_exec` | POST /api/sessions/{id}/exec runs in session |
| `test_session_state_persists` | cd in session persists |
| `test_session_env_persists` | export in session persists |
| `test_close_session` | DELETE /api/sessions/{id} closes |
| `test_duplicate_session_error` | Can't create same ID twice |

## test_files.py - File Operations Tests

| Test | Description |
|------|-------------|
| `test_list_files` | GET /api/files lists directory |
| `test_list_files_shows_metadata` | Shows name, size, is_dir |
| `test_read_file` | GET /api/files/content reads file |
| `test_read_binary_file` | Binary files base64 encoded |
| `test_write_file` | POST /api/files/content writes |
| `test_write_creates_dirs` | Creates parent directories |
| `test_download_file` | GET /api/files/download works |

## test_proxy.py - Port Proxy Tests

| Test | Description |
|------|-------------|
| `test_proxy_get_request` | GET /proxy/{port}/ proxies |
| `test_proxy_post_request` | POST requests proxied |
| `test_proxy_with_path` | Path passed through |
| `test_proxy_with_query` | Query string passed |
| `test_proxy_headers_forwarded` | Headers forwarded (except auth) |
| `test_proxy_connection_error` | 502 when port not listening |
| `test_proxy_timeout` | 504 on timeout |
