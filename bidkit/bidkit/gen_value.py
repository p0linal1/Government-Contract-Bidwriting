#!/usr/bin/env python3
"""
gen_value.py — the DETERMINISTIC, DOCUMENT-ONLY value GENERATOR (spec Requirement 3.5 / 8.5).

Why: the value-research GRADER (gate_value.py) scores how good a value estimate is, but something
has to PRODUCE the estimate. The full four-line triangulation + incumbent hunt is research that
needs the web and judgment, so it runs in the AGENT RUNNER. But when no agent runner is available
(the default on this box), the field must still never be blank: this module produces a best-effort
value estimate from the figures ALREADY on disk — the portal record's estimated value and the
dollar amounts the facts extractor already pulled out of rfp/ — and marks it for exactly what it is:
a LOW-confidence, document-only estimate with a wide corridor, every line sourced or an explicit
UNKNOWN-with-reason. It writes `opportunity.json.value_estimate` and `research/value-analysis.md`
in the shape the grader reads, so a thin opportunity goes from "no figure yet" to an honest,
reviewable corridor the principal can react to.

The one hard rule (bid-guardrails.md) holds: nothing is presented as a settled fact. A
document-only estimate is explicitly labelled document-only and LOW/at-most-MEDIUM confidence, so
it is never mistaken for the researched number.

NON-DESTRUCTIVE: if a stronger estimate already exists (an analyst/agent-runner anchor, or a
value-analysis.md that was not written by this generator), the generator LEAVES IT ALONE. It only
fills a genuinely empty or previously-document-only slot. Idempotent: re-running on an unchanged
opportunity reproduces the same output.

Reads/writes the opportunity folder only; nothing company- or bid-specific lives here
(gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.gen_value <opp-dir> [--force] [--json]
"""
import argparse, json, os, sys, datetime as dt

from . import opportunity_lint

# A marker written into the value-analysis.md and the value_estimate so a later pass (and the
# tests) can tell a document-only generated estimate from a researched one — and so the generator
# knows it is safe to overwrite its OWN prior output but never an analyst's.
GENERATOR_TAG = "document-only (deterministic generator)"
_MARKER = "<!-- gen_value: document-only -->"

# A write-back estimate is one lifted from an ANALYST value-analysis.md into the (blank) canonical
# value_estimate — it carries the analyst's figure, not the document-only generator's. This tag
# distinguishes it from both a document-only estimate and a hand-authored anchor.
WRITEBACK_TAG = "written back from research/value-analysis.md"
import re as _re

# Headline patterns in an analyst value-analysis.md, tried in order of authority:
#   1) an explicit anchor line:  "anchor ... $<amount>"  /  "appropriation ... $<amount>"
#   2) the Likely figure:        "Likely $<amount>"  /  "Likely ~$<amount>"
_ANCHOR_RE = _re.compile(r"(?i)\banchor\w*\b[^\n$]{0,60}(\$\s?[0-9][0-9,.]*\s*[kmb]?)")
_LIKELY_RE = _re.compile(r"(?i)\blikely\b[^\n$]{0,20}(\$\s?~?\s?[0-9][0-9,.]*\s*[kmb]?)")
# Confidence after a 'confidence' label. The filler between the label and the value is restricted
# to non-letters (whitespace/colon/punctuation/'is therefore' would be letters — so we allow a few
# connective words explicitly) so it cannot swallow the "MEDIUM-" of "MEDIUM-HIGH" and leave a bare
# "HIGH". MEDIUM-HIGH is listed before HIGH so the longer token wins.
_CONF_RE = _re.compile(r"(?i)\b(?:overall\s+)?confidence\b(?:\s+is(?:\s+therefore)?)?\s*:?\s*\*{0,2}\s*"
                       r"(MEDIUM[-\s]?HIGH|HIGH|MEDIUM|LOW)")
# a URL in the same analysis is used as the anchor source when we lift an anchor headline
_URL_RE = _re.compile(r"https?://\S+")

# Snippet cues that mean a `kind:"value"` money hit is really an insurance / liability / bond
# limit mis-tagged by proximity — exclude these from the value corridor (they are not contract
# values). Generic English/finance terms only; no company or bid specifics.
_NON_VALUE_CUES = (
    "liability", "insurance", "coverage", "aggregate", "umbrella", "workers", "bond",
    "e&o", "errors and omissions", "per incident", "per occurrence", "cyber ",
)


