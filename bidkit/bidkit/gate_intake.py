#!/usr/bin/env python3
"""
gate_intake.py — the intake-&-facts stage gate (research/extraction type; the first stage).

Why: everything downstream (value, pricing, fit, go/no-go) assumes the basic facts are CONFIRMED
from the RFP, not left as the poller's DETECTED guesses. bidkit.brief labels every date/format
rule as a detection with `confirmed: false`; the human/agent intake step must confirm them from
the solicitation text and apply any addenda (which often move the deadline). This gate FAILS
unless the load-bearing facts were actually confirmed with a source and the referenced
attachments are present in rfp/ — so a downstream stage never builds on an unconfirmed guess.

It is a research/extraction gate: the facts exist in the RFP document; the gate checks they were
read and recorded with provenance, not fabricated or left as a guess.

Reads the opportunity folder only; nothing company- or bid-specific lives here
(gate: tests/test_no_hardcoding.py). Registers itself as the 'intake-facts' stage (order 10).
"""
import re

from .evaluation import (EvalContext, GateResult, GateFinding, FAIL, WARN, Stage, register, RESEARCH)


def _confirmed_with_source(block):
    """A date-ish block is 'confirmed with a source' if confirmed is truthy AND a non-empty
    source string is present."""
    if not isinstance(block, dict):
        return (False, False)
    return (bool(block.get("confirmed")), bool(block.get("source")))


def gate(ctx: EvalContext) -> GateResult:
    res = GateResult("intake-facts")
    opp = ctx.opportunity()

    if not opp:
        res.add(GateFinding("opportunity-json", ok=False, severity=FAIL, performed=False,
                            message="opportunity.json missing — intake not performed"))
        return res

    # 1) the submission deadline is confirmed from the RFP, with a source (not a DETECTED guess)
    due = opp.get("due")
    if not isinstance(due, dict) or not due:
        res.add(GateFinding("due-confirmed", ok=False, severity=FAIL, performed=False,
                            message="no due date recorded"))
    else:
        confirmed, sourced = _confirmed_with_source(due)
        if confirmed and sourced:
            res.add(GateFinding("due-confirmed", ok=True,
                                message=f"due confirmed: {due.get('date')} ({due.get('source','')[:50]})"))
        elif confirmed and not sourced:
            res.add(GateFinding("due-confirmed", ok=False, severity=FAIL, performed=True,
                                message="due.confirmed=true but no due.source"))
        else:
            res.add(GateFinding("due-confirmed", ok=False, severity=FAIL, performed=True,
                                message="due date still a DETECTED guess (confirmed=false) — confirm from the RFP and apply addenda"))

    # 2) format rules were copied from the RFP, not left as the tool's detection
    fmt = opp.get("format")
    if not isinstance(fmt, dict) or not fmt:
        res.add(GateFinding("format-confirmed", ok=False, severity=FAIL, performed=False,
                            message="no format block recorded"))
    elif "format_detected" in opp and "format" not in opp:
        res.add(GateFinding("format-confirmed", ok=False, severity=FAIL, performed=True,
                            message="only format_detected present — copy confirmed rules into 'format'"))
    else:
        # page_limit of null is acceptable (some RFPs set none); the block existing + populated is the check
        populated = any(fmt.get(k) is not None for k in ("page_limit", "min_font_pt", "page_size", "font_family_allow"))
        res.add(GateFinding("format-confirmed", ok=bool(populated),
                            severity=FAIL, performed=True,
                            message=("format rules recorded" if populated
                                     else "format block present but empty — record the RFP's rules")))

    # 3) a buyer contact is recorded (who to ask / submit to)
    contact = opp.get("contact") or (opp.get("portal_record") or {}).get("contact")
    res.add(GateFinding("contact-recorded", ok=bool(contact), severity=WARN,
                        performed=bool(contact),
                        message=("contact recorded" if contact else "no buyer contact recorded")))

    # 4) referenced attachments are present in rfp/ — a research-coverage check. We look at the
    #    portal record's document list (the authoritative 'what was posted') when present.
    pr = ctx.json("rfp", "portal-record.json")
    rec = (pr[0] if isinstance(pr, list) and pr else pr) if pr else None
    present = set(ctx.rfp_files())
    if rec and (rec.get("documents") or rec.get("amendments")):
        named = [d.get("name") for d in list(rec.get("documents") or []) + list(rec.get("amendments") or [])
                 if d.get("name")]
        missing = [n for n in named if n not in present and n.replace("'", "_") not in present]
        if missing:
            res.add(GateFinding("attachments-present", ok=False, severity=FAIL, performed=True,
                                message=f"{len(missing)} posted document(s) not in rfp/: {missing[:3]}"))
        else:
            res.add(GateFinding("attachments-present", ok=True,
                                message=f"all {len(named)} posted documents present in rfp/"))
    else:
        # no portal record to reconcile against — at least some RFP material should be on file
        res.add(GateFinding("attachments-present", ok=bool(present), severity=WARN,
                            performed=bool(present),
                            message=(f"{len(present)} file(s) in rfp/ (no portal record to reconcile)"
                                     if present else "rfp/ is empty — fetch the solicitation documents")))

    return res


register(Stage("intake-facts", 10, RESEARCH, gate,
               tasklist_template="Intake: confirm the deadline and format rules from the RFP text "
               "(not the DETECTED guesses), apply all addenda, record the buyer contact, and "
               "fetch every posted document/amendment into rfp/."))


def main(argv=None):
    import argparse, json, sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = gate(EvalContext(a.opp))
    if a.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"[{res.confidence}] intake-facts")
        for f in res.findings:
            if not f.ok:
                print(f"   {'!!' if f.blocking_failure else '~ '} {f.check}: {f.message}")
    return 0   # graders score confidence; they never fail the pipeline


if __name__ == "__main__":
    import sys
    sys.exit(main())
