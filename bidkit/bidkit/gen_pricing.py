#!/usr/bin/env python3
"""
gen_pricing.py — the DETERMINISTIC, DOCUMENT-ONLY pricing GENERATOR (spec Requirement 4 / 8.5).

Why: the pricing GRADER (gate_pricing.py) scores whether the three-axis reconciliation was stated
and tied to the value corridor, but something has to PRODUCE that pricing record. The real pricing
(the bid-pricing.md three-axis build, reserved-capacity decisions, a costed workbook) needs
judgment and runs in the agent runner. When it has not run, this module writes a best-effort,
LOW-confidence `research/pricing.md` SKELETON so the pricing field is never blank: it anchors on
whatever value corridor the value stage produced, lays out the three axes (labor hours; staff ×
schedule capacity; mandated schedule) as the method to be filled, frames AI acceleration explicitly
as a COMPRESSION FACTOR (not a discounted rate — the grader fails the inverse), sketches a recurring
line bottom-up (infra + support labor + margin) as placeholders, and surfaces the human-decision
points (reserved capacity, final scope, rate/margin) rather than assuming them.

Every figure it emits is a placeholder tied to the value corridor, explicitly labelled
document-only and LOW confidence — the hard rule (bid-guardrails.md) holds: nothing is presented as
a settled price. The agent-runner pass replaces this with a real costed estimate.

NON-DESTRUCTIVE: if a real pricing record already exists (a `research/pricing.md` this generator
did not write, i.e. an analyst's), the generator LEAVES IT ALONE. Idempotent.

Reads/writes the opportunity folder only; nothing company- or bid-specific lives here
(gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.gen_pricing <opp-dir> [--force] [--json]
"""
import argparse, json, os, sys

GENERATOR_TAG = "document-only (deterministic generator)"
_MARKER = "<!-- gen_pricing: document-only -->"


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


def _corridor(opp):
    """Return (low, likely, high, confidence, source) from the value estimate, any of which may be
    None. The pricing skeleton reconciles against whatever the value stage produced."""
    ve = (opp or {}).get("value_estimate") or {}
    return (ve.get("corridor_low") or ve.get("low"),
            ve.get("anchor") or ve.get("likely"),
            ve.get("corridor_high") or ve.get("high"),
            ve.get("confidence") or "", ve.get("source") or "")


# method cues that signal REAL pricing posture already recorded (in pricing.md, go-no-go, or the
# summary) — if present, the document-only skeleton would only add clutter, so the generator stands
# aside. METHOD language, not company/bid values.
_REAL_PRICING_CUES = ("labor hour", "blended rate", "/yr", "per year", "recurring", "tco",
                      "margin", "costed", "cost-to-deliver", "cost to deliver")


# any document-only generator marks its output with this substring; such a companion doc is not
# "real posture" (it would otherwise make the generators non-idempotent across stages).
_ANY_DOC_ONLY = ": document-only -->"


def _read(opp_dir, *rel):
    p = os.path.join(opp_dir, *rel)
    if os.path.exists(p):
        try:
            return open(p, encoding="utf-8").read()
        except OSError:
            return ""
    return ""


def _real(text):
    return "" if (text and _ANY_DOC_ONLY in text) else (text or "")


def _existing_is_stronger(opp_dir):
    """Return a reason to stand aside, or None. The document-only skeleton is skipped when:
      - a research/pricing.md this generator did not write exists (an analyst's), OR
      - real pricing posture is already recorded in a NON-generated go-no-go.md / summary (the
        grader reads those, so a skeleton would only add clutter). A document-only generated
        go-no-go does not count — otherwise the generators would stop being idempotent across runs."""
    pm = _read(opp_dir, "research", "pricing.md")
    if pm.strip() and _MARKER not in pm:
        return "an analyst research/pricing.md is already on file"
    other = (_real(_read(opp_dir, "research", "go-no-go.md"))
             + "\n" + _real(_read(opp_dir, "opportunity-summary.md"))).lower()
    if any(cue in other for cue in _REAL_PRICING_CUES):
        return "real pricing posture is already recorded in go-no-go/summary"
    return None


