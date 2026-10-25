import datetime as dt, email.utils, json, os
from email.message import EmailMessage
from bidkit import inbox


# ----------------------------------------------------------------------------- helpers
def _msg(subject, body, sender="Buyer Name <buyer@agency.example.gov>", mid=None, attachments=(),
         html=None, date=None):
    m = EmailMessage()
    m["Subject"] = subject; m["From"] = sender; m["To"] = "bids@example.com"
    m["Date"] = date or email.utils.format_datetime(dt.datetime(2026, 9, 1, 10, 0, tzinfo=dt.timezone.utc))
    m["Message-ID"] = mid or email.utils.make_msgid(domain="agency.example.gov")
    if html:
        m.set_content(body); m.add_alternative(html, subtype="html")
    else:
        m.set_content(body)
    for fname, data in attachments:
        m.add_attachment(data, maintype="application", subtype="octet-stream", filename=fname)
    return m


def _cfg(tmp_path):
    """A repo-like root with a template and an inbox config."""
    root = tmp_path / "repo"; (root / "inbox").mkdir(parents=True)
    tmpl = root / "opportunities" / "_template"
    for d in ("initial-email/attachments", "rfp", "deliverables/bid/final", "SUBMIT"):
        (tmpl / d).mkdir(parents=True)
    (tmpl / "opportunity.json").write_text(json.dumps({
        "id": "{{ID}}", "agency": "{{AGENCY}}", "title": "{{TITLE}}",
        "source": {"type": "{{SOURCE_TYPE}}", "received": "{{RECEIVED}}", "from": "{{FROM}}", "message_id": "{{MESSAGE_ID}}"},
        "due": {"date": "{{DUE_DATE}}", "confirmed": False},
        "format": {"font_family_allow": ["Arial"], "min_font_pt": 10, "margin_in": 1, "page_size": "letter", "page_limit": None},
        "fonts": {"regular": "r", "bold": "b", "italic": "i", "bold_italic": "bi"},
        "folders": {"extract": "e", "draft": "d", "final": "f", "submit": "SUBMIT"}}, indent=1))
    cfgp = root / "inbox" / "inbox.json"
    cfgp.write_text(json.dumps({
        "imap": {"host": "imap.example.com", "port": 993, "user": "bids@example.com", "password_env": "TEST_PW"},
        "match": {"from_deny": ["spam.example"],
                  "from_trust": ["webscustomerservice@des.wa.gov", "federalgovadvisors.com", "supplierservices@demandstar.com"]},
        "attachment_types": [".pdf", ".xlsx"], "max_attachment_mb": 1}))
    return inbox.load_config(str(cfgp)), root


RFP_BODY = """Skagit Example College invites proposals for Database Design and Application Development.

Proposals are due August 24, 2026, by 2:30 pm. Questions by Aug 5, 2026.
Documents: https://portal.example.gov/bids/2026-110/docs
Contact: Rebecca Example, rebecca@agency.example.gov
"""


# ----------------------------------------------------------------------------- unit: derivations
def test_solicitation_number_and_slug():
    assert inbox.solicitation_number("RFP 26-013 BIPIN RMS and JMS/CMS Software Replacement") == "26-013"
    assert inbox.solicitation_number("Fwd: Bid RFP #2026-110 - RFP 2026-110 Database Design") == "2026-110"
    assert inbox.solicitation_number("Re: Solicitation No. ITB-24-0087 Fleet Telematics") == "ITB-24-0087"
    assert inbox.solicitation_number("Lunch on Friday?") is None
    assert inbox.slug_from_subject("RFP 26-013 BIPIN RMS and JMS/CMS Software Replacement") == "BIPIN-RMS-JMS-CMS"
    assert inbox.slug_from_subject("Fwd: Request for Proposal - Database Design and App Development") == "Database-Design-App-Development"


