"""Tests for the orchestrator (bidkit.harness): autonomy modes, degrade-to-a, idempotency."""
import datetime, json, os
import pytest
from bidkit import harness
from bidkit.evaluation import EvalContext


def _opp(root, name, opportunity, files=None):
    d = root / name
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    (d / "rfp" / "main.pdf").write_text("x", encoding="utf-8")
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


def _cfg(tmp_path, **over):
    cfg = dict(harness.DEFAULTS)
    cfg["opportunities_dir"] = str(tmp_path / "opps")
    cfg["state"] = str(tmp_path / "state.json")
    cfg["queue"] = str(tmp_path / "queue.jsonl")
    cfg.update(over)
    return cfg


def test_config_defaults_to_notify_only(tmp_path):
    cfg = harness.load_config(None)
    assert cfg["autonomy"] == "a"


def test_bad_autonomy_rejected(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"autonomy": "z"}), encoding="utf-8")
    with pytest.raises(harness.HarnessError):
        harness.load_config(str(p))


def test_mode_a_null_agent_writer_does_not_run(tmp_path):
    # In mode a the AGENT WRITER never runs (no judgment fields written). The deterministic PREP
    # pass may refresh facts files — that is infrastructure, not agent writing — so we assert on the
    # worker + judgment fields, not byte-identity of the folder.
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="a", prep={"enabled": False})   # isolate: prep off → folder untouched
    before = set(os.listdir(d))
    report = harness.orchestrate(cfg)
    assert set(os.listdir(d)) == before          # with prep off, mode a changes nothing
    assert "null" in report.mode_note
    assert any(r.opportunity == "a" for r in report.results)


def test_mode_a_prep_writes_only_deterministic_facts(tmp_path):
    import json as _j
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="a")            # prep on by default
    harness.orchestrate(cfg)
    oj = _j.load(open(d / "opportunity.json"))
    # prep may add deterministic facts (due block, facts pointer) AND a DOCUMENT-ONLY value estimate
    # (the deterministic generator half of value-research), but NEVER the agent-JUDGMENT fields.
    assert "recommendation" not in oj and "status" not in oj
    # the value_estimate prep writes is explicitly the document-only, LOW-confidence generator output
    ve = oj.get("value_estimate") or {}
    assert ve.get("generator") == "document-only (deterministic generator)"
    assert ve.get("confidence") == "LOW" and "anchor" not in ve


def test_mode_b_without_runner_degrades_to_a(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="b", agent_cli=None)   # no runner
    report = harness.orchestrate(cfg)
    assert "DEGRADED to notify-only" in report.mode_note


def test_mode_b_agent_writer_does_not_touch_judgment_fields(tmp_path):
    # The mode-b guardrail is that the AGENT WRITER does not change canonical JUDGMENT fields.
    # Deterministic prep may refresh facts and write a document-only value estimate; it must never
    # write the agent-judgment fields recommendation/status.
    import json as _j
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a", "status": "intake"})
    cfg = _cfg(tmp_path, autonomy="b", agent_cli=None)   # degrades to notify-only; prep still runs
    harness.orchestrate(cfg)
    oj = _j.load(open(d / "opportunity.json"))
    assert oj.get("status") == "intake"                  # judgment field unchanged
    assert "recommendation" not in oj
    # a document-only value estimate IS allowed (it is confidence-tagged, not a judgment)
    assert (oj.get("value_estimate") or {}).get("generator") == "document-only (deterministic generator)"


def test_idempotency_skips_unchanged(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    # a steady-state opp (confirmed due) has no outstanding prep, so the second run truly skips it
    # due date relative to today: a fixed date eventually passes and flips the skip reason
    due = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    _opp(opps, "a", {"id": "a", "due": {"date": due, "confirmed": True, "source": "RFP p.1"}})
    cfg = _cfg(tmp_path, autonomy="a")
    harness.orchestrate(cfg)                      # first run records the hash
    report2 = harness.orchestrate(cfg)            # second run, unchanged + nothing to prep
    r = next(r for r in report2.results if r.opportunity == "a")
    assert r.skipped_reason == "unchanged since last run"


def test_prep_reaches_unchanged_backlog_with_unconfirmed_due(tmp_path):
    # an opp that is "unchanged" (hash stored) but still has an unconfirmed due date must still get
    # prepped — this is the backlog-connection fix.
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "due": {"date": "", "confirmed": False, "source": "bidkit.inbox (GUESS)"}})
    cfg = _cfg(tmp_path, autonomy="a")
    harness.orchestrate(cfg)                      # records hash
    report2 = harness.orchestrate(cfg)            # unchanged, but due still unconfirmed → prep runs
    r = next(r for r in report2.results if r.opportunity == "a")
    assert r.skipped_reason == "" and r.prep_notes   # not skipped; prep ran


