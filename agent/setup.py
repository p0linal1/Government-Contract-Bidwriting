"""Create or update Cadocary's bid agents on Claude Managed Agents.

Run from the repo root with the key in the environment:

    ANTHROPIC_API_KEY=... python3 agent/setup.py

Safe to run again. It records what it made in agent/ids.json and only
uploads the skills, agents, and memory that changed.
"""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).parent
IDS_FILE = HERE / "ids.json"
API = "https://api.anthropic.com/v1"
AGENTS_BETA = "managed-agents-2026-04-01"
MEMORY_BETA = "agent-memory-2026-07-22"
MODEL = {"id": "claude-opus-5-5", "effort": {"type": "high"}}

HELPERS = [
    {
        "key": "qualifier",
        "name": "Cadocary Qualifier",
        "description": "Reads an RFP, decides pursue or pass, lists every requirement and deadline, and checks the other agents' work.",
        "skill": "rfp-qualifying",
        "tools": ["read", "write", "glob", "grep"],
    },
    {
        "key": "researcher",
        "name": "Cadocary Researcher",
        "description": "Finds what an RFP is worth, comparable past awards, the incumbent, likely competitors, and a price, with a source for every number.",
        "skill": "rfp-research",
        "tools": ["read", "write", "glob", "grep", "web_search", "web_fetch"],
    },
    {
        "key": "drafter",
        "name": "Cadocary Drafter",
        "description": "Writes the complete proposal from the qualification, the research, and Cadocary's approved facts.",
        "skill": "proposal-drafting",
        "tools": ["read", "write", "edit", "glob", "grep"],
    },
]

OPERATOR = {
    "key": "operator",
    "name": "Cadocary Operator",
    "description": "Runs the bid pipeline: pulls new RFPs, hands qualifying, research, and drafting to its three agents, checks their work, and writes the packet Doug reviews.",
    "skill": "agent-delegation",
    "tools": ["read", "write", "glob", "grep"],
}

# Polina's hosted SAM.gov tool (cloud/AGENT-INTEGRATION.md on the sam-research-agent branch).
# Its address stays out of the repo; the bearer token lives in the vault, never on the agent.
SAM_SERVER = "sam-research"

ENVIRONMENT = {
    "name": "cadocary-bids",
    # The researcher needs the open web, and limited networking also limits web search and fetch.
    # No agent has bash, so search, fetch, and our own tools are the only ways out.
    "config": {"type": "cloud", "networking": {"type": "unrestricted"}},
}

MEMORY_STORES = [
    {
        "key": "rfp-library",
        "name": "RFP Library",
        "description": "Every RFP the pipeline has found: an index, one record per RFP, and earlier findings. Read-only for agents.",
    },
    {
        "key": "cadocary-facts",
        "name": "Cadocary Facts",
        "description": "The facts about Cadocary LLC that agents may use. Nothing about Cadocary may be claimed unless it is here. Read-only for agents.",
    },
]


def call(method, path, body=None, *, beta=AGENTS_BETA, files=None):
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "anthropic-beta": beta,
    }
    data = None
    if files is not None:
        boundary = uuid.uuid4().hex
        data = multipart(files, boundary)
        headers["content-type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    request = urllib.request.Request(f"{API}/{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"{method} /{path} failed ({error.code}): {error.read().decode()}")


def multipart(files, boundary):
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="files[]"; filename="{name}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n".encode() + content + b"\r\n"
        for name, content in files
    ]
    return b"".join(parts) + f"--{boundary}--\r\n".encode()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def save(ids):
    IDS_FILE.write_text(json.dumps(ids, indent=2) + "\n")


def sync_environment(ids):
    if "environment" not in ids:
        environment = call("POST", "environments", ENVIRONMENT)
        ids["environment"] = {"id": environment["id"], "name": ENVIRONMENT["name"]}
        save(ids)
    return ids["environment"]


def sync_memory_store(spec, ids):
    stores = ids.setdefault("memory_stores", {})
    readme = (HERE / "memory" / spec["key"] / "README.md").read_text()
    known = stores.get(spec["key"])
    if known is None:
        store = call("POST", "memory_stores", {"name": spec["name"], "description": spec["description"]}, beta=MEMORY_BETA)
        memory = call("POST", f"memory_stores/{store['id']}/memories", {"path": "/README.md", "content": readme}, beta=MEMORY_BETA)
        known = {"id": store["id"], "name": spec["name"], "readme_id": memory["id"]}
    elif known["fingerprint"] != fingerprint(readme):
        call("POST", f"memory_stores/{known['id']}/memories/{known['readme_id']}", {"content": readme}, beta=MEMORY_BETA)
    known["fingerprint"] = fingerprint(readme)
    stores[spec["key"]] = known
    save(ids)
    return known


