"""Tests for the write-back consistency linter (bidkit.opportunity_lint). Fixtures are built
in tmp_path so no real bid data is touched."""
import json, os
import pytest
from bidkit import opportunity_lint as lint


# --------------------------------------------------------------- money normalizer
@pytest.mark.parametrize("text,expected", [
    ("$1.6M", 1_600_000),
    ("1,600,000", 1_600_000),
    ("~$1.12M", 1_120_000),
    ("1119683", 1_119_683),
    ("$500k", 500_000),
    ("4 lines of research", None),      # bare small number is not a value
    ("", None),
])
def test_parse_money(text, expected):
    assert lint.parse_money(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Recommendation: PASS — borderline", "pass"),
    ("**Recommendation: BID**", "bid"),
    ("## Recommendation\n**CONDITIONAL-BID** pending staffing", "conditional"),
    ("## 5. Recommendation\n**Qualified BID — but only after the decision**", "conditional"),
    ("## Recommendation: **PASS** (decline / no-bid)", "pass"),
    ("DECISION: BID — positive expected value", "bid"),
    ("## Recommendation (revised)\n**NO-BID as currently staffed**", "pass"),
    ("Recommendation: partner with a prime", "partner"),
    ("Recommendation: foothold bid for the vehicle", "foothold"),
    # a stray verb in unrelated prose, with NO recommendation section, must NOT be picked up
    ("The vendor will pass the data through; we build the API.", None),
    ("nothing decisive", None),
])
def test_parse_recommendation(text, expected):
    assert lint.parse_recommendation(text) == expected


# --------------------------------------------------------------- fixture builder
def _opp(tmp_path, name, opportunity, files=None):
    d = tmp_path / name
    (d / "rfp").mkdir(parents=True)
    (d / "research").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return str(d)


CLEAN_OPP = {
    "id": "clean", "status": "bid",
    "value_estimate": {"anchor": 1_119_683, "anchor_source": "https://city.gov/btip.pdf",
                       "likely": 1_600_000},
    "due": {"confirmed": True, "source": "RFP Section 2.4"},
}
CLEAN_VA = "### Value estimate\n- anchor ~$1.12M from the adopted BTIP line\n- **Likely $1.6M**\n"
CLEAN_SUMMARY = "**Recommendation: BID.** Value ~$1.6M (research/value-analysis.md).\n"
CLEAN_GNG = "Recommendation: BID — the corridor supports it.\n"


def test_clean_opp_passes(tmp_path):
    d = _opp(tmp_path, "clean", CLEAN_OPP, {
        "research/value-analysis.md": CLEAN_VA,
        "opportunity-summary.md": CLEAN_SUMMARY,
        "research/go-no-go.md": CLEAN_GNG,
    })
    res = lint.lint_dir(d)
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_value_mismatch_fails(tmp_path):
    opp = dict(CLEAN_OPP)
    opp["value_estimate"] = {"anchor": 2_600_000, "anchor_source": "x.pdf", "likely": 2_600_000}
    d = _opp(tmp_path, "drift", opp, {"research/value-analysis.md": CLEAN_VA})
    res = lint.lint_dir(d)
    f = next(f for f in res.findings if f.check == "value-consistency")
    assert not f.ok and f.blocking_failure


def test_anchor_without_source_fails(tmp_path):
    opp = dict(CLEAN_OPP)
    opp["value_estimate"] = {"anchor": 1_119_683, "likely": 1_600_000}  # no anchor_source
    d = _opp(tmp_path, "nosrc", opp, {"research/value-analysis.md": CLEAN_VA})
    res = lint.lint_dir(d)
    f = next(f for f in res.findings if f.check == "value-anchor-provenance")
    assert not f.ok


def test_due_confirmed_without_source_fails(tmp_path):
    opp = dict(CLEAN_OPP)
    opp["due"] = {"confirmed": True}  # no source
    d = _opp(tmp_path, "due", opp)
    res = lint.lint_dir(d)
    f = next(f for f in res.findings if f.check == "due-provenance")
    assert not f.ok and f.blocking_failure


def test_recommendation_mismatch_fails(tmp_path):
    d = _opp(tmp_path, "recmm", CLEAN_OPP, {
        "opportunity-summary.md": "**Recommendation: BID.**",
        "research/go-no-go.md": "Recommendation: PASS.",
    })
    res = lint.lint_dir(d)
    f = next(f for f in res.findings if f.check == "recommendation-consistency")
    assert not f.ok


def test_status_contradicts_recommendation_fails(tmp_path):
    opp = dict(CLEAN_OPP); opp["status"] = "bid"
    d = _opp(tmp_path, "status", opp, {"opportunity-summary.md": "**Recommendation: PASS.**"})
    res = lint.lint_dir(d)
    f = next(f for f in res.findings if f.check == "status-consistency")
    assert not f.ok


def test_portal_record_count_mismatch_fails(tmp_path):
    opp = dict(CLEAN_OPP)
    opp["portal_record"] = {"documents": 5, "amendments": 1}
    pr = [{"documents": [{"name": "a.pdf"}, {"name": "b.pdf"}],
           "amendments": [{"name": "c.pdf"}, {"name": "d.pdf"}, {"name": "e.pdf"}]}]
    d = _opp(tmp_path, "portal", opp, {"rfp/portal-record.json": json.dumps(pr)})
    res = lint.lint_dir(d)
    f = next(f for f in res.findings if f.check == "portal-record-consistency")
    assert not f.ok and ("amendments" in f.message)


def test_summary_value_without_source_warns(tmp_path):
    d = _opp(tmp_path, "warn", CLEAN_OPP, {
        "opportunity-summary.md": "The contract is worth about $1,600,000 total.\n",
    })
    res = lint.lint_dir(d)
    f = next(f for f in res.findings if f.check == "summary-cites-sources")
    assert not f.ok and f.severity == lint.WARN and not f.blocking_failure


def test_missing_inputs_skip_not_fail(tmp_path):
    # only opportunity.json, no derived artifacts ⇒ no hard failures
    d = _opp(tmp_path, "bare", {"id": "bare"})
    res = lint.lint_dir(d)
    assert res.passed


def test_cli_exit_nonzero_on_drift(tmp_path, capsys):
    opp = dict(CLEAN_OPP)
    opp["value_estimate"] = {"anchor": 2_600_000, "anchor_source": "x.pdf", "likely": 2_600_000}
    d = _opp(tmp_path, "drift", opp, {"research/value-analysis.md": CLEAN_VA})
    rc = lint.main([d])
    assert rc == 1
