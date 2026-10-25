"""Tests for the document-only verdict GENERATOR (bidkit.gen_gonogo). It writes ONLY
research/go-no-go.md (a LOW-confidence PROVISIONAL verdict citing upstream + conditions) and MUST
NEVER touch the canonical judgment fields opportunity.json status / recommendation. Offline."""
import json
import pytest
from bidkit import gen_gonogo


def _opp(tmp_path, opportunity, gonogo_md=None, summary_md=None):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    if gonogo_md is not None:
        (d / "research" / "go-no-go.md").write_text(gonogo_md, encoding="utf-8")
    if summary_md is not None:
        (d / "opportunity-summary.md").write_text(summary_md, encoding="utf-8")
    return d


def test_writes_provisional_verdict_citing_upstream(tmp_path):
    d = _opp(tmp_path, {"id": "a", "title": "A System",
                        "value_estimate": {"anchor": 1119683, "confidence": "MEDIUM-HIGH"}})
    note = gen_gonogo.generate(str(d))
    assert "written" in note
    md = (d / "research" / "go-no-go.md").read_text(encoding="utf-8")
    assert gen_gonogo._MARKER in md
    assert "CONDITIONAL-BID" in md
    for cue in ("Value", "Pricing", "Fit"):     # cites each upstream stage
        assert cue in md
    assert "$1,119,683" in md                    # the value headline is carried in


def test_never_writes_canonical_judgment_fields(tmp_path):
    d = _opp(tmp_path, {"id": "a", "status": "intake"})
    gen_gonogo.generate(str(d))
    oj = json.load(open(d / "opportunity.json", encoding="utf-8"))
    assert oj.get("status") == "intake"          # unchanged
    assert "recommendation" not in oj            # never written by the document-only generator


def test_stands_aside_for_analyst_gonogo(tmp_path):
    analyst = "# Go/no-go\n\nDECISION: BID — positive expected value.\n"
    d = _opp(tmp_path, {"id": "a"}, gonogo_md=analyst)
    note = gen_gonogo.generate(str(d))
    assert "skipped" in note
    assert (d / "research" / "go-no-go.md").read_text(encoding="utf-8") == analyst


def test_stands_aside_when_summary_has_recommendation(tmp_path):
    # a recommendation already in the summary would make a provisional verdict a false disagreement
    d = _opp(tmp_path, {"id": "a"}, summary_md="**Recommendation: PASS** — out of scope.\n")
    note = gen_gonogo.generate(str(d))
    assert "skipped" in note
    assert not (d / "research" / "go-no-go.md").exists()


def test_idempotent(tmp_path):
    d = _opp(tmp_path, {"id": "a", "value_estimate": {"likely": 500000}})
    gen_gonogo.generate(str(d))
    first = (d / "research" / "go-no-go.md").read_text(encoding="utf-8")
    gen_gonogo.generate(str(d))
    assert (d / "research" / "go-no-go.md").read_text(encoding="utf-8") == first


def test_missing_opportunity_json_is_safe_noop(tmp_path):
    d = tmp_path / "empty"; d.mkdir()
    assert "no opportunity.json" in gen_gonogo.generate(str(d))
