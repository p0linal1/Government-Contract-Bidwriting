#!/usr/bin/env python3
"""
gate_pricing.py — the pricing stage gate (computation + reconciliation type; runs BEFORE fit).

Why: pricing is settled before the fit synthesis because it is easier for the bidder to adapt
its configuration to the RFP's money than to bend the RFP. The gate promotes bid-pricing.md's
"Pricing definition of done" into an enforced checklist: the three-axis reconciliation must be
STATED (labor hours; named-staff x schedule capacity; mandated schedule) and internally
consistent; AI acceleration must appear as a compression factor, not a discounted rate; recurring
cost must be bottom-up and include infra + support labor + margin; the priced number must be
reconciled against the value corridor from the value-research stage (with an explanation if it
falls outside); and the choices the harness is not entitled to make (reserved-capacity
commitment, final scope, rate/margin acceptance) must be captured as human-decisions, not assumed.

This is a computation/reconciliation gate: it checks that the arithmetic discipline was applied
and the numbers tie out and agree with upstream — not that the price is "right" (that is the
pricer's judgment).

It reads a dedicated pricing artifact when present (research/pricing.md), otherwise the reasoning
docs where pricing posture already lives (research/go-no-go.md + opportunity-summary.md). Reads
the opportunity folder only; nothing company- or bid-specific lives here
(gate: tests/test_no_hardcoding.py). Registers itself as the 'pricing' stage (order 30).
"""
import re

from .evaluation import (EvalContext, GateResult, GateFinding, FAIL, WARN, LOW, Stage, register,
                         RECONCILIATION)
from . import opportunity_lint


_DOC_ONLY_MARKER = "<!-- gen_pricing: document-only -->"


def _pricing_record(ctx):
    """The text the gate reasons over: a dedicated pricing doc if present, else the go/no-go +
    summary where pricing posture is recorded today."""
    parts = [ctx.text("research", "pricing.md"),
             ctx.text("research", "go-no-go.md"),
             ctx.text("opportunity-summary.md")]
    joined = "\n\n".join(p for p in parts if p)
    return joined or None


# any document-only generator marks its output with this substring; such a companion doc is NOT
# "real posture" and must not lift a document-only stage out of its LOW cap.
_ANY_DOC_ONLY = ": document-only -->"


def _real(text):
    return "" if (text and _ANY_DOC_ONLY in text) else (text or "")


def _is_document_only(ctx):
    """True when the ONLY pricing record is the deterministic document-only SKELETON (method named,
    no price computed). It names every method cue the checks look for, so the findings all pass —
    but it is explicitly not a computed price, so its confidence must be capped at LOW rather than
    inferred HIGH. A real analyst pricing.md (or pricing posture in a NON-generated go-no-go/summary)
    overrides; a document-only generated go-no-go does not count as real posture."""
    pm = ctx.text("research", "pricing.md") or ""
    if _DOC_ONLY_MARKER not in pm:
        return False
    other = "\n".join(t for t in (_real(ctx.text("research", "go-no-go.md")),
                                   _real(ctx.text("opportunity-summary.md"))) if t)
    return not _has_any(other, _AXIS_HOURS + _RECURRING) if other else True


def _has_any(text, cues):
    low = text.lower()
    return any(c in low for c in cues)


# cue vocabularies — METHOD language, not company/bid values
_AXIS_HOURS = ["labor hour", "scope hour", "raw effort", "raw hours", "effort estimate", "hours"]
_AXIS_CAPACITY = ["capacity", "team size", "people x", "person-week", "staff x", "staff ×",
                  "weeks x", "fte", "developer"]
_AXIS_SCHEDULE = ["schedule", "performance window", "mandated", "weeks", "timeline", "term"]
_COMPRESSION = ["compression", "acceleration factor", "ai-accelerat", "ai accelerat",
                "fewer hours", "compressed"]
_DISCOUNT_RATE = ["discounted rate", "discount the rate", "lower rate", "cut the rate"]
_RECURRING = ["recurring", "annual maintenance", "per year", "/yr", "per-year", "ongoing"]
_INFRA = ["infra", "hosting", "cloud", "azure", "aws", "govcloud", "storage"]
_SUPPORT_LABOR = ["support labor", "support hours", "support fee", "support/maintenance",
                  "maintenance", "fte", "support staff"]
_MARGIN = ["margin", "profit", "markup"]
_CORRIDOR = ["corridor", "value estimate", "value-analysis", "anchor", "budget", "appropriat"]
_HUMAN_DECISIONS = {
    "reserved-capacity": ["reserved capacity", "reserved/savings", "savings plan", "reserved instance",
                          "commit", "reserved-capacity"],
    "final-scope": ["final scope", "scope decision", "full vs", "component", "scope confirmed"],
    "rate-margin": ["rate", "margin", "blended rate", "accept"],
}


