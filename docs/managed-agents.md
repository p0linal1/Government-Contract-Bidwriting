# Claude Managed Agents: Reference

Compiled from the Managed Agents docs on 2026-10-25. Where the docs do not say something, this file says "Not documented". Examples marked "composed" are built from documented fields but are not copied from a docs example.

---

## 1. What it is

Managed Agents is Anthropic's hosted agent harness that runs Claude in a managed cloud sandbox, so you do not build the agent loop, tool execution, or runtime yourself. You define an agent once, start sessions from it, and send those sessions messages while the agent reads files, runs commands, searches the web, and calls your tools. Your app follows the work through a server-sent event stream, and the session's event history is stored on Anthropic's side.

- Status: beta.
- Beta header: `anthropic-beta: managed-agents-2026-04-01` on every Managed Agents request (the SDKs set it automatically).
- Memory store endpoints use a different beta header: `anthropic-beta: agent-memory-2026-07-22`. Do not send both headers on one memory store request (400). Session endpoints, including attaching a memory store to a session, still use `managed-agents-2026-04-01`.
- Base URL: `https://api.anthropic.com`. All paths are under `/v1/`. Some docs examples add `?beta=true`.
- Headers used in the guides: `x-api-key: $ANTHROPIC_API_KEY`, `anthropic-version: 2023-06-01`, `content-type: application/json`.
- The API reference examples use `anthropic-version: 2026-10-21` instead. The guides and the reference disagree; use the value your SDK sends.
- Not eligible for Zero Data Retention or HIPAA BAA coverage (overview page).

---

## 2. Building blocks

| Concept | ID prefix seen in docs | What it is | Made by |
|---|---|---|---|
| Agent | `agent_` | Reusable, versioned config: model, system prompt, tools, MCP servers, skills, multiagent block | `POST /v1/agents` |
| Environment | `env_` | Sandbox config: cloud networking, preinstalled packages | `POST /v1/environments` |
| Session | `sesn_` | One running instance of an agent in an environment, with its own sandbox and history | `POST /v1/sessions` |
| Events | `sevt_` | Messages in (`user.*`) and out (`agent.*`, `session.*`, `span.*`, `workflow_run.*`) | `POST /v1/sessions/{id}/events` and the server |
| Session resource | `sesrsc_` | A file, memory store, or GitHub repo attached to a session | session create or `POST /v1/sessions/{id}/resources` |
| Vault | `vlt_` | Container for credentials, keyed to an end user or service | `POST /v1/vaults` |
| Vault credential | `vcrd_` | One secret (MCP OAuth, MCP bearer, or environment variable) | `POST /v1/vaults/{id}/credentials` |
| Files | `file_` | Uploaded files, mounted read-only into a session; outputs come back as files | `POST /v1/files` |
| Memory store | `memstore_` | Text documents mounted into a session at `/mnt/memory/<slug>/` | `POST /v1/memory_stores` |
| Memory version | `memver_` | Immutable history entry for each memory change | Automatic |
| Skill | `skill_` (custom) or short name (Anthropic, e.g. `xlsx`) | Filesystem-based expertise attached to an agent | `POST /v1/skills` |
| Deployment | `depl_` | Cron schedule that starts a session from an agent on a timer | `POST /v1/deployments` |
| Deployment run | `drun_` | One attempt by a deployment to create a session | Automatic |
| Workflow run | `wrun_` | Background program run by an agent that fans out work to threads | Started by the agent |
| Thread | Not documented | A session's child context (subagent or workflow thread); the primary thread is the session stream | Server |
| Outcome | `outc_` | A target and rubric the agent works toward, graded by a separate grader | `user.define_outcome` event |

Diagram:

```text
Agent (model, system, tools, mcp_servers, skills, multiagent)
  |
  |  referenced by
  v
Session  ---- runs in ----> Environment (cloud sandbox config)
  |  |  |
  |  |  +-- resources:  files (read-only, /mnt/session/uploads)
  |  |                 memory stores (/mnt/memory/<slug>/)
  |  |                 GitHub repos (/workspace/<repo>)
  |  |
  |  +-- vault_ids --> Vault --> credentials (MCP OAuth, bearer, env var)
  |  |
  |  +-- events <----> your app
  |  |                  in:  user.message, user.interrupt, user.tool_confirmation,
  |  |                       user.custom_tool_result, user.define_outcome
  |  |                  out: agent.*, session.*, span.*, workflow_run.*
  |  |
  |  +-- threads: subagents and workflow-run agents (multiagent only)
  |
  +-- outputs written to /mnt/session/outputs --> Files API (scope_id = session id)

Skills (Anthropic or custom, or SKILL.md in a mounted repo) --> available to the agent
Deployment (cron) --> creates a new Session on schedule (agent + environment + initial_events)
Webhooks --> notify your server of state changes; you fetch the object by id
```

---

## 3. Creating an agent

### Endpoint

`POST /v1/agents`

### Request body fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | 1 to 256 chars |
| `model` | string or object | yes | Model ID string (for example `"claude-opus-5-5"`) or object `{"id": "...", "effort": ..., "speed": "standard" or "fast", "inference_geo": "us" or "global"}`. Claude 4.5 and later. |
| `system` | string or null | no | The system prompt. Field name is `system`. Max 100,000 chars. |
| `description` | string or null | no | Max 2,048 chars |
| `tools` | array | no | Up to 256 tools across all toolsets. Entries: `{"type": "agent_toolset_20260401", ...}`, `{"type": "mcp_toolset", "mcp_server_name": "..."}`, or `{"type": "custom", "name", "description", "input_schema"}`. |
| `mcp_servers` | array | no | Up to 20. Each: `{"type": "url", "name": "...", "url": "..."}`. Every server needs a matching `mcp_toolset`. |
| `skills` | array | no | Each: `{"type": "anthropic", "skill_id": "xlsx", "version"?}` or `{"type": "custom", "skill_id": "skill_...", "version"?}`. Version defaults to latest. |
| `multiagent` | object or null | no | `{"type": "multiagent_20261001", "advisor"?, "subagents"?, "workflows"?}`. See section 14. |
| `metadata` | map of string | no | Max 16 pairs, keys up to 64 chars, values up to 512 chars |
| `execution_identity` | object or null | no | Default `{"type": "service_account"}`. `{"type": "aws_role", "role_arn": "..."}` applies on Claude Platform on AWS only. |

Permission policies have no top-level field. Set them inside `tools[].default_config.permission_policy` or `tools[].configs[].permission_policy` (section 7).

Response adds: `id`, `type` (`"agent"`), `version` (starts at 1), `created_at`, `updated_at`, `archived_at`. Omitted model fields are filled with defaults (for example `model.effort`).

### Full JSON example

```json
{
  "name": "Coding Assistant",
  "model": "claude-opus-5-5",
  "system": "You are a helpful coding agent.",
  "description": "A general-purpose coding agent.",
  "tools": [
    { "type": "agent_toolset_20260401" }
  ],
  "metadata": { "team": "docs" }
}
```

Request: `POST https://api.anthropic.com/v1/agents` with the headers in section 1.

### Python SDK equivalent

```python
from anthropic import Anthropic

client = Anthropic()  # reads ANTHROPIC_API_KEY

agent = client.beta.agents.create(
    name="Coding Assistant",
    model="claude-opus-5-5",
    system="You are a helpful coding agent.",
    tools=[{"type": "agent_toolset_20260401"}],
)
print(agent.id, agent.version)
```

Also available: the `ant` CLI (`ant apply coding-assistant.md`), which records IDs in `claude-lock.json`.

### Update an agent

`POST /v1/agents/{agent_id}` with only the fields you want to change.

- `version` is optional. If you send it, the update returns 409 when it does not match the current version (optimistic concurrency). If you omit it, the update applies unconditionally (last write wins).
- Omitted fields are kept.
- Scalar fields (`model`, `system`, `name`, `description`) are replaced. `system` and `description` can be cleared with `null`. `model` and `name` cannot be cleared.
- Arrays (`tools`, `mcp_servers`, `skills`) are replaced in full. Send `null` or `[]` to clear.
- `metadata` merges key by key. A key set to `null` is deleted.
- A no-op update does not create a version.
- Updates to archived agents are rejected.
- Other agents that list this agent in `predefined_agents` keep the version they pinned.

```bash
curl -fsSL "https://api.anthropic.com/v1/agents/$AGENT_ID" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -d '{"version": 1, "system": "You are a helpful coding agent. Always write tests."}'
```

```python
updated = client.beta.agents.update(
    agent.id,
    version=agent.version,
    system="You are a helpful coding agent. Always write tests.",
)
print(updated.version)  # 2
```

### Versions and archive

- `GET /v1/agents/{agent_id}/versions` lists versions (`limit` default 20, max 100; `page` cursor). Python: `client.beta.agents.versions.list(agent.id)`.
- A session uses the latest version unless you pin one: `"agent": {"type": "agent", "id": "...", "version": 1}`.
- `POST /v1/agents/{agent_id}/archive` makes the agent read-only. New sessions cannot reference it. Existing sessions keep running. Archiving cannot be undone.
- Retrieve (`GET /v1/agents/{agent_id}`) and list (`GET /v1/agents`) endpoints exist in the API reference index. Their parameters were not read for this file.

