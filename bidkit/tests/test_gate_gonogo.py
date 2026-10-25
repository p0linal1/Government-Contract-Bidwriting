"""Tests for the go/no-go verdict gate (bidkit.gate_gonogo) — synthesis + reconciliation."""
import json
import pytest
from bidkit import gate_gonogo
from bidkit.evaluation import EvalContext


# A fully-passing upstream so the proceed-verdict tests isolate the go/no-go logic.
GOOD_OPP = {"id": "x", "status": "bid",
            "due": {"confirmed": True, "source": "RFP Section 2.4"},
            "format": {"page_limit": 50, "min_font_pt": 10, "page_size": "letter", "font_family_allow": ["Arial"]},
            "value_estimate": {"anchor": 1_600_000, "anchor_source": "https://city.gov/btip.pdf",
                               "likely": 1_600_000, "source": "research/value-analysis.md"}}

VALUE_ANALYSIS = """# Value
## Line 1 — affordability
Adopted budget $1.6M, https://city.gov/btip.pdf
## Line 2 — procurement thresholds
Board approval above $50k, https://city.gov/policy.pdf
## Line 3 — comparable awards
Comparable $1.4M, https://peer.gov/a.pdf
## Line 4 — cost-to-deliver
Bottom-up blended-rate build modeled.
## Incumbent
Greenfield; searched, no public record of a prior award.
## Value estimate
- **Likely $1.6M**
- confidence: MEDIUM-HIGH
"""

PRICING_FIT = """# Pricing & fit
Three-axis: labor hours; capacity 5 developers x 60 weeks; mandated schedule. AI acceleration as a
compression factor. Recurring $300k/yr: hosting infra + support labor + margin. Reconciled to the
value corridor/budget. Reserved capacity committed; scope and rate accepted.

## What the RFP wants
Evaluator scoring weights favor fit + references.
## Candidate configurations
- Option A: solo US + AI build (no offshore)
- Option B: offshore team
## Selected configuration
Selected Option A because it maximally matches the scoring and removes offshore risk. The offshore
staffing/locality question is flagged as a human-decision / open item for the principal to decide.
## Competitiveness
Competitive on price and local presence.
## Prior performance
Portfolio offered as transferable/adjacent experience plus net-new build scope, with a reference-gap note.
"""


def _opp(tmp_path, verdict_md, opportunity=None, value=VALUE_ANALYSIS, pricingfit=PRICING_FIT,
         summary_rec=None):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "rfp" / "main.pdf").write_text("x", encoding="utf-8")
    (d / "opportunity.json").write_text(json.dumps(opportunity or GOOD_OPP), encoding="utf-8")
    (d / "research" / "value-analysis.md").write_text(value, encoding="utf-8")
    if pricingfit:
        (d / "research" / "pricing.md").write_text(pricingfit, encoding="utf-8")
        (d / "research" / "fit-synthesis.md").write_text(pricingfit, encoding="utf-8")
    (d / "research" / "go-no-go.md").write_text(verdict_md, encoding="utf-8")
    # keep the summary recommendation consistent with the verdict for the reconciliation check
    (d / "opportunity-summary.md").write_text(summary_rec or verdict_md, encoding="utf-8")
    return EvalContext(str(d))


REASONED_BID = """# Go / No-Go
**DECISION: BID** — positive expected value. Given the value corridor (~$1.6M anchor) and our
cost-to-deliver/pricing within it, and the selected fit configuration (solo US + AI) assessed as
competitive, we bid.
Recommendation: BID
"""


def test_reasoned_bid_passes(tmp_path):
    res = gate_gonogo.gate(_opp(tmp_path, REASONED_BID))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_no_verdict_fails(tmp_path):
    res = gate_gonogo.gate(_opp(tmp_path, "# Notes\nSome analysis with no recommendation section.\n",
                                summary_rec="# Notes\nno rec here\n"))
    f = next(f for f in res.findings if f.check in ("verdict-stated", "verdict-record"))
    assert not f.ok


