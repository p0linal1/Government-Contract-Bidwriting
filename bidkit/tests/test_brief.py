import json, os
import fitz, pytest
from bidkit import brief
from conftest import real_sample

RFP_TEXT = """REQUEST FOR PROPOSAL 27-004
Example County
Jail Management System Replacement

Date of RFP: September 10, 2026
Pre-proposal conference: September 24, 2026 at 10:00 am (optional)
Questions are due by October 9, 2026 at 5:00 PM PT.
Final addenda will be posted no later than October 16, 2026.
Proposals must be received no later than 2:00 PM Pacific Time on October 30, 2026.
Notice of intent to award is anticipated November 20, 2026. Contract start January 4, 2027.

RFP Coordinator: Jane Buyer, Procurement Officer, jane.buyer@example.gov, (555) 010-2000.

The County has budgeted $1,250,000 for this project. The total contract value shall not exceed $1,500,000
over the initial five (5) year term with two (2) one-year renewal options. A performance bond of $50,000 is
required. Contractor shall maintain cyber liability insurance of $2,000,000 per occurrence.

Submittals shall be limited to a maximum of twenty (20) numbered pages. Font shall be Arial no smaller than
11 point. Margins on all edges shall be a minimum of 1 inch. Pages shall be 8.5" x 11". Proposals shall be
submitted electronically as a single PDF not to exceed 25 MB by email with the subject line "RFP 27-004".

Required forms: Attachment A - Proposal Certification, Attachment B - Requirements Workbook,
Exhibit C - Sample Contract, and Appendix 1 - Insurance Requirements. Attachment A must be signed.

EVALUATION CRITERIA
Technical approach: 40 points. Experience and references: 25 points. Cost: 25 points. Demonstration: 10 points.
Proposals will be scored by an evaluation committee.
"""


def _make_pdf(path, text):
    d = fitz.open(); pg = d.new_page()
    y = 60
    for line in text.splitlines():
        pg.insert_text((40, y), line, fontsize=8, fontname="helv"); y += 11
        if y > 780: pg = d.new_page(); y = 60
    d.save(path); d.close()


@pytest.fixture
def opp(tmp_path):
    o = tmp_path / "27-004-Example-County-Jail"; (o / "rfp").mkdir(parents=True); (o / "initial-email").mkdir()
    _make_pdf(str(o / "rfp" / "RFP 27-004 Jail Management System.pdf"), RFP_TEXT)
    (o / "rfp" / "Attachment A - Proposal Certification.pdf").write_bytes(b"%PDF-1.4 stub")
    (o / "rfp" / "B - Requirements Workbook.xlsx").write_bytes(b"PK stub")            # present, matched by token 'B'
    (o / "initial-email" / "email.md").write_text("# Fwd: RFP 27-004\n\n- **From:** Jane Buyer <jane.buyer@example.gov>\n\nProposals due October 30, 2026.\n")
    (o / "opportunity.json").write_text(json.dumps({"id": o.name, "agency": "Example County", "title": "RFP 27-004 Jail Management System Replacement",
                                                    "source": {"type": "email", "from": "jane.buyer@example.gov"}, "due": {"date": "", "confirmed": False},
                                                    "format": {"font_family_allow": ["Arial"], "min_font_pt": 10, "margin_in": 0.75, "page_size": "letter", "page_limit": None},
                                                    "fonts": {"regular": "r", "bold": "b", "italic": "i", "bold_italic": "bi"}, "folders": {}}))
    return o


def test_extract_text_pdf_and_gather_sources(opp):
    text, meta = brief.extract_text(str(opp / "rfp" / "RFP 27-004 Jail Management System.pdf"))
    assert "Jail Management System Replacement" in text and meta["pages"] >= 1 and meta["words"] > 100
    labels = [l for l, _ in brief.gather_sources(str(opp))]
    assert labels[0] == "email" and "RFP 27-004 Jail Management System.pdf" in labels


def test_schedule_events_classified_with_time_and_tz(opp):
    facts, _ = brief.build_facts(str(opp))
    s = facts["schedule"]
    assert s["issued"]["date"] == "2026-09-10"
    assert s["prebid"]["date"] == "2026-09-24" and s["prebid"]["time"] == "10:00"
    assert s["questions"]["date"] == "2026-10-09" and s["questions"]["time"] == "17:00"
    assert s["addenda"]["date"] == "2026-10-16"
    assert s["due"]["date"] == "2026-10-30" and s["due"]["time"] == "14:00" and s["due"]["tz"].lower().startswith("pacific")
    assert s["award"]["date"] == "2026-11-20"
    assert s["start"]["date"] == "2027-01-04"