---

## 4. Environments

### Create

`POST /v1/environments`

```json
{
  "name": "python-dev",
  "config": {
    "type": "cloud",
    "packages": {
      "pip": ["pandas", "numpy"],
      "npm": ["express@4.18.0"]
    },
    "networking": {
      "type": "limited",
      "allowed_hosts": ["api.example.com"],
      "allow_package_managers": true,
      "allow_mcp_servers": false
    }
  }
}
```

```python
environment = client.beta.environments.create(
    name="python-dev",
    config={
        "type": "cloud",
        "packages": {"pip": ["pandas", "numpy"], "npm": ["express@4.18.0"]},
        "networking": {
            "type": "limited",
            "allowed_hosts": ["api.example.com"],
            "allow_package_managers": True,
        },
    },
)
```

### Fields

- `name`: a unique, descriptive name.
- `config.type`: `"cloud"` (this page). Self-hosted is a separate environment type.
- `config.packages`: optional object with arrays for `apt`, `cargo`, `gem`, `go`, `npm`, `pip`. Versions can be pinned (for example `"sqlalchemy==2.0.30"`, `"express@4.18.0"`, `"rails:7.1.0"`). Unpinned installs the latest version. Install order is alphabetical (apt, cargo, gem, go, npm, pip). Packages are cached across sessions that share the environment.
- `config.networking.type`:
  - `limited`: sandbox network access is restricted to `allowed_hosts`. With no hosts listed, no outbound host is allowed (files, memory stores, and GitHub repos attached to the session still work).
  - `unrestricted`: full outbound access except a safety blocklist. Read the risks section of the docs before using it.
  - If you omit `networking` through the API, the environment is `unrestricted`. The Console form starts at Limited.
- `allowed_hosts`: bare hostnames or wildcards (`*.example.com`). No scheme, port, or path. `example.com` does not match `www.example.com`. Also applies to the `web_search` and `web_fetch` tools under `limited` networking.
- `allow_package_managers` (default false): adds a fixed list of public registries and code hosts (npm, PyPI, crates, Go proxy, Maven, RubyGems, Packagist, Ubuntu apt, Docker, GitHub, GitLab, Bitbucket). Must be `true` when `packages` is set on a `limited` environment, otherwise the request returns 400.
- `allow_mcp_servers` (default false): allows the MCP server hosts declared on agents. Without it, session creation fails with 400 when an agent's MCP host is not in `allowed_hosts`.
- Warning in the docs: network access is granted by host, not by operation. An allowed host can receive uploads such as `git push` or package publishing. Set `bash` to `always_ask` or `auto` when the agent reads untrusted input.

### Other endpoints

- `GET /v1/environments` (list), `GET /v1/environments/{environment_id}` (retrieve).
- `POST /v1/environments/{environment_id}/archive`: read-only; existing sessions continue.
- `DELETE /v1/environments/{environment_id}`: only if no session references it.
- Update endpoint exists in the API reference index (`environments/update`). Its body was not read for this file.
- Environments are not versioned. Each session gets its own sandbox; sessions do not share filesystem state.

### Sandbox specification (cloud)

| Property | Value |
|---|---|
| OS | Ubuntu 24.04 LTS |
| Architecture | x86_64 (amd64) |
| Memory | Up to 8 GB |
| Disk | Up to 10 GB |
| Session runtime or idle timeout | Not documented |

### Preinstalled software

