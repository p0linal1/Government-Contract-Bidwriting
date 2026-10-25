"""Tests for the document-only value GENERATOR (bidkit.gen_value).

The generator's job is to make the value field never blank: it mines figures already on disk and
writes an honest, LOW-confidence, document-only estimate — and it NEVER clobbers a stronger
(analyst/agent-runner) estimate. These tests prove: a thin opp gets an UNKNOWN/LOW estimate; a
figure on file produces a corridor; insurance/liability figures are not mistaken for contract
value; an existing anchor is left untouched; and the pass is idempotent. Offline, no network."""
import json
import pytest
from bidkit import gen_value


def _opp(tmp_path, opportunity, facts=None):
    d = tmp_path / "opp"
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    if facts is not None:
        (d / "opportunity-facts.json").write_text(json.dumps(facts), encoding="utf-8")
    return d


def _ve(d):
    return json.load(open(d / "opportunity.json", encoding="utf-8")).get("value_estimate") or {}


# --------------------------------------------------------------------------- thin opp
def test_thin_opp_gets_unknown_low_estimate(tmp_path):
    d = _opp(tmp_path, {"id": "a"})
    note = gen_value.generate(str(d))
    ve = _ve(d)
    assert ve["confidence"] == "LOW"
    assert ve["likely"] is None and "anchor" not in ve
    assert ve["generator"] == gen_value.GENERATOR_TAG
    assert "UNKNOWN" in note
    # the analysis doc exists, carries the document-only marker, and the four lines are honest UNKNOWNs
    md = (d / "research" / "value-analysis.md").read_text(encoding="utf-8")
    assert gen_value._MARKER in md
    assert "document-only" in md.lower()
    assert md.count("UNKNOWN") >= 4


# --------------------------------------------------------------------------- a real figure on file
def test_portal_estimated_value_becomes_corridor(tmp_path):
    d = _opp(tmp_path, {"id": "a", "portal_record": {"estimated_value": 500000,
                                                      "url": "https://portal.gov/bid/1"}})
    gen_value.generate(str(d))
    ve = _ve(d)
    assert ve["confidence"] == "LOW"                      # document-only is always LOW
    # a single figure becomes a wide band centered on it
    assert ve["low"] < 500000 < ve["high"]
    assert ve["likely"] == 500000
    md = (d / "research" / "value-analysis.md").read_text(encoding="utf-8")
    assert "$500,000" in md and "portal" in md.lower()


def test_facts_value_signals_build_a_spread_corridor(tmp_path):
    facts = {"money_value_signals": [
        {"kind": "value", "amount": 800000, "text": "$800k", "snippet": "contract value approx $800,000", "source": "rfp.pdf"},
        {"kind": "value", "amount": 1200000, "text": "$1.2M", "snippet": "not to exceed $1,200,000 over the term", "source": "rfp.pdf"},
    ]}
    d = _opp(tmp_path, {"id": "a"}, facts=facts)
    gen_value.generate(str(d))
    ve = _ve(d)
    assert ve["low"] == 800000 and ve["high"] == 1200000  # low..high from the spread
    assert ve["confidence"] == "LOW"


def test_insurance_figures_are_not_treated_as_value(tmp_path):
    # amounts tagged value but whose snippet is clearly an insurance/liability limit must be ignored
    facts = {"money": [
        {"kind": "value", "amount": 1000000, "text": "$1,000,000",
         "snippet": "Commercial General Liability $1,000,000 per occurrence", "source": "rfp.pdf"},
        {"kind": "value", "amount": 2000000, "text": "$2,000,000",
         "snippet": "Umbrella Liability $2,000,000 in aggregate", "source": "rfp.pdf"},
    ]}
    d = _opp(tmp_path, {"id": "a"}, facts=facts)
    gen_value.generate(str(d))
    ve = _ve(d)
    # all figures were insurance ⇒ nothing usable ⇒ honest UNKNOWN, not a bogus $1M-$2M corridor
    assert ve["likely"] is None


# --------------------------------------------------------------------------- non-destructive
def test_does_not_clobber_an_existing_anchor(tmp_path):
    strong = {"id": "a", "value_estimate": {
        "anchor": 1119683, "anchor_source": "https://city.gov/btip.pdf",
        "likely": 1600000, "confidence": "MEDIUM-HIGH", "basis": "four-line triangulation"}}
    d = _opp(tmp_path, strong)
    note = gen_value.generate(str(d))
    ve = _ve(d)
    assert ve["anchor"] == 1119683                        # untouched
    assert "generator" not in ve                          # not overwritten by the document-only pass
    assert "skipped" in note


