"""Run the bid agent on one stored RFP: one session, its documents attached, its findings saved after.

    python3 agent/run.py <rfp-id> [--steps read,qualify | all] [--budget-usd 40]

The RFP must be in the library already (`python3 agent/library.py sync`). Needs ANTHROPIC_API_KEY,
SAM_TOOL_URL, and SAM_TOOL_TOKEN; agent/README.md has the one-line command that reads them from
Secret Manager.
"""

import argparse
import json
import sys
import time
import urllib.parse

from library import IDS_FILE, anthropic, fetch_documents, require_environment, save_findings, start_run

STEPS = ["read", "qualify", "research", "draft"]
POLL_SECONDS = 30
# Output files can reach the Files API a few seconds after the session goes idle.
OUTPUT_DELAY_SECONDS = 15


def parse_steps(text):
    if text == "all":
        return STEPS
    steps = text.split(",")
    unknown = [step for step in steps if step not in STEPS]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown step {', '.join(unknown)}; choose from {', '.join(STEPS)}, or all")
    return [step for step in STEPS if step in steps]


def uploads_folder(rfp_id):
    return f"/mnt/session/uploads/{rfp_id}/"


def findings_folder(rfp_id):
    # Kept apart from the documents folder, which the Reader reads in full.
    return f"/mnt/session/uploads/findings/{rfp_id}/"


def large_findings(record):
    """The latest copy of each earlier finding that was too big for a memory, by name."""
    return {finding["name"]: finding for finding in record["findings"] if finding.get("file_id")}


def starting_message(record, steps):
    rfp_id = record["rfp_id"]
    attached = [document for document in record["documents"] if document["file_id"]]
    missing = [document for document in record["documents"] if not document["file_id"]]
    lines = [
        f'RFP {rfp_id}: {record["agency"]}, "{record["title"]}", solicitation {record["solicitation_number"]}.',
        f"SAM.gov notice {rfp_id} ({record['sam_url']}). Proposal deadline on SAM.gov: {record['deadline']}.",
        f"Use {rfp_id} as the rfp id, so this RFP's outputs go in /mnt/session/outputs/{rfp_id}/.",
        "",
        f"Its documents are attached under {uploads_folder(rfp_id)}. Have the Reader read them there:",
        *[f"- {document['name']}" for document in attached],
    ]
    if missing:
        lines += ["", "These could not be attached, so send the Reader their links instead:"]
        lines += [f"- {document['name']}: {document['url']}" for document in missing]
    lines += ["", f"Its library record is /mnt/memory/rfp-library/rfps/{rfp_id}/record.json."]
    if record["findings"]:
        lines.append(f"Findings from earlier runs are in /mnt/memory/rfp-library/rfps/{rfp_id}/findings/.")
    if large_findings(record):
        lines.append(f"Earlier findings too big for the library are attached under {findings_folder(rfp_id)}: {', '.join(large_findings(record))}.")
    lines.append("")
    if steps == STEPS:
        lines.append("Run every step for this RFP, from reading to the packet.")
    else:
        lines.append(f"Run only these steps: {', '.join(steps)}. Then stop and give your final summary.")
    return "\n".join(lines)


def create_session(ids, record, steps, budget_usd):
    rfp_id = record["rfp_id"]
    operator = ids["agents"]["operator"]
    stores = [
        {"type": "memory_store", "memory_store_id": store["id"], "access": "read_only"}
        for store in ids["memory_stores"].values()
    ]
    # mount_path is rooted at /mnt/session/uploads/.
    files = [
        {"type": "file", "file_id": document["file_id"], "mount_path": f"/{rfp_id}/{document['name']}"}
        for document in record["documents"]
        if document["file_id"]
    ]
    files += [
        {"type": "file", "file_id": finding["file_id"], "mount_path": f"/findings/{rfp_id}/{name}"}
        for name, finding in large_findings(record).items()
    ]
    return anthropic("POST", "sessions", {
        "agent": {"type": "agent", "id": operator["id"], "version": operator["version"]},
        "environment_id": ids["environment"]["id"],
        "vault_ids": [ids["vault"]["id"]],
        "title": f"{record['title']} ({', '.join(steps)})",
        "metadata": {"rfp_id": rfp_id, "steps": ",".join(steps)},
        "resources": stores + files,
        "budget": {"type": "limit", "max_list_cost": {"amount": str(round(budget_usd * 100)), "currency": "USD"}},
        "initial_events": [{"type": "user.message", "content": [{"type": "text", "text": starting_message(record, steps)}]}],
    })


