#!/usr/bin/env python3
"""
gate_value.py — the value-research stage gate (research type; the highest-ROI gate).

Why: contract-value research is the single highest-leverage step in an evaluation. On the
calibration bid, a web search that surfaced the incumbent's prior contract moved an about-to-be
~$1M bid to a confident ~$5M bid. This gate makes that depth MANDATORY and VERIFIED rather than
lucky: it FAILS unless the four independent value lines were each ATTEMPTED (with a sourced
figure or an explicit UNKNOWN-with-reason) and the incumbent prior-contract hunt was RUN with its
outcome recorded — distinguishing "searched and found nothing" from "never searched" (spec
Requirement 2.3, 3). It also refuses a HIGH-confidence claim that lacks a real anchor, and
requires the written estimate to agree with the canonical opportunity.json (via the consistency
linter).

The gate reads the STATED research record (research/value-analysis.md) + opportunity.json
value_estimate. It verifies the process was performed and sourced; it does NOT re-derive the
estimate (that is the analyst's judgment — gates verify, they do not replace the analyst).

Reads the opportunity folder only; nothing company- or bid-specific lives here
(gate: tests/test_no_hardcoding.py). Registers itself as the 'value-research' stage.
"""
import re

from .evaluation import (EvalContext, GateResult, GateFinding, FAIL, WARN, HIGH, MEDIUM, LOW,
                         require_attempted, distinct_notrun_vs_empty, Stage, register, RESEARCH)
from . import opportunity_lint

# The four independent value lines (spec Requirement 3.1). Each is detected by any of its cue
# phrases so the gate is robust to wording ("Line 1 — Buyer affordability", "## Affordability",
# "the buyer's audited financials", …). These are METHOD names, not company/bid values.
VALUE_LINES = {
    "affordability": ["affordab", "audited financ", "adopted budget", "appropriat",
                      "can the buyer afford", "buyer's own money", "cip ", "capital improvement"],
    "procurement-thresholds": ["procurement threshold", "purchasing policy", "board-approval",
                               "board approval", "quote-vs", "simplified acquisition", "value floor"],
    "comparable-awards": ["comparable", "unit-rate", "unit rate", "per-student", "per-seat",
                          "per-bed", "per-capita", "other agencies", "price list"],
    "cost-to-deliver": ["cost-to-deliver", "cost to deliver", "bottom-up", "bottom up",
                        "blended rate", "capacity hours", "tco"],
}

INCUMBENT_CUES = ["incumbent", "current vendor", "current contract", "prior contract",
                  "prior award", "predecessor contract", "existing contract", "current system"]


def _sections(text):
    """Split a value-analysis doc into (heading, body) blocks on markdown headers, so each line's
    presence can be judged on its own section rather than the whole doc."""
    if not text:
        return []
    parts = re.split(r"(?m)^(#{1,6}\s+.*)$", text)
    # parts = [pre, head1, body1, head2, body2, ...]
    blocks = []
    pre = parts[0]
    if pre.strip():
        blocks.append(("", pre))
    for i in range(1, len(parts), 2):
        head = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        blocks.append((head, head + "\n" + body))
    return blocks


def _line_blob(text, cues):
    """Return the text of the section(s) that discuss a given value line, or None if the line is
    not addressed anywhere in the doc."""
    hits = []
    for head, block in _sections(text):
        low = block.lower()
        if any(c in low for c in cues):
            hits.append(block)
    if not hits:
        # also check the whole doc in case it isn't sectioned
        low = (text or "").lower()
        if any(c in low for c in cues):
            return text
        return None
    return "\n".join(hits)


def _confidence(text):
    m = re.search(r"confidence[^\n:]*:?\s*\*{0,2}\s*(HIGH|MEDIUM[-\s]?HIGH|MEDIUM|LOW)", text or "", re.I)
    return m.group(1).upper().replace(" ", "-") if m else None


