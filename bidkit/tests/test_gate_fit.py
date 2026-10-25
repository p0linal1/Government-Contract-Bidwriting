"""Tests for the fit-&-winnability synthesis gate (bidkit.gate_fit). Central cases: the gate
requires a SYNTHESIS (not a single assumed structure) and treats a well-founded PASS as valid."""
import json
import pytest
from bidkit import gate_fit
from bidkit.evaluation import EvalContext


def _opp(tmp_path, fit_md=None, go_no_go=None, summary=None):
    d = tmp_path / "opp"
    (d / "research").mkdir(parents=True)
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    if fit_md is not None:
        (d / "research" / "fit-synthesis.md").write_text(fit_md, encoding="utf-8")
    if go_no_go is not None:
        (d / "research" / "go-no-go.md").write_text(go_no_go, encoding="utf-8")
    if summary is not None:
        (d / "opportunity-summary.md").write_text(summary, encoding="utf-8")
    return EvalContext(str(d))


FULL_FIT = """# Fit synthesis

## What the RFP is looking for
The evaluator priorities: 55 of 100 scoring points on demonstrated fit + references; strong risk
posture on data handling; local presence is weighted.

## Candidate configurations
- Option A: US-only solo principal + AI-accelerated build (no offshore; smallest compliance surface)
- Option B: US principal + offshore development team (more capacity, offshore-access risk)
- Option C: teaming with a prime that holds in-domain references

## Selected configuration
Selected best-fit: Option A (US-only solo + AI build), chosen because the RFP scores local presence
and data-handling risk heavily, and this configuration maximally marketable here — it removes the
offshore-access risk and leans on the resident-principal local advantage.

## Competitiveness
This configuration would be competitive: it beats COTS on price and differentiates on local
presence, though the reference gap against in-domain turnkey deployments is a real risk.

## Prior performance
Portfolio items are offered as transferable/adjacent experience plus net-new build scope, with an
explicit reference-gap note (no in-domain turnkey deployment).
"""


def test_full_synthesis_passes(tmp_path):
    res = gate_fit.gate(_opp(tmp_path, fit_md=FULL_FIT))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_missing_fit_record_fails(tmp_path):
    res = gate_fit.gate(_opp(tmp_path))
    f = next(f for f in res.findings if f.check == "fit-record")
    assert not f.ok and not f.performed


def test_single_config_assumed_fails(tmp_path):
    # jumps straight to one structure with no alternatives considered
    md = ("## What the RFP wants\nScoring weights favor local presence.\n"
          "## Selected configuration\nWe will present a US principal + offshore team because it gives capacity.\n"
          "## Competitiveness\nThis would be competitive on price.\n")
    res = gate_fit.gate(_opp(tmp_path, fit_md=md))
    f = next(f for f in res.findings if f.check == "candidate-configs")
    assert not f.ok


def test_selection_without_reasoning_fails(tmp_path):
    md = ("## What the RFP wants\nScoring weights, evaluator priorities noted.\n"
          "## Candidate configurations\n- Option A: solo + AI\n- Option B: offshore team\n"
          "## Selected configuration\nSelected: Option A.\n"   # no reasoning
          "## Competitiveness\nCompetitive on price.\n")
    res = gate_fit.gate(_opp(tmp_path, fit_md=md))
    f = next(f for f in res.findings if f.check == "selected-config")
    assert not f.ok


def test_no_competitiveness_fails(tmp_path):
    md = FULL_FIT.replace(
        "## Competitiveness\nThis configuration would be competitive: it beats COTS on price and differentiates on local\npresence, though the reference gap against in-domain turnkey deployments is a real risk.\n", "")
    res = gate_fit.gate(_opp(tmp_path, fit_md=md))
    f = next(f for f in res.findings if f.check == "competitiveness-assessed")
    assert not f.ok


def test_locality_conflict_unsurfaced_fails(tmp_path):
    # an offshore conflict is present but silently resolved (no human-decision/surface language)
    md = ("## What the RFP wants\nScoring favors local presence; evaluator priorities noted.\n"
          "## Candidate configurations\n- Option A: solo US\n- Option B: offshore team\n"
          "## Selected configuration\nSelected Option B (offshore team) because it adds capacity; "
          "the offshore developers will handle regulated data directly.\n"
          "## Competitiveness\nCompetitive on capacity.\n")
    res = gate_fit.gate(_opp(tmp_path, fit_md=md))
    f = next(f for f in res.findings if f.check == "locality-conflict")
    assert not f.ok