def test_derive_id_with_and_without_number():
    oid, num = inbox.derive_id(_msg("RFP 26-013 BIPIN RMS Replacement", "x"))
    assert oid == "26-013-BIPIN-RMS-Replacement" and num == "26-013"
    oid2, num2 = inbox.derive_id(_msg("Invitation to Bid: Parking Lot Resurfacing", "x"))
    assert num2 is None and oid2.startswith("20260901-") and "Parking" in oid2


def test_normalize_ref_number():
    # body path (strip_label=True): drop a bare/marked label prefix
    assert inbox.normalize_ref_number("RFP # 10266", strip_label=True) == "10266"
    assert inbox.normalize_ref_number("DRSRFP 26-06", strip_label=True) == "DRSRFP-26-06"        # 'DRSRFP' isn't a bare label token, kept
    assert inbox.normalize_ref_number("RFP-26-084-CCC-0-2026/DFW", strip_label=True) == "26-084-CCC-0-2026-DFW"
    assert inbox.normalize_ref_number("RFP Release", strip_label=True) is None                   # no digit
    # path-safety + preservation (default, subject path): a label hyphenated into the id is kept
    assert inbox.normalize_ref_number("ITB-24-0087") == "ITB-24-0087"
    assert inbox.normalize_ref_number("R2701") == "R2701"
    assert inbox.normalize_ref_number("2026_01") == "2026_01"
    assert inbox.normalize_ref_number("") is None


# WEBS-style notification: generic subject, real number + title in the body.
WEBS_BODY = """Our records indicate that you are currently registered to receive solicitations in the following category and may be interested in bidding on:
Title: On-Site Digital Conversion
Description: The successful bidder will digitize approximately 520,000 agency documents.
Estimated Value: 100,000
Customer Reference Number: R2701
Close Date: Wednesday, October 21, 2026
Posting Organization: Gambling Commission
To view the full details login now at:
https://pr-webs-vendor.des.wa.gov/Search_BidDetails.aspx?ID=57544
"""

DEMANDSTAR_BODY = """A Bid Addendum has posted to OpenBids!
Dear Pat Principal,
DuPage County - Procurement Services has posted an addendum to DuPage Circuit Clerk CMS and Web
Software Development and Support (RFP-26-084-CCC-0-2026/DFW).
Responses are due 10/02/2026 2:00 PM (Central) for this bid.
"""


def test_derive_id_from_webs_body():
    # Subject is generic; number + slug must come from the body's Customer Reference Number / Title.
    oid, num = inbox.derive_id(_msg("WEBS Bidding Opportunity", WEBS_BODY,
                                    sender="webscustomerservice@des.wa.gov"))
    assert num == "R2701"
    assert oid == "R2701-Site-Digital-Conversion"          # 'On' is a stopword; title-derived slug


def test_derive_id_from_demandstar_body_sanitizes_slash():
    oid, num = inbox.derive_id(_msg("Important Bid Notice", DEMANDSTAR_BODY,
                                    sender="supplierservices@demandstar.com"))
    assert num == "26-084-CCC-0-2026-DFW"                   # slash sanitized; folder-path safe
    assert "/" not in oid and oid.startswith("26-084-CCC-0-2026-DFW-")


def test_generic_subject_without_body_number_falls_back_to_date():
    oid, num = inbox.derive_id(_msg("WEBS Bidding Opportunity", "No reference number here.",
                                    sender="webscustomerservice@des.wa.gov"))
    assert num is None and oid.startswith("20260901-")


def test_body_number_requires_digit_rejects_prose():
    # FGA "FGA: New Opportunity Found …" body sometimes contains "(RFP Release)" — must NOT match.
    oid, num = inbox.derive_id(_msg("FGA: New Opportunity Found for YourCo LLC", "Status: (RFP Release)",
                                    sender="opportunities@federalgovadvisors.com"))
    assert num is None and oid.startswith("20260901-")