- Python 3.10, 3.11, 3.12, 3.13 (pip, uv, poetry). NumPy, pandas, Matplotlib, openpyxl, python-docx, python-pptx, pypdf installed for `python3`.
- Node.js 20, 21, 22 (default 22); npm, yarn, pnpm, bun.
- Go 1.24 (default) and 1.25.
- Rust (stable, rustup, cargo).
- Java OpenJDK 21 (maven, gradle).
- Ruby 3.1, 3.2, 3.3 (default 3.3).
- PHP 8.3 (composer).
- C/C++: GCC 13, Clang, make, cmake, ninja.
- Databases: PostgreSQL 16 and Redis 7 (installed, server not running by default); SQLite via bindings.
- Tools: git, curl, wget, jq, yq, tar, zip, unzip, tmux, docker (limited), ripgrep, sed, awk, grep, vim, nano, diff, patch, ffmpeg, ImageMagick, pandoc, LibreOffice (headless), Poppler, qpdf, tesseract (English), TeX Live (pdflatex, xelatex, latexmk).
- Playwright for Python and Node.js, with Chromium at `/opt/pw-browsers/chromium` (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` is set). Chromium is not on `PATH`. Firefox and WebKit are not installed.

---

## 5. Sessions

### Create

`POST /v1/sessions`

Body fields:

| Field | Type | Notes |
|---|---|---|
| `agent` | string, or `{"type": "agent", "id", "version"}`, or `{"type": "agent_with_overrides", "id", "version"?, "model"?, "system"?, "tools"?, "mcp_servers"?, "skills"?}` | String = latest version. Overrides apply to this session only. Set `system`, `skills` to `null` or `[]` to clear. `model` cannot be null. |
| `environment_id` | string | Required |
| `title` | string or null | Optional label |
| `resources` | array, max 500 | `github_repository` (`url`, `authorization_token`?, `checkout`?, `mount_path`?), `file` (`file_id`, `mount_path`?), `memory_store` (`memory_store_id`, `access`?, `instructions`? up to 4,096 chars) |
| `vault_ids` | array of string | Vaults supplying credentials (section 12) |
| `budget` | object | `{"type": "limit", "max_list_cost": {"amount": "125", "currency": "USD"}}`. Can only be set at creation. Section 19. |
| `initial_events` | array, max 50 | `user.message` or `user.define_outcome`. A non-empty list starts the agent in the same call (session created `running`). Not accepted here: `user.tool_result`, `user.custom_tool_result`, `user.tool_confirmation`, `user.interrupt`, `system.message`. |
| `metadata` | map | Your own tracking data |

Creating a session without `initial_events` registers it in `idle` and does no work until you send an event.

```json
{
  "agent": { "type": "agent", "id": "agent_011CZkYpogX7uDKUyvBTophP", "version": 1 },
  "environment_id": "env_011CZkZ9X2dpNyB7HsEFoRfW",
  "title": "Quickstart session",
  "vault_ids": ["vlt_01ABC..."],
  "budget": { "type": "limit", "max_list_cost": { "amount": "125", "currency": "USD" } },
  "initial_events": [
    { "type": "user.message", "content": [{ "type": "text", "text": "List the files in the working directory." }] }
  ]
}
```

```python
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
    title="Quickstart session",
    budget={"type": "limit", "max_list_cost": {"amount": "125", "currency": "USD"}},
)
print(session.id, session.status)
```

### Send a user message

`POST /v1/sessions/{session_id}/events`

```json
{
  "events": [
    {
      "type": "user.message",
      "content": [{ "type": "text", "text": "Summarize the README." }]
    }
  ]
}
```

```python
client.beta.sessions.events.send(
    session.id,
    events=[{"type": "user.message", "content": [{"type": "text", "text": "Summarize the README."}]}],
)
```

`user.message.content` accepts `text`, `image` (base64, url, or file source), and `document` (base64, text, url, or file source; optional `context` and `title`). A `redacted` block is rejected in user events.

### Stream

`GET /v1/sessions/{session_id}/events/stream?beta=true` (server-sent events). Open the stream before you send the first event; a stream only delivers events emitted after it opens. Section 6 has the Python loop.

### List past events

`GET /v1/sessions/{session_id}/events?beta=true`

| Query parameter | Notes |
|---|---|
| `limit` | Page size (int32) |
| `page` | Opaque cursor from `next_page` |
| `order` | `asc` (default) or `desc`, sorted by `processed_at` |
| `types` | Array of event type strings to filter |
| `created_at[gt]`, `created_at[gte]`, `created_at[lt]`, `created_at[lte]` | Time bounds, compared against `processed_at` |

Response: `data` (array of events) and `next_page`. The events page does not document `prev_page`.

### Interrupt

Send `user.interrupt`, then optionally a `user.message` to redirect:

```json
{
  "events": [
    { "type": "user.interrupt" },
    { "type": "user.message", "content": [{ "type": "text", "text": "Instead, fix the bug on line 42." }] }
  ]
}
```

- `user.interrupt` accepts an optional `session_thread_id`. Without it, every non-archived thread is interrupted. With it, only that thread.
- An interrupt does not end open workflow runs.

### Resume

Send a `user.message` to an idle session. The session keeps its history and sandbox.

### Retrieve, list, update, archive, delete

| Operation | Request |
|---|---|
| Retrieve | `GET /v1/sessions/{session_id}` |
| List | `GET /v1/sessions` with `limit` (page size), `page` (cursor from `next_page` or `prev_page`), `order` (`asc` or `desc`, default `desc`), `agent_id` filter, `created_at` filters |
| Update | `POST /v1/sessions/{session_id}`. Can change `agent.tools` and `agent.mcp_servers` (full replacement, session only, no new agent version), `budget` (replace or `null` to remove), and `metadata` or `title`. Session must be `idle`. Open workflow runs cause a 400. |
| Archive | `POST /v1/sessions/{session_id}/archive`. A running session cannot be archived: interrupt and wait for `idle` first. |
| Delete | `DELETE /v1/sessions/{session_id}`. Permanent. Deletes events and sandbox. Files the session produced are deleted too. Memory stores, vaults, skills, environments, and agents are not affected. |

### Session resources (add and remove on a running session)

- `POST /v1/sessions/{session_id}/resources` with `{"type": "file", "file_id": "..."}` adds a file.
- `GET /v1/sessions/{session_id}/resources` lists resources.
- `DELETE /v1/sessions/{session_id}/resources/{resource_id}` removes one.
- Memory stores can only be attached at session creation. Not documented for GitHub repos.

### Session statuses

| Status | Meaning |
|---|---|
| `idle` | Waiting for input or confirmation. Can be idle while a workflow run is open. |
| `running` | Executing |
| `rescheduling` | Transient error; retrying. The stream event is `session.status_rescheduled`. |
| `terminated` | Ended by an unrecoverable error or by archiving. |

### Threads

- `GET /v1/sessions/{session_id}/threads` lists threads. Child threads have a non-null `parent_thread_id`.
- `GET /v1/sessions/{session_id}/threads/{thread_id}/stream` streams one thread (supports `event_deltas[]`).
- Thread events endpoints exist (`/threads/{thread_id}/events`); a thread-archive endpoint exists in the index.

---

## 6. The tool loop and transparency

### Event envelope

Every persisted event has `id` (for example `sevt_...`), `type`, and `processed_at`. On events you send, `processed_at` is null while queued. Event type strings follow `{domain}.{action}`.

### Events you send

| Type | Fields |
|---|---|
| `user.message` | `content` (array of text, image, or document blocks) |
| `user.interrupt` | `session_thread_id`? |
| `user.tool_confirmation` | `tool_use_id` (id of the `agent.tool_use` or `agent.mcp_tool_use` event), `result` (`"allow"` or `"deny"`), `deny_message`? (max 10,000 chars, only with deny) |
| `user.custom_tool_result` | `custom_tool_use_id` (id of the `agent.custom_tool_use` event), `content`? (text, image, document, or search_result blocks), `is_error`?, `session_thread_id`? |
| `user.define_outcome` | `description`, `rubric` (`{"type": "text", "content"}` up to 262,144 chars, or `{"type": "file", "file_id"}`), `max_iterations`? (default 3, max 20) |
| `user.tool_result` | `tool_use_id`, `content`?, `is_error`?. Self-hosted environments only. |
| `system.message` | `content` (text blocks only). Must be the last event and follow a user message or tool result. Only on models that accept mid-conversation system messages. |

### Events you receive: agent

| Type | Fields |
|---|---|
| `agent.message` | `content` (text or redacted blocks) |
| `agent.thinking` | Progress signal only. No thinking content. |
| `agent.tool_use` | `id`, `name`, `input`, `evaluated_permission` (`allow`, `ask`, `deny`), `evaluation`?, `session_thread_id`? |
| `agent.tool_result` | `tool_use_id`, `content`?, `is_error`? |
| `agent.mcp_tool_use` | `name`, `input`, `mcp_server_name`, `evaluated_permission`, `evaluation`?, `session_thread_id`? |
| `agent.mcp_tool_result` | `mcp_tool_use_id`, `content`?, `is_error`? |
| `agent.custom_tool_use` | `name`, `input`, `session_thread_id`?. No permission fields. |
| `agent.thread_context_compacted` | No extra fields. Context was compacted. |
| `agent.thread_message_sent` | `content`, `to_session_thread_id`, `to_agent_name`? |
| `agent.thread_message_received` | `content`, `from_session_thread_id`, `from_agent_name`? |

### Events you receive: session

| Type | Fields |
|---|---|
| `session.status_running` | No extra fields |
| `session.status_idle` | `stop_reason` (`type`: `end_turn`, `requires_action`, `budget_reached`, `retries_exhausted`, `refusal`, among others; `event_ids` array when `requires_action`), `stop_details`? |
| `session.status_rescheduled` | Transient error; retrying |
| `session.status_terminated` | Unrecoverable error or archived |
| `session.error` | `error` with `type`, `message`, `retry_status` (`type`: `retrying`, `exhausted`, `terminal`), plus type-specific fields such as `mcp_server_name` |
| `session.updated` | Only the changed fields: `agent`?, `budget`?, `metadata`?, `title`? |
| `session.usage` | `usage` (see section 19), `budget`? Emitted before going idle. |
| `session.deleted` | Ends the stream |
| `session.thread_created` | `agent_name`, `session_thread_id`, `workflow_run_id` (null unless a workflow run thread) |
| `session.thread_status_running` | `agent_name`, `session_thread_id` |
| `session.thread_status_idle` | `agent_name`, `session_thread_id`, `stop_reason`, `stop_details`? |
| `session.thread_status_rescheduled` | `agent_name`, `session_thread_id` |
| `session.thread_status_terminated` | `agent_name`, `session_thread_id` |

### Events you receive: workflow runs (dynamic workflows)

| Type | Fields |
|---|---|
| `workflow_run.created` | `workflow_run_id`, `name`, `description`, `phases` (each `id`, `name`, `description`) |
| `workflow_run.status_running` | `workflow_run_id` |
| `workflow_run.status_idle` | `workflow_run_id` (paused, for example at budget) |
| `workflow_run.phase_started` | `workflow_run_id`, `workflow_run_phase_id` |
| `workflow_run.phase_ended` | `workflow_run_id`, `workflow_run_phase_id`, `phase_started_id` |
| `workflow_run.status_ended` | `workflow_run_id`, `result` (`{"type": "completed"}`, `{"type": "stopped"}`, or `{"type": "error", "error": {"type", "message"}}`) |
| `workflow_run.error` | `error` (`type`, `message`), `workflow_run_id` (null if no run was created) |

### Events you receive: span

| Type | Fields |
|---|---|
| `span.model_request_start` | No extra fields |
| `span.model_request_end` | `model_request_start_id`, `is_error`, `model_usage` (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `speed`?) |
| `span.outcome_evaluation_start` | `outcome_id`, `iteration` (0-based) |
| `span.outcome_evaluation_ongoing` | `outcome_id`, `iteration` (heartbeat) |
| `span.outcome_evaluation_end` | `outcome_id`, `iteration`, `outcome_evaluation_start_id`, `result`, `explanation`, `usage` |

### Event deltas (live text, stream only)

Deltas are a preview. They are never persisted and are not replayed on reconnect. Opt in per stream connection with the `event_deltas[]` query parameter (`agent.message` and/or `agent.thinking`):

```text
GET /v1/sessions/{session_id}/events/stream?beta=true&event_deltas%5B%5D=agent.message
```

Stream shapes:

```json
{ "type": "event_start", "event": { "type": "agent.message", "id": "sevt_01abc..." } }
{ "type": "event_delta", "event_id": "sevt_01abc...", "delta": { "type": "content_delta", "index": 0, "content": { "type": "text", "text": "Here is the summary" } } }
```

Rules:
- Concatenate deltas by `(event_id, index)`. The buffered `agent.message` with the same `id` is authoritative: replace the preview with it.
- Deltas may be dropped under load. A preview is only a prefix.
- `agent.thinking` produces only `event_start`; no deltas.
- Tool calls and results are never previewed.
- A thread's previews appear only on that thread's stream.

### Stream and print every event (Python)

```python
from anthropic import Anthropic

client = Anthropic()  # reads ANTHROPIC_API_KEY

session = client.beta.sessions.create(agent="agent_...", environment_id="env_...")

with client.beta.sessions.events.stream(session.id) as stream:
    client.beta.sessions.events.send(
        session.id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": "Hello"}]}],
    )
    for event in stream:
        print(event.type, getattr(event, "id", ""))
        if event.type == "agent.message":
            for block in event.content:
                if block.type == "text":
                    print(block.text)
        if event.type == "session.status_idle" and event.stop_reason.type != "requires_action":
            break