def _line_substantiated(blob):
    """True when a value line's section carries ACTUAL research — a dollar figure or a citation —
    rather than only an honest 'UNKNOWN — not derivable / needs the agent-runner pass' placeholder.
    Used only for confidence scoring (MEDIUM needs substantiated lines); the UNKNOWN placeholder is
    still a valid, non-penalised 'performed and recorded' outcome for the provenance findings."""
    if not blob or not blob.strip():
        return False
    low = blob.lower()
    # a line that is wholly an UNKNOWN placeholder is honest but not researched
    if "unknown" in low and not re.search(r"https?://|\.pdf", low):
        # no citation; if it also has no concrete currency figure, it's just a placeholder
        if not re.search(r"\$\s?[0-9]|\b[0-9][0-9,.]*\s*[kmb]\b", low):
            return False
    return True


# "no incumbent" / greenfield cues: when present, the hunt ran and concluded there is no prior
# contract — a valid performed-and-found-nothing outcome, NOT a found anchor.
_NO_INCUMBENT_CUES = ["greenfield", "no incumbent", "no unified", "no prior", "n/a — no",
                      "n/a - no", "no public record", "none found", "not found", "no entrenched"]

# A contract dollar figure for the incumbent must carry a currency marker ($ or a k/M/B suffix) —
# a bare 4-5 digit integer in incumbent prose is usually a year or an RFP number, not an award.
_CURRENCY_AMOUNT_RE = re.compile(r"\$\s?[0-9][0-9,]*(?:\.[0-9]+)?\s*[kmb]?|\b[0-9][0-9,.]*\s*[kmb]\b", re.I)


def _incumbent_amounts(blob):
    """Dollar amounts in the incumbent discussion that carry a currency marker."""
    out = []
    for m in _CURRENCY_AMOUNT_RE.finditer(blob or ""):
        v = opportunity_lint.parse_money(m.group(0))
        if v:
            out.append(v)
    return out


def _incumbent_found(text):
    """True only if the incumbent discussion names a concrete prior award (a currency-marked dollar
    figure with a citation) AND does not conclude greenfield/none. 'No incumbent found' is a valid
    outcome, not a found anchor."""
    blob = _line_blob(text, INCUMBENT_CUES)
    if not blob:
        return False
    low = blob.lower()
    if any(c in low for c in _NO_INCUMBENT_CUES):
        return False
    return bool(_incumbent_amounts(blob)) and bool(re.search(r"https?://|\.pdf|council|packet|legistar", blob, re.I))