def test_money_signals_ranked_and_classified(opp):
    facts, _ = brief.build_facts(str(opp))
    kinds = {round(m["amount"]): m["kind"] for m in facts["money"]}
    assert kinds[1250000] == "value" and kinds[1500000] == "value"
    assert kinds[50000] == "bond" and kinds[2000000] == "insurance"
    assert [round(m["amount"]) for m in facts["money_value_signals"]][:2] == [1500000, 1250000]


def test_contacts_format_attachments_evaluation(opp):
    facts, _ = brief.build_facts(str(opp))
    emails = {e for c in facts["contacts"] for e in c["emails"]}
    assert "jane.buyer@example.gov" in emails
    assert any("(555) 010-2000" in p for c in facts["contacts"] for p in c["phones"])
    fd = facts["format_detected"]
    assert fd["font_family"] == "Arial" and fd["min_font_pt"] == 11 and fd["margin_in"] == 1.0
    assert fd["page_limit"] == 20 and fd["page_size"] == "letter" and fd["file_size_cap_mb"] == 25
    att = {r["label"]: r for r in facts["attachments"]}
    assert att["Attachment A"]["present"] and att["Attachment A"]["title"].startswith("Proposal Certification")
    assert att["Attachment B"]["present"]                                   # matched by the 'B' token in the filename
    assert not att["Exhibit C"]["present"] and not att["Appendix 1"]["present"]
    ev = " ".join(s["snippet"] for s in facts["evaluation"])
    assert "40 points" in ev and "25 points" in ev
    assert any("subject line" in s["snippet"].lower() for s in facts["submission"])
    assert facts["term"] and any("five (5) year" in s["snippet"] for s in facts["term"])


def test_run_writes_facts_research_and_updates_opportunity_json(opp):
    facts, changed, nq = brief.run(str(opp))
    md = (opp / "opportunity-facts.md").read_text()
    assert "DETECTED" in md and "| **due** | 2026-10-30 | 14:00 |" in md
    assert "✘ **missing**" in md and "Exhibit C" in md and "✔" in md
    assert "$1,500,000" in md and "jane.buyer@example.gov" in md
    assert (opp / "opportunity-facts.json").exists()
    oj = json.load(open(opp / "opportunity.json"))
    assert changed and oj["due"]["date"] == "2026-10-30" and oj["due"]["confirmed"] is False and oj["due"]["time"] == "14:00"
    assert oj["milestones"]["questions"]["date"] == "2026-10-09" and oj["milestones"]["questions"]["confirmed"] is False
    assert oj["format_detected"]["page_limit"] == 20 and oj["format"]["page_limit"] is None      # authoritative block untouched
    # research
    plan = (opp / "research" / "research-plan.md").read_text()
    assert nq >= 10 and '"Example County"' in plan and "council agenda" in plan and "incumbent" in plan.lower()
    assert '"27-004"' in plan and "legistar" in plan
    assert (opp / "research" / "findings.md").exists() and "UNKNOWN" in (opp / "research" / "findings.md").read_text()
    qs = json.load(open(opp / "research" / "queries.json")); assert all({"query", "why", "look_for"} <= set(q) for q in qs)
    # re-run does not clobber a filled findings.md or a confirmed due date
    (opp / "research" / "findings.md").write_text("# filled by human\n")
    oj["due"] = {"date": "2026-10-31", "confirmed": True}; json.dump(oj, open(opp / "opportunity.json", "w"))
    brief.run(str(opp))
    assert (opp / "research" / "findings.md").read_text() == "# filled by human\n"
    assert json.load(open(opp / "opportunity.json"))["due"]["date"] == "2026-10-31"


def test_keywords_and_queries():
    kws = brief.keywords_from_title("Fwd: RFP 27-004 Jail Management System Replacement - Now Posted")
    assert kws and "Jail Management System Replacement" in kws[0]
    qs = brief.research_queries("Example County", "Jail Management System", "27-004", kws)
    joined = " ".join(q["query"] for q in qs)
    assert "council agenda" in joined and "site:legistar.com" in joined and "site:des.wa.gov" in joined
    assert all(q["why"] and q["look_for"] for q in qs)


