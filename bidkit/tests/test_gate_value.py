"""Tests for the value-research gate (bidkit.gate_value). The central cases prove the
process-performed discipline (spec Req 2.3): a search that RAN and found nothing passes; a blank
with no evidence of a search fails."""
import json
import pytest
from bidkit import gate_value
from bidkit.evaluation import EvalContext


def _opp(tmp_path, va_text, opportunity=None):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity or {"id": "x"}), encoding="utf-8")
    if va_text is not None:
        (d / "research" / "value-analysis.md").write_text(va_text, encoding="utf-8")
    return EvalContext(str(d))


# a complete, well-sourced four-line analysis with an incumbent found
FULL_VA = """# Value analysis

## Line 1 — Buyer affordability
Adopted budget line $1,119,683, see https://city.gov/btip.pdf

## Line 2 — Buyer procurement thresholds (value floor)
Board-approval required above $50,000 per the purchasing policy https://city.gov/policy.pdf

## Line 3 — Comparable public awards + unit-rate proxy
Comparable EDMS award $1.2M at a peer city, https://peer.gov/award.pdf

## Line 4 — Bottom-up cost-to-deliver
Bottom-up blended-rate build ~$1.4M, capacity hours modeled.

## Incumbent
Incumbent is Acme Systems; prior contract ~$3M, council packet https://city.gov/packet.pdf

## Value estimate
- **Likely $1.6M**
- **Overall confidence: MEDIUM-HIGH**
"""

GOOD_OPP = {"id": "x", "value_estimate": {"anchor": 1_600_000, "anchor_source": "https://city.gov/btip.pdf",
                                          "likely": 1_600_000, "source": "research/value-analysis.md"}}


def test_full_analysis_passes(tmp_path):
    res = gate_value.gate(_opp(tmp_path, FULL_VA, GOOD_OPP))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_missing_value_analysis_fails_as_not_performed(tmp_path):
    res = gate_value.gate(_opp(tmp_path, None, GOOD_OPP))
    f = next(f for f in res.findings if f.check == "value-analysis-present")
    assert not f.ok and not f.performed


# ---- the Req 2.3 distinction on the incumbent hunt ----
def test_incumbent_searched_nothing_found_passes(tmp_path):
    va = FULL_VA.replace(
        "Incumbent is Acme Systems; prior contract ~$3M, council packet https://city.gov/packet.pdf",
        "Incumbent: searched council packets, Legistar, and the state portal; no public record of a prior award found.")
    # drop the HIGH-anchor dependency: confidence stays MEDIUM-HIGH; no incumbent $ so no consistency check
    res = gate_value.gate(_opp(tmp_path, va, GOOD_OPP))
    inc = next(f for f in res.findings if f.check == "incumbent-search")
    assert inc.ok and inc.performed
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_incumbent_blank_no_search_fails(tmp_path):
    # remove the incumbent section entirely ⇒ the hunt was not performed
    va = FULL_VA.replace(
        "## Incumbent\nIncumbent is Acme Systems; prior contract ~$3M, council packet https://city.gov/packet.pdf\n", "")
    res = gate_value.gate(_opp(tmp_path, va, GOOD_OPP))
    inc = next(f for f in res.findings if f.check == "incumbent-search")
    assert not inc.ok and not inc.performed


def test_a_value_line_blank_fails(tmp_path):
    # drop Line 3 (comparables) entirely
    va = (FULL_VA.split("## Line 3")[0]
          + "## Line 4 — Bottom-up cost-to-deliver\nBottom-up ~$1.4M.\n\n"
          + "## Incumbent\nnone, searched, no public record\n\n"
          + "## Value estimate\n- **Likely $1.6M**\n- confidence: MEDIUM\n")
    res = gate_value.gate(_opp(tmp_path, va, GOOD_OPP))
    f = next(f for f in res.findings if f.check == "line:comparable-awards")
    assert not f.ok and not f.performed