```

For live text with deltas: `client.beta.sessions.events.stream(session.id, event_deltas=["agent.message"])`. The Python SDK ships an accumulator helper (`accumulate_managed_agents_event`); its import path is not shown on the docs page.

### Reconnect without losing events

1. Open a new stream.
2. List the full history (`GET /v1/sessions/{id}/events`) and record the seen `id` values.
3. Process live events, skipping any `id` already seen.

### Pause points

When the session pauses for input, it emits `session.status_idle` with `stop_reason.type = "requires_action"` and `stop_reason.event_ids`. Answer each id with `user.custom_tool_result` or `user.tool_confirmation`. The session returns to `running` when all are answered.

---

## 7. Built-in tools, permission policies, and approvals

### The toolset

`{"type": "agent_toolset_20260401"}` enables the built-in tools:

| Name | Purpose |
|---|---|
| `bash` | Run shell commands |
| `read` | Read a file |
| `write` | Write a file |
| `edit` | String replacement in a file |
| `glob` | File pattern matching |
| `grep` | Regex search |
| `web_fetch` | Fetch a URL |
| `web_search` | Web search |

All are enabled by default. A tool output over 100,000 characters is written to a sandbox file, and the model gets a preview and the path.

### Configuring the toolset

```json
{
  "type": "agent_toolset_20260401",
  "default_config": {
    "enabled": true,
    "permission_policy": { "type": "always_allow" }
  },
  "configs": [
    { "name": "bash", "permission_policy": { "type": "always_ask" } },
    { "name": "web_fetch", "enabled": false }
  ]
}
```

- `configs[]` entries take `name`, `enabled`?, and `permission_policy`?. The `type` field is optional and inferred from `name`.
- Disable a tool with `"enabled": false`.
- To enable only a few tools, set `default_config.enabled` to `false` and enable each one in `configs`.
- The default permission policy is `always_allow` for the agent toolset.

### Permission policy types

| Policy | Behavior |
|---|---|
| `always_allow` | Runs with no confirmation. Default for the agent toolset. |
| `always_ask` | Pauses for your approval. Default for MCP toolsets. |
| `auto` | Server evaluates each call: runs it if judged safe, denies it if high-risk, or pauses for approval if undetermined. |

Set at `default_config.permission_policy` (whole toolset) or `configs[].permission_policy` (one tool). Works on the agent toolset and on `mcp_toolset`. Permission policies do not govern custom tools.

Under `auto`:
- A denied call returns an error tool result: `Permission to use {tool_name} has been denied.` with `is_error: true`. The session keeps running. Your client cannot override the denial.
- Your `user.message` text counts as intent and can change an `auto` decision. Tool results and fetched content do not.
- The docs say `auto` is not a human checkpoint. Use `always_ask` where a person must review.

### How each call is labeled

`agent.tool_use` and `agent.mcp_tool_use` carry `evaluated_permission` (`allow`, `ask`, or `deny`) and usually an `evaluation` object. Example of a denied call:

```json
{
  "type": "agent.tool_use",
  "id": "sevt_01pqr...",
  "name": "bash",
  "input": { "command": "rm -rf /workspace/reports" },
  "evaluated_permission": "deny",
  "evaluation": {
    "type": "auto",
    "evaluated_permission": { "type": "deny", "reason_code": "high_risk" }
  }
}
```

Tools that the agent calls but that are not enabled get `deny` with no `evaluation`.

### Approval flow

1. The session emits `agent.tool_use` or `agent.mcp_tool_use` with `evaluated_permission: "ask"`.
2. The session emits `session.status_idle` with `stop_reason: {"type": "requires_action", "event_ids": ["sevt_..."]}`.
3. Send `user.tool_confirmation` for each id:

```json
{
  "events": [
    { "type": "user.tool_confirmation", "tool_use_id": "sevt_01def...", "result": "allow" },
    { "type": "user.tool_confirmation", "tool_use_id": "sevt_01ghi...", "result": "deny",
      "deny_message": "Use the staging project, not production." }
  ]
}
```

- Sending a confirmation for an event whose `evaluated_permission` is not `ask` returns 400. This includes calls that `auto` denied.
- A call from a workflow-run thread reaches your client on the primary stream. The call waits only until the run finishes with that thread or the run ends.

---

## 8. Custom tools

Your code runs these tools. The agent asks; you answer.

### Declare

```json
{
  "type": "custom",
  "name": "get_weather",
  "description": "Get current weather for a city. Use when the user asks about weather. Do not use for forecasts beyond 7 days.",
  "input_schema": {
    "type": "object",
    "properties": {
      "location": { "type": "string", "description": "City name" }
    },
    "required": ["location"]
  }
}
```

Rules:
- Name cannot start with `mcp__` or `ant__`, and cannot match a built-in tool name. Otherwise 400.
- A session is refused with 400 if its agent (or a listed subagent or workflow agent) has a custom tool starting with `ant__`.
- The docs recommend descriptions of three to four sentences.

### Answer calls (Python loop)

Composed from the documented fields (`agent.custom_tool_use` gives `id`, `name`, `input`; `user.custom_tool_result` takes `custom_tool_use_id`, `content`, `is_error`):

```python
import json

from anthropic import Anthropic

client = Anthropic()

def run_tool(name: str, tool_input: dict) -> str:
    if name == "get_weather":
        return json.dumps({"location": tool_input["location"], "forecast": "sunny"})
    raise KeyError(name)

def answer(session_id: str, call_id: str, text: str, is_error: bool) -> None:
    client.beta.sessions.events.send(
        session_id,
        events=[{
            "type": "user.custom_tool_result",
            "custom_tool_use_id": call_id,
            "content": [{"type": "text", "text": text}],
            "is_error": is_error,
        }],
    )

with client.beta.sessions.events.stream(session.id) as stream:
    for event in stream:
        if event.type == "agent.custom_tool_use":
            try:
                answer(session.id, event.id, run_tool(event.name, event.input), False)
            except KeyError as missing:
                answer(session.id, event.id, f"Unknown tool: {missing}", True)
        elif event.type == "session.status_idle" and event.stop_reason.type == "end_turn":
            break
```

- You may answer as soon as `agent.custom_tool_use` arrives. The later `requires_action` idle can be ignored. A second result for the same call is accepted and has no effect.
- When you reconnect, `stop_reason.event_ids` on the latest idle lists the calls still waiting.

---

## 9. MCP connector

### Two-step setup

1. The agent declares the server (name and URL, no secrets):

```json
{
  "name": "GitHub Assistant",
  "model": "claude-opus-5-5",
  "mcp_servers": [
    { "type": "url", "name": "github", "url": "https://api.githubcopilot.com/mcp/" }
  ],
  "tools": [
    { "type": "agent_toolset_20260401" },
    {
      "type": "mcp_toolset",
      "mcp_server_name": "github",
      "default_config": { "permission_policy": { "type": "always_ask" } },
      "configs": [{ "name": "delete_repository", "enabled": false }]
    }
  ]
}
```

2. The session supplies credentials by passing `vault_ids` on creation (section 12).

### Rules

- `mcp_servers`: up to 20 per agent. `name` unique, 1 to 255 chars. `url` up to 2,048 chars. Transport: streamable HTTP; SSE servers work through an automatic fallback.
- Every `mcp_servers` entry must be referenced by an `mcp_toolset`, and every `mcp_toolset` must reference a declared server. Otherwise the agent is rejected.
- `mcp_toolset` `mcp_server_name` must equal the server `name`.
- Default `permission_policy` on `mcp_toolset` is `always_ask`. Set `always_allow` only for servers you trust.
- `mcp_toolset.configs[]` accepts only `name`, `enabled`, and `permission_policy`. Tool names are the bare names the server reports.
- Credentials are matched by URL (scheme and host lowercased, default ports and trailing slash stripped). A different path or subdomain does not match. If no credential matches, the connection is made unauthenticated.
- Session creation does not check MCP connectivity or credentials.
- Under `limited` environment networking, session creation returns 400 if an MCP host is not in `allowed_hosts` (unless `allow_mcp_servers` is true).

### Errors

| Where | Error | Meaning |
|---|---|---|
| Agent create or update | 400 | Unreferenced server, dangling toolset, more than 20 servers, duplicate name |
| Session create | 400 | MCP host blocked by `limited` networking |
| `session.error` | `mcp_connection_failed_error` | Server unreachable, timeout, or non-auth HTTP failure |
| `session.error` | `mcp_authentication_failed_error` | Credential rejected, auth required with no matching credential, or OAuth refresh failed |

The connection is retried on the next `session.status_idle` to `session.status_running` transition.

Also: MCP tool output over 100,000 characters is written to a sandbox file (same as built-in tools).

---

## 10. Files and the file system

### Upload

```bash
curl --fail-with-body -sS https://api.anthropic.com/v1/files \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -F file=@data.csv
```

```python
from pathlib import Path

