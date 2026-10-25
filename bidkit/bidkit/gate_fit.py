#!/usr/bin/env python3
"""
gate_fit.py — the fit-&-winnability stage gate (synthesis type; runs AFTER pricing).

Why: fit is NOT a filter that asks "does this contract fit a fixed company?" — it is a SYNTHESIS
that asks "what is this RFP looking for, what is the maximally marketable configuration the bidder
can assemble from any subset of its capabilities to match it, and would that best-fit
configuration be competitive?" The bidder is a capability SUPERSET; the bid presents the best-fit
SUBSET. A given structure (e.g. a US-principal + offshore team, or a US-only solo + AI pitch) is
an OUTPUT chosen for a particular RFP, never a default identity.

So this gate verifies the synthesis was PERFORMED and recorded, and explicitly does NOT expect any
particular structure (spec Requirement 5):
  (a) what the RFP wants was extracted (evaluator priorities / scoring weights / risk / locality);
  (b) more than one candidate configuration was considered (a single assumed option is not synthesis);
  (c) a best-fit configuration was selected WITH reasoning;
  (d) its competitiveness was assessed.
Plus: a staffing/locality or regulated-data conflict implied by the selected configuration must be
SURFACED as a human-decision, never silently resolved; a portfolio item offered as prior
performance must carry honest transferable-experience framing (not an overclaimed turnkey match);
and a well-founded PASS (configuration not competitive) is a VALID outcome, not a gate failure.

Reads a dedicated research/fit-synthesis.md when present, else the reasoning docs where the fit
synthesis lives today (research/go-no-go.md + opportunity-summary.md). Reads the opportunity
folder only; nothing company- or bid-specific lives here (gate: tests/test_no_hardcoding.py).
Registers itself as the 'fit' stage (order 40).
"""
import re

from .evaluation import (EvalContext, GateResult, GateFinding, FAIL, WARN, LOW, Stage, register,
                         SYNTHESIS, require_alternatives_considered, require_reasoned_selection,
                         require_surfaced_not_resolved)


_DOC_ONLY_MARKER = "<!-- gen_fit: document-only -->"


def _fit_record(ctx):
    parts = [ctx.text("research", "fit-synthesis.md"),
             ctx.text("research", "go-no-go.md"),
             ctx.text("opportunity-summary.md")]
    joined = "\n\n".join(p for p in parts if p)
    return joined or None


# any document-only generator marks its output with this substring; such a companion doc is NOT
# "real posture" and must not lift a document-only stage out of its LOW cap.
_ANY_DOC_ONLY = ": document-only -->"


def _real(text):
    """Return the text only if it is NOT a document-only generated artifact (else '')."""
    return "" if (text and _ANY_DOC_ONLY in text) else (text or "")


def _is_document_only(ctx):
    """True when the ONLY fit record is the deterministic document-only SKELETON (it satisfies the
    structural checks by construction, so its confidence must be capped at LOW rather than inferred
    HIGH). Real fit posture in go-no-go/summary overrides — but a document-only generated go-no-go
    (which also mentions competitiveness) does NOT count as real posture."""
    fs = ctx.text("research", "fit-synthesis.md") or ""
    if _DOC_ONLY_MARKER not in fs:
        return False
    other = "\n".join(t for t in (_real(ctx.text("research", "go-no-go.md")),
                                   _real(ctx.text("opportunity-summary.md"))) if t)
    return not _has_any(other, _COMPETITIVE) if other else True


def _has_any(text, cues):
    low = text.lower()
    return any(c in low for c in cues)


# cue vocabularies — all METHOD/analysis language, never a company structure
_RFP_WANTS = ["rfp is looking for", "evaluator", "scoring weight", "scoring", "evaluation criteria",
              "weighted", "points", "risk posture", "what the rfp wants", "wants", "priorities",
              "selection criteria", "rubric"]
_COMPETITIVE = ["competitive", "winnab", "win probability", "would win", "against the incumbent",
                "differentiat", "competitiveness", "beat", "edge over"]
# a staffing/locality/regulated-data conflict may be present…
_CONFLICT = ["offshore", "locality", "local presence", "local-presence", "regulated data",
             "cjis", "cji", "phi", "out of the us", "outside the us", "overseas", "foreign"]
# …and must be surfaced as an OPEN human-decision rather than resolved silently
_SURFACED = ["human decision", "human-decision", "open item", "open question", "surface",
             "decision needed", "to be decided", "needs a decision", "flag", "⚠", "resolve with the",
             "principal decides", "requires a decision"]
# prior-performance honesty cues
_PASTPERF = ["prior performance", "past performance", "reference", "portfolio"]
_HONEST_FRAMING = ["transferable", "adjacent", "net-new build", "net new build", "not a turnkey",
                   "no in-domain turnkey", "reference gap", "reference-gap", "greenfield build"]
