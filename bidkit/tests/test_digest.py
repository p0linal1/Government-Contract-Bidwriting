"""Tests for the daily digest composer (bidkit.digest). Uses a fake sender — never sends mail."""
import json, os
import pytest
from bidkit import digest, harness, portfolio


def _opp(root, name, opportunity, files=None, draft=None):
    d = root / name
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    (d / "rfp" / "main.pdf").write_text("x", encoding="utf-8")
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if draft:
        fd = d / "deliverables" / "bid" / "final"
        fd.mkdir(parents=True)
        (fd / draft).write_bytes(b"%PDF-1.4 fake pdf bytes")
    return d


def _cfg(tmp_path, **digest_over):
    cfg = dict(harness.DEFAULTS)
    cfg["opportunities_dir"] = str(tmp_path / "opps")
    cfg["state"] = str(tmp_path / "state.json")
    cfg["queue"] = str(tmp_path / "queue.jsonl")
    cfg["log_dir"] = str(tmp_path / "logs")
    cfg["digest"] = {"to": "principal@example.com", "from": "harness@example.com",
                     "max_attachment_mb": 20, "send_on_empty": True}
    cfg["digest"].update(digest_over)
    return cfg


def _report_and_rows(cfg):
    report = harness.orchestrate(cfg, dry_run=True)
    rows = portfolio.build_portfolio(cfg["opportunities_dir"], run_gates=False)
    return report, rows


def test_lead_line_has_xyz(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "value_estimate": {"anchor": 100000}},
         files={"opportunity-summary.md": "**Recommendation: BID**"})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "opportunities added," in body and "passed go/no-go" in body
    assert msg["To"] == "principal@example.com"


def test_passer_draft_attached(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "winner", {"id": "winner", "value_estimate": {"anchor": 1}},
         files={"opportunity-summary.md": "**Recommendation: BID**"}, draft="proposal.pdf")
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    atts = [p.get_filename() for p in msg.iter_attachments()]
    assert any("winner" in (a or "") and a.endswith(".pdf") for a in atts)


def test_oversize_draft_not_attached_but_listed(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "big", {"id": "big", "value_estimate": {"anchor": 1}},
         files={"opportunity-summary.md": "**Recommendation: BID**"}, draft="huge.pdf")
    cfg = _cfg(tmp_path, max_attachment_mb=0)   # force the over-cap branch
    report, rows = _report_and_rows(cfg)
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    atts = list(msg.iter_attachments())
    body = msg.get_body(preferencelist=("plain",)).get_content()
    # oversize draft is NOT attached, but the passer is still listed in the Passed section
    assert not atts and "big" in body


def test_needs_decision_section(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"},
         files={"opportunity-summary.md": "## Open items\n- Confirm the teaming decision with the partner\n"})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Needs your decision" in body and "teaming decision" in body


def test_review_section_lists_low_confidence_stages(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})   # no confirmed due ⇒ intake stage is LOW confidence
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    body = msg.get_body(preferencelist=("plain",)).get_content()
    # reframed from "needs attention / stalls at" to a review/override list carrying confidence
    assert "Review / override" in body
    assert "intake-facts" in body and "LOW" in body