def test_cli_and_empty_opportunity(tmp_path, capsys):
    o = tmp_path / "EMPTY"; o.mkdir(); (o / "opportunity.json").write_text(json.dumps({"id": "EMPTY", "due": {}}))
    assert brief.main([str(o)]) == 0
    out = capsys.readouterr().out
    assert "0 document(s)" in out and (o / "opportunity-facts.md").exists()
    assert "No dollar figures found" in (o / "opportunity-facts.md").read_text()
    assert brief.main([str(tmp_path / "nope")]) == 2


REAL = real_sample("26-013-BIPIN", "rfp", "26-013 RFP - BIPIN RFP .pdf")

@pytest.mark.skipif(not REAL, reason="real BIPIN RFP not present")
def test_real_bipin_rfp_facts(tmp_path):
    """Regression on the real RFP: the format rules and the 24-page limit that mattered must be detected."""
    o = tmp_path / "26-013-BIPIN"; (o / "rfp").mkdir(parents=True)
    import shutil; shutil.copy(REAL, o / "rfp" / os.path.basename(REAL))
    (o / "opportunity.json").write_text(json.dumps({"id": "26-013-BIPIN", "agency": "City of Kennewick", "title": "RFP 26-013 BIPIN RMS and JMS/CMS Software Replacement", "due": {}}))
    facts, changed, nq = brief.run(str(o))
    fd = facts["format_detected"]
    assert fd.get("font_family") == "Arial" and fd.get("min_font_pt") == 10 and fd.get("margin_in") == 0.75 and fd.get("page_limit") == 24
    labels = {r["label"] for r in facts["attachments"]}
    assert any(l.startswith("Attachment") for l in labels)
    assert facts["schedule"].get("due"), "the RFP's due date should be detected"
    assert any("Tracy" in e or "kennewick" in e.lower() for c in facts["contacts"] for e in c["emails"] + c["lines"])



def test_brief_refreshes_inbox_guess_but_not_human_values(tmp_path):
    """The poller writes a crude due-date guess from the email (earliest cued date) tagged with a
    bidkit.inbox source; once the RFP is read, brief must be allowed to replace it. A human-entered or
    confirmed value must be left alone."""
    o = tmp_path / "27-004-X"; (o / "rfp").mkdir(parents=True)
    _make_pdf(str(o / "rfp" / "rfp.pdf"), "Proposals must be received no later than 2:00 PM Pacific Time on October 30, 2026.\nQuestions are due by October 9, 2026.")
    oj = {"id": "27-004-X", "agency": "Procurement Office", "agency_source": "bidkit.inbox (sender name — GUESS)",
          "due": {"date": "2026-10-09", "time": "", "timezone": "America/Los_Angeles", "confirmed": False, "source": "bidkit.inbox (email text — GUESS)"}}
    (o / "opportunity.json").write_text(json.dumps(oj))
    brief.run(str(o), research=False)
    d = json.load(open(o / "opportunity.json"))
    assert d["due"]["date"] == "2026-10-30" and d["due"]["time"] == "14:00" and d["due"]["source"].startswith("bidkit.brief")
    assert d["due"]["confirmed"] is False
    # human-entered (no source) value is protected
    d["due"] = {"date": "2026-11-01", "time": "", "confirmed": False}; json.dump(d, open(o / "opportunity.json", "w"))
    brief.run(str(o), research=False)
    assert json.load(open(o / "opportunity.json"))["due"]["date"] == "2026-11-01"


def test_agency_detection_overrides_sender_name_guess(tmp_path):
    o = tmp_path / "27-004-Y"; (o / "rfp").mkdir(parents=True)
    _make_pdf(str(o / "rfp" / "rfp.pdf"), "Benton County Request for Proposals.\nBenton County will award a contract.\nQuestions to the Procurement Office.\nBenton County reserves all rights.")
    oj = {"id": "27-004-Y", "agency": "Procurement Office", "agency_source": "bidkit.inbox (sender name — GUESS)", "title": "RFP 27-004 Jail Management System", "due": {}}
    (o / "opportunity.json").write_text(json.dumps(oj))
    facts, changed, nq = brief.run(str(o))
    d = json.load(open(o / "opportunity.json"))
    assert d["agency"] == "Benton County" and d["agency_source"].startswith("bidkit.brief")
    plan = (o / "research" / "research-plan.md").read_text()
    assert '"Benton County"' in plan and '"Procurement Office"' not in plan
    # a human-set agency is never overridden
    d["agency"] = "Benton County Sheriff's Office"; d.pop("agency_source"); json.dump(d, open(o / "opportunity.json", "w"))
    brief.run(str(o))
    assert json.load(open(o / "opportunity.json"))["agency"] == "Benton County Sheriff's Office"


