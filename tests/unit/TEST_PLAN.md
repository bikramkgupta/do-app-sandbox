# Unit Tests Plan

Fast tests with mocks that don't require real DO credentials.

## test_types.py - Type and Dataclass Tests

| Test | Description |
|------|-------------|
| `test_sandbox_mode_enum` | Verify SandboxMode.WORKER and SERVICE values |
| `test_sandbox_state_enum` | Verify SandboxState enum values |
| `test_service_config_defaults` | ServiceConfig has correct defaults |
| `test_service_config_custom` | ServiceConfig accepts custom values |
| `test_stream_event_creation` | StreamEvent dataclass creation |
| `test_snapshot_metadata_creation` | SnapshotMetadata with all fields |
| `test_hibernated_sandbox_creation` | HibernatedSandbox stores mode, config, metadata |
| `test_git_credentials_https` | GitCredentials with token |
| `test_git_credentials_ssh` | GitCredentials with ssh_key |
| `test_exposed_port_creation` | ExposedPort with url and protocol |

## test_service_client.py - HTTP Client Tests

| Test | Description |
|------|-------------|
| `test_client_initialization` | Client stores base_url and token |
| `test_client_headers` | Authorization header is set correctly |
| `test_exec_request_format` | exec() sends correct JSON payload |
| `test_exec_response_parsing` | exec() parses CommandResult correctly |
| `test_exec_stream_sse_parsing` | exec_stream() parses SSE events correctly |
| `test_exec_stream_event_types` | Handles stdout, stderr, exit, error events |
| `test_exec_background_response` | exec_background() returns pid |
| `test_process_list_parsing` | list_processes() parses response |
| `test_session_create_response` | create_session() returns session_id |
| `test_async_client_initialization` | AsyncSandboxServiceClient works |

## test_snapshot.py - Snapshot Manager Logic Tests

| Test | Description |
|------|-------------|
| `test_snapshot_id_generation` | Auto-generates snap-xxxx ID |
| `test_default_exclude_patterns` | Default excludes caches, keeps deps |
| `test_tar_command_building` | Builds correct tar command with excludes |
| `test_metadata_serialization` | SnapshotMetadata to/from JSON |
| `test_snapshot_key_format` | Spaces key format is correct |
| `test_list_snapshots_filtering` | Filters by image and tags |

## test_sandbox_state.py - Sandbox State Machine Tests

| Test | Description |
|------|-------------|
| `test_initial_state_active` | New sandbox starts in ACTIVE state |
| `test_ensure_awake_active` | _ensure_awake() passes for ACTIVE |
| `test_ensure_awake_hibernated` | _ensure_awake() raises for HIBERNATED |
| `test_mode_property` | mode property returns correct value |
| `test_state_property` | state property returns correct value |

## test_deployer.py - Deployer Service Mode Tests

| Test | Description |
|------|-------------|
| `test_worker_spec_generation` | Worker mode generates worker spec |
| `test_service_spec_generation` | Service mode generates service spec |
| `test_service_token_generation` | Service mode generates random token |
| `test_service_spec_has_env_token` | Service spec includes SANDBOX_API_TOKEN |
| `test_service_spec_cache_disabled` | Service spec has cache disabled for SSE |
| `test_image_repo_mapping` | Correct image repos for worker/service |

## test_exceptions.py - Exception Tests

| Test | Description |
|------|-------------|
| `test_snapshot_error_hierarchy` | SnapshotError subclasses |
| `test_service_mode_error_hierarchy` | ServiceModeError subclasses |
| `test_hibernation_error_hierarchy` | HibernationError subclasses |
| `test_exception_messages` | Exceptions have descriptive messages |