_OVERCLAIM = ["proven turnkey", "turnkey solution we have", "identical deployment", "exact match"]

# candidate-configuration detection: enumerated options under a configs section, or explicit
# "Option/Configuration N" / "Candidate" markers.
_CONFIG_SECTION = re.compile(r"(?im)^#{1,6}[^\n]*\b(candidate|configuration|option|staffing model|"
                             r"delivery model|team structure)s?\b")
_CONFIG_ITEM = re.compile(r"(?im)^\s*(?:[-*]|\d+[.)]|option\s+\w|configuration\s+\w|candidate\s+\w)\s+\S")

# a PASS verdict is a valid fit outcome
_PASS_CUES = ["not competitive", "would not win", "recommend pass", "no-bid", "decline", "pass"]


def _candidate_configs(text):
    """Extract candidate configurations the synthesis considered. Looks for an explicit configs
    section and counts enumerated items within it; falls back to counting option/candidate markers
    anywhere. Returns a list of short labels (for evidence)."""
    labels = []
    # find a configs section and read its bullet/numbered items until the next header
    m = _CONFIG_SECTION.search(text)
    if m:
        tail = text[m.end():]
        nxt = re.search(r"(?m)^#{1,6}\s", tail)
        block = tail[:nxt.start()] if nxt else tail
        for line in block.splitlines():
            if _CONFIG_ITEM.match(line):
                labels.append(line.strip()[:50])
    if len(labels) < 2:
        # fallback: explicit Option/Configuration/Candidate N markers anywhere
        for mm in re.finditer(r"(?im)\b(option|configuration|candidate)\s+(?:\w+|\d+)\b", text):
            labels.append(mm.group(0))
    # de-dupe preserving order
    seen, out = set(), []
    for l in labels:
        k = l.lower()
        if k not in seen:
            seen.add(k); out.append(l)
    return out


_SELECTION_RE = re.compile(
    r"(?i)\b(selected(?:\s+best[-\s]?fit)?|chosen|best[-\s]?fit (?:is|configuration|model)|"
    r"we (?:will )?present|recommend(?:ed)? configuration|the (?:delivery|staffing) model is|"
    r"delivery is\b.{0,40}\b(?:solo|principal|offshore|team|us-only|hybrid)|"
    r"decision:?\s*(?:bid|conditional|pass|foothold))\b([^\n]{0,160})")

# An ECHO of this gate's own instruction ("a selected best-fit WITH REASONING, and a competitiveness
# read…") is NOT a selection — the agent restated the task instead of choosing. Reject a match whose
# tail is instruction-template prose. METHOD language, not company/bid values.
_SELECTION_ECHO = re.compile(
    r"(?i)\bwith\s+reasoning\b|\ba\s+competitiveness\s+read\b|\bbest[-\s]?fit\s+with\b|"
    r"\bselect(?:ed|ion)?\s+(?:a\s+)?best[-\s]?fit\s+(?:with|configuration\s+with)\b")

# A real selection NAMES a concrete configuration: an explicit Configuration/Option/Candidate label,
# or a structural staffing/delivery token (prime, solo, teaming, offshore, hybrid, component, …).
_CONCRETE_CONFIG = re.compile(
    r"(?i)\b(configuration\s+[A-Z0-9]|option\s+[A-Z0-9]|candidate\s+[A-Z0-9]|prime[-\s]?solo|"
    r"prime\b|solo\b|team(?:ing)?\b|subcontract|offshore\b|us[-\s]?only|hybrid\b|component\b|"
    r"full[-\s]?custom|foothold\b)")

# Reasoning may be a connective ("because/since/to match…"), numbered justifications ("(1)…(2)…"),
# or rationale nouns (advantage/risk/value/edge) — a selection stated as "X — <substantial clause>"
# is reasoned. We accept any of these signals within the window around the selection.
_REASONING_RE = re.compile(r"(?i)(\b(because|since|scores?|to match|given that|given the|so that|"
                           r"rationale|maximally marketable|best positions|removes? the|leans on|"
                           r"this (?:removes|resolves|avoids)|not offshore|low cash risk|expected value)\b"
                           r"|\(\s*1\s*\).{0,120}\(\s*2\s*\)"              # numbered (1)…(2) justifications
                           r"|\b(advantage|risk|value|edge|floor|differentiat)\w*\b)")