def test_detect_agency_and_clean_agency():
    assert brief.detect_agency("City of Kennewick invites proposals. City of Kennewick reserves rights. Tyler Technologies is the incumbent.") == "City of Kennewick"
    assert brief.detect_agency("Skagit Valley College RFP. Skagit Valley College will evaluate.") == "Skagit Valley College"
    assert brief.detect_agency("no agency here") is None
    assert brief.clean_agency("Procurement Office") == "" and brief.clean_agency("Purchasing Department") == ""
    assert brief.clean_agency("City of Kennewick / BIPIN") == "City of Kennewick"
    assert brief.clean_agency("Benton County (WA)") == "Benton County"


def test_portal_record_feeds_schedule_money_agency_and_research(tmp_path):
    """bidkit.portal leaves rfp/portal-record.json (the portal's own solicitation page) and
    research/portal-vendors-downloading.csv; brief must fold both in with their own source labels."""
    o = tmp_path / "20260916-Data-Analytics"; (o / "rfp").mkdir(parents=True); (o / "research").mkdir()
    (o / "initial-email").mkdir()
    (o / "initial-email" / "email.md").write_text("# WEBS Notification: Risk Data Analytics\n\nA new solicitation was posted. Log in to WEBS to view it.\n")
    (o / "opportunity.json").write_text(json.dumps({"id": o.name, "agency": "WEBS Notifications", "agency_source": "bidkit.inbox (sender name — GUESS)",
                                                    "title": "WEBS Notification: Risk Data Analytics", "solicitation_number": "",
                                                    "source": {"type": "email", "from": "noreply@portal.example"}, "due": {"date": "", "confirmed": False}}))
    rec = {"portal": "webs", "portal_key": "des.wa.gov", "url": "https://portal.example/Search_BidDetails.aspx?ID=1", "system_id": "1",
           "reference": "2026_07", "organization": "Springfield, City of", "title": "Risk Data Analytics Software", "description": "d",
           "posted": "2026-09-14", "closed": "2026-09-27", "estimated_value_text": "1,500,000", "estimated_value": 1500000.0,
           "contact": {"name": "Buyer Contact", "phone": "(000) 000-0000", "email": "buyer@agency.example"},
           "documents": [{"name": "RFP - Data Analytics.pdf", "url": "u"}], "amendments": [{"date": "2026-09-16", "name": "Addendum 1.pdf", "url": "u2"}]}
    (o / "rfp" / "portal-record.json").write_text(json.dumps([rec]))
    (o / "rfp" / "portal-record.md").write_text("# not a solicitation document\n")
    (o / "research" / "portal-vendors-downloading.csv").write_text("company,email,phone,status,portal,source_url,captured_at\n"
                                                                    "Alpha Analytics LLC,a@alpha.example,(000) 000-0001,Mc-SB,des.wa.gov,u,t\n"
                                                                    "Beta Software Inc,b@beta.example,(000) 000-0002,,des.wa.gov,u,t\n")
    facts, changed, nq = brief.run(str(o))
    # portal-*.md is NOT read as a document
    assert [d["label"] for d in facts["documents"]] == ["email"]
    # schedule + money + contacts from the record, with the portal as source
    assert facts["schedule"]["due"]["date"] == "2026-09-27" and "portal-record.json" in facts["schedule"]["due"]["source"]
    assert facts["schedule"]["issued"]["date"] == "2026-09-14"
    assert facts["money_value_signals"][0]["amount"] == 1500000.0 and "Estimated Initial Contract Value" in facts["money_value_signals"][0]["snippet"]
    assert any("buyer@agency.example" in c["emails"] for c in facts["contacts"])
    # organization normalised from the portal's index-style name and used for the agency
    assert facts["agency_detected"] == "City of Springfield"
    oj = json.load(open(o / "opportunity.json"))
    assert changed and oj["agency"] == "City of Springfield" and oj["agency_source"].startswith("bidkit.brief")
    assert oj["due"]["date"] == "2026-09-27" and oj["due"]["confirmed"] is False
    assert oj["portal_record"]["reference"] == "2026_07" and oj["portal_record"]["estimated_value"] == 1500000.0 and oj["portal_record"]["amendments"] == 1
    assert oj["solicitation_number"] == "2026_07"                     # filled from the portal because the poller had none
    md = (o / "opportunity-facts.md").read_text()
    assert "## Portal record" in md and "**closes 2026-09-27**" in md and "1,500,000" in md and "Vendors downloading (portal, opt-in list): 2" in md
    plan = (o / "research" / "research-plan.md").read_text()
    assert "Competitive field — 2 vendor(s)" in plan and "Alpha Analytics LLC (Mc-SB)" in plan and "Beta Software Inc" in plan
    assert "Estimated Initial Contract Value on the portal: **1,500,000**" in plan
    # queries use the portal's real title and number, not the notification subject
    qs = json.load(open(o / "research" / "queries.json"))
    assert any("2026_07" in q["query"] for q in qs) and not any("Notification" in q["query"] for q in qs)


