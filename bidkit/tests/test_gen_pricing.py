"""Tests for the document-only pricing GENERATOR (bidkit.gen_pricing). It writes a LOW-confidence
pricing SKELETON reconciled to the value corridor, never a computed price, and stands aside for
analyst work. Offline, no network."""
import json
import pytest
from bidkit import gen_pricing, gate_pricing
from bidkit.evaluation import EvalContext, LOW


def _opp(tmp_path, opportunity, pricing_md=None, gonogo_md=None):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    if pricing_md is not None:
        (d / "research" / "pricing.md").write_text(pricing_md, encoding="utf-8")
    if gonogo_md is not None:
        (d / "research" / "go-no-go.md").write_text(gonogo_md, encoding="utf-8")
    return d


def test_writes_skeleton_reconciled_to_corridor(tmp_path):
    d = _opp(tmp_path, {"id": "a", "value_estimate": {"low": 900000, "likely": 1600000,
                                                      "high": 2600000, "confidence": "MEDIUM"}})
    note = gen_pricing.generate(str(d))
    assert "written" in note
    md = (d / "research" / "pricing.md").read_text(encoding="utf-8")
    assert gen_pricing._MARKER in md
    assert "$1,600,000" in md                 # reconciled to the corridor likely
    assert "compression factor" in md.lower() # AI framed as compression, not a discounted rate


def test_skeleton_grades_low(tmp_path):
    d = _opp(tmp_path, {"id": "a", "value_estimate": {"likely": 1000000, "confidence": "MEDIUM"}})
    gen_pricing.generate(str(d))
    res = gate_pricing.gate(EvalContext(str(d)))
    assert res.confidence == LOW               # a document-only skeleton is never more than LOW


def test_no_corridor_still_writes_unknown_skeleton(tmp_path):
    d = _opp(tmp_path, {"id": "a"})            # no value_estimate at all
    gen_pricing.generate(str(d))
    md = (d / "research" / "pricing.md").read_text(encoding="utf-8")
    assert "UNKNOWN" in md and gen_pricing._MARKER in md


def test_non_destructive_analyst_pricing(tmp_path):
    analyst = "# Pricing\n\nThree-axis build: 4000 labor hours at a blended rate; recurring $200k/yr.\n"
    d = _opp(tmp_path, {"id": "a", "value_estimate": {"likely": 1000000}}, pricing_md=analyst)
    note = gen_pricing.generate(str(d))
    assert "skipped" in note
    assert (d / "research" / "pricing.md").read_text(encoding="utf-8") == analyst  # untouched


def test_stands_aside_when_real_pricing_in_gonogo(tmp_path):
    gng = "# Go/no-go\n\nPricing: ~4000 labor hours; recurring $220k/yr incl. margin; TCO reconciled.\n"
    d = _opp(tmp_path, {"id": "a", "value_estimate": {"likely": 1000000}}, gonogo_md=gng)
    note = gen_pricing.generate(str(d))
    assert "skipped" in note
    assert not (d / "research" / "pricing.md").exists()   # no clutter skeleton written


def test_idempotent(tmp_path):
    d = _opp(tmp_path, {"id": "a", "value_estimate": {"likely": 1000000}})
    gen_pricing.generate(str(d))
    first = (d / "research" / "pricing.md").read_text(encoding="utf-8")
    gen_pricing.generate(str(d))
    assert (d / "research" / "pricing.md").read_text(encoding="utf-8") == first


def test_missing_opportunity_json_is_safe_noop(tmp_path):
    d = tmp_path / "empty"; d.mkdir()
    assert "no opportunity.json" in gen_pricing.generate(str(d))