def _selected_and_reasoning(text):
    """Find a GENUINE 'selected best-fit configuration' statement and whether reasoning accompanies
    it. A match is rejected when it is an ECHO of this gate's instruction ("a selected best-fit with
    reasoning, and a competitiveness read…") rather than a real choice, OR when it does not name a
    CONCRETE configuration (a Configuration/Option label or a structural staffing/delivery token)
    within its window. Scans a window AROUND the selection (reasoning often precedes the conclusion)
    for a rationale clause. Returns (selection, reasoning) — reasoning None if absent, selection None
    if no real selection was made (so the grader reports 'not performed', not a false 'no reasoning')."""
    for m in _SELECTION_RE.finditer(text):
        tail = m.group(2) or ""
        # 1) reject an instruction echo (either in the matched phrase or its immediate tail)
        if _SELECTION_ECHO.search(m.group(0)) or _SELECTION_ECHO.search(tail):
            continue
        start = max(0, m.start() - 200)
        window = text[start:m.start() + 400]
        # 2) require a concrete named configuration near the selection (not just the word "selected")
        if not _CONCRETE_CONFIG.search(m.group(0) + " " + window):
            continue
        selection = m.group(0).strip()[:120]
        reasoning = window if _REASONING_RE.search(window) else None
        return (selection, reasoning)
    return (None, None)


def gate(ctx: EvalContext) -> GateResult:
    res = GateResult("fit")
    rec = _fit_record(ctx)
    if not rec:
        res.add(GateFinding("fit-record", ok=False, severity=FAIL, performed=False,
                            message="no fit record (research/fit-synthesis.md or go-no-go/summary) — fit synthesis not performed"))
        return res

    # (a) what the RFP wants was extracted
    res.add(GateFinding("rfp-wants-extracted", ok=_has_any(rec, _RFP_WANTS), severity=FAIL,
                        performed=_has_any(rec, _RFP_WANTS),
                        message=("RFP wants / evaluation priorities extracted" if _has_any(rec, _RFP_WANTS)
                                 else "no extraction of what the RFP is looking for (evaluator priorities / scoring)")))

    # (b) more than one candidate configuration considered — the no-default-assumed check
    configs = _candidate_configs(rec)
    res.add(require_alternatives_considered("candidate-configs", "candidate configurations", configs, min_n=2))

    # (c) a best-fit configuration selected WITH reasoning
    selection, reasoning = _selected_and_reasoning(rec)
    res.add(require_reasoned_selection("selected-config", "best-fit configuration", selection, reasoning))

    # (d) competitiveness of the selected configuration assessed
    res.add(GateFinding("competitiveness-assessed", ok=_has_any(rec, _COMPETITIVE), severity=FAIL,
                        performed=_has_any(rec, _COMPETITIVE),
                        message=("competitiveness of the best-fit configuration assessed" if _has_any(rec, _COMPETITIVE)
                                 else "no assessment of whether the best-fit configuration would be competitive")))

    # conflict surfaced, not silently resolved (locality / regulated-data / offshore)
    conflict = _has_any(rec, _CONFLICT)
    surfaced = _has_any(rec, _SURFACED)
    res.add(require_surfaced_not_resolved("locality-conflict", "staffing/locality/regulated-data",
                                          surfaced=surfaced, conflict_present=conflict))

    # prior-performance honesty: if portfolio/references are offered, require honest framing and no overclaim
    if _has_any(rec, _PASTPERF):
        if _has_any(rec, _OVERCLAIM) and not _has_any(rec, _HONEST_FRAMING):
            res.add(GateFinding("pastperf-honest", ok=False, severity=FAIL, performed=True,
                                message="prior performance appears overclaimed (turnkey/exact-match) without transferable-experience framing"))
        else:
            res.add(GateFinding("pastperf-honest", ok=_has_any(rec, _HONEST_FRAMING), severity=WARN,
                                performed=True,
                                message=("honest transferable-experience / reference-gap framing present"
                                         if _has_any(rec, _HONEST_FRAMING)
                                         else "prior performance offered without an explicit transferable/reference-gap note")))

    # CONFIDENCE: a document-only fit SKELETON satisfies the structural checks by construction (it
    # names RFP-wants, two configs, a selection, competitiveness) — but it is an unresearched draft,
    # so it must be LOW. Otherwise confidence is inferred from the findings (a real synthesis earns
    # MEDIUM/HIGH).
    if _is_document_only(ctx):
        res.set_confidence(LOW)

    return res


register(Stage("fit", 40, SYNTHESIS, gate, depends_on=["pricing"],
               tasklist_template="Fit & winnability (synthesis): extract what the RFP wants "
               "(priorities / scoring / risk / locality); generate >1 candidate configuration from "
               "the capability superset; select the maximally marketable best-fit with reasoning; "
               "assess its competitiveness; surface any staffing/locality/regulated-data conflict "
               "as a human-decision; frame portfolio prior performance honestly."))


def main(argv=None):
    import argparse, json, sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = gate(EvalContext(a.opp))
    if a.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"[{res.confidence}] fit")
        for f in res.findings:
            if not f.ok:
                print(f"   {'!!' if f.blocking_failure else '~ '} {f.check}: {f.message}")
    return 0   # graders score confidence; they never fail the pipeline


if __name__ == "__main__":
    import sys
    sys.exit(main())