def test_locality_conflict_surfaced_passes(tmp_path):
    res = gate_fit.gate(_opp(tmp_path, fit_md=FULL_FIT))  # Option A removes offshore risk; conflict discussed+surfaced
    f = next(f for f in res.findings if f.check == "locality-conflict")
    assert f.ok


def test_overclaimed_pastperf_fails(tmp_path):
    # prior performance overclaimed as turnkey/exact-match with NO transferable/reference-gap framing
    md = ("## What the RFP wants\nEvaluator priorities and scoring weights noted.\n"
          "## Candidate configurations\n- Option A: solo + AI\n- Option B: offshore team\n"
          "## Selected configuration\nSelected Option A because it maximally matches the scoring.\n"
          "## Competitiveness\nCompetitive on price and fit.\n"
          "## Prior performance\nWe have a proven turnkey solution we have deployed identically before, an exact match to this RFP.\n")
    res = gate_fit.gate(_opp(tmp_path, fit_md=md))
    f = next(f for f in res.findings if f.check == "pastperf-honest")
    assert not f.ok and f.blocking_failure


def test_well_founded_pass_passes_the_gate(tmp_path):
    # synthesis concluding the best-fit config is NOT competitive is a valid outcome, gate passes
    md = ("## What the RFP wants\nEvaluator priorities: in-domain turnkey product with references; scoring heavily weighted there.\n"
          "## Candidate configurations\n- Option A: solo + AI custom build\n- Option B: teaming with a prime\n"
          "## Selected configuration\nBest-fit is Option A, chosen because it is the only configuration we can field; "
          "but given the turnkey+references weighting this is a weak match.\n"
          "## Competitiveness\nNot competitive — we would not win against entrenched in-domain incumbents; recommend PASS.\n")
    res = gate_fit.gate(_opp(tmp_path, fit_md=md))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_registered_as_synthesis_after_pricing():
    from bidkit import evaluation as ev
    ev._load_gates()
    ids = [s.id for s in ev.ordered_stages()]
    assert any(s.id == "fit" and s.type == ev.SYNTHESIS for s in ev.ordered_stages())
    assert ids.index("pricing") < ids.index("fit")


# ----------------------------------------------------------------------------- P3b: instruction-echo
def test_echoed_instruction_is_not_a_real_selection(tmp_path):
    # the 2026-10-09 bug: the agent restated the task ("a selected best-fit with reasoning, and a
    # competitiveness read") instead of choosing. That must NOT register as a selection-with-no-
    # reasoning; it should read as 'not performed' (no concrete config named).
    echo = """# Fit synthesis

## What the RFP wants
Evaluator priorities and scoring weights extracted.

## Candidate configurations
- Option A: one approach
- Option B: another approach

## Selection
Produce a selected best-fit with reasoning, and a competitiveness read of that configuration.
"""
    sel, reasoning = gate_fit._selected_and_reasoning(echo)
    assert sel is None                                 # the echo is not a real selection

    res = gate_fit.gate(_opp(tmp_path, fit_md=echo))
    sc = next(f for f in res.findings if f.check == "selected-config")
    assert not sc.ok and sc.performed is False         # reported as NOT performed, not 'no reasoning'


def test_concrete_selection_with_reasoning_passes(tmp_path):
    real = """# Fit synthesis

## What the RFP wants
Scoring weights extracted; local presence weighted.

## Candidate configurations
- Option A: US-only solo principal
- Option B: prime + local teaming partner

## Selection
Selected best-fit: **Configuration B (prime + local teaming partner)** because it closes the
on-site requirement the solo option cannot meet and adds the court-CMS reference the RFP scores.
Competitiveness: a credible underdog given the incumbent advantage.
"""
    sel, reasoning = gate_fit._selected_and_reasoning(real)
    assert sel is not None and reasoning is not None   # concrete config + because-clause