file = client.files.upload(file=Path("data.csv"))
print(file.id)  # file_...
```

### Mount into a session (read-only)

```json
"resources": [
  { "type": "file", "file_id": "file_011CNha8iCJcU1wXNR6q4V8w", "mount_path": "/data.csv" }
]
```

- The file is available at `/mnt/session/uploads/<mount_path>`. Default when `mount_path` is omitted: `/mnt/session/uploads/<file_id>`.
- Mounted files are read-only copies. The agent writes modified versions to new paths.
- Each session copy has its own `file_id` and does not count toward storage limits.
- Maximum 500 files per session.
- Supported types: any. Size limits: Not documented on this page.

### Outputs

- The agent writes to `/mnt/session/outputs/`.
- List session outputs: `GET /v1/files?scope_id=<session_id>` with `anthropic-beta: managed-agents-2026-04-01`.
- Download: `GET /v1/files/{file_id}/content`.
- Outputs can appear a few seconds after the session goes idle. If an expected file is missing, list again after a short delay.
- Output files are deleted when the session is deleted. Download first.

---

## 11. Memory stores

### Create

`POST /v1/memory_stores` (header `anthropic-beta: agent-memory-2026-07-22`)

```json
{
  "name": "User Preferences",
  "description": "Per-user preferences and project context."
}
```

The `description` is shown to the agent. Other create fields: Not documented on the pages read.

```python
store = client.beta.memory_stores.create(
    name="User Preferences",
    description="Per-user preferences and project context.",
)
```

### Seed or edit memories

- Create: `POST /v1/memory_stores/{memory_store_id}/memories` with `{"path": "/formatting.md", "content": "..."}`. Create does not overwrite.
- Update: `POST /v1/memory_stores/{memory_store_id}/memories/{memory_id}` with `content` and/or `path` (rename). Optional `precondition: {"type": "content_sha256", "content_sha256": "..."}` applies the change only if the stored hash still matches.
- Read: `GET /v1/memory_stores/{memory_store_id}/memories/{memory_id}`.
- List: `GET /v1/memory_stores/{memory_store_id}/memories` with `path_prefix` (must end in `/`) and `depth` (omit or 0 for the whole subtree, 1 for immediate children).
- Delete: `DELETE /v1/memory_stores/{memory_store_id}/memories/{memory_id}`.

### Attach to a session

Only at session creation. Max 8 memory stores per session.

```json
"resources": [
  {
    "type": "memory_store",
    "memory_store_id": "memstore_01Hx...",
    "access": "read_only",
    "instructions": "Team standards. Check before starting any task."
  }
]
```

- `access`: `read_write` (default) or `read_only`. Enforced at the filesystem level.
- `instructions`: up to 4,096 chars, shown to the agent with the store name and description.
- Each store mounts at `/mnt/memory/<slug>/`, where the slug is the display name lowercased with non-alphanumeric runs replaced by hyphens. Read the exact path from the `mount_path` field on the session's memory-store resource.
- Writes outside a store's mount path under `/mnt/memory/` fail.
- The agent's reads and writes show up as normal `agent.tool_use` and `agent.tool_result` events.
- The agent toolset must be enabled.

### Limits

- Each memory: 100 kB (about 25k tokens).
- Each store: 10,000 memories. Writes fail when full.
- Each session: 8 memory stores.
- Versions: retained 30 days, except the recent versions of live memories.
- Stores can be archived (one-way). Store delete removes its memories and versions.

### Versions and audit

- `GET /v1/memory_stores/{memory_store_id}/memory_versions?memory_id=...` lists versions, newest first.
- `GET /v1/memory_stores/{memory_store_id}/memory_versions/{memory_version_id}` returns a version with `content`.
- `POST /v1/memory_stores/{memory_store_id}/memory_versions/{memory_version_id}/redact` scrubs content from a historical version and keeps the audit trail. The live head version cannot be redacted.
- There is no restore endpoint. Roll back by writing an old version's `content` back with an update.

### Store management

- `GET /v1/memory_stores?include_archived=true`
- `POST /v1/memory_stores/{memory_store_id}/archive` (one-way)
- `DELETE /v1/memory_stores/{memory_store_id}`

Warning in the docs: stores attach as `read_write` by default. A prompt-injected agent can write into a store that later sessions trust. Use `read_only` for reference material.

---

## 12. Vaults and credentials

Vaults and credentials are workspace-scoped. Any API key with workspace access can reference them at session creation.

### Create a vault

`POST /v1/vaults`

```json
{
  "display_name": "Alice",
  "metadata": { "external_user_id": "usr_abc123" }
}
```

Response: `type: "vault"`, `id` (`vlt_...`), `display_name`, `metadata`, `created_at`, `updated_at`, `archived_at`.

### Add a credential

`POST /v1/vaults/{vault_id}/credentials`. Body: `display_name` plus an `auth` object whose `type` is one of three:

**1. `mcp_oauth`: OAuth access for an MCP server (refresh supported)**

```json
{
  "display_name": "Alice's Slack",
  "auth": {
    "type": "mcp_oauth",
    "mcp_server_url": "https://mcp.slack.com/mcp",
    "access_token": "xoxp-...",
    "expires_at": "2099-12-31T23:59:59Z",
    "refresh": {
      "token_endpoint": "https://slack.com/api/oauth.v2.user.access",
      "client_id": "1234567890.0987654321",
      "scope": "channels:read chat:write",
      "refresh_token": "xoxe-1-...",
      "token_endpoint_auth": { "type": "client_secret_post", "client_secret": "abc123..." }
    }
  }
}
```

`token_endpoint_auth.type` is `none`, `client_secret_basic`, or `client_secret_post`. `refresh.token_endpoint` and `client_id` cannot change after creation.

**2. `static_bearer`: fixed token for an MCP server**

```json
{
  "display_name": "Linear API key",
  "auth": {
    "type": "static_bearer",
    "mcp_server_url": "https://mcp.linear.app/mcp",
    "token": "lin_api_..."
  }
}
```

**3. `environment_variable`: secret injected into outbound requests**

```json
{
  "display_name": "Notion API key",
  "auth": {
    "type": "environment_variable",
    "secret_name": "NOTION_API_KEY",
    "secret_value": "ntn_...",
    "networking": { "type": "limited", "allowed_hosts": ["api.notion.com"] },
    "injection_location": { "header": true, "body": false }
  }
}
```

- The sandbox sees an opaque placeholder in the environment variable. The real value is substituted at egress, only for hosts in the credential's `allowed_hosts`. The environment must also allow that host.
- `injection_location` has `header` and `body` booleans. If you provide the object, omitted fields default to false. If you omit the object, both are enabled. Both false is a 400. Console-created credentials enable header only.
- Clients that check the key format locally, or sign requests from the secret (for example AWS SigV4), will not work with a placeholder.
- Not supported with self-hosted sandboxes.

### Credential secret values are write-only

`token`, `access_token`, `refresh_token`, `client_secret`, and `secret_value` are never returned.

### Attach at session creation

```json
{ "agent": "agent_...", "environment_id": "env_...", "vault_ids": ["vlt_..."] }
```

- With several vaults, the first vault with a matching credential wins.
- In multiagent sessions, vault credentials apply to every thread.

### Limits and operations

- Max 20 credentials per vault.
- `mcp_server_url` (MCP credentials) or `secret_name` (env var credentials) must be unique among active credentials in a vault. Duplicate returns 409.
- Keys are immutable. To change `mcp_server_url` or `secret_name`, archive and create anew.
- Secret values, `display_name`, and `injection_location` can be updated (`POST /v1/vaults/{vault_id}/credentials/{credential_id}`).
- Credentials are re-resolved during a session, so rotation applies without restart.
- `POST /v1/vaults/{vault_id}/credentials/{credential_id}/mcp_oauth_validate` returns `status`: `valid`, `invalid` (re-authorize), or `unknown` (transient; retry).
- Archive vault: `POST /v1/vaults/{vault_id}/archive`. Purges secrets; new sessions fail; running sessions continue.
- Archive credential: `POST /v1/vaults/{vault_id}/credentials/{credential_id}/archive`.
- Delete: hard delete, no record kept. Max vaults per workspace, vault_ids per session: Not documented.

Webhook events for vaults: `vault.created`, `vault.archived`, `vault.deleted`, `vault_credential.created`, `vault_credential.archived`, `vault_credential.deleted`, `vault_credential.refresh_failed`.

---

## 13. Skills

### Anthropic skills

Pre-built, in every workspace, referenced by short name: `pptx`, `xlsx`, `docx`, `pdf`. Attach with `{"type": "anthropic", "skill_id": "xlsx"}`.

### Custom skills: upload

`POST /v1/skills` (multipart, field `files[]`). A skill is a directory with a `SKILL.md` plus supporting files, as a zip or as individual files.

```bash
curl -X POST "https://api.anthropic.com/v1/skills" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -F "files[]=@example_skill.zip"
```

```python
from anthropic.lib import files_from_dir