def test_guess_due_date_formats():
    assert inbox.guess_due_date("Proposals are due August 24, 2026, by 2:30 pm.")[0] == "2026-08-24"
    assert inbox.guess_due_date("Submission deadline: 09/16/2026 3:00 PM PT")[0] == "2026-09-16"
    assert inbox.guess_due_date("Responses must be submitted no later than 2026-10-01.")[0] == "2026-10-01"
    assert inbox.guess_due_date("Closing Sept. 30th, 2026")[0] == "2026-09-30"
    assert inbox.guess_due_date("Posted 2026-01-01. Questions by Aug 5, 2026. Due August 24, 2026.")[0] == "2026-08-05"  # earliest cue'd date
    assert inbox.guess_due_date("No dates here at all.") == (None, None)


def test_matching_rules(tmp_path):
    cfg, _ = _cfg(tmp_path)
    assert inbox.matches(_msg("RFP 26-013 Something", "x"), cfg)[0]
    assert inbox.matches(_msg("Request for Quote: widgets", "x"), cfg)[0]
    assert not inbox.matches(_msg("Your receipt", "x"), cfg)[0]
    assert not inbox.matches(_msg("RFP 1-1 spam", "x", sender="x@spam.example"), cfg)[0]       # deny wins
    assert not inbox.matches(_msg("Surfpark opening", "x"), cfg)[0]                             # 'RFP' inside a word doesn't match


def test_trusted_senders_file_regardless_of_subject(tmp_path):
    cfg, _ = _cfg(tmp_path)
    # WEBS / FGA / DemandStar notification subjects carry NO RFP/RFQ keyword, yet must be filed.
    ok, reason = inbox.matches(_msg("WEBS Bidding Opportunity", "x", sender="webscustomerservice@des.wa.gov"), cfg)
    assert ok and "trusted sender" in reason
    assert inbox.matches(_msg("FGA: New Opportunity Found for YourCo LLC (Due December 4, 2026)", "x",
                              sender="opportunities@federalgovadvisors.com"), cfg)[0]
    assert inbox.matches(_msg("Breakdown for Opportunity: DuPage Circuit Clerk", "x",
                              sender="noreply@notify.federalgovadvisors.com"), cfg)[0]          # domain-level trust
    assert inbox.matches(_msg("Important Bid Notice", "x", sender="supplierservices@demandstar.com"), cfg)[0]
    # A non-trusted sender with a non-keyword subject is still ignored.
    assert not inbox.matches(_msg("Opportunity Recommendations", "x", sender="news@vendor.example"), cfg)[0]


def test_from_deny_overrides_trust(tmp_path):
    cfg, _ = _cfg(tmp_path)
    cfg["match"]["from_trust"] = ["des.wa.gov"]
    cfg["match"]["from_deny"] = ["webscustomerservice@des.wa.gov"]
    assert not inbox.matches(_msg("WEBS Bidding Opportunity", "x", sender="webscustomerservice@des.wa.gov"), cfg)[0]


def test_bidding_opportunity_keyword(tmp_path):
    cfg, _ = _cfg(tmp_path)
    # Even from an unknown sender, the WEBS-style subject is caught by the added keyword.
    assert inbox.matches(_msg("Bidding Opportunity - Notice", "x", sender="someone@unknown.example"), cfg)[0]