def dollars(session):
    return int(session["usage"]["list_cost"]["amount"]) / 100


def wait_until_idle(session_id):
    """Poll until the session stops. It stays running while any helper agent is still working."""
    started = time.monotonic()
    while True:
        session = anthropic("GET", f"sessions/{session_id}")
        if session["status"] in ("idle", "terminated"):
            return session
        minutes = (time.monotonic() - started) / 60
        print(f"  {session['status']}, {minutes:.0f} min, ${dollars(session):.2f} so far", flush=True)
        time.sleep(POLL_SECONDS)


def final_events(session_id):
    """The Operator's last message and why the session stopped, read from the newest event back."""
    message = stop_reason = page = None
    while message is None or stop_reason is None:
        query = {"order": "desc", "limit": 100, **({"page": page} if page else {})}
        listing = anthropic("GET", f"sessions/{session_id}/events?{urllib.parse.urlencode(query)}")
        for event in listing["data"]:
            if stop_reason is None and event["type"] == "session.status_idle":
                stop_reason = event["stop_reason"]["type"]
            # Helper agents' messages carry a thread id; the Operator's do not.
            if message is None and event["type"] == "agent.message" and not event.get("session_thread_id"):
                message = "".join(block.get("text", "") for block in event["content"])
        page = listing.get("next_page")
        if not page:
            break
    return message, stop_reason


def main():
    parser = argparse.ArgumentParser(description="Run the bid agent on one stored RFP.")
    parser.add_argument("rfp_id", help="the RFP's SAM.gov notice id")
    parser.add_argument("--steps", type=parse_steps, default=STEPS, help="comma-separated steps from read,qualify,research,draft, or all (the default)")
    parser.add_argument("--budget-usd", type=float, default=40, help="the session's spending cap in dollars (default 40)")
    args = parser.parse_args()
    require_environment("ANTHROPIC_API_KEY", "SAM_TOOL_URL", "SAM_TOOL_TOKEN")
    ids = json.loads(IDS_FILE.read_text())

    record = fetch_documents(args.rfp_id)
    unsaved = [run for run in record["runs"] if "saved_at" not in run]
    if unsaved:
        session_id = unsaved[-1]["session_id"]
        sys.exit(
            f"Session {session_id} on this RFP hasn't been saved, so it may still be running. "
            f"Once it has finished, run: python3 agent/library.py save-findings {session_id} {args.rfp_id}"
        )
    session = create_session(ids, record, args.steps, args.budget_usd)
    start_run(record, session["id"], args.steps)
    print(f"Session {session['id']} started on {args.rfp_id}: {', '.join(args.steps)}, budget ${args.budget_usd:.2f}.")
    print(f"If this script stops, the session keeps going. Save it later with: python3 agent/library.py save-findings {session['id']} {args.rfp_id}")

    started = time.monotonic()
    session = wait_until_idle(session["id"])
    elapsed = (time.monotonic() - started) / 60
    message, stop_reason = final_events(session["id"])
    print(f"\nSession {session['status']} ({stop_reason or 'no stop reason'}).")
    print(f"Cost ${dollars(session):.2f} at list price, {session['usage']['active_seconds'] / 60:.1f} active minutes, {elapsed:.1f} minutes start to finish.")
    print("\nFinal message from the Operator:\n")
    print(message or "(no message)")
    print()

    time.sleep(OUTPUT_DELAY_SECONDS)
    save_findings(session["id"], args.rfp_id)


if __name__ == "__main__":
    main()