skill = client.skills.create(files=files_from_dir("example_skill"))
print(skill.id, skill.latest_version_id)  # skill_..., version id
```

- `display_title` is optional. If omitted, the display name comes from the `name` field in `SKILL.md`.
- List, retrieve, delete, and version endpoints exist (`/v1/skills/...`). Their bodies are not documented on this page.
- The SDK method is `client.skills.create` (not under `beta`) in the Python examples.

### Attach to an agent

```json
"skills": [
  { "type": "anthropic", "skill_id": "xlsx" },
  { "type": "custom", "skill_id": "skill_01AbCdEfGhIjKlMnOpQrStUv", "version": "latest" }
]
```

- `version` is optional. It defaults to latest. Pin a number to freeze.
- Up to 500 skills per session, counted as the deduplicated set across all agents in the session.
- Each skill adds context cost. Mounting more skills slows sandbox start.
- Requires the `read` tool. A session with `read` disabled does not load skills.

### Load skills from a GitHub repository

Attach a `github_repository` resource to the session. The server scans exactly `.claude/skills/<skill-name>/SKILL.md` at the repository root, one directory deep, at session start. No upload and no `skills` entry is needed.

```json
"resources": [
  {
    "type": "github_repository",
    "url": "https://github.com/org/repo",
    "mount_path": "/workspace/repo",
    "authorization_token": "ghp_...",
    "checkout": { "type": "branch", "name": "main" }
  }
]
```

- `mount_path` defaults to `/workspace/<repo-name>`.
- Scan runs once at session start. Mid-session pushes are not picked up.
- Only cloud environments support repo mounts. Self-hosted does not.
- Treat a mounted repo as part of the agent's trust boundary. Anyone who can commit can change a skill's instructions. Review `.claude/skills` before mounting repos that take outside contributions.

---

## 14. Subagents and multi-agent orchestration

### The `multiagent` block

```json
{
  "multiagent": {
    "type": "multiagent_20261001",
    "advisor": { "type": "disabled" },
    "subagents": {
      "type": "enabled",
      "inline_agents": { "type": "enabled" },
      "predefined_agents": [
        { "type": "agent", "id": "agent_...", "version": 1 },
        "agent_...",
        { "type": "self" }
      ]
    },
    "workflows": {
      "type": "enabled",
      "inline_agents": { "type": "enabled" },
      "predefined_agents": []
    }
  }
}
```

- `subagents` and `workflows` are each `enabled` or `disabled`. Both default to enabled. `inline_agents` (agents the agent defines itself at run time, not saved) is enabled by default.
- `predefined_agents` entries: a string ID (latest version at creation), `{"type": "agent", "id", "version"?}` (pinned), or `{"type": "self"}` (copies of the agent itself).
- With `inline_agents` disabled, `predefined_agents` must have at least one entry.
- An agent that has its own `multiagent` set cannot be listed as a subagent or workflow agent of another agent.
- `advisor`: `{"type": "enabled", "model": "..."}` lets the primary thread consult a model mid-turn. Only the primary thread can use it, and calls bill at the advisor model's rates. The name `anthropic.advisor` is reserved while enabled.
- The older `coordinator` type (agents roster) is still accepted. It cannot start workflow runs.

### How delegation works

- The agent delegates by calling its subagents. Each subagent runs in its own session thread with its own history, and its thread is persistent: the agent can send follow-up messages.
- All threads share the sandbox filesystem and the session's vault credentials.
- Delegation is one level deep (a subagent cannot spawn its own subagents).
- Max 25 child threads at a time (idle ones included).
- Subagent events appear on the primary stream as `session.thread_created`, `session.thread_status_*`, and `agent.thread_message_*`.
- To read one thread: `GET /v1/sessions/{id}/threads` to find it, then `GET /v1/sessions/{id}/threads/{thread_id}/stream`.
- Interrupt one thread: `user.interrupt` with `session_thread_id`.
- Tool confirmations from a subagent are routed to the primary stream and carry `session_thread_id`.
- A predefined agent uses its own model, system prompt, tools, MCP servers, and skills. An inline agent uses the parent's model, tools, MCP servers, and skills.
- Session-level `agent_with_overrides` apply to the primary agent and its `self` copies.
- Subagent MCP servers must be allowed by the environment's networking (section 4).

### Full example: operator with four subagents (composed)

Step 1: create the four subagents, each without a `multiagent` block:

```python
from anthropic import Anthropic

client = Anthropic()

roles = {
    "sourcing": "Find candidate leads that match the brief. Return a numbered list with a source link for each.",
    "qualifying": "Score each lead against the qualification rules. Return pass or fail with one reason per lead.",
    "research": "Research one lead. Return a short profile with cited facts only.",
    "drafting": "Draft one outreach email per qualified lead in the brand voice. Do not send anything.",
}

subagents = {
    role: client.beta.agents.create(
        name=f"Operator {role.title()}",
        model="claude-sonnet-5-5",
        system=prompt,
        tools=[{"type": "agent_toolset_20260401"}],
    )
    for role, prompt in roles.items()
}
```

Step 2: create the operator that lists them:

```python
operator = client.beta.agents.create(
    name="Operator",
    model="claude-opus-5-5",
    system=(
        "You run the outreach operator. Delegate sourcing, qualifying, research, "
        "and drafting to your subagents in that order. Report results in one summary."
    ),
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "multiagent_20261001",
        "subagents": {
            "type": "enabled",
            "inline_agents": {"type": "disabled"},
            "predefined_agents": [
                {"type": "agent", "id": a.id, "version": a.version}
                for a in subagents.values()
            ],
        },
        "workflows": {"type": "disabled"},
    },
)
```

Step 3: start a session and send the work:

```python
environment = client.beta.environments.create(
    name="operator-env",
    config={"type": "cloud", "networking": {"type": "limited", "allowed_hosts": ["api.example-crm.com"]}},
)

session = client.beta.sessions.create(
    agent=operator.id,
    environment_id=environment.id,
    title="Weekly outreach run",
)

client.beta.sessions.events.send(
    session.id,
    events=[{"type": "user.message", "content": [{"type": "text", "text": "Run this week's outreach cycle for the Seattle list."}]}],
)
```

Notes:
- The four subagents share the operator's sandbox and vault credentials.
- Each subagent's thread can be streamed separately.
- Setting `workflows` to `disabled` keeps the operator to subagent delegation. Leave it enabled to let the agent write workflow runs.

---

## 15. Workflow runs (dynamic workflows)

- A workflow is a program the agent writes to run many agents in phases and combine their results. A workflow run is one execution of it, in the background on the server.
- Turn on with `workflows.type: "enabled"` in the `multiagent` block (on by default under `multiagent_20261001`).
- No approval step: the agent starts the run in the same turn it writes the workflow. To review first, tell the agent in the system prompt or message to describe the run and wait for approval.
- Runs are followed on the session's event stream (`workflow_run.*` events, section 6). Each agent works in its own thread, which carries the run's `workflow_run_id`.
- A run's agents work with the same sandbox files and the same MCP credentials.
- Interrupt: a `user.interrupt` pauses runs. It does not end them. To stop a run, ask the agent to stop it.
- Budget: when the session reaches its budget, open runs pause (`workflow_run.status_idle`). Changing the budget resumes them, unless an interrupt paused them.

### Limits

| Limit | Value | At the limit |
|---|---|---|
| Threads working at once in one run | 64 | Run waits; the API does not guarantee this number |
| Agents started by one workflow, over its life | 1,000 | `thread_limit_error` |
| Run lifetime | 24 hours by default, or the lifetime the agent sets | `timeout_error` |
| Open runs per session | 10 by default | Start refused; `workflow_run.error` with `max_workflow_runs_error` |

- Runs cannot nest: only the primary thread can start a run.
- No event you send ends a run. Archiving the session can.
- A run's threads are exempt from the 25-child-thread limit.
- You cannot stop a run's thread by ID, or archive one while its run is open.
- Make tools safe to call twice: a run can create more than one thread for the same work.
- Name and description are shortened to 64 and 256 chars.
- Other workflow limits exist but are not listed.
- Run work counts toward your Messages API rate limits for each model.

### Run results

| `result.type` | Meaning |
|---|---|
| `completed` | The workflow finished. Does not mean the work passed; check the threads. |
| `stopped` | The agent stopped the run, or the session was archived |
| `error` with `timeout_error` | Lifetime reached |
| `error` with `program_error` | Workflow code failed or broke a workflow rule |
| `error` with `thread_limit_error` | Over the 1,000-agent limit |
| `error` with `unknown_error` | Server limit or internal failure |

### When is the work done?

Both must be true:
1. Every run you have seen created has a `workflow_run.status_ended`.
2. A `session.status_idle` with `stop_reason: end_turn` arrives, not caused by your own interrupt.

An idle session by itself does not mean the work is done.

---

## 16. Outcomes and grading

An outcome tells the session what "done" looks like. A separate grader scores the artifact against your rubric, and the agent iterates until it is satisfied or runs out of iterations.

### Start an outcome

Send `user.define_outcome` to an existing session, or include it in `initial_events` at creation (only one outcome per create request):

```json
{
  "events": [
    {
      "type": "user.define_outcome",
      "description": "Build a DCF model for Costco in .xlsx",
      "rubric": { "type": "text", "content": "# DCF Model Rubric\n- Projects revenue for at least 5 years forward\n- Sensitivity table on WACC and terminal growth" },
      "max_iterations": 5
    }
  ]
}
```

- `rubric` is required. Inline text (`{"type": "text", "content"}`, up to 262,144 chars) or an uploaded file (`{"type": "file", "file_id"}`).
- `max_iterations` defaults to 3, max 20.
- The agent starts work on receipt. No separate message is needed.
- Write rubric criteria that can be graded one by one. Vague criteria give noisy grading.

### Events

- `span.outcome_evaluation_start`: `iteration` (0-based; 0 is the first evaluation), `outcome_id`.
- `span.outcome_evaluation_ongoing`: heartbeat. The grader's reasoning is not shown.
- `span.outcome_evaluation_end`: `result`, `explanation` (which criteria passed or failed), `iteration`, `usage`.

| `result` | What happens next |
|---|---|
| `satisfied` | Session goes idle |
| `needs_revision` | Agent starts another iteration |
| `max_iterations_reached` | One final acknowledgment turn, then idle. No further grading. |
| `failed` | Idle. Used when the rubric does not fit the deliverable. |
| `interrupted` | Set when you interrupt during an active outcome. The outcome ends. |

### Reading results

- Live: watch for `span.outcome_evaluation_end` on the stream.
- Polling: `GET /v1/sessions/{session_id}` and read `outcome_evaluations[].result`. Values while grading: `pending`, `running`, `evaluating`.
- Deliverables: the agent writes to `/mnt/session/outputs/`. List with `GET /v1/files?scope_id=<session_id>`.

### Rules

- One outcome at a time. Chain by sending a new `user.define_outcome` after the previous `span.outcome_evaluation_end`.
- The session keeps history across outcomes.
- No grading starts while a workflow run is open.
- You can send `user.message` during an outcome to steer, but it is not required.

---

## 17. Scheduled deployments (cron)

A deployment creates a new session from an agent on a schedule.

### Create

`POST /v1/deployments` with header `anthropic-beta: managed-agents-2026-04-01` (the docs use `?beta=true` on the URL).

| Field | Type | Notes |
|---|---|---|
| `name` | string | Required. 1 to 256 chars. |
| `agent` | string or `{"type": "agent", "id", "version"?}` | Required. String = latest version. Must not be archived. |
| `environment_id` | string | Required |
| `initial_events` | array, 1 to 50 | Required. Each is `user.message`, `user.define_outcome`, or `system.message` (deployments accept `system.message`, sessions do not). |
| `schedule` | object or null | `{"type": "cron", "expression": "...", "timezone": "..."}`. Both `expression` and `timezone` required when set. |
| `budget` | object or null | Same shape as a session budget. Copied onto every session the deployment starts. `null` removes it. |
| `description` | string or null | Max 2,048 chars |
| `metadata` | map | Max 16 pairs |
| `resources` | array, max 500 | `github_repository`, `file`, `memory_store` (same shapes as session create) |
| `vault_ids` | array, max 50 | Vaults for credentials |

Full example: every day at 6:00 AM Pacific (composed; `expression` and `timezone` per docs):

```python
deployment = client.beta.deployments.create(
    name="Daily outreach cycle",
    agent={"type": "agent", "id": operator.id, "version": operator.version},
    environment_id=environment.id,
    initial_events=[
        {"type": "user.message", "content": [{"type": "text", "text": "Run the daily outreach cycle for the Seattle list."}]}
    ],
    schedule={
        "type": "cron",
        "expression": "0 6 * * *",
        "timezone": "America/Los_Angeles",
    },
    budget={"type": "limit", "max_list_cost": {"amount": "2000", "currency": "USD"}},
)
print(deployment.id, deployment.schedule.upcoming_runs_at)
```

```json
{
  "name": "Daily outreach cycle",
  "agent": { "type": "agent", "id": "agent_...", "version": 1 },
  "environment_id": "env_...",
  "initial_events": [
    { "type": "user.message", "content": [{ "type": "text", "text": "Run the daily outreach cycle for the Seattle list." }] }
  ],
  "schedule": { "type": "cron", "expression": "0 6 * * *", "timezone": "America/Los_Angeles" },
  "budget": { "type": "limit", "max_list_cost": { "amount": "2000", "currency": "USD" } }
}
```

### Schedule format

- `expression`: 5-field POSIX cron (`minute hour day-of-month month day-of-week`). Day-of-week 0 and 7 both mean Sunday. Not supported: seconds, year, `L`, `W`, `#`, `?`, and shortcuts such as `@daily`. Max 256 chars.
- `timezone`: IANA name (`America/Los_Angeles`, `UTC`). Validated.
- Granularity: minute.
- DST: wall-clock matching. `0 6 * * *` in `America/Los_Angeles` fires at 6:00 AM local in both PST and PDT. Times that do not exist on spring-forward day do not fire; times that occur twice on fall-back day fire twice. Avoid 1 to 3 AM local if missed or duplicate runs matter.
- Jitter: actual start can be delayed by up to 15 percent of the interval between runs, with a minimum of 5 seconds and a maximum of 9 minutes. `upcoming_runs_at` shows the schedule without jitter.

