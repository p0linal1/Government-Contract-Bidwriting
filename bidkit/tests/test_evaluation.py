"""Tests for the gate engine core (bidkit.evaluation): base helpers, stage registry,
ordering, fail-stops-advancement, and extensibility."""
import os
import pytest
from bidkit import evaluation as ev


# ------------------------------------------------------------------ base helpers: research
def test_require_sourced_passes_with_url():
    f = ev.require_sourced("c", "value", "Likely $1.6M, see https://example.gov/budget.pdf")
    assert f.ok and f.performed


def test_require_sourced_passes_with_doc_citation():
    f = ev.require_sourced("c", "due", "October 15 2026 (RFP Section 2.4)")
    assert f.ok


def test_require_sourced_passes_with_unknown_reason():
    f = ev.require_sourced("c", "annual", "UNKNOWN — agency refused to publish a ceiling in Q&A")
    assert f.ok


def test_require_sourced_fails_bare_number():
    f = ev.require_sourced("c", "value", "$1,600,000")
    assert not f.ok and f.blocking_failure and f.performed


def test_require_sourced_fails_absent():
    f = ev.require_sourced("c", "value", None)
    assert not f.ok and not f.performed


def test_require_sourced_rejects_bare_unknown():
    f = ev.require_sourced("c", "value", "UNKNOWN")
    assert not f.ok


# ------------------------------------------------------------------ the Req 2.3 distinction
def test_distinct_notrun_passes_when_search_ran_and_found():
    f = ev.distinct_notrun_vs_empty("inc", "incumbent",
                                    "Tyler Public Safety, prior award https://city.gov/packet.pdf")
    assert f.ok and f.performed


def test_distinct_notrun_passes_when_searched_nothing_found():
    f = ev.distinct_notrun_vs_empty("inc", "incumbent",
                                    "Searched council packets and the state portal; no public record of a prior award.")
    assert f.ok


def test_distinct_notrun_fails_when_blank():
    f = ev.distinct_notrun_vs_empty("inc", "incumbent", "")
    assert not f.ok and not f.performed


def test_distinct_notrun_fails_when_content_but_no_evidence_of_running():
    f = ev.distinct_notrun_vs_empty("inc", "incumbent", "probably none")
    assert not f.ok and f.performed


# ------------------------------------------------------------------ base helpers: synthesis
def test_require_alternatives_needs_two():
    assert ev.require_alternatives_considered("c", "configs", ["a", "b"]).ok
    assert not ev.require_alternatives_considered("c", "configs", ["only-one"]).ok
    empty = ev.require_alternatives_considered("c", "configs", [])
    assert not empty.ok and not empty.performed   # nothing recorded ⇒ not performed


def test_require_reasoned_selection():
    assert ev.require_reasoned_selection("c", "cfg", "US-only dev + AI pitch",
                                         "chosen because the RFP scores local presence heavily and ...").ok
    assert not ev.require_reasoned_selection("c", "cfg", "US-only dev", "short").ok
    assert not ev.require_reasoned_selection("c", "cfg", None, "x").performed


def test_require_cites_upstream():
    cues = [("value",), ("price", "cost"), ("fit", "config")]
    good = ev.require_cites_upstream("c", "verdict",
                                     "Given the value corridor, our cost to deliver, and the selected fit config, we bid.",
                                     cues)
    assert good.ok
    bad = ev.require_cites_upstream("c", "verdict", "We should bid, it looks good.", cues)
    assert not bad.ok


def test_require_surfaced_not_resolved():
    assert ev.require_surfaced_not_resolved("c", "locality", surfaced=True, conflict_present=True).ok
    assert not ev.require_surfaced_not_resolved("c", "locality", surfaced=False, conflict_present=True).ok
    assert ev.require_surfaced_not_resolved("c", "locality", surfaced=False, conflict_present=False).ok


# ------------------------------------------------------------------ GateResult semantics
def test_gateresult_pass_fail():
    res = ev.GateResult("s")
    res.add(ev.GateFinding("a", ok=True))
    assert res.passed
    res.add(ev.GateFinding("b", ok=False, severity=ev.WARN))   # warning does not block
    assert res.passed
    res.add(ev.GateFinding("c", ok=False, severity=ev.FAIL))   # hard fail blocks
    assert not res.passed and res.status == "fail"


# ------------------------------------------------------------------ registry + engine
@pytest.fixture
def three_dummy_stages():
    saved = list(ev.STAGES)
    ev.STAGES.clear()
    calls = []

    def mk(name, ok):
        def gate(ctx):
            calls.append(name)
            r = ev.GateResult(name)
            r.add(ev.GateFinding("chk", ok=ok))
            return r
        return gate

    ev.register(ev.Stage("one", 10, ev.RESEARCH, mk("one", True)))
    ev.register(ev.Stage("three", 30, ev.SYNTHESIS, mk("three", True)))
    ev.register(ev.Stage("two", 20, ev.RECONCILIATION, mk("two", False)))  # middle fails
    yield calls
    ev.STAGES[:] = saved


def test_registry_sorts_by_order(three_dummy_stages):
    assert [s.id for s in ev.ordered_stages()] == ["one", "two", "three"]


def test_engine_runs_all_stages_never_halts(tmp_path, three_dummy_stages, monkeypatch):
    # generate → grade → ALWAYS continue: a low-confidence (failing-finding) middle stage must NOT
    # stop the pipeline; every stage runs and is graded.
    monkeypatch.setattr(ev, "_load_gates", lambda: None)  # don't pull real gates over the dummies
    opp = tmp_path / "opp"; opp.mkdir()
    eng = ev.EvaluationEngine(str(opp))
    results = eng.run()
    assert [r.stage for r in results] == ["one", "two", "three"]   # all three ran
    assert three_dummy_stages == ["one", "two", "three"]
    # the middle stage graded LOW (it had a blocking finding) but did not halt the rest
    assert results[1].confidence == ev.LOW
    assert results[2].confidence == ev.HIGH


def test_extensibility_add_stage_without_engine_change(three_dummy_stages, monkeypatch):
    monkeypatch.setattr(ev, "_load_gates", lambda: None)
    def gate(ctx):
        r = ev.GateResult("four"); r.add(ev.GateFinding("c", ok=True)); return r
    ev.register(ev.Stage("four", 40, ev.RESEARCH, gate))
    assert [s.id for s in ev.ordered_stages()] == ["one", "two", "three", "four"]


def test_register_replaces_same_id(three_dummy_stages):
    before = len(ev.ordered_stages())
    def gate(ctx):
        r = ev.GateResult("one"); r.add(ev.GateFinding("c", ok=True)); return r
    ev.register(ev.Stage("one", 10, ev.RESEARCH, gate))
    assert len(ev.ordered_stages()) == before  # replaced, not duplicated


def test_evalcontext_missing_vs_present(tmp_path):
    opp = tmp_path / "opp"; opp.mkdir()
    ctx = ev.EvalContext(str(opp))
    assert ctx.opportunity() is None            # missing ⇒ None, not an error
    (opp / "opportunity.json").write_text('{"id": "x"}', encoding="utf-8")
    ctx2 = ev.EvalContext(str(opp))
    assert ctx2.opportunity()["id"] == "x"
    assert ctx2.rfp_files() == []
