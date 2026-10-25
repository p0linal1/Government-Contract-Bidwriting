"""Tests for the intake-&-facts gate (bidkit.gate_intake)."""
import json
import pytest
from bidkit import gate_intake
from bidkit.evaluation import EvalContext


def _opp(tmp_path, opportunity, rfp_files=None, portal_record=None):
    d = tmp_path / "opp"
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    for name in (rfp_files or []):
        (d / "rfp" / name).write_text("x", encoding="utf-8")
    if portal_record is not None:
        (d / "rfp" / "portal-record.json").write_text(json.dumps(portal_record), encoding="utf-8")
    return EvalContext(str(d))


CONFIRMED_OPP = {
    "id": "x",
    "due": {"date": "2026-10-15", "confirmed": True, "source": "RFP Section 2.4"},
    "format": {"page_limit": 50, "min_font_pt": 10, "page_size": "letter", "font_family_allow": ["Arial"]},
    "contact": {"name": "A. Buyer", "email": "buyer@agency.gov"},
}


def test_confirmed_intake_passes(tmp_path):
    res = gate_intake.gate(_opp(tmp_path, CONFIRMED_OPP, rfp_files=["main.pdf"]))
    assert res.passed, [f.message for f in res.findings if not f.ok]


def test_missing_opportunity_json_fails(tmp_path):
    d = tmp_path / "opp"; d.mkdir()
    res = gate_intake.gate(EvalContext(str(d)))
    f = next(f for f in res.findings if f.check == "opportunity-json")
    assert not f.ok and not f.performed


def test_unconfirmed_due_fails(tmp_path):
    opp = dict(CONFIRMED_OPP)
    opp["due"] = {"date": "2026-10-15", "confirmed": False, "source": "email guess"}
    res = gate_intake.gate(_opp(tmp_path, opp, rfp_files=["main.pdf"]))
    f = next(f for f in res.findings if f.check == "due-confirmed")
    assert not f.ok and f.performed


def test_confirmed_due_without_source_fails(tmp_path):
    opp = dict(CONFIRMED_OPP)
    opp["due"] = {"date": "2026-10-15", "confirmed": True}
    res = gate_intake.gate(_opp(tmp_path, opp, rfp_files=["main.pdf"]))
    f = next(f for f in res.findings if f.check == "due-confirmed")
    assert not f.ok


def test_only_format_detected_fails(tmp_path):
    opp = {"id": "x",
           "due": {"confirmed": True, "source": "RFP p.1"},
           "format_detected": {"page_limit": 30}}   # no 'format'
    res = gate_intake.gate(_opp(tmp_path, opp, rfp_files=["main.pdf"]))
    f = next(f for f in res.findings if f.check == "format-confirmed")
    assert not f.ok


def test_missing_posted_attachment_fails(tmp_path):
    pr = [{"documents": [{"name": "main.pdf"}, {"name": "exhibit-b.xlsx"}], "amendments": []}]
    res = gate_intake.gate(_opp(tmp_path, CONFIRMED_OPP, rfp_files=["main.pdf"], portal_record=pr))
    f = next(f for f in res.findings if f.check == "attachments-present")
    assert not f.ok and "exhibit-b.xlsx" in f.message


def test_all_posted_attachments_present_passes(tmp_path):
    pr = [{"documents": [{"name": "main.pdf"}, {"name": "exhibit-b.xlsx"}], "amendments": []}]
    res = gate_intake.gate(_opp(tmp_path, CONFIRMED_OPP,
                                rfp_files=["main.pdf", "exhibit-b.xlsx"], portal_record=pr))
    f = next(f for f in res.findings if f.check == "attachments-present")
    assert f.ok


def test_apostrophe_filename_reconciles(tmp_path):
    # portal record names a file with an apostrophe; on disk it's saved with '_'
    pr = [{"documents": [{"name": "ExA_Bidder'sCert.docx"}], "amendments": []}]
    res = gate_intake.gate(_opp(tmp_path, CONFIRMED_OPP,
                                rfp_files=["ExA_Bidder_sCert.docx"], portal_record=pr))
    f = next(f for f in res.findings if f.check == "attachments-present")
    assert f.ok


def test_empty_rfp_without_portal_record_warns_not_fails(tmp_path):
    res = gate_intake.gate(_opp(tmp_path, CONFIRMED_OPP))  # no rfp files, no portal record
    f = next(f for f in res.findings if f.check == "attachments-present")
    assert not f.ok and f.severity == gate_intake.WARN and not f.blocking_failure
    # the gate overall still passes (the warn is advisory; due+format+contact are fine)
    assert res.passed


def test_registered_as_first_stage():
    from bidkit import evaluation as ev
    ev._load_gates()
    stages = ev.ordered_stages()
    assert stages[0].id == "intake-facts"
    assert any(s.id == "intake-facts" and s.type == ev.RESEARCH for s in stages)