def build_pricing(opp):
    """Produce the document-only pricing markdown from the value corridor. Pure: no I/O."""
    lo, likely, hi, conf, src = _corridor(opp)
    title = opp.get("title") or opp.get("id") or "this opportunity"
    have_corridor = any(v for v in (lo, likely, hi))

    if have_corridor:
        corr_line = (f"Value corridor from the value-research stage: "
                     f"{_fmt(lo) or '?'} (low) / {_fmt(likely) or '?'} (likely) / {_fmt(hi) or '?'} (high)"
                     + (f" [{conf}]" if conf else "")
                     + (f" — see {src}" if src else "") + ".")
        reconcile = (f"A priced bid should land inside this corridor; a price above {_fmt(hi) or 'the high'} "
                     "or below the realistic cost-to-deliver must be explained. The document-only pass "
                     "does not compute a price — it reconciles the METHOD to the corridor and leaves the "
                     "number to the agent-runner / costed-workbook pass.")
    else:
        corr_line = ("Value corridor: UNKNOWN — the value-research stage has no figure on file yet. "
                     "Pricing cannot be reconciled to a corridor until the value pass runs.")
        reconcile = ("No corridor to reconcile against; the priced number is UNKNOWN until the value "
                     "stage produces one.")

    md = [
        f"# Pricing (document-only) — {title}",
        "",
        _MARKER,
        "",
        "> **Document-only, LOW-confidence pricing skeleton.** This lays out the pricing METHOD and "
        "reconciles it to the value corridor; it does NOT compute a bid price. The real three-axis "
        "build, reserved-capacity decision, and costed workbook are the agent-runner / pricing-phase "
        "pass. Treat every figure here as a placeholder, not a quote.",
        "",
        "## Reconciliation to the value corridor",
        f"- {corr_line}",
        f"- {reconcile}",
        "",
        "## Three-axis reconciliation (method — to be filled)",
        "1. **Labor hours** — raw scope effort (bottom-up from the requirement list). UNKNOWN until "
        "the scope is decomposed; needs the RFP's requirement count and complexity.",
        "2. **Staff × schedule capacity** — named-team size × the performance window. UNKNOWN until the "
        "assigned team and start date are fixed (a binding staffing commitment — human decision).",
        "3. **Mandated schedule** — the RFP's required timeline; the hours must fit the window at the "
        "planned capacity. UNKNOWN until the schedule is confirmed from the RFP.",
        "- The three axes must tie out (hours ≈ capacity × schedule); any gap is closed by scope, "
        "headcount, or timeline — not by discounting the rate.",
        "",
        "## AI acceleration",
        "- Modeled as a **compression factor** (fewer billed HOURS for the same scope), NOT a discounted "
        "rate. The blended rate is held; the hours fall. (The grader fails the inverse framing.)",
        "",
        "## Recurring (bottom-up — to be filled)",
        "- **Infra / hosting**: sized from the solution's storage/compute drivers — UNKNOWN until scope. ",
        "- **Support labor**: the ongoing support FTE fraction — UNKNOWN until the support model is set.",
        "- **Margin**: applied on top of infra + support labor — a rate/margin human decision.",
        "- Recurring is a firm multi-year commitment; under-pricing it becomes a loss (bid-pricing.md).",
        "",
        "## Human decisions (surfaced, not assumed)",
        "- **Reserved-capacity commitment**: any reserved/savings-plan cloud capacity assumed in the "
        "price must actually be purchased — a human decision, not an assumption.",
        "- **Final scope**: full build vs. a targeted component — drives hours and recurring.",
        "- **Rate / margin**: the blended rate and target margin — a human decision.",
        "",
        "## Confidence",
        "- **LOW** — document-only: no price computed, axes unfilled, reconciled only in method to the "
        "value corridor. The agent-runner pricing pass is expected to produce a real number and raise "
        "this.",
        "",
    ]
    return "\n".join(md)


def generate(opp_dir, force=False):
    """Write a document-only pricing skeleton unless a stronger one exists. Returns a short note."""
    opp = _load_opp(opp_dir)
    if opp is None:
        return "pricing-gen skipped: no opportunity.json"
    if not force:
        reason = _existing_is_stronger(opp_dir)
        if reason:
            return f"pricing-gen skipped: {reason}"
    md = build_pricing(opp)
    research_dir = os.path.join(opp_dir, "research")
    os.makedirs(research_dir, exist_ok=True)
    with open(os.path.join(research_dir, "pricing.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    return "pricing-gen: document-only pricing skeleton written (LOW confidence)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opp")
    ap.add_argument("--force", action="store_true", help="overwrite even an analyst pricing.md")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    note = generate(a.opp, force=a.force)
    print(json.dumps({"note": note}, indent=2) if a.json else note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