def test_unreasoned_label_fails_cites_upstream(tmp_path):
    md = "# Go/No-Go\nRecommendation: BID\nIt looks good, let's go for it.\n"
    res = gate_gonogo.gate(_opp(tmp_path, md))
    f = next(f for f in res.findings if f.check == "cites-upstream")
    assert not f.ok and f.blocking_failure


def test_bid_on_incomplete_upstream_caps_confidence_not_blocks(tmp_path):
    # thin value research ⇒ the verdict is still PRODUCED (BID), but its confidence is capped LOW
    # by the low-confidence upstream — not withheld (spec Req 5a.2).
    from bidkit.evaluation import LOW
    bad_value = "# Value\n## affordability\nprobably about a million\n## cost-to-deliver\nmodeled\n## Value estimate\n- Likely $1M\n- confidence: LOW\n"
    res = gate_gonogo.gate(_opp(tmp_path, REASONED_BID, value=bad_value))
    # the verdict was still stated (not blocked)
    assert any(f.check == "verdict-stated" and f.ok for f in res.findings)
    # confidence is capped LOW by the weak upstream
    f = next(f for f in res.findings if f.check == "upstream-confidence")
    assert not f.ok and "capped" in f.message
    assert res.confidence == LOW


def test_conditional_without_conditions_fails(tmp_path):
    md = ("# Go/No-Go\nRecommendation: CONDITIONAL-BID\nGiven the value corridor, our pricing/cost, "
          "and the selected fit configuration's competitiveness, we lean bid.\n")
    res = gate_gonogo.gate(_opp(tmp_path, md, summary_rec="Recommendation: CONDITIONAL-BID\n"))
    f = next(f for f in res.findings if f.check == "conditions-stated")
    assert not f.ok


def test_conditional_with_conditions_passes_that_check(tmp_path):
    md = ("# Go/No-Go\nRecommendation: CONDITIONAL-BID — conditional on the staffing decision; only if "
          "the two-on-site requirement is resolved. Given the value corridor, our pricing/cost, and the "
          "selected fit configuration's competitiveness.\n")
    res = gate_gonogo.gate(_opp(tmp_path, md, summary_rec="Recommendation: CONDITIONAL-BID conditional on staffing\n"))
    f = next(f for f in res.findings if f.check == "conditions-stated")
    assert f.ok


def test_foothold_requires_basis(tmp_path):
    md = ("# Go/No-Go\nRecommendation: FOOTHOLD — conditional on the vehicle; depends on utilization. "
          "Given the value corridor, pricing/cost, and the selected fit configuration competitiveness.\n")
    res = gate_gonogo.gate(_opp(tmp_path, md, summary_rec="Recommendation: FOOTHOLD depends on utilization\n"))
    basis = next(f for f in res.findings if f.check == "basis-of-bid-stated")
    assert basis.ok  # 'foothold'/'strategic'/'revenue' basis cue present via 'foothold'


def test_well_founded_pass_passes(tmp_path):
    md = ("# Go/No-Go\nRecommendation: PASS — not competitive. Given the value corridor is thin, our "
          "cost-to-deliver, and the selected fit configuration would not win against in-domain incumbents.\n")
    opp = dict(GOOD_OPP); opp["status"] = "pass"
    res = gate_gonogo.gate(_opp(tmp_path, md, opportunity=opp,
                                summary_rec="Recommendation: PASS — not competitive\n"))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_reconciliation_mismatch_fails(tmp_path):
    # go-no-go says BID but the summary says PASS ⇒ recommendation-consistency hard fail
    res = gate_gonogo.gate(_opp(tmp_path, REASONED_BID,
                                summary_rec="Recommendation: PASS — decline\n"))
    f = next(f for f in res.findings if f.check == "reconcile:recommendation-consistency")
    assert not f.ok


def test_registered_last():
    from bidkit import evaluation as ev
    ev._load_gates()
    ids = [s.id for s in ev.ordered_stages()]
    assert ids[-1] == "go-no-go"
    assert any(s.id == "go-no-go" and s.type == ev.SYNTHESIS for s in ev.ordered_stages())
