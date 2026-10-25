#!/usr/bin/env python3
"""opportunity_intake_status.py — cross-reference opportunity folders against the inbox queue.

Produces a CSV of every opportunity folder on disk vs. what the email-intake poller
(bidkit.inbox) has filed into inbox/queue.jsonl. "Opened" = the poller has at least one
queue entry pointing at that folder (it was filed/ingested from an email). "Unopened" = the
folder exists but the poller has no entry for it (created by hand or portal, or its source
email doesn't match the router's solicitation-number keying).

Usage: python3 tools/opportunity_intake_status.py [--root <repo-root>] [--out <csv>]
Run from the repo root or pass --root.
"""
import argparse, csv, json, os, sys


def load_queue(queue_path):
    """message_id-level rows -> per-opportunity aggregate."""
    by_opp = {}
    if not os.path.exists(queue_path):
        return by_opp
    for line in open(queue_path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        opp = (d.get("opportunity") or "").replace("opportunities/", "").rstrip("/")
        if not opp:
            continue
        agg = by_opp.setdefault(opp, {"actions": [], "subjects": [], "froms": set(),
                                      "solicitation_number": None, "due_guess": None,
                                      "first_processed": None, "last_processed": None})
        agg["actions"].append(d.get("action"))
        if d.get("subject"):
            agg["subjects"].append(d["subject"])
        if d.get("from"):
            agg["froms"].add(d["from"])
        agg["solicitation_number"] = agg["solicitation_number"] or d.get("solicitation_number")
        agg["due_guess"] = agg["due_guess"] or d.get("due_guess")
        ts = d.get("processed_at")
        if ts:
            agg["first_processed"] = min(agg["first_processed"] or ts, ts)
            agg["last_processed"] = max(agg["last_processed"] or ts, ts)
    return by_opp


def folder_intake_done(root, opp):
    """Heuristic: intake produced an opportunity-summary.md for this folder."""
    return os.path.exists(os.path.join(root, "opportunities", opp, "opportunity-summary.md"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--out", default=None, help="CSV path (default: <root>/inbox/opportunity-intake-status.csv)")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    out = a.out or os.path.join(root, "inbox", "opportunity-intake-status.csv")

    opp_dir = os.path.join(root, "opportunities")
    folders = sorted(d for d in os.listdir(opp_dir)
                     if os.path.isdir(os.path.join(opp_dir, d))
                     and not d.startswith(".") and d not in ("_template", "sourcing"))
    queue = load_queue(os.path.join(root, "inbox", "queue.jsonl"))

    rows = []
    for opp in folders:
        q = queue.get(opp)
        opened = q is not None
        actions = q["actions"] if q else []
        rows.append({
            "opportunity": opp,
            "intake_status": "opened" if opened else "unopened",
            "in_inbox_queue": "yes" if opened else "no",
            "queue_messages": len(actions),
            "actions": ";".join(a for a in actions if a) if actions else "",
            "solicitation_number": (q or {}).get("solicitation_number") or "",
            "due_guess": (q or {}).get("due_guess") or "",
            "source_sender": ";".join(sorted((q or {}).get("froms", set()))) if q else "",
            "first_filed": (q or {}).get("first_processed") or "",
            "intake_summary_present": "yes" if folder_intake_done(root, opp) else "no",
        })

    # Queue entries whose folder is gone (shouldn't happen, but surface it if it does).
    for opp in sorted(set(queue) - set(folders)):
        rows.append({"opportunity": opp, "intake_status": "queued_folder_missing",
                     "in_inbox_queue": "yes", "queue_messages": len(queue[opp]["actions"]),
                     "actions": ";".join(a for a in queue[opp]["actions"] if a),
                     "solicitation_number": queue[opp].get("solicitation_number") or "",
                     "due_guess": queue[opp].get("due_guess") or "", "source_sender": "",
                     "first_filed": queue[opp].get("first_processed") or "", "intake_summary_present": "no"})

    cols = ["opportunity", "intake_status", "in_inbox_queue", "queue_messages", "actions",
            "solicitation_number", "due_guess", "source_sender", "first_filed", "intake_summary_present"]
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    opened = sum(1 for r in rows if r["intake_status"] == "opened")
    unopened = sum(1 for r in rows if r["intake_status"] == "unopened")
    print(f"wrote {out}")
    print(f"  {len(rows)} opportunity folder(s): {opened} opened (in queue), {unopened} unopened (not in queue)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