# ----------------------------------------------------------------------------- filing
def test_new_opportunity_is_filed_from_template(tmp_path):
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    msg = _msg("Bid RFP #2026-110 - Database Design and Application Development", RFP_BODY,
               attachments=[("RFP 2026-110.pdf", b"%PDF-1.4 fake"), ("notes.exe", b"MZ")])
    r = inbox.process_message(msg, cfg, state)
    assert r["action"] == "new" and r["opportunity"] == "opportunities/2026-110-Database-Design-Application-Development"
    opp = root / r["opportunity"]
    assert (opp / "initial-email" / "email.eml").exists()
    assert (opp / "initial-email" / "email.md").exists()
    assert (opp / "initial-email" / "attachments" / "RFP 2026-110.pdf").read_bytes() == b"%PDF-1.4 fake"
    assert not (opp / "initial-email" / "attachments" / "notes.exe").exists()
    assert r["attachments"] == ["RFP 2026-110.pdf"] and any("notes.exe" in s for s in r["attachments_skipped"])
    assert (opp / "initial-email" / "links.md").read_text().count("https://portal.example.gov") == 1
    assert (opp / "rfp").is_dir() and (opp / "SUBMIT").is_dir()               # template tree copied
    oj = json.loads((opp / "opportunity.json").read_text())
    assert oj["id"] == "2026-110-Database-Design-Application-Development"
    assert oj["source"]["type"] == "email" and oj["source"]["from"] == "buyer@agency.example.gov"
    assert oj["due"]["date"] == "2026-08-05" and oj["due"]["confirmed"] is False   # a GUESS, flagged
    brief = (opp / "intake-brief.md").read_text()
    assert "GUESS" in brief and "run intake on opportunities/2026-110-Database-Design-Application-Development" in brief
    # queue + state
    q = [json.loads(l) for l in (root / "inbox" / "queue.jsonl").read_text().splitlines()]
    assert q[0]["action"] == "new"
    assert msg["Message-ID"] in state["processed"]


def test_duplicate_message_is_skipped(tmp_path):
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    msg = _msg("RFP 26-013 BIPIN", RFP_BODY, mid="<dup@x>")
    assert inbox.process_message(msg, cfg, state)["action"] == "new"
    r2 = inbox.process_message(msg, cfg, state)
    assert r2["action"] == "skip" and r2["reason"] == "already processed"
    assert len([p for p in (root / "opportunities").iterdir() if not p.name.startswith("_")]) == 1


def test_followup_routes_into_existing_opportunity(tmp_path):
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    inbox.process_message(_msg("RFP 26-013 BIPIN RMS Replacement", RFP_BODY, mid="<orig@x>"), cfg, state)
    add = _msg("RFP 26-013 - Addendum 2 posted", "Addendum 2 is now available.", mid="<add2@x>",
               attachments=[("Addendum 2.pdf", b"%PDF")])
    r = inbox.process_message(add, cfg, state)
    assert r["action"] == "followup" and r["opportunity"] == "opportunities/26-013-BIPIN-RMS-Replacement"
    fu = root / r["written"]
    assert fu.parent.name == "followups" and (fu / "attachments" / "Addendum 2.pdf").exists()
    assert (root / r["brief"]).exists() and "FOLLOW-UP" in (root / r["brief"]).read_text()
    # no second opportunity folder was created
    assert len([p for p in (root / "opportunities").iterdir() if not p.name.startswith("_")]) == 1


def test_non_bid_email_is_ignored_and_not_filed(tmp_path):
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    r = inbox.process_message(_msg("Team lunch Friday", "pizza?"), cfg, state)
    assert r["action"] == "ignore"
    assert not [p for p in (root / "opportunities").iterdir() if not p.name.startswith("_")]
    assert not (root / "inbox" / "queue.jsonl").exists()


def test_dry_run_writes_nothing(tmp_path):
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    r = inbox.process_message(_msg("RFP 26-013 BIPIN", RFP_BODY, attachments=[("a.pdf", b"%PDF")]), cfg, state, dry_run=True)
    assert r["action"] == "new" and "would_write" in r and r["attachments"] == ["a.pdf"]
    assert not [p for p in (root / "opportunities").iterdir() if not p.name.startswith("_")]
    assert state["processed"] == {} and not (root / "inbox" / "queue.jsonl").exists()


