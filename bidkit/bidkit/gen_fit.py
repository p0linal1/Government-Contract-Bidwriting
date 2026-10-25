#!/usr/bin/env python3
"""
gen_fit.py — the DETERMINISTIC, DOCUMENT-ONLY fit-synthesis GENERATOR (spec Requirement 5 / 8.5).

Why: the fit GRADER (gate_fit.py) scores whether a SYNTHESIS was performed — what the RFP wants,
more than one candidate configuration from the bidder's capability superset, a reasoned selection,
and a competitiveness read. The real synthesis needs judgment and the web (reading the evaluation
rubric, sizing the competition) and runs in the agent runner. When it has not run, this module
writes a best-effort, LOW-confidence `research/fit-synthesis.md` SKELETON so the fit field is never
blank: it extracts what the RFP wants from the facts on file, enumerates at least two candidate
configurations from the configured capability superset (prime-solo vs. teaming, full-build vs.
component), selects one with a stated rationale, gives an honest competitiveness read, frames any
prior performance as transferable experience with a reference-gap note, and SURFACES (never
resolves) a staffing/locality conflict as a human decision.

Every judgment it emits is explicitly document-only and LOW confidence — the hard rule
(bid-guardrails.md) holds: it is a reviewable draft, never a settled fit decision. The agent-runner
pass replaces it with a real synthesis.

The capability superset is COMPANY data; the library never names a company. The capability file
path is passed in by the caller (harness config / opportunity.json `capability_file`); when none is
available the generator still produces a synthesis from the RFP-wants alone, with generic
configurations. Nothing company- or bid-specific lives here (gate: tests/test_no_hardcoding.py).

NON-DESTRUCTIVE: an analyst `research/fit-synthesis.md`, or real fit posture already in
go-no-go/summary, is left untouched. Idempotent.

CLI:
  python3 -m bidkit.gen_fit <opp-dir> [--capability PATH] [--force] [--json]
"""
import argparse, json, os, sys

GENERATOR_TAG = "document-only (deterministic generator)"
_MARKER = "<!-- gen_fit: document-only -->"

# RFP-want signal cues found in the facts/opportunity (what the evaluator cares about). METHOD
# language only — these describe the ANALYSIS, never a company or a bid.
_LOCALITY_CUES = ("on-site", "onsite", "on site", "local", "in-person", "in person", "resident",
                  "physically", "locality")
_REGULATED_CUES = ("cjis", "cji", "phi", "hipaa", "pii", "criminal justice", "regulated")

# fit posture already recorded elsewhere (so the skeleton would be clutter)
_REAL_FIT_CUES = ("candidate configuration", "best-fit", "best fit", "winnab", "competitiveness",
                  "evaluator priorities", "fit synthesis", "configuration a", "configuration 1")


def _read(opp_dir, *rel):
    p = os.path.join(opp_dir, *rel)
    if os.path.exists(p):
        try:
            return open(p, encoding="utf-8").read()
        except OSError:
            return ""
    return ""


def _load_json(path):
    if path and os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _load_opp(opp_dir):
    return _load_json(os.path.join(opp_dir, "opportunity.json"))


def _facts(opp_dir):
    return _load_json(os.path.join(opp_dir, "opportunity-facts.json")) or {}


def _capability(opp, opp_dir, capability_path):
    """Resolve the capability superset JSON from (in order): an explicit path argument, the
    opportunity.json `capability_file` key (relative to the opp dir), else None. Keeping the path
    in config/opportunity — never in the library — is what keeps this module company-agnostic."""
    if capability_path:
        cap = _load_json(capability_path)
        if cap:
            return cap
    rel = (opp or {}).get("capability_file")
    if rel:
        cap = _load_json(rel if os.path.isabs(rel) else os.path.join(opp_dir, rel))
        if cap:
            return cap
    return None


