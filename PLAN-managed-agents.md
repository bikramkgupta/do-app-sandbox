# Plan: Managed Agents on DigitalOcean App Platform

## Context

Anthropic's engineering blog describes their **Managed Agents** architecture — a platform that decouples the "brain" (Claude), the "harness" (orchestrator loop), and the "sandbox" (execution environment). The `do-app-sandbox` SDK already provides the sandbox layer on DigitalOcean App Platform. This plan builds the **harness + frontend** layers on top of it, creating a self-hosted Managed Agents clone that demonstrates the full pattern with a compelling demo.

**Goal**: Build an open-source, self-hosted agent platform on DigitalOcean that lets a user describe a coding task in a web UI and watch an autonomous Claude agent write code, install packages, run tests, and produce working software — all inside a cloud sandbox.

---

## A. End-User Demo Scenarios

### Demo 1: "Build a Flask REST API for a todo app"
User types the request and watches the agent:
1. Write `app.py` with Flask routes (CRUD for todos)
2. Write `requirements.txt` and install dependencies (streaming output visible)
3. Write `test_app.py` with pytest tests
4. Run tests — see them pass
5. Start the Flask server on port 8080
6. User clicks "Preview" to see the running app in an iframe

### Demo 2: "Analyze this CSV and create a visualization"
User uploads a CSV, agent:
1. Installs pandas + matplotlib
2. Writes and runs an analysis script
3. Produces a chart (PNG downloaded and displayed inline)

### Demo 3: "Clone a repo, find the bug, fix it"
User provides a GitHub URL, agent:
1. Clones, installs deps, runs tests (sees failures)
2. Reads code, diagnoses the bug, edits files
3. Re-runs tests — all pass
4. Shows a diff of changes

---

## B. System Architecture

```
+-------------------------------------------+
|        FastAPI + HTMX Frontend            |  <-- Single service on DO App Platform
|  (Server-rendered HTML, SSE streaming)    |
+-------------------------------------------+
|        Orchestrator (Harness)             |
|  - Agent configs, Environment configs     |
|  - Session management & event log         |
|  - Claude Opus 4.6 Messages API calls     |
|  - Tool routing to sandboxes              |
+-------------------------------------------+
         |                    |
    +---------+         +---------+
    | Sandbox |         | Sandbox |  <-- DO App Platform apps (1 per session)
    | Python  |         | Node.js |
    | Service |         | Service |
    +---------+         +---------+
```

**Single deployable unit**: The orchestrator + HTMX frontend is one FastAPI app deployed as a DO App Platform service. Sandboxes are created on-demand (or from a pre-warmed pool) as separate App Platform apps using the existing `do-app-sandbox` SDK.

---

## C. Components & Key Design Decisions

### C.1: Data Models (`orchestrator/models.py`)

| Model | Fields | Notes |
|-------|--------|-------|
| **AgentConfig** | id, name, model (`claude-opus-4-6`), system_prompt, tools list, max_tokens | Reusable template, created once |
| **EnvironmentConfig** | id, name, image (`python`/`node`), pre_install commands, networking | Container template |
| **Session** | id, agent_id, env_id, sandbox_app_id, sandbox_url, sandbox_token, status, created_at | Running instance |
| **Event** | id, session_id, type, data, timestamp, sequence | Append-only log entry |

Event types mirror Anthropic's: `user.message`, `agent.message`, `agent.tool_use`, `agent.tool_result`, `session.status_running`, `session.status_idle`

### C.2: The Harness Loop (`orchestrator/harness.py`)

The core agent loop using the **Claude Messages API** (not Managed Agents API):

```
1. Build messages array from session event log
2. Call claude-opus-4-6 via Messages API with tool definitions + stream=True
3. Stream assistant text to frontend via SSE
4. If response contains tool_use blocks:
   a. Route each tool call to the sandbox via AsyncSandboxServiceClient
   b. Emit tool_use + tool_result events
   c. Append tool results to messages, goto step 2
5. If no tool_use (end_turn): emit session.status_idle, done
```

### C.3: Tool Definitions & Routing (`orchestrator/tools.py`, `orchestrator/tool_executor.py`)

| Tool | Claude Schema | Routes To |
|------|--------------|-----------|
| `bash` | `{command: str, timeout?: int}` | `AsyncSandboxServiceClient.exec()` / `exec_stream()` |
| `read_file` | `{path: str}` | Sandbox API `POST /files/read` |
| `write_file` | `{path: str, content: str}` | Sandbox API `POST /files/write` |
| `edit_file` | `{path: str, old_string: str, new_string: str}` | Read + string replace + write |
| `glob` | `{pattern: str, path?: str}` | `bash` with `find` or Python glob |
| `grep` | `{pattern: str, path?: str}` | `bash` with `grep -rn` |

### C.4: Frontend — FastAPI + HTMX (`orchestrator/templates/`)