def test_normalize_org_name():
    assert brief.normalize_org_name("Springfield, City of") == "City of Springfield"
    assert brief.normalize_org_name("Enterprise Services (DES), Dept. of") == "Dept. of Enterprise Services (DES)"
    assert brief.normalize_org_name("Washington Counties Risk Pool") == "Washington Counties Risk Pool"
    assert brief.normalize_org_name("Washington, University of") == "University of Washington"
    assert brief.normalize_org_name("") == ""


# --------------------------------------------------------------- auto-confirm due from docs
def _facts_with_due(source, time_s, snippet):
    return {"schedule": {"due": {"date": "2026-09-10", "time": time_s, "tz": "PT",
                                 "source": source, "snippet": snippet}}}


def _opp_json(tmp_path, due):
    import json as _j
    d = tmp_path / "opp"
    d.mkdir()
    (d / "opportunity.json").write_text(_j.dumps({"id": "x", "due": due}), encoding="utf-8")
    return str(d)


DEADLINE_SNIP = "Proposal Submission Deadline September 10, 2026, 3:00 pm PT Shortlist Notification"


def test_autoconfirm_confirms_document_sourced_due(tmp_path):
    opp = _opp_json(tmp_path, {"date": "2026-09-10", "confirmed": False, "source": "bidkit.brief (DETECTED)"})
    facts = _facts_with_due("26-013 RFP.pdf", "15:00", DEADLINE_SNIP)
    ok, note = brief.auto_confirm_due_from_docs(opp, facts)
    import json as _j
    due = _j.load(open(opp + "/opportunity.json"))["due"]
    assert ok and due["confirmed"] is True and due["time"] == "15:00"
    assert "26-013 RFP.pdf" in due["source"]


def test_autoconfirm_refuses_email_source(tmp_path):
    opp = _opp_json(tmp_path, {"date": "2026-09-10", "confirmed": False})
    facts = _facts_with_due("email", "15:00", DEADLINE_SNIP)
    ok, note = brief.auto_confirm_due_from_docs(opp, facts)
    assert not ok and "not a document" in note


def test_autoconfirm_refuses_without_time(tmp_path):
    opp = _opp_json(tmp_path, {"date": "2026-09-10", "confirmed": False})
    facts = _facts_with_due("rfp.pdf", None, DEADLINE_SNIP)   # no time of day
    ok, note = brief.auto_confirm_due_from_docs(opp, facts)
    assert not ok and "no time" in note


def test_autoconfirm_refuses_without_deadline_cue(tmp_path):
    opp = _opp_json(tmp_path, {"date": "2026-09-10", "confirmed": False})
    facts = _facts_with_due("rfp.pdf", "15:00", "The project kickoff meeting is September 10, 2026 at 3:00 pm.")
    ok, note = brief.auto_confirm_due_from_docs(opp, facts)
    assert not ok and "cue" in note


def test_autoconfirm_leaves_already_confirmed(tmp_path):
    opp = _opp_json(tmp_path, {"date": "2026-09-10", "confirmed": True, "source": "human"})
    facts = _facts_with_due("rfp.pdf", "15:00", DEADLINE_SNIP)
    ok, note = brief.auto_confirm_due_from_docs(opp, facts)
    assert not ok and "already confirmed" in note


def test_autoconfirm_refuses_followup_email(tmp_path):
    opp = _opp_json(tmp_path, {"date": "2026-09-10", "confirmed": False})
    facts = _facts_with_due("followup:20260917-1551", "15:00", DEADLINE_SNIP)
    ok, note = brief.auto_confirm_due_from_docs(opp, facts)
    assert not ok and "not a document" in note