def _rfp_wants(opp, facts):
    """What the RFP appears to want, from the facts/opportunity on file. Honest and shallow — the
    real evaluator-priority extraction is the agent-runner pass reading the rubric."""
    wants = []
    title = (opp or {}).get("title") or ""
    if title:
        wants.append(f"Scope signalled by the title: \u201c{title}\u201d.")
    evaluation = facts.get("evaluation") or []
    if evaluation:
        wants.append(f"The facts record {len(evaluation)} evaluation/scoring signal(s) — the "
                     "agent-runner pass must read the rubric for weights.")
    setaside = facts.get("setaside") or []
    if setaside:
        wants.append("A set-aside / preference signal is present — check eligibility.")
    term = facts.get("term") or []
    if term:
        wants.append("A contract term/period signal is present (affects multi-year posture).")
    blob = json.dumps(facts).lower() + " " + json.dumps(opp or {}).lower()
    locality = any(c in blob for c in _LOCALITY_CUES)
    regulated = any(c in blob for c in _REGULATED_CUES)
    if locality:
        wants.append("A **locality / on-site** signal is present — weigh local presence.")
    if regulated:
        wants.append("A **regulated-data** signal (CJIS/PHI/PII) is present — weigh data-handling.")
    if not wants:
        wants.append("UNKNOWN — the documents on file do not yet reveal evaluator priorities; the "
                     "agent-runner pass must read the RFP's evaluation section.")
    return wants, locality, regulated


def _candidate_configs(cap):
    """At least two candidate configurations synthesised from the capability superset. These are
    STRUCTURAL options (how to assemble a bid), not a fixed identity — the whole point of the fit
    synthesis. With no capability file, fall back to generic structural options so the synthesis
    still considers alternatives."""
    caps = (cap or {}).get("core_capabilities") or []
    cap_hint = f" (drawing on: {', '.join(caps[:4])}{'…' if len(caps) > 4 else ''})" if caps else ""
    return [
        ("Configuration A — Prime, full custom build",
         f"Bid as prime and deliver the full scope as a custom build{cap_hint}. "
         "Maximises margin and control; relies on the bidder's own capacity."),
        ("Configuration B — Prime + domain/local teaming partner, targeted scope",
         "Bid as prime but team with a domain or local partner for the parts outside the bidder's "
         "lane (or to meet an on-site / locality requirement), and/or scope the bid to the "
         "highest-fit component. Lowers risk and closes gaps; shares margin."),
    ]