HTMX is perfect here because:
- Server-rendered HTML fragments pushed via SSE
- No build step, no JavaScript framework
- Real-time streaming via `hx-sse` extension
- Agent events render as HTML fragments streamed to the page

**Pages**:
- `/` — Dashboard: list sessions, create new session
- `/sessions/{id}` — Session view: chat panel + SSE stream + file preview
- `/agents` — Agent config management
- `/environments` — Environment config management

**Key HTMX patterns**:
- `hx-ext="sse" sse-connect="/v1/sessions/{id}/stream"` — auto-connect SSE
- `sse-swap="agent.message"` — swap agent messages into chat
- `sse-swap="agent.tool_use"` — render tool call cards
- `sse-swap="agent.tool_result"` — render tool results
- Session creation via `hx-post="/v1/sessions"` with `hx-swap="outerHTML"`

### C.5: SSE Event Streaming (`orchestrator/routes/sessions.py`)

```python
@app.get("/v1/sessions/{session_id}/stream")
async def stream_session(session_id: str):
    async def generate():
        async for event in session_event_queue(session_id):
            html = render_event_as_html(event)  # Jinja2 fragment
            yield f"event: {event.type}\ndata: {html}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

Each event type has a Jinja2 template fragment (e.g., `_agent_message.html`, `_tool_use.html`, `_tool_result.html`) that HTMX swaps into the DOM.

---

## D. API Endpoints

### Agent & Environment CRUD
```
POST   /v1/agents                    — Create agent config
GET    /v1/agents                    — List agents
GET    /v1/agents/{id}               — Get agent
DELETE /v1/agents/{id}               — Delete agent

POST   /v1/environments              — Create environment
GET    /v1/environments              — List environments
DELETE /v1/environments/{id}         — Delete environment
```

### Session & Events
```
POST   /v1/sessions                  — Create session (provisions sandbox)
GET    /v1/sessions                  — List sessions
GET    /v1/sessions/{id}             — Get session status
DELETE /v1/sessions/{id}             — Terminate & cleanup sandbox

POST   /v1/sessions/{id}/events      — Send user message or interrupt
GET    /v1/sessions/{id}/stream      — SSE stream (HTML fragments for HTMX)
GET    /v1/sessions/{id}/events      — Fetch event history (JSON, paginated)
```

### Sandbox Proxy
```
GET    /v1/sessions/{id}/preview/{port}/{path} — Proxy to sandbox app port
```

---

## E. Existing Code to Reuse (NOT rewrite)

| File | What It Provides | How We Use It |
|------|-----------------|---------------|
| `src/do_app_sandbox/sandbox.py` | `Sandbox.create(mode=SandboxMode.SERVICE)` | Provision sandboxes for sessions |
| `src/do_app_sandbox/service_client.py` | `AsyncSandboxServiceClient` with `exec()`, `exec_stream()`, file ops | Tool executor routes all calls through this |
| `src/do_app_sandbox/manager.py` | `SandboxManager` with pre-warmed pools | Optional: eliminate cold-start for demo |
| `src/do_app_sandbox/deployer.py` | `Deployer` with App Platform spec generation | Called internally by Sandbox.create() |
| `images/sandbox_api/main.py` | FastAPI sandbox API (exec, files, sessions, proxy) | Runs inside each sandbox container |
| `images/sandbox-python-service/Dockerfile` | Python 3.12 + FastAPI service image | The container image for sandboxes |
| `src/do_app_sandbox/types.py` | `CommandResult`, `SandboxMode`, `ServiceConfig` | Reusable types |

---

## F. New Code to Build

### Directory Structure
```
orchestrator/
  main.py                    — FastAPI app, startup/shutdown, CORS, static files
  models.py                  — Pydantic models (AgentConfig, EnvironmentConfig, Session, Event)
  store.py                   — In-memory store (dicts + event lists), optional Redis/PG later
  harness.py                 — Core agent loop (Claude API + tool routing)
  tools.py                   — Claude tool definitions (JSON schemas)
  tool_executor.py           — Routes tool calls to sandbox via AsyncSandboxServiceClient
  sandbox_lifecycle.py       — Create/delete sandboxes, manage service clients
  event_emitter.py           — EventEmitter class (persist + push to SSE queues)
  routes/
    agents.py                — Agent CRUD endpoints
    environments.py          — Environment CRUD endpoints
    sessions.py              — Session CRUD + events + SSE stream
    preview.py               — Sandbox port proxy
    pages.py                 — HTMX page routes (/, /sessions/{id}, /agents, /environments)
  templates/
    base.html                — Base layout (Tailwind CSS, HTMX script tags)
    index.html               — Dashboard
    session.html             — Session view with chat panel
    agents.html              — Agent config page
    environments.html        — Environment config page
    fragments/
      _agent_message.html    — Agent text message fragment
      _tool_use.html         — Tool call card fragment
      _tool_result.html      — Tool result fragment (with terminal-like output for bash)
      _user_message.html     — User message bubble
      _status.html           — Status indicator
      _session_card.html     — Session list item
  static/
    style.css                — Custom styles (terminal theme, code blocks)
  Dockerfile                 — Multi-stage: just Python (no Node build step needed with HTMX)
  pyproject.toml             — Dependencies
  .do/app.yaml               — DO App Platform spec