def _usable_money_signals(facts):
    """Dollar figures from the facts extractor that plausibly represent a CONTRACT value: the
    curated `money_value_signals` plus `money` entries tagged kind=='value', minus anything whose
    snippet reads like an insurance/liability limit. Returns a list of (amount:int, snippet, source)."""
    out = []
    seen = set()
    pools = (facts.get("money_value_signals") or []) + [
        m for m in (facts.get("money") or []) if (m.get("kind") == "value")
    ]
    for m in pools:
        amt = m.get("amount")
        if not amt:
            continue
        snip = (m.get("snippet") or "").lower()
        if any(cue in snip for cue in _NON_VALUE_CUES):
            continue
        amt = int(round(amt))
        if amt < 1000:            # a sub-$1k figure is never a contract value here
            continue
        key = (amt, m.get("source"))
        if key in seen:
            continue
        seen.add(key)
        out.append((amt, m.get("snippet") or "", m.get("source") or ""))
    return out


def _portal_value(opp):
    """A real estimated value from the portal record, if present and non-trivial. Portals often
    carry a placeholder like 0.01 ('not disclosed') — treat anything below a small floor as absent."""
    pr = opp.get("portal_record") or {}
    v = pr.get("estimated_value")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None, ""
    if v < 1000:                  # placeholder / not-disclosed
        return None, ""
    return int(round(v)), (pr.get("url") or pr.get("portal") or "portal record")


