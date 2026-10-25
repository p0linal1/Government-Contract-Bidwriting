#!/usr/bin/env python3
"""
portfolio.py — one view of every live opportunity: stage reached, gate pass/fail, due, value,
recommendation; plus the X/Y/Z counts the daily digest reports.

Why: the harness needs a single, accurate picture of the pipeline — what stage each opportunity
has reached, which gates pass, how close the deadline is, the value anchor, and the current
recommendation — both for a human to read and to substantiate the digest email's "X added, Y
updated, Z passed go/no-go". This supersedes tools/opportunity_intake_status.py (which only
answered "did intake produce a summary"): the stage is computed from the artifacts actually on
disk, and the gate rollup comes from the real evaluation gates.

Stage ladder (computed from artifacts, spec Requirement 3.3):
  filed       — the folder exists
  researched  — research/value-analysis.md (or findings.md) present
  estimated   — opportunity.json value_estimate populated
  drafted      — a draft exists in the deliverables draft/quarantine location
  submitted   — a SUBMIT set exists
A terminal PASS (recommendation pass / status pass) is shown as 'passed'.

Counts for the digest:
  added    — opportunities first filed since the last run (inbox/queue.jsonl 'new' + watermark)
  updated  — opportunities with queue activity since the last run that were not first-filed then
  passed   — opportunities whose go/no-go recommendation is a proceed verdict (bid/conditional/foothold)

Nothing company- or bid-specific lives here; all values come from the opportunity folders and the
inbox state (gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.portfolio <opportunities-dir> [--format md|csv|json]
                              [--queue inbox/queue.jsonl] [--state inbox/portfolio-state.json]
                              [--counts] [--update-watermark]
"""
import argparse, csv, io, json, os, sys, datetime as dt

from .evaluation import EvalContext, EvaluationEngine, ordered_stages, _load_gates
from . import opportunity_lint

SKIP_DIRS = {"_template", "sourcing"}

PROCEED_VERDICTS = {"bid", "conditional", "foothold", "partner"}


# --------------------------------------------------------------------------- stage computation
def _has_real_content(path):
    """True if a directory holds files other than scaffolding placeholders (.gitkeep, .DS_Store)."""
    if not os.path.isdir(path):
        return False
    return any(not n.startswith(".") for n in os.listdir(path))


def compute_stage(ctx):
    """Lifecycle stage from artifacts on disk (not from a status field, which can lag)."""
    opp = ctx.opportunity() or {}
    # submitted? (a real file in the SUBMIT folder — not just a .gitkeep placeholder)
    folders = opp.get("folders") or {}
    submit = folders.get("submit", "SUBMIT")
    if _has_real_content(ctx.path(submit)):
        return "submitted"
    # drafted? (a draft/quarantine folder with real content)
    for cand in (folders.get("draft"), "proposed", folders.get("final"), "deliverables/bid/final"):
        if cand and _has_real_content(ctx.path(cand)):
            return "drafted"
    # estimated?
    if (opp.get("value_estimate") or {}):
        stage = "estimated"
    elif ctx.exists("research", "value-analysis.md") or ctx.exists("research", "findings.md"):
        stage = "researched"
    else:
        stage = "filed"
    return stage


def recommendation(ctx):
    rec = opportunity_lint.parse_recommendation(ctx.text("opportunity-summary.md")) \
        or opportunity_lint.parse_recommendation(ctx.text("research", "go-no-go.md"))
    if rec is None:
        opp = ctx.opportunity() or {}
        rec = opportunity_lint.parse_recommendation(opp.get("recommendation") or "")
    return rec


def _days_remaining(due):
    if not isinstance(due, dict) or not due.get("date"):
        return None
    try:
        d = dt.date.fromisoformat(due["date"][:10])
    except ValueError:
        return None
    return (d - dt.date.today()).days


# --------------------------------------------------------------------------- row
def build_row(opp_dir, run_gates=True):
    ctx = EvalContext(opp_dir)
    opp = ctx.opportunity() or {}
    due = opp.get("due") or {}
    ve = opp.get("value_estimate") or {}
    rec = recommendation(ctx)
    row = {
        "opportunity": ctx.id,
        "status": opp.get("status") or "",
        "source": (opp.get("source") or {}).get("type") or "",
        "due": due.get("date") or "",
        "due_confirmed": bool(due.get("confirmed")),
        "days_remaining": _days_remaining(due),
        "value_anchor": ve.get("anchor") or ve.get("likely") or "",
        "value_confidence": ve.get("confidence") or "",
        "recommendation": rec or "",
        "stage": compute_stage(ctx),
    }
    if run_gates:
        _load_gates()
        gate_summary, n_fail, first_fail = [], 0, None
        for s in ordered_stages():
            passed = s.gate(ctx).passed      # evaluate each gate exactly once
            gate_summary.append(f"{s.id}:{'P' if passed else 'F'}")
            if not passed:
                n_fail += 1
                if first_fail is None:
                    first_fail = s.id
        row["gates"] = " ".join(gate_summary)
        row["gates_failed"] = n_fail
        row["pipeline_at"] = first_fail or "complete"   # first failing gate, or complete
    return row