```

### Dependencies (`pyproject.toml`)
```
anthropic>=0.50.0
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
httpx>=0.27.0
do-app-sandbox>=0.2.2
jinja2>=3.1.0
python-multipart>=0.0.9
pydantic>=2.0
```

---

## G. Implementation Phases

### Phase 1: Orchestrator Core (the "brain" + "harness")
1. **Scaffold project** — Create `orchestrator/` directory, `pyproject.toml`, `main.py`
2. **Data models** — `models.py` with Pydantic models for Agent, Environment, Session, Event
3. **In-memory store** — `store.py` with dict-based storage
4. **Agent & Environment CRUD** — `routes/agents.py`, `routes/environments.py`
5. **Tool definitions** — `tools.py` with Claude-compatible JSON schemas
6. **Tool executor** — `tool_executor.py` routing to `AsyncSandboxServiceClient`
7. **Harness loop** — `harness.py` with the core agent loop (Claude API calls + tool routing)
8. **Event emitter** — `event_emitter.py` for persist + SSE push
9. **Session routes** — `routes/sessions.py` with create, events, SSE stream

### Phase 2: Sandbox Integration
10. **Sandbox lifecycle** — `sandbox_lifecycle.py` wrapping `Sandbox.create(mode=SERVICE)`
11. **Pre-install support** — Run environment setup commands before agent starts
12. **Preview proxy** — `routes/preview.py` proxying to sandbox ports
13. **Optional pool** — Integrate `SandboxManager` for pre-warmed sandboxes

### Phase 3: HTMX Frontend
14. **Base template** — `templates/base.html` with Tailwind + HTMX
15. **Dashboard page** — List sessions, create new session form
16. **Session page** — Chat panel with SSE streaming via `hx-ext="sse"`
17. **Event fragments** — HTML fragments for each event type
18. **Agent/Environment pages** — Config management UI

### Phase 4: Deployment & Polish
19. **Dockerfile** — Single-stage Python image
20. **DO App spec** — `.do/app.yaml` for one-click deploy
21. **Default presets** — Pre-configured "Coding Assistant" agent + "Python Dev" environment
22. **System prompt** — Well-crafted system prompt telling Claude about the sandbox environment
23. **Interrupt support** — `user.interrupt` event to cancel agent mid-execution
24. **README** — Setup instructions, demo walkthrough

---

## H. DigitalOcean Hosting

### Orchestrator App Spec (`.do/app.yaml`)
```yaml
name: managed-agents-demo
region: nyc1
services:
  - name: orchestrator
    image:
      registry_type: GHCR
      registry: bikramkgupta
      repository: managed-agents-orchestrator
      tag: latest
    instance_count: 1
    instance_size_slug: apps-s-1vcpu-2gb
    http_port: 8080
    envs:
      - key: ANTHROPIC_API_KEY
        scope: RUN_TIME
        type: SECRET
      - key: DIGITALOCEAN_TOKEN
        scope: RUN_TIME
        type: SECRET
      - key: APP_SANDBOX_REGION
        scope: RUN_TIME
        value: nyc1
    health_check:
      http_path: /health
    routes:
      - path: /
```

### Networking
- Orchestrator ↔ Sandboxes: HTTPS over public URLs (`*.ondigitalocean.app`) with bearer token auth
- Each sandbox's API token is generated at creation time and stored in the session
- For production: could use DO VPC or Tailscale (images already exist at `images/tailscale-*/`)

### Cost (demo)
- Orchestrator: ~$12/month (1 vCPU, 2GB)
- Each active sandbox: ~$5/month (1 vCPU, 1GB)
- 2 pre-warmed sandboxes: +$10/month
- **Total**: ~$22-27/month for a functional demo

---

## I. Verification

### How to test end-to-end
1. Deploy orchestrator to DO App Platform (or run locally with `uvicorn orchestrator.main:app`)
2. Open the web UI at the orchestrator URL
3. Click "New Session" — verify sandbox provisions (check DO dashboard for new app)
4. Type "Create a Python script that prints the first 10 Fibonacci numbers" — watch:
   - Agent message streams in real-time
   - Tool use cards appear (write_file, bash)
   - Tool results show file contents and command output
   - Session goes idle when done
5. Click "Preview" — verify sandbox port proxy works
6. Delete session — verify sandbox app is destroyed

### Unit tests
- Test tool definitions parse correctly
- Test event emitter stores and streams events
- Test harness loop with mocked Claude API responses
- Test tool executor with mocked sandbox client

### Integration tests
- Test sandbox creation and deletion via the SDK
- Test full agent loop with a real Claude API call against a real sandbox
- Test SSE streaming from orchestrator to a test client
