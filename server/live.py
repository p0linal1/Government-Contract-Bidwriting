"""The bid agent's recent runs on Managed Agents, in plain English, for the app's Agent page.

A session is one run, and each agent in it works in its own thread. The page polls every few
seconds, so the whole answer is cached briefly, and anything finished is read once and kept.
"""

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

API = "https://api.anthropic.com/v1"
BETA = "managed-agents-2026-04-01"
IDS_FILE = Path(__file__).resolve().parent.parent / "agent" / "ids.json"
OPERATOR_ID = json.loads(IDS_FILE.read_text())["agents"]["operator"]["id"]

AGENTS = ["Operator", "Reader", "Qualifier", "Researcher", "Drafter"]
SESSION_COUNT = 5
STEP_COUNT = 8
CACHE_SECONDS = 4
EVENTS_PAGE_SIZE = 1000
MESSAGE_LENGTH = 140

SESSION_STATUS = {"running": "running", "rescheduling": "running", "idle": "finished", "terminated": "stopped"}
THREAD_STATUS = {"running": "working", "rescheduling": "working", "idle": "done", "terminated": "done"}

cache_lock = threading.Lock()
cached = {"at": float("-inf"), "answer": None}
# By session or thread id: (updated_at, what was read). Only for ones that have stopped.
finished_threads = {}
finished_steps = {}


def anthropic(path, beta=BETA):
    headers = {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "anthropic-beta": beta}
    with urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", headers=headers), timeout=30) as reply:
        return json.loads(reply.read())


def thread_events(session_id, thread_id):
    # Thread events come oldest first whatever the order asked for, so read them all.
    events, page = [], None
    while True:
        query = {"limit": EVENTS_PAGE_SIZE, **({"page": page} if page else {})}
        listing = anthropic(f"sessions/{session_id}/threads/{thread_id}/events?{urllib.parse.urlencode(query)}")
        events += listing["data"]
        page = listing.get("next_page")
        if not page or not listing["data"]:
            return events


def short_name(agent_name):
    return agent_name.removeprefix("Cadocary ")


def host(url):
    return (urlparse(url).hostname or "a web page").removeprefix("www.")


def file_name(path):
    return Path(path).name or "a file"


def what_file(path):
    if path.startswith("/workspace/skills/"):
        return "its skill"
    if path.startswith("/mnt/memory/cadocary-facts"):
        return "Cadocary's facts"
    if path.startswith("/mnt/memory/rfp-library"):
        return "the RFP Library"
    # Where Managed Agents puts a tool result too long to hand back at once.
    if file_name(path).startswith("repl-output-"):
        return "the rest of a long result"
    return file_name(path) if path else "the files"