def test_html_only_body_and_links(tmp_path):
    cfg, root = _cfg(tmp_path)
    m = EmailMessage(); m["Subject"] = "RFQ 24-777 Widgets"; m["From"] = "a@b.example"; m["Message-ID"] = "<h@x>"
    m["Date"] = email.utils.format_datetime(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc))
    m.set_content("<html><body><p>Quotes <b>due</b> 09/30/2026.</p><a href='https://p.example.gov/q/1'>Docs</a></body></html>", subtype="html")
    text, htmlb = inbox.body_text(m)
    assert "Quotes due 09/30/2026." in text and "<" not in text
    assert inbox.extract_links(text, htmlb) == ["https://p.example.gov/q/1"]
    assert inbox.guess_due_date(text)[0] == "2026-09-30"


# ----------------------------------------------------------------------------- poll with fake fetcher
class FakeFetcher:
    def __init__(self, msgs): self.msgs = msgs; self.seen = []
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def uids_since(self, days): return [str(i) for i in range(len(self.msgs))]
    def fetch(self, uid): return self.msgs[int(uid)]
    def mark_seen(self, uid): self.seen.append(uid)


def test_poll_end_to_end_with_fake_fetcher_and_mark_seen(tmp_path):
    cfg, root = _cfg(tmp_path); cfg["mark_seen"] = True
    msgs = [_msg("RFP 26-013 BIPIN", RFP_BODY, mid="<a@x>"), _msg("Lunch", "no", mid="<b@x>"),
            _msg("RFP 26-013 Addendum 1", "add", mid="<c@x>")]
    ff = FakeFetcher(msgs)
    results = inbox.poll(cfg, fetcher_factory=lambda c: ff)
    assert [r["action"] for r in results] == ["new", "ignore", "followup"]
    assert ff.seen == ["0", "2"]                                    # only filed messages get \Seen
    st = json.loads((root / "inbox" / "state.json").read_text())
    assert st["last_poll"] and len(st["processed"]) == 2
    # second poll: everything already processed or ignored; nothing new written
    results2 = inbox.poll(cfg, fetcher_factory=lambda c: FakeFetcher(msgs))
    assert [r["action"] for r in results2] == ["skip", "ignore", "skip"]


