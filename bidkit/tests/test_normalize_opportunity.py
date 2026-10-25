"""Tests for normalize_opportunity + the defensive readers (P0).

The mode-c agent sometimes writes opportunity.json fields in richer-but-wrong shapes — a DICT
'recommendation', a prose/sentence 'anchor', a sentence 'status' — which crashed the deterministic
readers (re.search / int on a non-string). These prove the shapes are coerced losslessly and the
readers never raise. Offline."""
import json
from bidkit import opportunity_lint as L


def test_dict_recommendation_coerced_to_string():
    opp = {"id": "x", "recommendation": {"verdict": "CONDITIONAL-BID", "confidence": "MEDIUM",
                                         "conditions": ["team up"], "reasoning": "long prose"}}
    norm, reps = L.normalize_opportunity(opp)
    assert isinstance(norm["recommendation"], str) and "CONDITIONAL" in norm["recommendation"]
    assert norm["recommendation_detail"]["verdict"] == "CONDITIONAL-BID"   # detail preserved
    assert any("recommendation" in r for r in reps)


def test_prose_anchor_coerced_to_int_prose_preserved():
    opp = {"id": "x", "value_estimate": {"anchor": "incumbent prior contract ~$5.18M per packet",
                                         "confidence": "MEDIUM"}}
    norm, reps = L.normalize_opportunity(opp)
    assert norm["value_estimate"]["anchor"] == 5180000
    assert "5.18M" in norm["value_estimate"]["anchor_basis"]                # prose not lost
    assert any("anchor" in r for r in reps)


def test_unparseable_anchor_becomes_null():
    opp = {"id": "x", "value_estimate": {"anchor": "to be determined after site visit"}}
    norm, _ = L.normalize_opportunity(opp)
    assert norm["value_estimate"]["anchor"] is None


def test_transient_status_left_alone():
    # 'intake' is a legitimate short/transient status, not malformed — must NOT be coerced
    opp = {"id": "x", "status": "intake", "recommendation": "PASS"}
    norm, reps = L.normalize_opportunity(opp)
    assert norm["status"] == "intake"
    assert not any("status" in r for r in reps)


def test_prose_status_coerced():
    opp = {"id": "x", "status": "CANCELLED - monitor the portal for a reissue next cycle",
           "recommendation": "PASS — cancelled"}
    norm, reps = L.normalize_opportunity(opp)
    assert norm["status"] == "pass"
    assert norm["status_detail"].startswith("CANCELLED")
    assert any("status" in r for r in reps)


def test_wellformed_opp_unchanged_and_idempotent():
    opp = {"id": "x", "status": "bid", "recommendation": "BID — strong anchor",
           "value_estimate": {"anchor": 1119683, "confidence": "HIGH"}}
    norm, reps = L.normalize_opportunity(opp)
    assert reps == []
    norm2, reps2 = L.normalize_opportunity(norm)
    assert reps2 == [] and norm2 == norm


def test_non_dict_input_safe():
    assert L.normalize_opportunity(None) == (None, [])
    assert L.normalize_opportunity("oops")[1] == []


# ---- defensive readers never raise on the bad shapes -------------------------------------------
def test_parse_recommendation_accepts_dict():
    assert L.parse_recommendation({"verdict": "no-bid"}) == "pass"
    assert L.parse_recommendation({"summary": "we recommend a conditional bid"}) == "conditional"
    assert L.parse_recommendation({"nothing": "here"}) is None   # no crash


def test_parse_money_accepts_number_and_nonstring():
    assert L.parse_money(1119683) == 1119683
    assert L.parse_money(500) is None            # sub-$1k not a contract value
    assert L.parse_money(True) is None           # bool is not a figure
    assert L.parse_money(["weird"]) is None       # no crash on a list


def test_normalize_dir_persists_and_is_idempotent(tmp_path):
    d = tmp_path / "opp"; d.mkdir()
    (d / "opportunity.json").write_text(json.dumps(
        {"id": "x", "recommendation": {"verdict": "BID"}}), encoding="utf-8")
    reps = L.normalize_dir(str(d))
    assert reps                                   # repaired
    on_disk = json.load(open(d / "opportunity.json"))
    assert on_disk["recommendation"] == "BID"
    assert L.normalize_dir(str(d)) == []          # second pass: nothing to do
