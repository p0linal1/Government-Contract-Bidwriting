"""Tests for the document-only fit-synthesis GENERATOR (bidkit.gen_fit). It writes a LOW-confidence
fit synthesis (RFP-wants, >=2 candidate configs, selected config, competitiveness, honesty framing,
conflict surfaced), stays company-agnostic (capability path is config, never hardcoded), and stands
aside for analyst work. Offline, no network."""
import json
import pytest
from bidkit import gen_fit, gate_fit
from bidkit.evaluation import EvalContext, LOW


def _opp(tmp_path, opportunity, facts=None, fit_md=None):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    if facts is not None:
        (d / "opportunity-facts.json").write_text(json.dumps(facts), encoding="utf-8")
    if fit_md is not None:
        (d / "research" / "fit-synthesis.md").write_text(fit_md, encoding="utf-8")
    return d


def _capfile(tmp_path):
    p = tmp_path / "capability.json"
    p.write_text(json.dumps({
        "core_capabilities": ["Custom Software Development", "SaaS Solutions", "API Development"],
        "past_performance": [{"name": "ProjectX", "scope": "a web platform"}],
    }), encoding="utf-8")
    return str(p)


def test_writes_synthesis_with_two_configs(tmp_path):
    d = _opp(tmp_path, {"id": "a", "title": "A System"})
    note = gen_fit.generate(str(d), capability_path=_capfile(tmp_path))
    assert "written" in note
    md = (d / "research" / "fit-synthesis.md").read_text(encoding="utf-8")
    assert gen_fit._MARKER in md
    assert "Configuration A" in md and "Configuration B" in md   # >=2 candidate configs
    assert "transferable" in md.lower()                          # honest prior-performance framing


def test_skeleton_grades_low(tmp_path):
    d = _opp(tmp_path, {"id": "a", "title": "A System"})
    gen_fit.generate(str(d), capability_path=_capfile(tmp_path))
    res = gate_fit.gate(EvalContext(str(d)))
    assert res.confidence == LOW


def test_locality_conflict_is_surfaced_not_resolved(tmp_path):
    facts = {"money": [], "evaluation": [], "research_keywords": ["on-site weekly in Springfield"]}
    d = _opp(tmp_path, {"id": "a", "title": "On-site conversion"}, facts=facts)
    gen_fit.generate(str(d), capability_path=_capfile(tmp_path))
    md = (d / "research" / "fit-synthesis.md").read_text(encoding="utf-8").lower()
    assert "human decision" in md and ("on-site" in md or "locality" in md)


def test_bid_agnostic_without_capability_file(tmp_path):
    # with no capability file the synthesis still considers >=2 configs (generic)
    d = _opp(tmp_path, {"id": "a", "title": "A System"})
    note = gen_fit.generate(str(d))               # no capability_path, no capability_file key
    assert "generic configs" in note
    md = (d / "research" / "fit-synthesis.md").read_text(encoding="utf-8")
    assert "Configuration A" in md and "Configuration B" in md


def test_capability_file_key_from_opportunity(tmp_path):
    cap = _capfile(tmp_path)
    d = _opp(tmp_path, {"id": "a", "title": "A System", "capability_file": cap})
    note = gen_fit.generate(str(d))               # resolves the path from opportunity.json
    assert "with capability superset" in note


def test_non_destructive_analyst_fit(tmp_path):
    analyst = "# Fit\n\nCandidate configuration 1 ... competitiveness assessed against the incumbent.\n"
    d = _opp(tmp_path, {"id": "a"}, fit_md=analyst)
    note = gen_fit.generate(str(d), capability_path=_capfile(tmp_path))
    assert "skipped" in note
    assert (d / "research" / "fit-synthesis.md").read_text(encoding="utf-8") == analyst


def test_missing_opportunity_json_is_safe_noop(tmp_path):
    d = tmp_path / "empty"; d.mkdir()
    assert "no opportunity.json" in gen_fit.generate(str(d))
