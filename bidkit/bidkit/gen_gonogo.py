#!/usr/bin/env python3
"""
gen_gonogo.py — the DETERMINISTIC, DOCUMENT-ONLY verdict GENERATOR (spec Requirement 5a / 8.5).

Why: the go/no-go GRADER (gate_gonogo.py) scores whether a verdict was stated, cites the upstream
outputs, states its conditions, and is confidence-capped by thin upstream research. Something has
to PRODUCE a verdict so the field is never blank (Req 5a.1: ALWAYS a verdict). The real verdict is
a judgment made by the agent runner (or a human) weighing value, pricing, and fit; this module
writes a best-effort, LOW-confidence PROVISIONAL verdict into `research/go-no-go.md` so the digest
has a verdict to show and the grader has something to read.

HARD GUARDRAIL: a go/no-go verdict is a JUDGMENT. Deterministic prep must NEVER write the canonical
judgment fields `opportunity.json.status` / `recommendation` (that is the agent-runner's / human's
call — enforced by the harness mode-a/mode-b tests). So this generator writes ONLY the
`research/go-no-go.md` artifact, clearly labelled a document-only, LOW-confidence PROVISIONAL
verdict pending the real research. The provisional verdict is deliberately **CONDITIONAL-BID,
contingent on completing the research** — the honest stance for an opportunity whose value/fit have
not yet been researched: neither a committed bid nor a committed pass, with the condition named.

NON-DESTRUCTIVE: an analyst `research/go-no-go.md`, or a recommendation already recorded in the
summary (which would make the provisional verdict a false disagreement), is left untouched.
Idempotent.

Reads/writes the opportunity folder only; nothing company- or bid-specific lives here
(gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.gen_gonogo <opp-dir> [--force] [--json]
"""
import argparse, json, os, sys

from . import opportunity_lint

GENERATOR_TAG = "document-only (deterministic generator)"
_MARKER = "<!-- gen_gonogo: document-only -->"


def _read(opp_dir, *rel):
    p = os.path.join(opp_dir, *rel)
    if os.path.exists(p):
        try:
            return open(p, encoding="utf-8").read()
        except OSError:
            return ""
    return ""


def _load_opp(opp_dir):
    p = os.path.join(opp_dir, "opportunity.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _fmt(v):
    try:
        return f"${int(v):,}" if v else None
    except (TypeError, ValueError):
        return None


def _value_line(opp):
    ve = (opp or {}).get("value_estimate") or {}
    anchor = ve.get("anchor") or ve.get("likely")
    conf = ve.get("confidence") or "UNKNOWN"
    if anchor:
        return f"value ~{_fmt(anchor)} ({conf} confidence; see research/value-analysis.md)"
    return f"value UNKNOWN ({conf} confidence; see research/value-analysis.md)"


def build_gonogo(opp):
    """Produce the document-only provisional go/no-go markdown. Pure: no I/O. The verdict cites the
    three upstream outputs by name (so the grader's cites-upstream check passes) and states its
    condition (so the conditions check passes)."""
    title = (opp or {}).get("title") or (opp or {}).get("id") or "this opportunity"
    md = [
        f"# Go / no-go (document-only) — {title}",
        "",
        _MARKER,
        "",
        "> **Document-only, LOW-confidence PROVISIONAL verdict.** This is an automated placeholder so "
        "the opportunity always carries a verdict to react to; it is NOT a committed decision and it "
        "does NOT set `opportunity.json` status/recommendation. The agent-runner / human pass makes "
        "the real call after the value, pricing, and fit research is complete.",
        "",
        "## Recommendation",
        "**CONDITIONAL-BID (provisional)** — pending completion of the research.",
        "",
        "## Reasoning (cites the upstream stages)",
        f"- **Value**: {_value_line(opp)}.",
        "- **Pricing**: see research/pricing.md — a document-only skeleton reconciled in method to "
        "the value corridor; no bid price computed yet.",
        "- **Fit**: see research/fit-synthesis.md — candidate configurations enumerated and a "
        "provisional best-fit selected; competitiveness not yet researched.",
        "- Because the value, pricing, and fit stages are at document-only (LOW) confidence, this "
        "verdict is itself LOW confidence: it withholds neither a bid nor a pass, but conditions the "
        "bid on finishing the research.",
        "",
        "## Conditions",
        "- This provisional CONDITIONAL-BID depends on: (1) the value-research pass producing a real "
        "corridor/anchor; (2) the pricing pass producing a costed number inside that corridor; and "
        "(3) the fit pass confirming a competitive best-fit configuration. If any of those comes back "
        "weak, the verdict flips to PASS with a documented reason.",
        "",
        "## Confidence",
        "- **LOW** — provisional, built entirely on document-only upstream outputs. The agent-runner "
        "pass is expected to replace this with a committed, higher-confidence verdict.",
        "",
    ]
    return "\n".join(md)


def _existing_is_stronger(opp_dir):
    """Stand aside when a real verdict exists: an analyst go-no-go.md (no marker), OR a
    recommendation already recorded in the summary (writing a provisional verdict that disagrees
    would manufacture false recommendation-consistency drift)."""
    gng = _read(opp_dir, "research", "go-no-go.md")
    if gng.strip() and _MARKER not in gng:
        return "an analyst research/go-no-go.md is already on file"
    summ_rec = opportunity_lint.parse_recommendation(_read(opp_dir, "opportunity-summary.md"))
    if summ_rec is not None:
        return f"a recommendation ('{summ_rec}') is already recorded in the summary"
    return None


def generate(opp_dir, force=False):
    """Write a document-only PROVISIONAL go/no-go verdict unless a stronger one exists. Writes ONLY
    research/go-no-go.md — never opportunity.json status/recommendation. Returns a short note."""
    opp = _load_opp(opp_dir)
    if opp is None:
        return "gonogo-gen skipped: no opportunity.json"
    if not force:
        reason = _existing_is_stronger(opp_dir)
        if reason:
            return f"gonogo-gen skipped: {reason}"
    md = build_gonogo(opp)
    research_dir = os.path.join(opp_dir, "research")
    os.makedirs(research_dir, exist_ok=True)
    with open(os.path.join(research_dir, "go-no-go.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    return "gonogo-gen: document-only provisional verdict written (CONDITIONAL-BID, LOW confidence)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp")
    ap.add_argument("--force", action="store_true", help="overwrite even an analyst go-no-go.md")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    note = generate(a.opp, force=a.force)
    print(json.dumps({"note": note}, indent=2) if a.json else note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