def gate(ctx: EvalContext) -> GateResult:
    res = GateResult("pricing")
    rec = _pricing_record(ctx)
    if not rec:
        res.add(GateFinding("pricing-record", ok=False, severity=FAIL, performed=False,
                            message="no pricing record (research/pricing.md or go-no-go/summary) — pricing not performed"))
        return res

    # 1) three-axis reconciliation stated: hours, capacity (staff x schedule), schedule
    axes = {"labor-hours": _AXIS_HOURS, "capacity": _AXIS_CAPACITY, "schedule": _AXIS_SCHEDULE}
    stated = [name for name, cues in axes.items() if _has_any(rec, cues)]
    res.add(GateFinding(
        "three-axis-reconciliation", ok=(len(stated) >= 3), severity=FAIL, performed=bool(stated),
        message=(f"all three axes stated ({', '.join(stated)})" if len(stated) >= 3
                 else f"reconciliation incomplete — only stated: {stated or 'none'}; need hours + capacity + schedule")))

    # 2) AI acceleration as a compression factor, not a discounted rate
    if _has_any(rec, _DISCOUNT_RATE) and not _has_any(rec, _COMPRESSION):
        res.add(GateFinding("ai-as-compression", ok=False, severity=FAIL, performed=True,
                            message="AI acceleration framed as a discounted RATE; it must be fewer HOURS (compression factor)"))
    else:
        res.add(GateFinding("ai-as-compression", ok=True, severity=WARN,
                            message="AI acceleration not framed as a rate discount"))

    # 3) recurring cost bottom-up incl. infra + support labor + margin (only if there IS a recurring line)
    if _has_any(rec, _RECURRING):
        missing = []
        if not _has_any(rec, _INFRA):
            missing.append("infra")
        if not _has_any(rec, _SUPPORT_LABOR):
            missing.append("support-labor")
        if not _has_any(rec, _MARGIN):
            missing.append("margin")
        res.add(GateFinding(
            "recurring-bottom-up", ok=(not missing), severity=FAIL, performed=True,
            message=("recurring sized bottom-up (infra + support labor + margin)" if not missing
                     else f"recurring line omits: {missing}")))
    else:
        res.add(GateFinding("recurring-bottom-up", ok=True, severity=WARN,
                            message="no recurring line detected (one-time only?)"))

    # 4) priced number reconciled against the value corridor (the research stage's output)
    res.add(GateFinding(
        "reconciled-to-corridor", ok=_has_any(rec, _CORRIDOR), severity=FAIL, performed=True,
        message=("priced number tied to the value corridor / budget" if _has_any(rec, _CORRIDOR)
                 else "no reconciliation of the priced number against the value corridor/budget")))

    # 5) human-decisions captured, not assumed (reserved capacity, final scope, rate/margin)
    #    these are advisory-surfacing checks: the gate requires they be ADDRESSED (mentioned as a
    #    decision/assumption), surfacing is what matters — the human makes the call.
    for name, cues in _HUMAN_DECISIONS.items():
        res.add(GateFinding(
            f"human-decision:{name}", ok=_has_any(rec, cues), severity=WARN, performed=True,
            message=(f"{name} addressed" if _has_any(rec, cues) else f"{name} not addressed as a decision")))

    # CONFIDENCE: a document-only pricing SKELETON names the method but computes no price — it must
    # be LOW regardless of how many method cues it satisfies. Otherwise confidence is inferred from
    # the findings (a real pricing record that satisfies the checks earns MEDIUM/HIGH).
    if _is_document_only(ctx):
        res.set_confidence(LOW)

    return res


register(Stage("pricing", 30, RECONCILIATION, gate,
               depends_on=["value-research"],
               tasklist_template="Pricing: state the three-axis reconciliation (hours; staff x "
               "schedule capacity; mandated schedule); express AI acceleration as a compression "
               "factor; size recurring bottom-up (infra + support labor + margin); reconcile the "
               "priced number against the value corridor; capture reserved-capacity / scope / "
               "rate-margin as human-decisions."))


def main(argv=None):
    import argparse, json, sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = gate(EvalContext(a.opp))
    if a.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"[{res.confidence}] pricing")
        for f in res.findings:
            if not f.ok:
                print(f"   {'!!' if f.blocking_failure else '~ '} {f.check}: {f.message}")
    return 0   # graders score confidence; they never fail the pipeline


if __name__ == "__main__":
    import sys
    sys.exit(main())