### Response fields

`id` (`depl_...`), `status` (`active` or `paused`; archived deployments still report `active` with `archived_at` set), `paused_reason`, `schedule` (`expression`, `timezone`, `last_run_at`, `upcoming_runs_at` up to 5), `agent`, `environment_id`, `initial_events`, `resources`, `vault_ids`, `budget`, `created_at`, `updated_at`, `archived_at`.

### Lifecycle

| Action | Request | Effect |
|---|---|---|
| Pause | `POST /v1/deployments/{id}/pause` | Stops scheduled runs. `paused_reason` becomes `{"type": "manual"}`. Manual runs still allowed. Running sessions continue. |
| Unpause | `POST /v1/deployments/{id}/unpause` | Resumes from the next occurrence. Missed runs are not backfilled. |
| Run now | `POST /v1/deployments/{id}/run` | Creates a session immediately. Writes a deployment run with `trigger_context.type: "manual"`. Does not emit `deployment_run` webhooks. |
| Archive | `POST /v1/deployments/{id}/archive` | Terminal. Schedule ends; the deployment cannot be modified. |
| Update | `POST /v1/deployments/{id}?beta=true` | Changes such as `budget` apply to runs started afterward |

### Run history

- `GET /v1/deployment_runs?deployment_id={id}` lists runs. Filter failures with `has_error=true`.
- `GET /v1/deployment_runs/{deployment_run_id}` retrieves one.
- Run fields: `id` (`drun_...`), `deployment_id`, `trigger_context` (`type`: `schedule` with `scheduled_at`, or `manual`), `session_id` (null on failure), `error` (`type`, `message`), `agent`, `created_at`.
- Common error types: `environment_archived_error`, `agent_archived_error`, `session_rate_limited_error`, `vault_archived_error`, `unknown_error`, and others.
- Auto-pause: unrecoverable errors (archived agent or environment, missing resource) pause the deployment and set `paused_reason.error.type`. Rate limits do not pause it; the next occurrence tries again.
- If the agent is archived, the deployment is archived too. If the agent is deleted, the next trigger archives the deployment.

### Limits

- 1,000 scheduled deployments per organization (contact support for more).
- `initial_events` 1 to 50. `resources` max 500. `vault_ids` max 50.

---

## 18. Webhooks

### Register an endpoint

Endpoints are created in the Claude Console on the Webhooks page (`platform.claude.com/settings/workspaces/default/webhooks`). Each endpoint belongs to one workspace.

- URL: HTTPS, port 443, publicly resolvable hostname.
- Event types: the list of `data.type` values to receive.
- Signing secret: starts with `whsec_`, 32 bytes, shown once at creation.

A creation API for webhook endpoints is Not documented on these pages. The index lists organization webhook endpoints under `/api/beta/organization/webhooks/...`; those were not read.

### Event names

Webhook names differ from stream names. Examples: stream `session.status_idle` = webhook `session.status_idled`; stream `session.status_running` = webhook `session.status_run_started`.

| Group | Events |
|---|---|
| Session | `session.status_run_started`, `session.status_idled`, `session.budget_reached`, `session.status_rescheduled`, `session.status_terminated`, `session.thread_created`, `session.thread_idled`, `session.thread_terminated`, `session.outcome_evaluation_ended`, `session.updated`, `session.deleted` |
| Vault | `vault.created`, `vault.archived`, `vault.deleted`, `vault_credential.created`, `vault_credential.archived`, `vault_credential.deleted`, `vault_credential.refresh_failed` |
| Agent | `agent.created`, `agent.updated` (new version only), `agent.archived`, `agent.deleted` |
| Deployment | `deployment.created`, `deployment.updated`, `deployment.paused`, `deployment.unpaused`, `deployment.archived`, `deployment.deleted` |
| Deployment run | `deployment_run.started` (scheduled runs only), `deployment_run.succeeded`, `deployment_run.failed` |
| Environment | `environment.created`, `environment.updated`, `environment.archived`, `environment.deleted` |
| Memory store | `memory_store.created`, `memory_store.archived`, `memory_store.deleted` |

Workflow run events do not trigger webhooks.

### Payload

Webhook events carry the type and id, not the full object. Fetch the object with GET.

```json
{
  "type": "event",
  "id": "whe_9d5c1f7e...",
  "created_at": "2026-03-18T14:05:22Z",
  "data": {
    "type": "session.status_idled",
    "id": "sesn_01XYZ...",
    "organization_id": "8a3d2f1e-...",
    "workspace_id": "c7b0e4d9-..."
  }
}
```

### Verify the signature

- Headers: `webhook-id`, `webhook-timestamp`, `webhook-signature`.
- Use the SDK's `unwrap` helper. It throws if the signature is invalid or the payload is more than 5 minutes old.
- Set `ANTHROPIC_WEBHOOK_SIGNING_KEY` to the `whsec_` secret. The Python client reads it from the environment.
- The raw signature algorithm is Not documented on these pages.