def test_high_confidence_without_anchor_fails(tmp_path):
    va = FULL_VA.replace("MEDIUM-HIGH", "HIGH").replace(
        "Incumbent is Acme Systems; prior contract ~$3M, council packet https://city.gov/packet.pdf",
        "Incumbent: no public prior-contract record found despite searching.")
    opp = {"id": "x", "value_estimate": {"likely": 1_600_000}}  # no sourced anchor
    res = gate_value.gate(_opp(tmp_path, va, opp))
    f = next(f for f in res.findings if f.check == "high-confidence-anchor")
    assert not f.ok


def test_high_confidence_with_anchor_passes(tmp_path):
    va = FULL_VA.replace("MEDIUM-HIGH", "HIGH")
    res = gate_value.gate(_opp(tmp_path, va, GOOD_OPP))
    f = next(f for f in res.findings if f.check == "high-confidence-anchor")
    assert f.ok


def test_unsourced_line_fails(tmp_path):
    va = FULL_VA.replace(
        "Adopted budget line $1,119,683, see https://city.gov/btip.pdf",
        "The budget is probably around a million.")   # no source, not UNKNOWN-with-reason
    res = gate_value.gate(_opp(tmp_path, va, GOOD_OPP))
    f = next(f for f in res.findings if f.check == "line:affordability")
    assert not f.ok


def test_no_confidence_stated_fails(tmp_path):
    va = FULL_VA.replace("- **Overall confidence: MEDIUM-HIGH**", "")
    res = gate_value.gate(_opp(tmp_path, va, GOOD_OPP))
    f = next(f for f in res.findings if f.check == "confidence-stated")
    assert not f.ok


def test_not_written_back_fails(tmp_path):
    res = gate_value.gate(_opp(tmp_path, FULL_VA, {"id": "x"}))  # no value_estimate
    f = next(f for f in res.findings if f.check == "value-written-back")
    assert not f.ok


def test_greenfield_no_incumbent_passes(tmp_path):
    """A performed hunt that concludes 'greenfield, no incumbent' (with the RFP as evidence) is a
    valid outcome and must PASS — and stray numbers in the prose (a year, an RFP number) must not
    be mistaken for an incumbent prior-$ anchor. Regression for the Springfield case."""
    va = FULL_VA.replace(
        "## Incumbent\nIncumbent is Acme Systems; prior contract ~$3M, council packet https://city.gov/packet.pdf",
        "## Incumbent\nNo unified ECM incumbent — greenfield. The RFP (10915-26, issued 2020-era policy) "
        "states there is no current citywide system; see rfp/main.pdf. N/A — no prior citywide ECM contract exists.")
    res = gate_value.gate(_opp(tmp_path, va, GOOD_OPP))
    inc = next(f for f in res.findings if f.check == "incumbent-search")
    assert inc.ok and inc.performed
    # the greenfield case must NOT trigger an incumbent-anchor-consistency check off stray numbers
    assert not any(f.check == "incumbent-anchor-consistency" for f in res.findings)
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_incumbent_outcome_in_findings_md_counts(tmp_path):
    """The incumbent hunt recorded in findings.md (not value-analysis.md) still counts as performed."""
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(GOOD_OPP), encoding="utf-8")
    va_no_inc = FULL_VA.replace(
        "## Incumbent\nIncumbent is Acme Systems; prior contract ~$3M, council packet https://city.gov/packet.pdf\n", "")
    (d / "research" / "value-analysis.md").write_text(va_no_inc, encoding="utf-8")
    (d / "research" / "findings.md").write_text(
        "## Incumbent\n- Vendor: searched Legistar and council packets; no public record found.\n", encoding="utf-8")
    res = gate_value.gate(EvalContext(str(d)))
    inc = next(f for f in res.findings if f.check == "incumbent-search")
    assert inc.ok and inc.performed


def test_registered_in_pipeline():
    from bidkit import evaluation as ev
    ev._load_gates()
    assert any(s.id == "value-research" and s.type == ev.RESEARCH for s in ev.ordered_stages())