def test_changed_inputs_reworked(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="a")
    harness.orchestrate(cfg)
    (d / "opportunity.json").write_text(json.dumps({"id": "a", "status": "bid"}), encoding="utf-8")
    report2 = harness.orchestrate(cfg)
    r = next(r for r in report2.results if r.opportunity == "a")
    assert r.skipped_reason == ""                 # re-worked because inputs changed


def _opp_empty_rfp(root, name, opportunity):
    """Like _opp but with an EMPTY rfp/ (no main.pdf) so the portal-fetch prep step has reason to run."""
    d = root / name
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    return d


def test_portal_fetch_default_is_mode_dependent(tmp_path):
    # P2a retrieval-first: portal_fetch defaults OFF in mode a, ON in mode b/c (unless the operator
    # set it explicitly). Asserted via prep notes on an opp whose rfp/ is empty (so the step has
    # work to attempt): mode a never attempts a portal fetch; mode c does (and degrades gracefully
    # with no portals configured).
    opps = tmp_path / "opps"; opps.mkdir()
    _opp_empty_rfp(opps, "a", {"id": "a"})
    rep_a = harness.orchestrate(_cfg(tmp_path, autonomy="a"))
    notes_a = " ".join(next(r for r in rep_a.results if r.opportunity == "a").prep_notes)
    assert "portal fetch" not in notes_a

    opps2 = tmp_path / "opps2"; opps2.mkdir()
    _opp_empty_rfp(opps2, "a", {"id": "a"})
    cfg_c = _cfg(tmp_path, autonomy="c", agent_cli=None)   # degrades to notify, but prep uses mode c
    cfg_c["opportunities_dir"] = str(opps2); cfg_c["state"] = str(tmp_path / "s2.json")
    rep_c = harness.orchestrate(cfg_c)
    notes_c = " ".join(next(r for r in rep_c.results if r.opportunity == "a").prep_notes)
    assert "portal fetch" in notes_c                        # attempted (then skipped: no portals)


def test_explicit_portal_fetch_config_wins(tmp_path):
    # an explicit prep.portal_fetch=False in config overrides the mode-c default
    opps = tmp_path / "opps"; opps.mkdir()
    _opp_empty_rfp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=None)
    cfg["prep"] = dict(harness.DEFAULTS["prep"]); cfg["prep"]["portal_fetch"] = False
    rep = harness.orchestrate(cfg)
    notes = " ".join(next(r for r in rep.results if r.opportunity == "a").prep_notes)
    assert "portal fetch" not in notes


def test_dry_run_writes_no_state(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="a")
    harness.orchestrate(cfg, dry_run=True)
    assert not os.path.exists(cfg["state"])       # dry-run persisted nothing


def test_content_hash_changes_with_rfp(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    h1 = harness.content_hash(str(d))
    (d / "rfp" / "addendum.pdf").write_text("new", encoding="utf-8")
    h2 = harness.content_hash(str(d))
    assert h1 != h2


def test_report_counts_present(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "value_estimate": {"anchor": 1}},
         files={"opportunity-summary.md": "**Recommendation: BID**"})
    cfg = _cfg(tmp_path, autonomy="a")
    report = harness.orchestrate(cfg)
    assert set(report.counts) == {"added", "updated", "passed"}


def test_open_items_structural_dashed(tmp_path):
    from bidkit.evaluation import EvalContext
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"}, files={"opportunity-summary.md":
        "## Scope\nSome analysis mentioning a teaming decision in prose.\n\n"
        "## Open items for the human\n"
        "- Confirm the no-bid decision.\n"
        "- Reserved-capacity commitment behind the recurring price.\n\n"
        "## Pricing\n- This bullet mentions a signature but is NOT a decision item.\n"})
    items = harness._open_items(EvalContext(str(d)))
    assert items == ["Confirm the no-bid decision.",
                     "Reserved-capacity commitment behind the recurring price."]