def sync_skill(name, ids):
    skills = ids.setdefault("skills", {})
    folder = HERE / "skills" / name
    files = [(f"{name}/{path.relative_to(folder)}", path.read_bytes()) for path in sorted(folder.rglob("*")) if path.is_file()]
    digest = fingerprint([(file_name, content.decode()) for file_name, content in files])
    known = skills.get(name)
    if known and known["fingerprint"] == digest:
        return known
    if known:
        version = call("POST", f"skills/{known['id']}/versions", files=files)
        known = {"id": known["id"], "version": version["id"]}
    else:
        skill = call("POST", "skills", files=files)
        known = {"id": skill["id"], "version": skill["latest_version_id"]}
    known["fingerprint"] = digest
    skills[name] = known
    save(ids)
    return known


def sync_vault(ids):
    """The vault holds the SAM tool's token. Sessions pass its id; Anthropic adds the token to each call."""
    if "vault" not in ids:
        vault = call("POST", "vaults", {"display_name": "Cadocary bid agent", "metadata": {"project": "cadocary-bids"}})
        ids["vault"] = {"id": vault["id"]}
        save(ids)
    vault = ids["vault"]
    if "sam_credential_id" not in vault:
        credential = call("POST", f"vaults/{vault['id']}/credentials", {
            "display_name": "SAM research tool",
            "auth": {"type": "static_bearer", "mcp_server_url": os.environ["SAM_TOOL_URL"], "token": os.environ["SAM_TOOL_TOKEN"]},
        })
        vault["sam_credential_id"] = credential["id"]
        save(ids)
    return vault


def toolset(names):
    allow = {"type": "always_allow"}
    return {
        "type": "agent_toolset_20260401",
        "default_config": {"enabled": False, "permission_policy": allow},
        "configs": [{"name": name, "enabled": True, "permission_policy": allow} for name in names],
    }


def agent_body(spec, skill, extra_tools=(), multiagent=None, mcp_servers=()):
    body = {
        "name": spec["name"],
        "description": spec["description"],
        "model": MODEL,
        "system": (HERE / "prompts" / f"{spec['key']}.md").read_text(),
        "tools": [toolset(spec["tools"]), *extra_tools],
        "skills": [{"type": "custom", "skill_id": skill["id"], "version": skill["version"]}],
        "metadata": {"project": "cadocary-bids", "role": spec["key"]},
    }
    if multiagent:
        body["multiagent"] = multiagent
    if mcp_servers:
        body["mcp_servers"] = list(mcp_servers)
    return body


def sync_agent(key, body, ids):
    agents = ids.setdefault("agents", {})
    known = agents.get(key)
    if known and known["fingerprint"] == fingerprint(body):
        return known
    agent = call("POST", f"agents/{known['id']}", body) if known else call("POST", "agents", body)
    known = {"id": agent["id"], "name": agent["name"], "version": agent["version"], "fingerprint": fingerprint(body)}
    agents[key] = known
    save(ids)
    return known


def main():
    missing = [name for name in ("ANTHROPIC_API_KEY", "SAM_TOOL_URL") if not os.environ.get(name)]
    if missing:
        sys.exit(f"Set {' and '.join(missing)} first. See agent/README.md for the one-line command.")
    ids = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}

    sync_environment(ids)
    sync_vault(ids)
    for spec in MEMORY_STORES:
        sync_memory_store(spec, ids)

    helpers = [sync_agent(spec["key"], agent_body(spec, sync_skill(spec["skill"], ids)), ids) for spec in HELPERS]
    multiagent = {
        "type": "multiagent_20261001",
        "advisor": {"type": "disabled"},
        "subagents": {
            "type": "enabled",
            "inline_agents": {"type": "disabled"},
            "predefined_agents": [{"type": "agent", "id": agent["id"], "version": agent["version"]} for agent in helpers],
        },
        "workflows": {"type": "disabled"},
    }
    sam_server = {"type": "url", "name": SAM_SERVER, "url": os.environ["SAM_TOOL_URL"]}
    # MCP tools default to "always ask", which would leave an unattended run waiting forever.
    sam_tools = {"type": "mcp_toolset", "mcp_server_name": SAM_SERVER, "default_config": {"permission_policy": {"type": "always_allow"}}}
    operator_body = agent_body(OPERATOR, sync_skill(OPERATOR["skill"], ids), [sam_tools], multiagent, [sam_server])
    sync_agent(OPERATOR["key"], operator_body, ids)

    for agent in ids["agents"].values():
        print(f"{agent['name']:<22} {agent['id']}  version {agent['version']}")
    print(f"{'Environment':<22} {ids['environment']['id']}")
    print(f"{'Vault':<22} {ids['vault']['id']}")
    for store in ids["memory_stores"].values():
        print(f"{store['name']:<22} {store['id']}")


if __name__ == "__main__":
    main()