def test_send_uses_injected_sender(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    # queue entry so 'added' is non-zero and the digest is not suppressed
    (tmp_path / "queue.jsonl").write_text(
        json.dumps({"opportunity": "opportunities/a", "processed_at": "2026-10-06T00:00:00+00:00", "action": "new"}) + "\n",
        encoding="utf-8")
    cfg = _cfg(tmp_path)
    sent = {}
    def fake_sender(msg, cfg):
        sent["to"] = msg["To"]; sent["subject"] = msg["Subject"]
    code, _ = digest.run(cfg, dry_run=False, sender=fake_sender)
    assert code == 0 and sent["to"] == "principal@example.com"


def test_quiet_run_suppressed_when_nothing_new(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, send_on_empty=False)
    # empty queue + a watermark so nothing is 'added'/'updated'
    (tmp_path / "state.json").write_text(json.dumps({"last_run": "2026-10-06T00:00:00+00:00"}), encoding="utf-8")
    (tmp_path / "queue.jsonl").write_text("", encoding="utf-8")
    sent = {"called": False}
    def fake_sender(msg, cfg):
        sent["called"] = True
    code, _ = digest.run(cfg, dry_run=False, sender=fake_sender)
    assert code == 0 and sent["called"] is False   # suppressed


def test_backend_failure_writes_eml_and_returns_nonzero(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    (tmp_path / "queue.jsonl").write_text(
        json.dumps({"opportunity": "opportunities/a", "processed_at": "2026-10-06T00:00:00+00:00", "action": "new"}) + "\n",
        encoding="utf-8")
    cfg = _cfg(tmp_path)
    def boom(msg, cfg):
        raise RuntimeError("backend down")
    code, result = digest.run(cfg, dry_run=False, sender=boom)
    assert code == 1 and "digest written to" in result
    # the .eml was written to the log dir
    assert any(f.endswith(".eml") for f in os.listdir(cfg["log_dir"]))


def _html_of(msg):
    return [p for p in msg.walk() if p.get_content_type() == "text/html"][0].get_content()


def test_has_html_alternative(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    types = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in types and "text/html" in types   # multipart/alternative


def test_html_passed_table_shows_value_source_and_rationale(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "winner",
         {"id": "winner", "value_estimate": {"anchor": 1119683, "confidence": "MEDIUM-HIGH",
                                             "anchor_source": "https://city.gov/btip.pdf"}},
         files={"opportunity-summary.md": "**Recommendation: BID**",
                "research/go-no-go.md": "DECISION: BID — positive expected value at low cash risk."})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    html = _html_of(digest.compose(report, rows, cfg, cfg["opportunities_dir"]))
    assert "$1,119,683" in html
    assert 'href="https://city.gov/btip.pdf"' in html and "[source]" in html
    assert "positive expected value" in html
    assert "<table" in html   # it's a real table


def test_html_review_table_shows_estimate_basis_and_remedy(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    # a DETECTED-but-unconfirmed due date → intake stage is LOW; it appears in Review / override
    # with the current estimate's basis (reason) and how to raise confidence (remedy)
    _opp(opps, "a", {"id": "a", "due": {"date": "2026-10-15", "confirmed": False, "source": "email guess"}})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    html = _html_of(digest.compose(report, rows, cfg, cfg["opportunities_dir"]))
    assert "Review / override" in html
    assert "DETECTED guess" in html                       # what the current best estimate rests on
    assert "Confirm the deadline from the RFP" in html    # how to raise confidence


def test_html_escapes_cell_text(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"},
         files={"opportunity-summary.md": "## Open items for the human\n- Handle <b>A & B</b> contract\n"})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    html = _html_of(digest.compose(report, rows, cfg, cfg["opportunities_dir"]))
    assert "&lt;b&gt;A &amp; B&lt;/b&gt;" in html          # user text escaped, not injected as markup


def test_null_subject_in_config_uses_default(tmp_path):
    # the example config ships subject:null — dcfg.get('subject') returns None, must fall back
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, subject=None, org_name="Acme LLC")
    report, rows = _report_and_rows(cfg)
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    assert msg["Subject"].startswith("Acme LLC Bid Sourcing")


def test_dry_run_does_not_send(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path)
    called = {"n": 0}
    def fake(msg, cfg):
        called["n"] += 1
    code, msg = digest.run(cfg, dry_run=True, sender=fake)
    assert code == 0 and called["n"] == 0 and hasattr(msg, "as_string")


# ----------------------------------------------------------------------------- review split (P2b)
def test_review_items_split_by_kind(tmp_path):
    # a needs-research gap goes to the Auto-research queue; a human-decision gap to Review/override
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    # inject one of each kind onto the result (bypassing the graders, to test the digest split)
    r = report.results[0]
    r.review_items = [
        {"stage": "intake-facts", "confidence": "LOW", "reason": "due date still a DETECTED guess",
         "remedy": "Confirm the deadline from the RFP.", "kind": "needs-research"},
        {"stage": "fit", "confidence": "LOW", "reason": "prime-solo vs teaming not decided",
         "remedy": "Decide the teaming posture.", "kind": "human-decision"},
    ]
    msg = digest.compose(report, rows, cfg, cfg["opportunities_dir"])
    body = msg.get_body(preferencelist=("plain",)).get_content()
    # split the body into its two sections and assert each item is under the RIGHT header
    rev_hdr = "## Review / override"
    q_hdr = "## Auto-research queue"
    assert rev_hdr in body and q_hdr in body
    rev_section = body[body.index(rev_hdr):body.index(q_hdr)]
    q_section = body[body.index(q_hdr):]
    assert "teaming posture" in rev_section and "teaming posture" not in q_section   # human → review
    assert "DETECTED guess" in q_section and "DETECTED guess" not in rev_section      # research → queue


# ----------------------------------------------------------------------------- past-due (P4a/P4b)
def test_expired_passer_split_out_of_live(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    # a passer whose CONFIRMED due date is in the past → EXPIRED, not live
    _opp(opps, "old", {"id": "old", "value_estimate": {"anchor": 500000},
                       "due": {"date": "2020-01-01", "confirmed": True, "source": "RFP p.1"}},
         files={"opportunity-summary.md": "**Recommendation: BID**"})
    # a passer with a future confirmed due → live
    _opp(opps, "live", {"id": "live", "value_estimate": {"anchor": 500000},
                        "due": {"date": "2099-01-01", "confirmed": True, "source": "RFP p.1"}},
         files={"opportunity-summary.md": "**Recommendation: BID**"})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    body = digest.compose(report, rows, cfg, cfg["opportunities_dir"]).get_body(preferencelist=("plain",)).get_content()
    live_hdr = "## Passed go/no-go — live"
    exp_hdr = "## Passed go/no-go — EXPIRED"
    assert live_hdr in body and exp_hdr in body
    live_sec = body[body.index(live_hdr):body.index(exp_hdr)]
    exp_sec = body[body.index(exp_hdr):]
    assert "live" in live_sec and "old" not in live_sec     # future-due in live, past-due not
    assert "old" in exp_sec                                  # past-due in the expired section


def test_unconfirmed_past_due_is_not_expired(tmp_path):
    # a DETECTED (unconfirmed) past due must NOT be treated as expired (not trusted)
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "value_estimate": {"anchor": 500000},
                     "due": {"date": "2020-01-01", "confirmed": False, "source": "email guess"}},
         files={"opportunity-summary.md": "**Recommendation: BID**"})
    cfg = _cfg(tmp_path)
    report, rows = _report_and_rows(cfg)
    body = digest.compose(report, rows, cfg, cfg["opportunities_dir"]).get_body(preferencelist=("plain",)).get_content()
    live_sec = body[body.index("## Passed go/no-go — live"):]
    # with no expired section, the unconfirmed-past-due passer stays live
    assert "- a —" in live_sec