def test_open_items_numbered_with_wrapped_lines(tmp_path):
    from bidkit.evaluation import EvalContext
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"}, files={"opportunity-summary.md":
        "## 6. Critical human decisions (resolve before drafting)\n"
        "These are surfaced, not silently resolved (guardrails):\n"
        "1. **Scope posture:** full contract vs. a targeted component bid —\n"
        "   this drives everything else.\n"
        "2. **Prime-solo vs. teaming:** team with a local firm?\n"
        "## Next section\n"})
    items = harness._open_items(EvalContext(str(d)))
    assert len(items) == 2
    assert items[0].startswith("Scope posture:") and "drives everything else" in items[0]
    assert items[1].startswith("Prime-solo vs. teaming:")


def test_open_items_ignores_decision_bullets_outside_the_section(tmp_path):
    # a bullet full of decision keywords but NOT under an open-items heading must be ignored
    from bidkit.evaluation import EvalContext
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"}, files={"opportunity-summary.md":
        "## Evaluation\n- The RFP scores the teaming/locality/signature decision at 20 points.\n"})
    items = harness._open_items(EvalContext(str(d)))
    assert items == []


def test_open_items_heading_variants(tmp_path):
    from bidkit.evaluation import EvalContext
    for heading in ("## Open items / decisions for the human",
                    "## Decision for the human (FGA will make the call)",
                    "## Needs your decision"):
        opps = tmp_path / ("opps" + str(abs(hash(heading)))); opps.mkdir()
        d = _opp(opps, "a", {"id": "a"},
                 files={"opportunity-summary.md": heading + "\n- The one real decision.\n"})
        items = harness._open_items(EvalContext(str(d)))
        assert items == ["The one real decision."], heading


def test_prep_default_enabled(tmp_path):
    cfg = harness.load_config(None)
    assert cfg["prep"]["enabled"] is True
    # portal_fetch is intentionally absent from DEFAULTS: its default is mode-dependent (off in a,
    # on in b/c), applied in orchestrate — not pinned here.
    assert "portal_fetch" not in cfg["prep"]


def test_prep_runs_brief_and_calendar(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    notes = harness.prep_opportunity(str(d), {"enabled": True, "brief": True,
                                              "confirm_due": True, "calendar": True, "portal_fetch": False})
    assert any("brief" in n for n in notes)
    assert any("calendar" in n for n in notes)
    assert (d / "opportunity-facts.md").exists()      # brief wrote the facts sheet
    assert (d / "calendar.ics").exists()              # calendar wrote the ics


def test_prep_confirms_doc_sourced_due(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a", "due": {"date": "", "confirmed": False, "source": "bidkit.brief (DETECTED)"}})
    # an RFP document with an explicit submission-deadline sentence carrying a time
    (d / "rfp").mkdir(exist_ok=True)
    (d / "rfp" / "rfp.txt").write_text(
        "Proposal Submission Deadline September 10, 2026, 3:00 pm PT. Submit via the portal.", encoding="utf-8")
    harness.prep_opportunity(str(d), {"enabled": True, "brief": True, "confirm_due": True,
                                      "calendar": True, "portal_fetch": False})
    import json as _j
    due = _j.load(open(d / "opportunity.json"))["due"]
    assert due["confirmed"] is True and due["date"] == "2026-09-10"


def test_prep_portal_fetch_off_by_default_in_orchestrate(tmp_path, monkeypatch):
    # with prep.portal_fetch false, portal is never imported/called even when rfp/ is empty
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    called = {"n": 0}
    import bidkit.portal as portal
    monkeypatch.setattr(portal, "fetch_for_opportunity", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    cfg = _cfg(tmp_path, autonomy="a")   # DEFAULTS prep.portal_fetch is False
    harness.orchestrate(cfg)
    assert called["n"] == 0


def test_orchestrate_runs_prep(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="a")
    report = harness.orchestrate(cfg)
    r = next(r for r in report.results if r.opportunity == "a")
    assert r.prep_notes   # prep ran and recorded notes


def test_prep_error_does_not_abort(tmp_path, monkeypatch):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    import bidkit.brief as brief
    monkeypatch.setattr(brief, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    notes = harness.prep_opportunity(str(d), {"enabled": True, "brief": True,
                                              "confirm_due": False, "calendar": True, "portal_fetch": False})
    assert any("brief skipped" in n for n in notes)   # error captured, prep continued


def test_one_bad_opportunity_does_not_abort(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "good", {"id": "good"})
    bad = opps / "bad"; (bad).mkdir()
    (bad / "opportunity.json").write_text("{ not json", encoding="utf-8")
    cfg = _cfg(tmp_path, autonomy="a")
    report = harness.orchestrate(cfg)
    names = {r.opportunity for r in report.results}
    assert "good" in names and "bad" in names
    bad_r = next(r for r in report.results if r.opportunity == "bad")
    assert bad_r.error
