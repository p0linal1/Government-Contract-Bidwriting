"""Tests for the pricing gate (bidkit.gate_pricing)."""
import json
import pytest
from bidkit import gate_pricing
from bidkit.evaluation import EvalContext


def _opp(tmp_path, pricing_md=None, go_no_go=None, summary=None, opportunity=None):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity or {"id": "x"}), encoding="utf-8")
    if pricing_md is not None:
        (d / "research" / "pricing.md").write_text(pricing_md, encoding="utf-8")
    if go_no_go is not None:
        (d / "research" / "go-no-go.md").write_text(go_no_go, encoding="utf-8")
    if summary is not None:
        (d / "opportunity-summary.md").write_text(summary, encoding="utf-8")
    return EvalContext(str(d))


FULL_PRICING = """# Pricing

Three-axis reconciliation: raw scope labor hours 22,170; team capacity = 5 developers x 65 weeks
x 40 hrs = 13,000 capacity hours over the mandated schedule. AI acceleration applied as a
compression factor x0.586 (fewer hours, not a discounted rate).

Recurring: $360k/yr = cloud hosting (infra) $108k + support labor/maintenance $252k, with margin
retained. Reserved/savings-plan capacity committed.

The priced 5-yr TCO reconciles against the value corridor / budget anchor from value-analysis.md.
Final scope confirmed; blended rate and margin accepted by the principal.
"""


def test_full_pricing_passes(tmp_path):
    res = gate_pricing.gate(_opp(tmp_path, pricing_md=FULL_PRICING))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_missing_pricing_record_fails(tmp_path):
    res = gate_pricing.gate(_opp(tmp_path))
    f = next(f for f in res.findings if f.check == "pricing-record")
    assert not f.ok and not f.performed


def test_incomplete_reconciliation_fails(tmp_path):
    # mentions hours but no capacity/schedule
    md = "We estimate about 10,000 labor hours of effort. Price is $2M."
    res = gate_pricing.gate(_opp(tmp_path, pricing_md=md))
    f = next(f for f in res.findings if f.check == "three-axis-reconciliation")
    assert not f.ok


def test_ai_as_discounted_rate_fails(tmp_path):
    # AI framed as a rate discount with NO compression-factor language anywhere
    md = ("Three-axis: labor hours 10,000; capacity 5 developers x 50 weeks; mandated schedule.\n"
          "We offer a lower rate thanks to AI (a discounted rate).\n"
          "Recurring $300k/yr: hosting infra + support labor/maintenance + margin.\n"
          "Reconciled to the value corridor/budget. Reserved capacity committed; scope and rate accepted.")
    res = gate_pricing.gate(_opp(tmp_path, pricing_md=md))
    f = next(f for f in res.findings if f.check == "ai-as-compression")
    assert not f.ok and f.blocking_failure


def test_recurring_missing_margin_fails(tmp_path):
    # recurring with infra + support labor but NO margin, and no 'margin'/'profit' word anywhere
    md = ("Three-axis: labor hours 10,000; capacity 5 developers x 50 weeks; mandated schedule.\n"
          "AI acceleration as a compression factor (fewer hours).\n"
          "Recurring $300k/yr: cloud hosting infra + support labor/maintenance.\n"
          "Reconciled to the value corridor/budget. Reserved capacity committed; scope confirmed.")
    res = gate_pricing.gate(_opp(tmp_path, pricing_md=md))
    f = next(f for f in res.findings if f.check == "recurring-bottom-up")
    assert not f.ok and "margin" in f.message


def test_no_corridor_reconciliation_fails(tmp_path):
    md = FULL_PRICING.replace(
        "The priced 5-yr TCO reconciles against the value corridor / budget anchor from value-analysis.md.", "")
    res = gate_pricing.gate(_opp(tmp_path, pricing_md=md))
    f = next(f for f in res.findings if f.check == "reconciled-to-corridor")
    assert not f.ok


def test_falls_back_to_go_no_go(tmp_path):
    # no pricing.md, but go-no-go has the full posture
    res = gate_pricing.gate(_opp(tmp_path, go_no_go=FULL_PRICING))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_registered_before_fit():
    from bidkit import evaluation as ev
    ev._load_gates()
    ids = [s.id for s in ev.ordered_stages()]
    assert "pricing" in ids
    # pricing must come before fit (when fit is registered)
    if "fit" in ids:
        assert ids.index("pricing") < ids.index("fit")