def gate(ctx: EvalContext) -> GateResult:
    res = GateResult("value-research")
    va = ctx.text("research", "value-analysis.md")
    findings = ctx.text("research", "findings.md")
    opp = ctx.opportunity()

    # The research record may live in value-analysis.md (the dedicated triangulation doc) and/or
    # findings.md (the research-plan log where the incumbent hunt and per-line results are first
    # recorded). Read both: a strong, well-sourced finding in findings.md is still "performed".
    record = "\n\n".join(t for t in (va, findings) if t)

    if not record:
        res.add(GateFinding("value-analysis-present", ok=False, severity=FAIL, performed=False,
                            message="no research/value-analysis.md or findings.md — value research not performed"))
        return res
    va = record

    # 1) each of the four lines was attempted. Three are EXTERNAL-DISCOVERY lines (affordability,
    #    procurement thresholds, comparable awards) that must show the search ran — a sourced figure
    #    or an explicit UNKNOWN-with-reason, never a bare blank. The fourth, cost-to-deliver, is an
    #    INTERNAL computation (the bidder's own bottom-up build/run estimate): it legitimately has
    #    no external URL, so it only needs to show the method was performed with a recorded outcome.
    for line_id, cues in VALUE_LINES.items():
        blob = _line_blob(va, cues)
        if line_id == "cost-to-deliver":
            res.add(require_attempted(f"line:{line_id}", f"value line '{line_id}'", blob))
        else:
            res.add(distinct_notrun_vs_empty(f"line:{line_id}", f"value line '{line_id}'", blob))

    # 2) the incumbent prior-contract hunt was RUN (outcome recorded, not blank) — the Req 2.3 check
    inc_blob = _line_blob(va, INCUMBENT_CUES)
    res.add(distinct_notrun_vs_empty("incumbent-search", "incumbent prior-contract hunt", inc_blob))

    # 3) convergence + confidence stated
    conf = _confidence(va)
    if conf is None:
        res.add(GateFinding("confidence-stated", ok=False, severity=FAIL, performed=True,
                            message="no overall confidence grade stated"))
    else:
        res.add(GateFinding("confidence-stated", ok=True, message=f"confidence: {conf}"))

    # 4) HIGH confidence requires a real anchor (incumbent prior $ OR an appropriation with a source)
    if conf == "HIGH":
        anchored = _incumbent_found(va)
        if not anchored and opp and "value_estimate" in opp:
            ve = opp["value_estimate"]
            anchored = bool(ve.get("anchor") and ve.get("anchor_source"))
        res.add(GateFinding(
            "high-confidence-anchor", ok=bool(anchored),
            severity=FAIL, performed=True,
            message=("HIGH confidence backed by a real anchor" if anchored
                     else "HIGH confidence claimed without an incumbent prior-$ or sourced appropriation anchor "
                          "(reserve HIGH for a hard anchor; otherwise MEDIUM/LOW)")))

    # 5) when an incumbent prior $ was found, the written estimate headline must be consistent with it
    if _incumbent_found(va) and opp and "value_estimate" in opp:
        inc_vals = _incumbent_amounts(_line_blob(va, INCUMBENT_CUES))
        headline = opp["value_estimate"].get("anchor") or opp["value_estimate"].get("likely")
        if inc_vals and headline:
            near = any(opportunity_lint._tol(int(headline), v, frac=0.5) for v in inc_vals)
            res.add(GateFinding(
                "incumbent-anchor-consistency", ok=bool(near), severity=FAIL, performed=True,
                message=("estimate headline is consistent with the incumbent prior $" if near
                         else f"estimate headline {int(headline):,} is far from the incumbent prior $ {inc_vals}")))

    # 6) the estimate was written back and the canonical/derived docs agree (reconciliation)
    lint_res = opportunity_lint.lint(ctx)
    for f in lint_res.findings:
        if f.check in ("value-consistency", "value-anchor-provenance") and not f.ok:
            res.add(GateFinding(f"writeback:{f.check}", ok=False, severity=FAIL, performed=True,
                                message=f.message))
    if opp and "value_estimate" not in opp:
        res.add(GateFinding("value-written-back", ok=False, severity=FAIL, performed=True,
                            message="estimate not written to opportunity.json value_estimate"))

    # CONFIDENCE (the grader's real job now — it scores, it does not block). HIGH only with a hard
    # anchor; MEDIUM when the lines were genuinely RESEARCHED (a figure or a citation), no hard
    # anchor; LOW when the research is thin/absent or the write-back is inconsistent. A line that is
    # only an honest "UNKNOWN — needs the agent-runner pass" (what the document-only generator
    # emits) is NOT a researched line: it keeps the stage at LOW, which is the correct, honest score
    # for a document-only estimate. A missing value-analysis = LOW, not a halt.
    lines_recorded = sum(1 for line_id in VALUE_LINES
                         if _line_substantiated(_line_blob(va, VALUE_LINES[line_id])))
    has_anchor = _incumbent_found(va) or bool(
        opp and (opp.get("value_estimate") or {}).get("anchor")
        and (opp.get("value_estimate") or {}).get("anchor_source"))
    writeback_ok = not any(f.check.startswith("writeback:") or f.check == "value-written-back"
                           for f in res.findings if f.blocking_failure)
    if has_anchor and conf == "HIGH" and writeback_ok:
        res.set_confidence(HIGH)
    elif lines_recorded >= 3 and writeback_ok:
        res.set_confidence(MEDIUM)
    else:
        res.set_confidence(LOW)

    return res


register(Stage("value-research", 20, RESEARCH, gate,
               tasklist_template="Value research: run the four lines (affordability, procurement "
               "thresholds, comparable awards+proxy, bottom-up cost-to-deliver) and the incumbent "
               "prior-contract hunt; source every number or mark UNKNOWN-with-reason; state "
               "convergence + confidence; write value_estimate back to opportunity.json."))


def main(argv=None):
    import argparse, json, sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = gate(EvalContext(a.opp))
    if a.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"[{res.confidence}] value-research")
        for f in res.findings:
            if not f.ok:
                print(f"   {'!!' if f.blocking_failure else '~ '} {f.check}: {f.message}")
    return 0   # graders score confidence; they never fail the pipeline


if __name__ == "__main__":
    import sys
    sys.exit(main())