def test_ingest_files_and_cli(tmp_path, capsys):
    cfg, root = _cfg(tmp_path)
    eml = tmp_path / "m.eml"; eml.write_bytes(_msg("RFP 26-013 BIPIN", RFP_BODY, mid="<f@x>").as_bytes())
    rc = inbox.main(["ingest", "--cfg", str(root / "inbox" / "inbox.json"), str(eml)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "NEW" in out and "new=1" in out
    rc = inbox.main(["queue", "--cfg", str(root / "inbox" / "inbox.json")]); assert rc == 0
    assert "26-013-BIPIN" in capsys.readouterr().out
    rc = inbox.main(["status", "--cfg", str(root / "inbox" / "inbox.json")]); assert rc == 0
    assert "processed messages: 1" in capsys.readouterr().out


def test_missing_password_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_PW", raising=False)
    cfg, _ = _cfg(tmp_path)
    cfg["imap"].pop("password_keychain_service", None)
    try:
        inbox.resolve_password(cfg["imap"]); assert False, "expected InboxError"
    except inbox.InboxError as e:
        assert "TEST_PW" in str(e)
    monkeypatch.setenv("TEST_PW", "s3cret")
    assert inbox.resolve_password(cfg["imap"]) == "s3cret"


def test_safe_filename():
    assert inbox.safe_filename("../../etc/passwd") == "passwd"
    assert inbox.safe_filename("RFP #26-013 (final).pdf") == "RFP _26-013 (final).pdf"
    assert inbox.safe_filename(None) == "attachment"


# ----------------------------------------------------------------------------- thread dedup (P1a)
FGA_SENDER = "FGA <alerts@federalgovadvisors.com>"
FGA_BODY = ("FGA: New Opportunity Found for YourCo LLC. A new solicitation matching your profile "
            "is available. Proposals due September 10, 2026.\nhttps://portal.example.gov/x\n")


def test_normalized_subject_strips_re_and_bracket_prefixes():
    s = "Re: [Priority!] Re: [Priority!] Re: FGA: New Opportunity Found (Due September 10, 2026)"
    assert inbox.normalized_subject(s) == "fga: new opportunity found (due september 10, 2026)"
    # a bare subject is unchanged (lowercased)
    assert inbox.normalized_subject("FGA: New Opportunity Found") == "fga: new opportunity found"


def test_thread_followup_by_normalized_subject_no_number(tmp_path):
    # The FGA dup bug: a 'New Opportunity Found' email has no solicitation number, and a later
    # '[Priority!] Re: ...' follow-up on the same thread used to mint a 2nd/3rd folder. It must now
    # attach as a followup to the first.
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    first = _msg("FGA: New Opportunity Found (Due September 10, 2026)", FGA_BODY, sender=FGA_SENDER, mid="<fga1@x>")
    r1 = inbox.process_message(first, cfg, state)
    assert r1["action"] == "new"
    followup = _msg("Re: [Priority!] Re: FGA: New Opportunity Found (Due September 10, 2026)",
                    FGA_BODY, sender=FGA_SENDER, mid="<fga2@x>")
    r2 = inbox.process_message(followup, cfg, state)
    assert r2["action"] == "followup" and r2["opportunity"] == r1["opportunity"]
    # exactly one opportunity folder, not two
    assert len([p for p in (root / "opportunities").iterdir() if not p.name.startswith("_")]) == 1


def test_thread_followup_by_in_reply_to(tmp_path):
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    first = _msg("FGA: New Opportunity Found (Due September 10, 2026)", FGA_BODY, sender=FGA_SENDER, mid="<fgaA@x>")
    inbox.process_message(first, cfg, state)
    reply = _msg("A totally different subject line", FGA_BODY, sender=FGA_SENDER, mid="<fgaB@x>")
    reply["In-Reply-To"] = "<fgaA@x>"            # explicit RFC-822 threading wins even if subject differs
    r2 = inbox.process_message(reply, cfg, state)
    assert r2["action"] == "followup"
    assert len([p for p in (root / "opportunities").iterdir() if not p.name.startswith("_")]) == 1


def test_same_generic_subject_different_sender_does_not_collapse(tmp_path):
    # guard: two genuinely different senders with the same generic subject must NOT be merged
    cfg, root = _cfg(tmp_path)
    state = inbox.load_state(cfg)
    a = _msg("FGA: New Opportunity Found (Due September 10, 2026)", FGA_BODY, sender=FGA_SENDER, mid="<a@x>")
    inbox.process_message(a, cfg, state)
    # same generic subject, DIFFERENT sender domain, trusted via supplierservices@demandstar.com
    b = _msg("FGA: New Opportunity Found (Due September 10, 2026)", FGA_BODY,
             sender="DemandStar <supplierservices@demandstar.com>", mid="<b@x>")
    r = inbox.process_message(b, cfg, state)
    # the THREAD matcher must not fire across domains: action is 'new', not 'followup'
    # (if the two happen to derive the same folder id that's a separate same-id mechanism, not thread dedup)
    assert r["action"] == "new"


def test_thread_dedup_can_be_disabled(tmp_path):
    cfg, root = _cfg(tmp_path)
    cfg["thread_dedup"] = False
    state = inbox.load_state(cfg)
    inbox.process_message(_msg("FGA: New Opportunity Found (Due September 10, 2026)", FGA_BODY,
                               sender=FGA_SENDER, mid="<d1@x>"), cfg, state)
    r = inbox.process_message(_msg("Re: [Priority!] FGA: New Opportunity Found (Due September 10, 2026)",
                                   FGA_BODY, sender=FGA_SENDER, mid="<d2@x>"), cfg, state)
    assert r["action"] == "new"                   # dedup off → old behavior (two folders)