def test_does_not_clobber_an_analyst_value_analysis(tmp_path):
    d = _opp(tmp_path, {"id": "a"})
    (d / "research").mkdir(parents=True)
    (d / "research" / "value-analysis.md").write_text(
        "# Value analysis\n\nAnalyst-written, no generator marker. Likely $2M.\n", encoding="utf-8")
    # a non-generator value_estimate also present
    opp = json.load(open(d / "opportunity.json"))
    opp["value_estimate"] = {"likely": 2000000, "confidence": "MEDIUM", "basis": "analyst"}
    (d / "opportunity.json").write_text(json.dumps(opp), encoding="utf-8")
    note = gen_value.generate(str(d))
    assert "skipped" in note
    md = (d / "research" / "value-analysis.md").read_text(encoding="utf-8")
    assert gen_value._MARKER not in md                    # analyst doc preserved


def test_force_overwrites(tmp_path):
    strong = {"id": "a", "value_estimate": {"anchor": 1119683, "anchor_source": "https://x", "likely": 1600000}}
    d = _opp(tmp_path, strong)
    gen_value.generate(str(d), force=True)
    ve = _ve(d)
    assert ve["generator"] == gen_value.GENERATOR_TAG     # forced document-only overwrite


# --------------------------------------------------------------------------- idempotent + self-owned
def test_idempotent_and_overwrites_its_own_prior_output(tmp_path):
    d = _opp(tmp_path, {"id": "a", "portal_record": {"estimated_value": 500000, "url": "https://p/1"}})
    gen_value.generate(str(d))
    first = _ve(d)
    # a second pass reproduces the same estimate (its own prior output is overwritable, not "stronger")
    gen_value.generate(str(d))
    second = _ve(d)
    assert first == second


def test_missing_opportunity_json_is_a_safe_noop(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    note = gen_value.generate(str(d))
    assert "no opportunity.json" in note


# --------------------------------------------------------------------------- build_analysis is pure
def test_build_analysis_is_pure_and_deterministic(tmp_path):
    opp = {"id": "a", "title": "Thing", "portal_record": {"estimated_value": 300000, "url": "https://p"}}
    ve1, md1 = gen_value.build_analysis(opp, {})
    ve2, md2 = gen_value.build_analysis(opp, {})
    assert ve1 == ve2 and md1 == md2                      # no hidden state / randomness
    assert ve1["likely"] == 300000


# --------------------------------------------------------------------------- write-back
def _opp_with_analysis(tmp_path, opportunity, analysis_md):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    (d / "research" / "value-analysis.md").write_text(analysis_md, encoding="utf-8")
    return d


def test_writeback_lifts_analyst_anchor_into_blank_canonical(tmp_path):
    analysis = ("# Value analysis\n\nThe anchor is the appropriation of $1,119,683, "
                "source https://city.gov/btip.pdf\n\n### Value estimate\n- Likely $1.6M\n"
                "- Overall confidence: MEDIUM-HIGH\n")
    d = _opp_with_analysis(tmp_path, {"id": "a"}, analysis)   # no value_estimate yet
    note = gen_value.writeback_from_analysis(str(d))
    assert "lifted analyst anchor" in note
    ve = _ve(d)
    assert ve["anchor"] == 1119683
    assert ve["anchor_source"] == "https://city.gov/btip.pdf"
    assert ve["confidence"] == "MEDIUM-HIGH"
    assert ve["writeback"] == gen_value.WRITEBACK_TAG


def test_writeback_lifts_likely_when_no_anchor(tmp_path):
    analysis = "# Value analysis\n\n### Value estimate\n- Likely ~$260k\n- Overall confidence: MEDIUM\n"
    d = _opp_with_analysis(tmp_path, {"id": "a"}, analysis)
    note = gen_value.writeback_from_analysis(str(d))
    assert "lifted analyst likely" in note
    ve = _ve(d)
    assert ve["likely"] == 260000 and ve["confidence"] == "MEDIUM"
    assert "anchor" not in ve


def test_writeback_noop_when_canonical_already_populated(tmp_path):
    analysis = "# Value analysis\n\n- Likely $1M\n- Overall confidence: HIGH\n"
    d = _opp_with_analysis(tmp_path, {"id": "a", "value_estimate": {"likely": 2000000}}, analysis)
    assert gen_value.writeback_from_analysis(str(d)) == ""        # does not overwrite
    assert _ve(d)["likely"] == 2000000


def test_writeback_noop_on_document_only_analysis(tmp_path):
    # a document-only generated analysis has no researched headline to lift
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps({"id": "a"}), encoding="utf-8")
    gen_value.generate(str(d))                                   # writes the document-only analysis
    # clear the canonical estimate but keep the document-only analysis
    oj = json.load(open(d / "opportunity.json")); oj.pop("value_estimate", None)
    (d / "opportunity.json").write_text(json.dumps(oj), encoding="utf-8")
    assert gen_value.writeback_from_analysis(str(d)) == ""        # refuses to lift from its own output


def test_generate_prefers_writeback_over_document_only(tmp_path):
    analysis = ("# Value analysis\n\nanchor $1,119,683 source https://city.gov/x.pdf\n"
                "- Overall confidence: HIGH\n")
    d = _opp_with_analysis(tmp_path, {"id": "a"}, analysis)
    note = gen_value.generate(str(d))                            # should write back, not doc-only
    assert "writeback" in note
    assert _ve(d)["anchor"] == 1119683
