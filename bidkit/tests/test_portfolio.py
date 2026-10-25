"""Tests for the portfolio dashboard (bidkit.portfolio): stage computation, counts, renderers."""
import json, os
import datetime as dt
import pytest
from bidkit import portfolio


def _mk(tmp_path, name, opportunity, files=None, subdirs=None):
    d = tmp_path / name
    (d / "rfp").mkdir(parents=True)
    (d / "research").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for sub in (subdirs or []):
        (d / sub).mkdir(parents=True, exist_ok=True)
        (d / sub / "x").write_text("x", encoding="utf-8")
    return str(d)


# --------------------------------------------------------------- stage ladder
def test_stage_filed(tmp_path):
    from bidkit.evaluation import EvalContext
    d = _mk(tmp_path, "a", {"id": "a"})
    assert portfolio.compute_stage(EvalContext(d)) == "filed"


def test_stage_researched(tmp_path):
    from bidkit.evaluation import EvalContext
    d = _mk(tmp_path, "a", {"id": "a"}, files={"research/value-analysis.md": "x"})
    assert portfolio.compute_stage(EvalContext(d)) == "researched"


def test_stage_estimated(tmp_path):
    from bidkit.evaluation import EvalContext
    d = _mk(tmp_path, "a", {"id": "a", "value_estimate": {"anchor": 100000}},
            files={"research/value-analysis.md": "x"})
    assert portfolio.compute_stage(EvalContext(d)) == "estimated"


def test_stage_drafted(tmp_path):
    from bidkit.evaluation import EvalContext
    d = _mk(tmp_path, "a", {"id": "a", "value_estimate": {"anchor": 1}},
            subdirs=["deliverables/bid/final"])
    assert portfolio.compute_stage(EvalContext(d)) == "drafted"


def test_stage_submitted(tmp_path):
    from bidkit.evaluation import EvalContext
    d = _mk(tmp_path, "a", {"id": "a", "folders": {"submit": "SUBMIT"}}, subdirs=["SUBMIT"])
    assert portfolio.compute_stage(EvalContext(d)) == "submitted"


def test_gitkeep_placeholder_does_not_count_as_submitted(tmp_path):
    # a SUBMIT/ folder with only a .gitkeep is scaffolding, NOT a submission (regression)
    from bidkit.evaluation import EvalContext
    d = tmp_path / "a"
    (d / "rfp").mkdir(parents=True)
    (d / "SUBMIT").mkdir(parents=True)
    (d / "SUBMIT" / ".gitkeep").write_text("", encoding="utf-8")
    (d / "deliverables" / "bid" / "final").mkdir(parents=True)
    (d / "deliverables" / "bid" / "final" / ".gitkeep").write_text("", encoding="utf-8")
    (d / "opportunity.json").write_text(json.dumps({"id": "a", "folders": {"submit": "SUBMIT"}}), encoding="utf-8")
    assert portfolio.compute_stage(EvalContext(str(d))) == "filed"


# --------------------------------------------------------------- days remaining
def test_days_remaining():
    future = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    assert portfolio._days_remaining({"date": future}) == 10
    assert portfolio._days_remaining({}) is None
    assert portfolio._days_remaining({"date": "not-a-date"}) is None


# --------------------------------------------------------------- row + portfolio
def test_build_portfolio_skips_template_and_sourcing(tmp_path):
    _mk(tmp_path, "real", {"id": "real"})
    (tmp_path / "_template").mkdir(); (tmp_path / "_template" / "opportunity.json").write_text("{}")
    (tmp_path / "sourcing").mkdir()
    rows = portfolio.build_portfolio(str(tmp_path), run_gates=False)
    names = {r["opportunity"] for r in rows}
    assert names == {"real"}


def test_row_has_recommendation_and_stage(tmp_path):
    d = _mk(tmp_path, "a", {"id": "a", "value_estimate": {"anchor": 100000, "confidence": "MEDIUM"}},
            files={"opportunity-summary.md": "**Recommendation: BID**"})
    row = portfolio.build_row(d, run_gates=False)
    assert row["recommendation"] == "bid" and row["stage"] == "estimated"
    assert row["value_anchor"] == 100000


# --------------------------------------------------------------- counts (X/Y/Z)
def _queue(tmp_path, entries):
    p = tmp_path / "queue.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return str(p)


def test_counts_first_run_everything_added(tmp_path):
    q = _queue(tmp_path, [
        {"opportunity": "opportunities/a", "processed_at": "2026-10-01T00:00:00+00:00", "action": "new"},
        {"opportunity": "opportunities/b", "processed_at": "2026-10-02T00:00:00+00:00", "action": "new"},
    ])
    rows = [{"opportunity": "a", "recommendation": "bid"}, {"opportunity": "b", "recommendation": "pass"}]
    c = portfolio.counts(rows, q, state_path=None)   # no watermark ⇒ first run
    assert set(c["added"]) == {"a", "b"} and c["updated"] == []
    assert c["passed"] == ["a"]


def test_counts_added_vs_updated_against_watermark(tmp_path):
    q = _queue(tmp_path, [
        {"opportunity": "opportunities/old", "processed_at": "2026-09-01T00:00:00+00:00", "action": "new"},
        {"opportunity": "opportunities/old", "processed_at": "2026-10-05T00:00:00+00:00", "action": "followup"},
        {"opportunity": "opportunities/new", "processed_at": "2026-10-04T00:00:00+00:00", "action": "new"},
    ])
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"last_run": "2026-10-01T00:00:00+00:00"}), encoding="utf-8")
    rows = [{"opportunity": "old", "recommendation": "pass"}, {"opportunity": "new", "recommendation": "conditional"}]
    c = portfolio.counts(rows, q, str(state))
    assert c["added"] == ["new"]       # first-filed after the watermark
    assert c["updated"] == ["old"]     # only follow-up activity after the watermark
    assert c["passed"] == ["new"]      # conditional is a proceed verdict


def test_update_watermark_roundtrip(tmp_path):
    sp = str(tmp_path / "state.json")
    when = portfolio.update_watermark(sp, when="2026-10-06T12:00:00+00:00")
    assert when == "2026-10-06T12:00:00+00:00"
    assert json.load(open(sp))["last_run"] == when


# --------------------------------------------------------------- renderers
def test_renderers_run(tmp_path):
    rows = [{"opportunity": "a", "stage": "estimated", "pipeline_at": "fit", "gates_failed": 1,
             "recommendation": "bid", "due": "2026-10-15", "due_confirmed": True,
             "days_remaining": 9, "value_anchor": 1600000, "value_confidence": "MEDIUM"}]
    assert "a" in portfolio.to_markdown(rows)
    assert "$1,600,000" in portfolio.to_markdown(rows)
    assert "opportunity" in portfolio.to_csv(rows)
    assert json.loads(portfolio.to_json(rows))[0]["opportunity"] == "a"