```python
from flask import Flask, request
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_WEBHOOK_SIGNING_KEY
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        event = client.beta.webhooks.unwrap(request.get_data(as_text=True), headers=dict(request.headers))
    except Exception:
        return "invalid signature", 400
    if event.data.type == "session.status_idled":
        session = client.beta.sessions.retrieve(event.data.id)
        print("idle:", session.status)
    return "", 200
```

Use the raw body bytes; parsing JSON first breaks the signature.

### Delivery

- Up to 3 attempts per endpoint and event, with jittered exponential backoff between 5 and 120 seconds. Every attempt has the same `event.id`. After the last failure the event is dropped; there is no replay.
- Return any 2xx to acknowledge. Deduplicate on `event.id`.
- Ordering is not guaranteed. Drive state from the fetched object, not arrival order.
- An event is delivered only to endpoints subscribed when it is emitted. Subscribing later does not backfill.
- `webhook-timestamp` is regenerated on each attempt. Use `created_at` in the payload for when the event happened.
- Auto-disable: a 3xx response (redirects are never followed), a URL that resolves to a non-public address, or continuous failures for a sustained period disables the endpoint. Re-enable in the Console.

---

## 19. Budgets and cost

### How cost is measured (list cost)

- Model tokens at each model's public list price.
- Web searches: $10 USD per 1,000 searches.
- Session running time: $0.08 USD per hour (on `active_seconds`, overlapping threads counted once).
- Web fetch requests carry no per-request charge.
- List cost is not your contracted price. Negotiated discounts make your bill lower than the cap.

### Setting a budget

- Set at session creation: `"budget": {"type": "limit", "max_list_cost": {"amount": "125", "currency": "USD"}}`.
- `amount` is a whole number of US cents as a string, no leading zeros, greater than zero. `"125"` is $1.25. `"25.00"` is rejected.
- `currency`: `USD` only.
- A budget cannot be added to a session created without one (400).
- Change: `POST /v1/sessions/{id}` with a new `budget`. The new cap must be greater than the consumed list cost (400 otherwise).
- Remove: `"budget": null`. One-way: a removed budget cannot be re-added.
- Deployments: budget is copied onto each session at start, so it caps each run separately. Set with `POST /v1/deployments/{id}`; `null` removes it.

### Enforcement

- Checked between model requests. The request that crosses the cap completes, so a paused session's `list_cost` can read a little above the cap (for example "53" for a "50" cap). Each working thread can overshoot by one request.
- At the cap, the session goes `idle` with `stop_reason: budget_reached`. It is not terminated.
- Event order at pause: `session.thread_status_idle` (`budget_reached`) for each thread, then `session.usage`, then `session.status_idle` (`budget_reached`).
- While at or over the cap, the session accepts only `user.tool_confirmation`, `user.tool_result`, `user.custom_tool_result`, and `user.interrupt`. A `user.message` is rejected with 400.
- Changing or removing the budget resumes paused work automatically. Paused workflow runs resume too, unless an interrupt paused them.
- Models with no public list price block budgeted sessions (400 at creation).
- Multiagent sessions share one budget across all threads. Advisor calls count against it.

### Usage fields

Session object `usage` and `session.usage` event:

```json
{
  "input_tokens": 5000,
  "output_tokens": 3200,
  "cache_read_input_tokens": 20000,
  "cache_creation": { "ephemeral_5m_input_tokens": 2000, "ephemeral_1h_input_tokens": 0 },
  "list_cost": { "amount": "187", "currency": "USD" },
  "active_seconds": 342.5,
  "server_tool_use": { "web_search_requests": 3, "web_fetch_requests": 0 }
}
```

- `list_cost` is in cents as a string. Enforcement uses the unrounded value, so reported figures can differ by up to half a cent.
- Thread retrieval returns the same usage fields per thread. Per-thread totals do not sum exactly to the session total.
- A session emits `session.usage` before every idle.

### Observability

- Console session viewer: `platform.claude.com/sessions` (Developers and Admins). Shows transcript, raw events, tools, resources, threads, and cost.
- `?event={event_id}` on a session URL opens at that event.
- OpenTelemetry tracing is referenced in the docs (`manage-claude/opentelemetry`); that page was not read for this file.

---

## 20. Limits and gotchas

Limits:
- Create endpoints: 300 requests per minute per organization. Read endpoints (retrieve, list, stream): 1,200 per minute. Org spend and usage-tier limits also apply.
- Agent: name 1 to 256; description 2,048; system 100,000 chars; metadata 16 pairs; tools 256 across toolsets; MCP servers 20.
- Custom tool names cannot start with `mcp__` or `ant__`, and cannot match built-in names.
- Session: initial events 50; resources 500; `vault_ids` count: Not documented; skills 500 (deduplicated); memory stores 8; files 500.
- Memory: 100 kB per memory; 10,000 memories per store; instructions 4,096 chars.
- Vault: 20 credentials per vault.
- Environment: up to 8 GB memory and 10 GB disk per sandbox. Session runtime and idle timeout: Not documented.
- Output file and tool output: over 100,000 characters goes to a file.
- Event deltas: best effort; not persisted; no replay.
- Deployments: 1,000 per organization; cron minute granularity.
- Workflow runs: 64 threads at once; 1,000 agents per run; 24-hour default lifetime; 10 open runs per session.
- Subagents: one level deep; 25 child threads at a time.
- Outcome rubric: 262,144 chars; `max_iterations` max 20.
- Budget amount: whole cents as a string.
- Memory store and session delete are permanent.
- Session file size limits and file type limits: Not documented on the pages read.

Gotchas:
- Open the event stream before sending the first event. Otherwise early events are missed.
- Interrupting does not end workflow runs or change budgets. Ask the agent to stop runs.
- An idle session is not necessarily done when workflow runs are open.
- Agent updates and session archive or delete fail with 400 while a workflow run is open.
- `user.tool_confirmation` on a non-`ask` event is a 400, including calls that `auto` denied.
- Environment variable credentials are substituted at egress only. Clients that validate keys locally will fail.
- `limited` networking with no hosts allows nothing. Packages on `limited` need `allow_package_managers: true`.
- Memory stores attach only at session creation and default to `read_write`.
- Repository skills load only at session start and only from `.claude/skills/<name>/SKILL.md`.
- Custom tool results for a call can be sent before `session.status_idle`; a duplicate is ignored.
- Deployments auto-pause on unrecoverable errors. Check `paused_reason` after an archive.
- Not eligible for Zero Data Retention or HIPAA BAA coverage.
- Two `anthropic-version` values appear in the docs (`2023-06-01` in guides, `2026-10-21` in the reference).
- Some webhook and stream event names differ (`session.status_idled` vs `session.status_idle`).

---

## 21. Sources

- https://platform.claude.com/llms.txt (index of Managed Agents pages)
- https://platform.claude.com/docs/en/managed-agents/overview
- https://platform.claude.com/docs/en/managed-agents/quickstart
- https://platform.claude.com/docs/en/managed-agents/agent-setup
- https://platform.claude.com/docs/en/managed-agents/environments
- https://platform.claude.com/docs/en/managed-agents/cloud-sandboxes-reference
- https://platform.claude.com/docs/en/managed-agents/sessions
- https://platform.claude.com/docs/en/managed-agents/session-operations
- https://platform.claude.com/docs/en/managed-agents/events-and-streaming
- https://platform.claude.com/docs/en/managed-agents/event-deltas
- https://platform.claude.com/docs/en/managed-agents/reference
- https://platform.claude.com/docs/en/managed-agents/tools
- https://platform.claude.com/docs/en/managed-agents/permission-policies
- https://platform.claude.com/docs/en/managed-agents/mcp-connector
- https://platform.claude.com/docs/en/managed-agents/vaults
- https://platform.claude.com/docs/en/managed-agents/files
- https://platform.claude.com/docs/en/managed-agents/memory
- https://platform.claude.com/docs/en/managed-agents/skills
- https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration
- https://platform.claude.com/docs/en/managed-agents/workflow-runs
- https://platform.claude.com/docs/en/managed-agents/define-outcomes
- https://platform.claude.com/docs/en/managed-agents/scheduled-deployments
- https://platform.claude.com/docs/en/managed-agents/webhooks
- https://platform.claude.com/docs/en/managed-agents/budgets
- https://platform.claude.com/docs/en/managed-agents/session-observability
- https://platform.claude.com/docs/en/api/beta/agents/create
- https://platform.claude.com/docs/en/api/beta/agents/update
- https://platform.claude.com/docs/en/api/beta/agents/versions
- https://platform.claude.com/docs/en/api/beta/sessions/create
- https://platform.claude.com/docs/en/api/beta/sessions/events/send
- https://platform.claude.com/docs/en/api/beta/sessions/events/list
- https://platform.claude.com/docs/en/api/beta/deployments/create

Not read for this file (referenced by the pages above): the OpenTelemetry page, the GitHub resource page, the Files API general page, the organization webhooks API, the Claude Platform on AWS and Google Cloud pages, and the dreaming pages.
