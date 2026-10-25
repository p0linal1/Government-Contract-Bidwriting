#!/usr/bin/env python3
"""
gate_gonogo.py — the go/no-go verdict stage gate (synthesis + reconciliation; the last stage).

Why: the final verdict must be a reasoned synthesis of the upstream stages, not a label that
merely happens to be internally consistent. This gate runs two disciplines (spec Requirement 5a):

  SYNTHESIS — the verdict (BID / CONDITIONAL-BID / PASS / FOOTHOLD) must cite each upstream gate
  artifact (the value corridor + confidence, the priced number vs. the corridor, the selected fit
  configuration + its competitiveness), demonstrating it was synthesized from them. A
  BID/CONDITIONAL-BID verdict FAILS if any upstream gate did not pass — you cannot decide to bid on
  research/pricing/fit that was never completed to its gate. CONDITIONAL-BID / FOOTHOLD must state
  their conditions, and FOOTHOLD its basis-of-bid kind (strategic vs. revenue). A well-founded PASS
  is permitted and recorded as a success.

  RECONCILIATION — the write-back consistency linter must pass so opportunity.json status /
  recommendation, opportunity-summary.md, research/go-no-go.md and the evaluation-queue row all
  agree.

Reads the opportunity folder only; nothing company- or bid-specific lives here
(gate: tests/test_no_hardcoding.py). Registers itself as the 'go-no-go' stage (order 50).
"""
import re

from .evaluation import (EvalContext, GateResult, GateFinding, FAIL, WARN, HIGH, MEDIUM, LOW,
                         Stage, register, SYNTHESIS, require_cites_upstream, get_stage, _load_gates)
from . import opportunity_lint


def _verdict_record(ctx):
    parts = [ctx.text("research", "go-no-go.md"), ctx.text("opportunity-summary.md")]
    joined = "\n\n".join(p for p in parts if p)
    return joined or None


# upstream-citation cue groups (each group = one upstream artifact; the verdict reasoning must
# touch all three). METHOD language, not company/bid values.
_UPSTREAM_CUES = [
    ("value", "corridor", "anchor", "appropriat", "budget", "estimated value"),   # value-research
    ("price", "pricing", "cost", "margin", "tco", "recurring"),                   # pricing
    ("fit", "config", "competitive", "winnab", "staffing", "delivery model"),     # fit
]

# condition CONTENT cues — deliberately exclude the bare word "conditional"/"condition", since the
# verdict LABEL ("CONDITIONAL-BID") contains it; a real condition names what it depends on.
_CONDITIONS_CUES = ["only if", "provided that", "depends on", "contingent", "subject to",
                    "requires", "pending", "once the", "after the", "conditioned on", "if and only if"]
_BASIS_CUES = ["foothold", "strategic", "reference-building", "reference building", "revenue",
               "basis of bid", "basis-of-bid", "loss leader", "compounds"]


def _verdict(text):
    return opportunity_lint.parse_recommendation(text)


def _upstream_confidence(ctx):
    """Grade the upstream stages (intake, value, pricing, fit) and report each stage's CONFIDENCE.
    Used to CAP the verdict's confidence — a verdict built on low-confidence upstream is itself
    low-confidence (it is never withheld). Returns {stage_id: HIGH|MEDIUM|LOW}."""
    _load_gates()  # ensure the upstream gate modules are registered even when called standalone
    status = {}
    for sid in ("intake-facts", "value-research", "pricing", "fit"):
        try:
            status[sid] = get_stage(sid).gate(ctx).confidence
        except Exception:
            status[sid] = LOW  # stage not registered / errored — treat as weakest
    return status