def plural(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def describe_command(command):
    downloads = len(re.findall(r"https?://", command))
    if "pdftotext" in command:
        pdfs = set(re.findall(r"[\w.-]+\.pdf", command))
        return f"pulled the text out of {pdfs.pop()}" if len(pdfs) == 1 else "pulled the text out of the PDFs"
    if re.search(r"\b(curl|wget)\b", command) and downloads:
        return f"downloaded {plural(downloads, 'file')}"
    if re.search(r"\b(unzip|munpack)\b", command):
        return "unpacked the attachments"
    if re.search(r"\bpython", command):
        return "ran a script"
    if re.search(r"\b(grep|rg)\b", command):
        return "searched the documents"
    if re.search(r"\b(cat|head|tail|sed)\b", command):
        return "read part of the documents"
    if re.search(r"\b(ls|find)\b", command):
        return "listed the files"
    return "ran a command"


def describe_call(name, tool_input):
    """One tool call as what it was for, the way prototype/src/agent/session.js describes them."""
    match name:
        case "web_search":
            return f"searched: {tool_input.get('query', '')}"
        case "web_fetch":
            return f"opened {host(tool_input.get('url', ''))}"
        case "read":
            return f"read {what_file(tool_input.get('file_path', ''))}"
        case "write":
            return f"saved {file_name(tool_input.get('file_path', ''))}"
        case "edit":
            return f"edited {file_name(tool_input.get('file_path', ''))}"
        case "grep":
            where, pattern = what_file(tool_input.get("path", "")), tool_input.get("pattern", "")
            # A regular expression reads as noise, so only plain words are quoted.
            return f'searched {where} for "{pattern}"' if re.fullmatch(r"[\w '.-]{1,60}", pattern) else f"searched {where}"
        case "glob":
            return "listed the files"
        case "bash":
            return describe_command(tool_input.get("command", ""))
        case "search_opportunities":
            return "searched SAM.gov for open notices"
        case "get_notice":
            return "opened a SAM.gov notice"
        case _:
            return f"used {name}"


def first_line(content):
    text = "".join(block.get("text", "") for block in content)
    lines = [line.strip(" #*-") for line in re.sub(r"[*`]", "", text).splitlines() if line.strip(" #*-")]
    if not lines:
        return ""
    line = lines[0]
    return line if len(line) <= MESSAGE_LENGTH else line[: MESSAGE_LENGTH - 1].rsplit(" ", 1)[0] + "…"


def describe(agent, event):
    """One event as a step a person would follow, or None for bookkeeping."""
    kind = event["type"]
    if kind in ("agent.tool_use", "agent.mcp_tool_use"):
        text = f"{agent} {describe_call(event['name'], event['input'])}"
    elif kind == "agent.thread_message_sent":
        # Only the Operator's handoffs name the receiver. A helper's message always goes back to it.
        receiver = event.get("to_agent_name")
        text = f"{agent} handed the work to the {short_name(receiver)}" if receiver else f"{agent} reported back to the Operator"
    elif kind == "agent.message":
        line = first_line(event["content"])
        if not line:
            return None
        text = f"{agent}: {line}"
    else:
        return None
    return {"agent": agent, "text": text, "at": event["processed_at"]}


def session_threads(session):
    known = finished_threads.get(session["id"])
    if known and known[0] == session["updated_at"]:
        return known[1]
    threads = anthropic(f"sessions/{session['id']}/threads")["data"]
    if session["status"] not in ("running", "rescheduling"):
        finished_threads[session["id"]] = (session["updated_at"], threads)
    return threads


def thread_steps(session_id, thread):
    known = finished_steps.get(thread["id"])
    if known and known[0] == thread["updated_at"]:
        return known[1]
    agent = short_name(thread["agent"]["name"])
    steps = [step for event in thread_events(session_id, thread["id"]) if (step := describe(agent, event))]
    if thread["status"] not in ("running", "rescheduling"):
        finished_steps[thread["id"]] = (thread["updated_at"], steps)
    return steps


def latest_steps(session_id, threads):
    steps = [step for thread in threads for step in thread_steps(session_id, thread)]
    steps.sort(key=lambda step: step["at"], reverse=True)
    return steps[:STEP_COUNT]


def agent_statuses(session, threads):
    """Each agent's state: working, done, or not started. An agent working in any thread is working."""
    statuses = {name: "not started" for name in AGENTS}
    for thread in threads:
        name = short_name(thread["agent"]["name"])
        if name in statuses and statuses[name] != "working":
            statuses[name] = THREAD_STATUS.get(thread["status"], thread["status"])
    # The Operator's thread goes idle while it waits on a helper, but it is still running the run.
    if SESSION_STATUS.get(session["status"]) == "running":
        statuses["Operator"] = "working"
    return statuses


def summary(session, threads):
    usage = session["usage"]
    return {
        "id": session["id"],
        "title": session.get("title") or "Untitled run",
        "status": SESSION_STATUS.get(session["status"], session["status"]),
        "started_at": session["created_at"],
        "cost_usd": int(usage["list_cost"]["amount"]) / 100,
        "active_minutes": round(usage["active_seconds"] / 60, 1),
        "agents": agent_statuses(session, threads),
    }


def snapshot():
    """The Operator's latest sessions, newest first, and the newest session's last steps, newest first."""
    with cache_lock:
        if time.monotonic() - cached["at"] < CACHE_SECONDS:
            return cached["answer"]
        sessions = anthropic(f"sessions?{urllib.parse.urlencode({'limit': SESSION_COUNT, 'agent_id': OPERATOR_ID})}")["data"]
        threads = [session_threads(session) for session in sessions]
        answer = {
            "sessions": [summary(session, its_threads) for session, its_threads in zip(sessions, threads)],
            "steps": latest_steps(sessions[0]["id"], threads[0]) if sessions else [],
        }
        cached.update(at=time.monotonic(), answer=answer)
        return cached["answer"]
