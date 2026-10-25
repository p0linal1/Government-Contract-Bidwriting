#!/usr/bin/env python3
"""MCP server that exposes the SAM.gov research pipeline as tools.

The research agent works only through these tools, so it never needs a shell or file access:

  search_sam       pull SAM.gov for profile.json's codes and filter to what's open (fetch + filter)
  pending_notices  the open notices that still need a fit score
  save_scores      record fit scores for some of them
  render_report    validate all scores and write data/report.md + data/ranked.json
  read_report      return data/report.md

Each tool shells out to the matching script in scripts/, so the scripts stay the single source of
truth and keep working on their own. Stdlib only: speaks MCP's newline-delimited JSON-RPC over
stdio. Registered for Claude Code in .mcp.json.

Run by hand to smoke-test:  python3 scripts/mcp_server.py   (then type JSON-RPC lines)
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "search_sam",
        "description": (
            "Pull open SAM.gov opportunities for the NAICS/PSC codes in profile.json, then drop awarded, "
            "expired, cancelled and set-aside-ineligible notices. Takes ~10-30s. Returns counts and what "
            "was filtered out. Run this first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Only keep deadlines within this many days."},
                "include_no_deadline": {
                    "type": "boolean",
                    "description": "Also keep notices with no response date (often presolicitations).",
                },
            },
        },
    },
    {
        "name": "pending_notices",
        "description": (
            "List the open notices that still need a fit score (new, or amended since last scored), with "
            "title, type, deadline, agency, codes, set-aside and a plain-text description excerpt. Also "
            "returns profile.json's capabilities and exclusions to score against."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_scores",
        "description": (
            "Save fit scores for some pending notices. Call as often as you like; later scores for the same "
            "notice replace earlier ones. Returns how many notices still need a score."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "description": "Map of notice_id to {fit, verdict, reason}.",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "fit": {"type": "integer", "minimum": 0, "maximum": 100},
                            "verdict": {"type": "string", "enum": ["pursue", "consider", "skip"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["fit", "verdict", "reason"],
                    },
                }
            },
            "required": ["scores"],
        },
    },
    {
        "name": "render_report",
        "description": (
            "Validate that every open notice has a well-formed score, then write data/report.md and "
            "data/ranked.json. Returns the pursue/consider/skip counts, or the list of problems to fix."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_report",
        "description": "Return the latest data/report.md.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def run(script, *args):
    """Run one pipeline script from the repo root; return (ok, combined output)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def pending_count():
    ok, out = run("scores.py", "pending")
    return out.splitlines()[0] if ok and out else out


def tool_search_sam(args):
    ok, fetched = run("fetch_sam_opportunities.py", *(["--include-no-deadline"] if args.get("include_no_deadline") else []))
    if not ok:
        return False, f"SAM.gov fetch failed:\n{fetched}"
    extra = []
    if args.get("days") is not None:
        extra += ["--days", str(int(args["days"]))]
    if args.get("include_no_deadline"):
        extra.append("--include-no-deadline")
    ok, filtered = run("filter_open.py", *extra)
    return ok, f"{fetched}\n\n{filtered}"


def tool_pending_notices(args):
    profile_path = ROOT / "profile.json"
    if not profile_path.exists():
        return False, "No profile.json. Copy profile.example.json to profile.json and set your NAICS codes."
    if not (DATA / "open_opportunities.json").exists():
        return False, "No search results yet. Call search_sam first."
    profile = json.loads(profile_path.read_text())
    rubric = (
        "Score against this profile.\n"
        f"capabilities: {json.dumps(profile.get('capabilities') or [])}\n"
        f"exclusions: {json.dumps(profile.get('exclusions') or [])}\n\n"
    )
    ok, out = run("scores.py", "pending")
    return ok, rubric + out


def tool_save_scores(args):
    scores = args.get("scores")
    if not isinstance(scores, dict) or not scores:
        return False, "scores must be a non-empty object of notice_id -> {fit, verdict, reason}"
    DATA.mkdir(exist_ok=True)
    staged = DATA / "new_scores.json"
    staged.write_text(json.dumps({"scores": scores}, indent=2))
    ok, out = run("scores.py", "merge", str(staged))
    if not ok:
        return False, out
    return True, f"{out}\n{pending_count()}"


def tool_render_report(args):
    return run("render_report.py")


def tool_read_report(args):
    report = DATA / "report.md"
    if not report.exists():
        return False, "No report yet. Call render_report first."
    return True, report.read_text()


HANDLERS = {
    "search_sam": tool_search_sam,
    "pending_notices": tool_pending_notices,
    "save_scores": tool_save_scores,
    "render_report": tool_render_report,
    "read_report": tool_read_report,
}


def handle(message):
    method, params = message.get("method"), message.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sam-research", "version": "1.0.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        handler = HANDLERS.get(params.get("name"))
        if handler is None:
            raise LookupError(f"unknown tool {params.get('name')!r}")
        try:
            ok, text = handler(params.get("arguments") or {})
        except subprocess.TimeoutExpired:
            ok, text = False, "timed out after 15 minutes"
        return {"content": [{"type": "text", "text": text or "(no output)"}], "isError": not ok}
    raise LookupError(f"method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in message:  # notification, e.g. notifications/initialized
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": handle(message)}
        except LookupError as exc:
            reply = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": str(exc)}}
        except Exception as exc:  # keep the server alive for the next call
            reply = {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32603, "message": str(exc)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