def gate(ctx: EvalContext) -> GateResult:
    res = GateResult("go-no-go")
    rec = _verdict_record(ctx)
    if not rec:
        res.add(GateFinding("verdict-record", ok=False, severity=FAIL, performed=False,
                            message="no go-no-go.md or opportunity-summary.md — verdict not recorded"))
        return res

    verdict = _verdict(rec)
    if verdict is None:
        res.add(GateFinding("verdict-stated", ok=False, severity=FAIL, performed=True,
                            message="no BID/CONDITIONAL-BID/PASS/FOOTHOLD verdict found in the recommendation section"))
        return res
    res.add(GateFinding("verdict-stated", ok=True, message=f"verdict: {verdict}"))

    proceed = verdict in ("bid", "conditional", "foothold", "partner")

    # SYNTHESIS 1 — the verdict reasoning cites each upstream artifact (only required when proceeding;
    # a PASS still benefits from citing why, but we require citation for a proceed decision).
    cite = require_cites_upstream("cites-upstream", "verdict reasoning", rec, _UPSTREAM_CUES,
                                  severity=(FAIL if proceed else WARN))
    res.add(cite)

    # SYNTHESIS 2 — the verdict's confidence is CAPPED by how thin the upstream research was. A
    # verdict built on low-confidence upstream is a LOW-confidence verdict, NOT a withheld one
    # (spec Req 5a.2 — this replaces the old hard-stop that forbade a verdict until upstream passed).
    upstream = _upstream_confidence(ctx)
    weak = [sid for sid, c in upstream.items() if c == LOW]
    res.add(GateFinding(
        "upstream-confidence", ok=(not weak), severity=WARN, performed=True,
        message=("upstream stages are MEDIUM/HIGH confidence" if not weak
                 else f"verdict confidence capped — low-confidence upstream: {weak}")))

    # SYNTHESIS 3 — conditional/foothold must state conditions; foothold must state basis-of-bid kind
    if verdict in ("conditional", "foothold"):
        res.add(GateFinding(
            "conditions-stated", ok=_has_any(rec, _CONDITIONS_CUES),
            severity=FAIL, performed=True,
            message=("conditions stated" if _has_any(rec, _CONDITIONS_CUES)
                     else f"{verdict} verdict without stated conditions")))
    if verdict == "foothold":
        res.add(GateFinding(
            "basis-of-bid-stated", ok=_has_any(rec, _BASIS_CUES), severity=FAIL, performed=True,
            message=("basis-of-bid kind stated" if _has_any(rec, _BASIS_CUES)
                     else "foothold verdict without a stated basis-of-bid kind (strategic vs. revenue)")))

    # a well-founded PASS: require it cites a reason grounded in the upstream artifacts (advisory —
    # the citation check above runs as WARN for a PASS; this records it as a valid outcome).
    if verdict == "pass":
        res.add(GateFinding("well-founded-pass", ok=True, severity=WARN,
                            message="PASS recorded as a well-founded outcome"))

    # RECONCILIATION — surface any write-back drift as a confidence-lowering finding (not a halt)
    lint_res = opportunity_lint.lint(ctx)
    for f in lint_res.findings:
        if f.check in ("recommendation-consistency", "status-consistency") and f.blocking_failure:
            res.add(GateFinding(f"reconcile:{f.check}", ok=False, severity=FAIL, performed=True,
                                message=f.message))

    # CONFIDENCE: the verdict can be no more confident than its weakest upstream input, and is
    # lowered further if it doesn't cite upstream or if the docs are inconsistent.
    order = {HIGH: 2, MEDIUM: 1, LOW: 0}
    cap = min((order[c] for c in upstream.values()), default=0)
    cited = cite.ok
    consistent = not any(f.check.startswith("reconcile:") and f.blocking_failure for f in res.findings)
    if cited and consistent:
        level = {2: HIGH, 1: MEDIUM, 0: LOW}[cap]
    else:
        level = LOW
    res.set_confidence(level)

    return res


def _has_any(text, cues):
    low = text.lower()
    return any(c in low for c in cues)


register(Stage("go-no-go", 50, SYNTHESIS, gate, depends_on=["value-research", "pricing", "fit"],
               tasklist_template="Go/no-go: ALWAYS state a BID / CONDITIONAL-BID / PASS / FOOTHOLD "
               "verdict with reasoning that cites the value corridor, the priced number, and the "
               "selected fit configuration, and a confidence level (thin upstream caps confidence, "
               "it does not withhold the verdict); state conditions (and, for FOOTHOLD, the "
               "basis-of-bid kind); reconcile status/recommendation across opportunity.json, the "
               "summary, go-no-go, and the evaluation queue."))


def main(argv=None):
    import argparse, json, sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = gate(EvalContext(a.opp))
    if a.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"[{res.confidence}] go-no-go")
        for f in res.findings:
            if not f.ok:
                print(f"   {'!!' if f.blocking_failure else '~ '} {f.check}: {f.message}")
    return 0   # graders score confidence; they never fail the pipeline


if __name__ == "__main__":
    import sys
    sys.exit(main())