def build_portfolio(opps_dir, run_gates=True):
    rows = []
    for name in sorted(os.listdir(opps_dir)):
        p = os.path.join(opps_dir, name)
        if not os.path.isdir(p) or name.startswith(".") or name in SKIP_DIRS:
            continue
        if not os.path.exists(os.path.join(p, "opportunity.json")):
            continue
        try:
            rows.append(build_row(p, run_gates=run_gates))
        except Exception as e:  # noqa: BLE001 — one bad folder must not sink the whole view
            rows.append({"opportunity": name, "stage": "ERROR", "recommendation": "",
                         "error": str(e)})
    return rows


# --------------------------------------------------------------------------- counts (X/Y/Z)
def _load_queue(queue_path):
    """opportunity -> sorted list of processed_at timestamps + first action."""
    by_opp = {}
    if not queue_path or not os.path.exists(queue_path):
        return by_opp
    for line in open(queue_path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        opp = (d.get("opportunity") or "").replace("opportunities/", "").rstrip("/")
        if not opp:
            continue
        rec = by_opp.setdefault(opp, {"ts": [], "actions": []})
        if d.get("processed_at"):
            rec["ts"].append(d["processed_at"])
        rec["actions"].append(d.get("action"))
    return by_opp


def counts(rows, queue_path, state_path):
    """X added / Y updated / Z passed-go-no-go, relative to the watermark in state_path."""
    state = {}
    if state_path and os.path.exists(state_path):
        try:
            state = json.load(open(state_path, encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    watermark = state.get("last_run")  # ISO timestamp or None
    queue = _load_queue(queue_path)

    added, updated = [], []
    for opp, rec in queue.items():
        ts = sorted(rec["ts"])
        if not ts:
            continue
        first, last = ts[0], ts[-1]
        if watermark is None:
            # first ever run: everything filed counts as added
            added.append(opp)
        else:
            if first > watermark:
                added.append(opp)
            elif last > watermark:
                updated.append(opp)
    passed = [r["opportunity"] for r in rows
              if (r.get("recommendation") in PROCEED_VERDICTS)]
    return {"added": sorted(set(added)), "updated": sorted(set(updated)), "passed": sorted(set(passed))}


def update_watermark(state_path, when=None):
    when = when or dt.datetime.now(dt.timezone.utc).isoformat()
    state = {}
    if os.path.exists(state_path):
        try:
            state = json.load(open(state_path, encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state["last_run"] = when
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    return when


# --------------------------------------------------------------------------- renderers
_COLS = ["opportunity", "stage", "pipeline_at", "gates_failed", "status", "recommendation",
         "due", "due_confirmed", "days_remaining", "value_anchor", "value_confidence", "source"]


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_COLS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def to_json(rows):
    return json.dumps(rows, indent=2)


def to_markdown(rows):
    hdr = ["Opportunity", "Stage", "Pipeline at", "Gates✗", "Rec", "Due", "Days", "Value", "Conf"]
    out = ["| " + " | ".join(hdr) + " |", "|" + "|".join(["---"] * len(hdr)) + "|"]
    for r in rows:
        val = r.get("value_anchor")
        val_s = f"${int(val):,}" if isinstance(val, (int, float)) and val else ""
        dr = r.get("days_remaining")
        dr_s = "" if dr is None else str(dr)
        due_s = (r.get("due") or "") + ("" if r.get("due_confirmed") else " (?)")
        out.append("| " + " | ".join([
            r.get("opportunity", ""), r.get("stage", ""), str(r.get("pipeline_at", "")),
            str(r.get("gates_failed", "")), r.get("recommendation", ""), due_s.strip(), dr_s,
            val_s, r.get("value_confidence", "")]) + " |")
    return "\n".join(out)


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opps_dir", help="the opportunities/ directory")
    ap.add_argument("--format", choices=["md", "csv", "json"], default="md")
    ap.add_argument("--queue", default=None, help="inbox/queue.jsonl (for counts)")
    ap.add_argument("--state", default=None, help="inbox/portfolio-state.json (watermark)")
    ap.add_argument("--counts", action="store_true", help="also print X/Y/Z counts")
    ap.add_argument("--no-gates", action="store_true", help="skip gate evaluation (faster)")
    ap.add_argument("--update-watermark", action="store_true", help="set last_run to now")
    a = ap.parse_args(argv)

    rows = build_portfolio(a.opps_dir, run_gates=not a.no_gates)
    if a.format == "csv":
        print(to_csv(rows))
    elif a.format == "json":
        print(to_json(rows))
    else:
        print(to_markdown(rows))

    if a.counts:
        c = counts(rows, a.queue, a.state)
        print(f"\nadded={len(c['added'])} updated={len(c['updated'])} passed-go-no-go={len(c['passed'])}")

    if a.update_watermark and a.state:
        when = update_watermark(a.state)
        print(f"watermark set to {when}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