def build_fit(opp, facts, cap):
    """Produce the document-only fit-synthesis markdown. Pure: no I/O."""
    title = (opp or {}).get("title") or (opp or {}).get("id") or "this opportunity"
    wants, locality, regulated = _rfp_wants(opp, facts)
    configs = _candidate_configs(cap)
    pastperf = (cap or {}).get("past_performance") or []

    md = [
        f"# Fit & winnability (document-only) — {title}",
        "",
        _MARKER,
        "",
        "> **Document-only, LOW-confidence fit synthesis.** Produced automatically from the facts on "
        "file and the capability superset. It enumerates candidate configurations and a provisional "
        "best-fit so the fit field is never blank; it is NOT a researched winnability read. The "
        "agent-runner pass (reading the evaluation rubric and sizing the competition) replaces it.",
        "",
        "## What the RFP wants (from the documents on file)",
    ] + [f"- {w}" for w in wants] + [
        "",
        "## Candidate configurations (synthesis — more than one considered)",
    ]
    for name, desc in configs:
        md += [f"### {name}", f"- {desc}"]
    md += [
        "",
        "## Selected best-fit configuration (provisional)",
        "- **Provisional selection: Configuration A (prime, full custom build)** — chosen because, "
        "absent a known gap the RFP forces, bidding as prime maximises margin and control. This is a "
        "**document-only default**, not a researched selection: if the RFP-wants above include an "
        "on-site/locality or platform gap, Configuration B (teaming) is likely stronger. Reasoning "
        "to be confirmed by the agent-runner pass against the evaluation rubric.",
        "",
        "## Competitiveness (honest, document-only)",
        "- UNKNOWN at document-only confidence — the competition and the evaluator weights have not "
        "been researched. Treat winnability as unassessed until the agent-runner pass; a well-founded "
        "weak-fit / PASS is a valid outcome if that pass finds the configuration uncompetitive.",
        "",
        "## Prior performance (honest framing)",
    ]
    if pastperf:
        for p in pastperf[:4]:
            nm = p.get("name") or "a prior project"
            md.append(f"- **{nm}** — offer as *transferable experience*, not an in-domain turnkey "
                      "match. Carry the reference-gap note: adjacent/commercial experience, not a "
                      "prior deployment of this exact system.")
    else:
        md.append("- No capability past-performance on file to the generator; the agent-runner pass "
                  "should select references and frame them as transferable experience with a "
                  "reference-gap note (never an overclaimed turnkey match).")
    md += ["", "## Staffing / locality / regulated-data conflict (surfaced, not resolved)"]
    if locality or regulated:
        signal = " and ".join(s for s, f in (("locality/on-site", locality),
                                              ("regulated-data", regulated)) if f)
        md.append(f"- ⚠ **Human decision:** the RFP shows a {signal} signal. If the selected "
                  "configuration's staffing cannot satisfy it (e.g. an on-site requirement, or a "
                  "regulated-data access rule), that is a conflict to RESOLVE WITH THE PRINCIPAL — "
                  "state the conflict and the most-likely resolution; do not silently pick a side. "
                  "LOW confidence until resolved.")
    else:
        md.append("- No locality / regulated-data conflict signalled by the documents on file. "
                  "Re-check once the RFP's requirements are read in full.")
    md += [
        "",
        "## Confidence",
        "- **LOW** — document-only: RFP-wants are shallow, the selection is a default (not researched "
        "against the rubric), and competitiveness is unassessed. The agent-runner pass is expected to "
        "raise this.",
        "",
    ]
    return "\n".join(md)


def _real(text):
    """Ignore a companion doc that is itself a document-only generated artifact (keeps the
    generators idempotent across stages — a generated go-no-go must not look like 'real posture')."""
    return "" if (text and ": document-only -->" in text) else (text or "")


def _existing_is_stronger(opp_dir):
    fs = _read(opp_dir, "research", "fit-synthesis.md")
    if fs.strip() and _MARKER not in fs:
        return "an analyst research/fit-synthesis.md is already on file"
    other = (_real(_read(opp_dir, "research", "go-no-go.md"))
             + "\n" + _real(_read(opp_dir, "opportunity-summary.md"))).lower()
    if any(cue in other for cue in _REAL_FIT_CUES):
        return "real fit posture is already recorded in go-no-go/summary"
    return None


def generate(opp_dir, capability_path=None, force=False):
    """Write a document-only fit synthesis unless a stronger one exists. Returns a short note."""
    opp = _load_opp(opp_dir)
    if opp is None:
        return "fit-gen skipped: no opportunity.json"
    if not force:
        reason = _existing_is_stronger(opp_dir)
        if reason:
            return f"fit-gen skipped: {reason}"
    facts = _facts(opp_dir)
    cap = _capability(opp, opp_dir, capability_path)
    md = build_fit(opp, facts, cap)
    research_dir = os.path.join(opp_dir, "research")
    os.makedirs(research_dir, exist_ok=True)
    with open(os.path.join(research_dir, "fit-synthesis.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    cap_note = "with capability superset" if cap else "no capability file — generic configs"
    return f"fit-gen: document-only fit synthesis written ({cap_note}, LOW confidence)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp")
    ap.add_argument("--capability", default=None, help="path to the capability superset JSON")
    ap.add_argument("--force", action="store_true", help="overwrite even an analyst fit-synthesis.md")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    note = generate(a.opp, capability_path=a.capability, force=a.force)
    print(json.dumps({"note": note}, indent=2) if a.json else note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