def _facts(opp_dir):
    p = os.path.join(opp_dir, "opportunity-facts.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _load_opp(opp_dir):
    p = os.path.join(opp_dir, "opportunity.json")
    if not os.path.exists(p):
        return None, p
    try:
        return json.load(open(p, encoding="utf-8")), p
    except json.JSONDecodeError:
        return None, p


def _existing_is_stronger(opp, opp_dir):
    """Return a short REASON string when there is already a value estimate the document-only
    generator must NOT clobber, or None when the slot is fillable. The generator only overwrites a
    blank slot or its OWN prior document-only output. Reasons distinguish the cases so the prep log
    (and a reader) can tell 'already researched' from the write-back gap the grader will flag."""
    ve = (opp or {}).get("value_estimate") or {}
    if ve.get("anchor") and ve.get("anchor_source"):
        return "a researched anchor is already recorded"
    if ve and ve.get("generator") != GENERATOR_TAG and (ve.get("likely") or ve.get("corridor_high")):
        return "a non-generator estimate is already recorded"
    va = os.path.join(opp_dir, "research", "value-analysis.md")
    if os.path.exists(va):
        txt = open(va, encoding="utf-8").read()
        if _MARKER not in txt and txt.strip():
            # an analyst analysis exists; if the canonical estimate is still blank, that is the
            # Springfield-style write-back gap — name it so it is not mistaken for 'done'.
            if not ve:
                return ("an analyst value-analysis.md exists but opportunity.json has no "
                        "value_estimate (write-back gap — the grader flags it)")
            return "an analyst value-analysis.md is already on file"
    return None


def _corridor(amounts):
    """Build a (low, likely, high) corridor from the usable document figures. With no figures the
    corridor is undefined (None); the caller then emits a pure-UNKNOWN estimate. With figures we
    widen deliberately — document-only mining is weak, so the band is intentionally generous."""
    vals = sorted(a for a in amounts if a)
    if not vals:
        return None
    lo, hi = vals[0], vals[-1]
    if lo == hi:
        # a single figure: treat it as the center of a wide +/-40% band (document-only uncertainty)
        likely = lo
        return int(likely * 0.6), int(likely), int(likely * 1.4)
    # spread of figures: low..high as given, likely = median
    mid = vals[len(vals) // 2]
    return lo, mid, hi


def _line(label, found, basis):
    """Render one of the four value lines for value-analysis.md. `found` None ⇒ UNKNOWN-with-reason
    (an honest 'the document-only pass could not source this'), never a blank."""
    if found is None:
        return (f"## {label}\n- UNKNOWN — not derivable from the documents on file. "
                f"{basis} Requires the agent-runner research pass (web search).\n")
    return f"## {label}\n- {found} {basis}\n"


def build_analysis(opp, facts):
    """Produce (value_estimate dict, value_analysis_markdown) from document figures only. Pure:
    no I/O, no network — fully deterministic for a given opportunity + facts."""
    sigs = _usable_money_signals(facts)
    pv, pv_src = _portal_value(opp)

    amounts = [a for a, _s, _src in sigs]
    if pv:
        amounts.append(pv)
    corr = _corridor(amounts)

    title = opp.get("title") or opp.get("id") or "this opportunity"
    sources = []
    if pv:
        sources.append(f"portal estimated value ${pv:,} ({pv_src})")
    for a, snip, src in sigs[:6]:
        sources.append(f"${a:,} — \u201c{(snip or '').strip()[:90]}\u201d [{src}]")

    # The four lines. Document-only mining can speak to at most comparable-figures-on-file; the
    # other three lines genuinely need external research, so they are honest UNKNOWN-with-reason.
    comparable_found = None
    if amounts:
        comparable_found = (f"Figures present in the documents on file span "
                            f"${min(amounts):,}\u2013${max(amounts):,}.")
    md = [
        f"# Value analysis (document-only) — {title}",
        "",
        _MARKER,
        "",
        "> **Document-only, LOW-confidence estimate.** Produced automatically from the figures already "
        "on file (the portal record and the amounts the facts extractor pulled from `rfp/`). It is a "
        "placeholder for the full four-line triangulation + incumbent hunt, which needs the agent-runner "
        "web-search pass. Treat every number here as a wide bracket, not a settled value.",
        "",
        _line("Line 1 — Buyer affordability", None,
              "No adopted budget / appropriation figure is on file."),
        _line("Line 2 — Procurement thresholds", None,
              "No purchasing-policy threshold is recorded in the documents."),
        _line("Line 3 — Comparable awards + figures on file", comparable_found,
              "These are raw document figures (which may include scope/line-item amounts), not matched "
              "comparable awards; the agent-runner pass must find true comparables."),
        _line("Line 4 — Bottom-up cost-to-deliver", None,
              "Not yet decomposed to a costed estimate; done in the pricing stage / agent-runner pass."),
        "## Incumbent prior-contract hunt",
        "- UNKNOWN — not performed in the document-only pass. The incumbent hunt needs web search "
        "(the single highest-ROI research step); run it in the agent-runner pass.",
        "",
        "## Convergence",
    ]
    if corr:
        lo, likely, hi = corr
        md += [
            f"- Document figures give a wide bracket **${lo:,} (low) / ${likely:,} (likely) / ${hi:,} (high)**.",
            "- Sources on file:",
        ] + [f"  - {s}" for s in sources]
        md += [
            "",
            "### Value estimate",
            f"- **Low ${lo:,} / Likely ${likely:,} / High ${hi:,}** — a wide document-only bracket.",
            "- **Overall confidence: LOW** — document-only; no incumbent anchor, no researched "
            "comparables, no affordability or threshold line. The agent-runner pass is expected to "
            "tighten this substantially.",
            "",
        ]
        ve = {
            "low": lo, "likely": likely, "high": hi,
            "corridor_low": lo, "corridor_high": hi,
            "confidence": "LOW",
            "basis": ("Document-only bracket from figures already on file (portal estimated value + "
                      "amounts extracted from rfp/). Not a researched estimate; the four-line "
                      "triangulation and incumbent hunt have not been run."),
            "source": "research/value-analysis.md",
            "generator": GENERATOR_TAG,
        }
    else:
        md += [
            "- **No usable dollar figure on file.** No portal estimated value and no contract-value "
            "amount in the extracted documents. A value cannot be bracketed from documents alone.",
            "",
            "### Value estimate",
            "- **UNKNOWN** — no figure derivable from the documents on file.",
            "- **Overall confidence: LOW** — nothing to anchor on until the agent-runner research "
            "pass (web search for affordability, thresholds, comparables, and the incumbent).",
            "",
        ]
        ve = {
            "low": None, "likely": None, "high": None,
            "confidence": "LOW",
            "basis": ("No dollar figure on file (no portal estimated value, no contract-value amount "
                      "in rfp/). Awaiting the agent-runner research pass."),
            "source": "research/value-analysis.md",
            "generator": GENERATOR_TAG,
        }
    return ve, "\n".join(md)


def writeback_from_analysis(opp_dir):
    """Close the Springfield-style write-back gap: when an ANALYST value-analysis.md carries a figure
    but opportunity.json has no value_estimate, lift the analyst headline into the canonical
    value_estimate (with its source + stated confidence) so a future session doesn't act on a blank
    canonical while the research doc holds the real number.

    Only acts when BOTH: (1) the canonical value_estimate is blank, AND (2) a NON-generated analyst
    value-analysis.md with a parseable headline is on file. It does NOT touch a document-only
    generated analysis (that has no researched headline to lift) and never overwrites an existing
    estimate. Returns a short note (or '' when it did nothing). Reused by prep and the CLI."""
    opp, opp_path = _load_opp(opp_dir)
    if opp is None:
        return ""
    if (opp.get("value_estimate") or {}):
        return ""   # canonical already populated — nothing to close
    va_path = os.path.join(opp_dir, "research", "value-analysis.md")
    if not os.path.exists(va_path):
        return ""
    txt = open(va_path, encoding="utf-8").read()
    if not txt.strip() or _MARKER in txt:
        return ""   # no analysis, or it is the document-only generator's own (no researched headline)

    # pick the headline: an explicit anchor beats the Likely figure
    anchor_m = _ANCHOR_RE.search(txt)
    likely_m = _LIKELY_RE.search(txt)
    headline = None
    is_anchor = False
    if anchor_m:
        headline = opportunity_lint.parse_money(anchor_m.group(1))
        is_anchor = headline is not None
    if headline is None and likely_m:
        headline = opportunity_lint.parse_money(likely_m.group(1))
    if headline is None:
        return ""   # analyst doc with no parseable figure — leave the grader to flag the gap

    conf_m = _CONF_RE.search(txt)
    conf = conf_m.group(1).upper().replace(" ", "-") if conf_m else "MEDIUM"
    url_m = _URL_RE.search(txt)

    ve = {"likely": headline, "confidence": conf,
          "basis": "Headline lifted from the analyst research/value-analysis.md on file.",
          "source": "research/value-analysis.md", "writeback": WRITEBACK_TAG}
    if is_anchor:
        ve["anchor"] = headline
        ve["anchor_source"] = url_m.group(0).rstrip(").,;") if url_m else "research/value-analysis.md"
        ve["anchor_basis"] = "Anchor headline lifted from research/value-analysis.md."

    opp["value_estimate"] = ve
    with open(opp_path, "w", encoding="utf-8") as fh:
        json.dump(opp, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    kind = "anchor" if is_anchor else "likely"
    return f"value-writeback: lifted analyst {kind} ${headline:,} ({conf}) into opportunity.json"


def generate(opp_dir, force=False):
    """Write a document-only value estimate for `opp_dir` unless a stronger one already exists.
    Returns a short note describing what happened (for the harness prep log). Idempotent.

    FIRST tries to close an analyst write-back gap (lift an existing analyst value-analysis.md
    headline into a blank canonical value_estimate); only if that does not apply does it fall back
    to generating a document-only estimate."""
    opp, opp_path = _load_opp(opp_dir)
    if opp is None:
        return "value-gen skipped: no opportunity.json"

    if not force:
        # close the write-back gap before anything else — an analyst figure beats a document-only one
        wb = writeback_from_analysis(opp_dir)
        if wb:
            return wb
        reason = _existing_is_stronger(opp, opp_dir)
        if reason:
            return f"value-gen skipped: {reason}"

    facts = _facts(opp_dir)
    ve, md = build_analysis(opp, facts)

    # write research/value-analysis.md
    research_dir = os.path.join(opp_dir, "research")
    os.makedirs(research_dir, exist_ok=True)
    with open(os.path.join(research_dir, "value-analysis.md"), "w", encoding="utf-8") as fh:
        fh.write(md)

    # write back opportunity.json value_estimate (preserve key order; additive)
    opp["value_estimate"] = ve
    with open(opp_path, "w", encoding="utf-8") as fh:
        json.dump(opp, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    headline = ve.get("likely")
    if headline:
        return f"value-gen: document-only estimate written (likely ${headline:,}, LOW confidence)"
    return "value-gen: document-only estimate written (UNKNOWN — no figure on file, LOW confidence)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp")
    ap.add_argument("--force", action="store_true",
                    help="overwrite even a stronger existing estimate (use with care)")
    ap.add_argument("--writeback-only", action="store_true",
                    help="only close an analyst write-back gap; do not generate a document-only estimate")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.writeback_only:
        note = writeback_from_analysis(a.opp) or "value-writeback: nothing to write back"
    else:
        note = generate(a.opp, force=a.force)
    if a.json:
        opp, _ = _load_opp(a.opp)
        print(json.dumps({"note": note, "value_estimate": (opp or {}).get("value_estimate")}, indent=2))
    else:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
